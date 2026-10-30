"""phone_girl environments: one base with the robot's real I/O, and the tasks on top.

Every task shares the actor's observation layout, the 17 joint targets and the
twist command slot (stand holds it at zero), so policies trained for different
tasks can be compared, swapped on the phone, and distilled into one. A task that
holds joints still scales their targets to nothing rather than dropping them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import torch

from mjlab.envs import ManagerBasedRlEnvCfg
from mjlab.envs import mdp
from mjlab.envs.mdp.actions import JointPositionActionCfg
from mjlab.managers.curriculum_manager import CurriculumTermCfg
from mjlab.managers.event_manager import EventTermCfg
from mjlab.managers.reward_manager import RewardTermCfg
from mjlab.managers.scene_entity_config import SceneEntityCfg
from mjlab.managers.termination_manager import TerminationTermCfg
from mjlab.scene import SceneCfg
from mjlab.sensor import ContactMatch, ContactSensorCfg
from mjlab.sim import MujocoCfg, SimulationCfg
from mjlab.tasks.velocity import mdp as velocity
from mjlab.tasks.velocity.mdp import UniformVelocityCommand, UniformVelocityCommandCfg
from mjlab.terrains import TerrainEntityCfg
from mjlab.viewer import ViewerConfig

from phone_girl import link as link_events
from phone_girl import observations, randomization as dr
from phone_girl.link import LinkCfg, delay_settings, servos
from phone_girl.phone import PhoneImuCfg
from phone_girl.robot import FEET, FOOT_SITES, JOINTS, LIMITS, index, robot_cfg, servo_friction_fields

PHYSICS_DT = 0.0025
ACTION_SCALE = 0.4  # rad per unit action, about the home pose
DR_EVENTS = ("servos", "supply", "body", "friction")
# What Stand balances with. The knees, thigh yaws and arms hold the default pose.
BALANCE_JOINTS = ("waist", "left_hip_roll", "left_hip_pitch", "right_hip_roll", "right_hip_pitch")


class ZeroTwist(UniformVelocityCommand):
    """The twist slot for tasks that hold it at zero. It has no joystick in the web
    viewer, whose sliders can't take a zero range."""

    def create_gui(self, *args, **kwargs) -> None:
        pass


@dataclass(kw_only=True)
class ZeroTwistCfg(UniformVelocityCommandCfg):
    resampling_time_range: tuple[float, float] = (1e9, 1e9)
    rel_standing_envs: float = 1.0
    ranges: UniformVelocityCommandCfg.Ranges = field(default_factory=lambda: UniformVelocityCommandCfg.Ranges(
        lin_vel_x=(0, 0), lin_vel_y=(0, 0), ang_vel_z=(0, 0)))

    def build(self, env) -> ZeroTwist:
        return ZeroTwist(self, env)


# Rewards specific to phone_girl.

def posture(env, std: float) -> torch.Tensor:
    robot = env.scene["robot"]
    return torch.exp(-torch.mean(((robot.data.joint_pos - robot.data.default_joint_pos) / std) ** 2, dim=1))


def com_over_feet(env, std: float) -> torch.Tensor:
    """How close the CoM's ground projection is to the line between the stilt tips."""
    robot = env.scene["robot"]
    com = env.sim.data.subtree_com[:, robot.indexing.body_ids[0], :2]
    feet = robot.data.site_pos_w[:, index(FOOT_SITES, env.device), :2]
    a, b = feet[:, 0], feet[:, 1]
    t = (((com - a) * (b - a)).sum(-1) / ((b - a) ** 2).sum(-1).clamp(min=1e-6)).clamp(0, 1)
    gap = com - (a + t[:, None] * (b - a))
    return torch.exp(-(gap ** 2).sum(-1) / std ** 2)


def stillness(env, std: float) -> torch.Tensor:
    robot = env.scene["robot"]
    speed = (robot.data.root_link_lin_vel_b[:, :2] ** 2).sum(-1) + 0.05 * (robot.data.root_link_ang_vel_b ** 2).sum(-1)
    return torch.exp(-speed / std ** 2)


def copper_loss(env) -> torch.Tensor:
    """Winding heat, W: what drains the battery and cooks the servos when held badly."""
    actuator = servos(env)
    return (actuator.current ** 2 * actuator.resistance).sum(-1)


class body_on_floor:
    """Termination: a fall, when anything but a stilt touches the floor.

    Read once per control step from the last physics step's contact list, as a
    contact sensor would count it. As contact sensors, one per body and updated
    every physics step, the same check cost 3.3 ms a control step at 1k worlds
    and 2.3 ms at 16k.
    """

    def __init__(self, cfg, env):
        model = env.sim.mj_model
        body = [model.body(model.geom_bodyid[g]).name for g in range(model.ngeom)]
        self.floor = torch.tensor([b == "terrain" for b in body], device=env.device)
        self.falls = torch.tensor([b.startswith("robot/") and not b.endswith("_knee_link") for b in body],
                                  device=env.device)
        self.slots = torch.arange(env.sim.data.contact.worldid[...].numel(), device=env.device)

    def __call__(self, env) -> torch.Tensor:
        data = env.sim.data
        a, b = data.contact.geom[...].long().unbind(1)
        active = self.slots < data.nacon[...]
        fall = active & ((self.floor[a] & self.falls[b]) | (self.floor[b] & self.falls[a]))
        world = torch.where(active, data.contact.worldid[...].long(), 0)
        hits = torch.zeros(env.num_envs, dtype=torch.int32, device=env.device)
        return hits.index_add_(0, world, fall.int()) > 0


def foot_slip(env, sensor_name: str = "feet_ground") -> torch.Tensor:
    robot, sensor = env.scene["robot"], env.scene[sensor_name]
    contact = (sensor.data.found > 0).float().reshape(env.num_envs, -1)
    # The sensor lists the feet in the model's order, right first, not in FEET's.
    sites = tuple(FOOT_SITES[FEET.index(name)] for name in sensor.primary_names)
    speed = robot.data.site_lin_vel_w[:, index(sites, env.device), :2].norm(dim=-1)
    return (speed ** 2 * contact).sum(-1)


def feet_off_floor(env, sensor_name: str = "feet_ground") -> torch.Tensor:
    return (env.scene[sensor_name].data.found == 0).float().reshape(env.num_envs, -1).sum(-1)


def base_cfg(link: LinkCfg | None = None, randomization: dr.Randomization | None = None,
             history: int = 3, play: bool = False) -> ManagerBasedRlEnvCfg:
    link = link or LinkCfg()
    randomization = randomization or dr.Randomization()
    decimation = round(link.interval_s / PHYSICS_DT)
    if abs(decimation * PHYSICS_DT - link.interval_s) > 1e-9:
        raise ValueError("The control period must be a whole number of physics steps")

    feet_ground = ContactSensorCfg(
        name="feet_ground", primary=ContactMatch(mode="geom", pattern=FEET, entity="robot"),
        secondary=ContactMatch(mode="body", pattern="terrain"), fields=("found", "force"),
        reduce="netforce", num_slots=1, track_air_time=True)

    events = {
        "friction_fields": EventTermCfg(func=servo_friction_fields, mode="startup"),
        "graph_recompute": EventTermCfg(func=dr.graph_recompute, mode="startup"),
        "reset_base": EventTermCfg(func=mdp.reset_root_state_uniform, mode="reset",
                                   params={"pose_range": {"yaw": (-math.pi, math.pi)}, "velocity_range": {}}),
        # Small, so the stilts, 4.6 mm apart at home, never start overlapping.
        "reset_joints": EventTermCfg(func=mdp.reset_joints_by_offset, mode="reset",
                                     params={"position_range": (-0.01, 0.01), "velocity_range": (0.0, 0.0),
                                             "asset_cfg": SceneEntityCfg("robot", joint_names=(".*",))}),
        "servos": EventTermCfg(func=dr.randomize_servos, mode="reset", params={"randomization": randomization}),
        "supply": EventTermCfg(func=dr.randomize_supply, mode="reset", params={"randomization": randomization}),
        "body": EventTermCfg(func=dr.randomize_body, mode="reset", params={"randomization": randomization}),
        "friction": EventTermCfg(func=dr.randomize_friction, mode="reset", params={"randomization": randomization}),
        "link": EventTermCfg(func=link_events.sample_link, mode="reset", params={"link": link}),
        "late_commands": EventTermCfg(func=link_events.late_commands, mode="step", params={"link": link}),
        "refresh_constants": EventTermCfg(func=dr.refresh_constants, mode="step", params={"every": 10}),
    }

    return ManagerBasedRlEnvCfg(
        decimation=decimation,
        scene=SceneCfg(terrain=TerrainEntityCfg(terrain_type="plane"),
                       entities={"robot": robot_cfg(**delay_settings(link, PHYSICS_DT))},
                       sensors=(PhoneImuCfg(), feet_ground), num_envs=1, extent=1.0),
        observations={"actor": observations.actor_group(history=history),
                      "critic": observations.critic_group()},
        actions={"joint_pos": JointPositionActionCfg(
            entity_name="robot", actuator_names=JOINTS, preserve_order=True, scale=ACTION_SCALE,
            use_default_offset=True, clip=dict(LIMITS))},
        commands={"twist": ZeroTwistCfg(entity_name="robot")},
        events=events,
        terminations={
            "time_out": TerminationTermCfg(func=mdp.time_out, time_out=True),
            "fell_over": TerminationTermCfg(func=mdp.bad_orientation, params={"limit_angle": math.radians(50)}),
            "body_on_floor": TerminationTermCfg(func=body_on_floor),
        },
        curriculum={} if play else {"randomization": CurriculumTermCfg(
            func=dr.dr_curriculum, params={"start": 0.3, "steps": 24 * 1500, "terms": DR_EVENTS})},
        viewer=ViewerConfig(origin_type=ViewerConfig.OriginType.ASSET_BODY, entity_name="robot",
                            body_name="torso", distance=1.2, elevation=-10.0, azimuth=135.0),
        sim=SimulationCfg(nconmax=24, njmax=160,
                          # Measured on CPU: ~2 Newton iterations on average, 10 at worst while falling.
                          mujoco=MujocoCfg(timestep=PHYSICS_DT, iterations=15, ls_iterations=30)),
        episode_length_s=20.0,
    )


def stand_cfg(play: bool = False, link: LinkCfg | None = None,
              randomization: dr.Randomization | None = None) -> ManagerBasedRlEnvCfg:
    """Balance on planted stilt tips with the waist and the hips' roll and pitch."""
    cfg = base_cfg(link, randomization, play=play)
    cfg.actions["joint_pos"].scale = {j: ACTION_SCALE if j in BALANCE_JOINTS else 0.0 for j in JOINTS}
    cfg.rewards = {
        "alive": RewardTermCfg(func=mdp.is_alive, weight=1.0),
        "upright": RewardTermCfg(func=velocity.upright, weight=1.0,
                                 params={"std": math.sqrt(0.1), "asset_cfg": SceneEntityCfg("robot", body_names=("torso",))}),
        "com_over_feet": RewardTermCfg(func=com_over_feet, weight=1.0, params={"std": 0.02}),
        "posture": RewardTermCfg(func=posture, weight=0.5, params={"std": 0.3}),
        "still": RewardTermCfg(func=stillness, weight=0.5, params={"std": 0.1}),
        "feet_off_floor": RewardTermCfg(func=feet_off_floor, weight=-2.0),
        "foot_slip": RewardTermCfg(func=foot_slip, weight=-2.0),
        "action_rate": RewardTermCfg(func=mdp.action_rate_l2, weight=-0.01),
        "copper_loss": RewardTermCfg(func=copper_loss, weight=-0.05),
        "joint_limits": RewardTermCfg(func=mdp.joint_pos_limits, weight=-1.0),
        "fall": RewardTermCfg(func=mdp.is_terminated, weight=-20.0),
    }
    if not play:
        # Shoves on the torso. A velocity kick would move the planted tips too.
        cfg.events["push"] = EventTermCfg(
            func=mdp.apply_body_impulse, mode="step",
            params={"asset_cfg": SceneEntityCfg("robot", body_names=("torso",)), "force_range": (-0.25, 0.25),
                    "torque_range": (0.0, 0.0), "duration_s": (0.05, 0.15), "cooldown_s": (1.0, 3.0)})
    return cfg


def stand_ideal_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Stand on the nominal robot over a perfect link: no randomization, latency or stalls.

    Not for deployment. If Stand doesn't learn, this says whether balancing on
    the stilt tips is possible at all with these servos, or whether the link
    and the unknowns are what make it hard.
    """
    link = LinkCfg(max_delay_s=0.0, write_s=(0.0, 0.0), read_s=(0.0, 0.0), late_probability=0.0,
                   stall_rate_hz=0.0)
    cfg = stand_cfg(play, link, dr.Randomization(scale=0.0))
    for name in ("link", "late_commands"):  # no lag to sample: commands land in the next physics step
        cfg.events.pop(name)
    cfg.curriculum = {}
    return cfg


def walk_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Follow a twist command on the stilt tips."""
    cfg = base_cfg(play=play)
    cfg.commands["twist"] = UniformVelocityCommandCfg(
        entity_name="robot", resampling_time_range=(3.0, 8.0), rel_standing_envs=0.15, debug_vis=True,
        ranges=UniformVelocityCommandCfg.Ranges(lin_vel_x=(-0.15, 0.25), lin_vel_y=(-0.1, 0.1),
                                                ang_vel_z=(-0.6, 0.6)))
    cfg.rewards = {
        "track_linear": RewardTermCfg(func=velocity.track_linear_velocity, weight=2.0,
                                      params={"command_name": "twist", "std": 0.1}),
        "track_angular": RewardTermCfg(func=velocity.track_angular_velocity, weight=1.0,
                                       params={"command_name": "twist", "std": 0.4}),
        "upright": RewardTermCfg(func=velocity.upright, weight=1.0,
                                 params={"std": math.sqrt(0.1), "asset_cfg": SceneEntityCfg("robot", body_names=("torso",))}),
        "posture": RewardTermCfg(func=posture, weight=0.3, params={"std": 0.5}),
        "air_time": RewardTermCfg(func=velocity.feet_air_time, weight=0.5,
                                  params={"sensor_name": "feet_ground", "threshold_min": 0.1, "threshold_max": 0.4,
                                          "command_name": "twist", "command_threshold": 0.05}),
        "foot_slip": RewardTermCfg(func=foot_slip, weight=-2.0),
        "action_rate": RewardTermCfg(func=mdp.action_rate_l2, weight=-0.01),
        "copper_loss": RewardTermCfg(func=copper_loss, weight=-0.05),
        "joint_limits": RewardTermCfg(func=mdp.joint_pos_limits, weight=-1.0),
        "fall": RewardTermCfg(func=mdp.is_terminated, weight=-20.0),
    }
    if not play:
        cfg.events["push"] = EventTermCfg(
            func=mdp.push_by_setting_velocity, mode="interval", interval_range_s=(3.0, 8.0),
            params={"velocity_range": {"x": (-0.1, 0.1), "y": (-0.1, 0.1)}})
    return cfg
