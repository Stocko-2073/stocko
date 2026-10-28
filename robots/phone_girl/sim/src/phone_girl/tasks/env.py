"""phone_girl environments: one base with the robot's real I/O, and the tasks on top.

Every task shares the actor's observation layout, the 17 joint targets and the
twist command slot (stand holds it at zero), so policies trained for different
tasks can be compared, swapped on the phone, and distilled into one.
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


def foot_slip(env, sensor_name: str = "feet_ground") -> torch.Tensor:
    robot = env.scene["robot"]
    contact = (env.scene[sensor_name].data.found > 0).float().reshape(env.num_envs, -1)
    speed = robot.data.site_lin_vel_w[:, index(FOOT_SITES, env.device), :2].norm(dim=-1)
    return (speed ** 2 * contact).sum(-1)


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
    # Anything but the stilts on the floor is a fall.
    body_ground = ContactSensorCfg(
        name="body_ground", primary=ContactMatch(mode="body", pattern=r"(?!.*_knee_link$).*", entity="robot"),
        secondary=ContactMatch(mode="body", pattern="terrain"), fields=("found",), reduce="netforce", num_slots=1)

    events = {
        "friction_fields": EventTermCfg(func=servo_friction_fields, mode="startup"),
        "reset_base": EventTermCfg(func=mdp.reset_root_state_uniform, mode="reset",
                                   params={"pose_range": {"yaw": (-math.pi, math.pi)}, "velocity_range": {}}),
        "reset_joints": EventTermCfg(func=mdp.reset_joints_by_offset, mode="reset",
                                     params={"position_range": (-0.03, 0.03), "velocity_range": (0.0, 0.0),
                                             "asset_cfg": SceneEntityCfg("robot", joint_names=(".*",))}),
        "servos": EventTermCfg(func=dr.randomize_servos, mode="reset", params={"randomization": randomization}),
        "supply": EventTermCfg(func=dr.randomize_supply, mode="reset", params={"randomization": randomization}),
        "body": EventTermCfg(func=dr.randomize_body, mode="reset", params={"randomization": randomization}),
        "friction": EventTermCfg(func=dr.randomize_friction, mode="reset", params={"randomization": randomization}),
        "link": EventTermCfg(func=link_events.sample_link, mode="reset", params={"link": link}),
        "late_commands": EventTermCfg(func=link_events.late_commands, mode="step", params={"link": link}),
    }

    return ManagerBasedRlEnvCfg(
        decimation=decimation,
        scene=SceneCfg(terrain=TerrainEntityCfg(terrain_type="plane"),
                       entities={"robot": robot_cfg(**delay_settings(link, PHYSICS_DT))},
                       sensors=(PhoneImuCfg(), feet_ground, body_ground), num_envs=1, extent=1.0),
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
            "body_on_floor": TerminationTermCfg(func=velocity.illegal_contact,
                                                params={"sensor_name": "body_ground"}),
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


def stand_cfg(play: bool = False) -> ManagerBasedRlEnvCfg:
    """Balance on the stilt tips and recover from pushes. Stepping is allowed."""
    cfg = base_cfg(play=play)
    cfg.rewards = {
        "alive": RewardTermCfg(func=mdp.is_alive, weight=1.0),
        "upright": RewardTermCfg(func=velocity.upright, weight=1.0,
                                 params={"std": math.sqrt(0.1), "asset_cfg": SceneEntityCfg("robot", body_names=("torso",))}),
        "com_over_feet": RewardTermCfg(func=com_over_feet, weight=1.0, params={"std": 0.02}),
        "posture": RewardTermCfg(func=posture, weight=0.5, params={"std": 0.3}),
        "still": RewardTermCfg(func=stillness, weight=0.5, params={"std": 0.1}),
        "foot_slip": RewardTermCfg(func=foot_slip, weight=-2.0),
        "action_rate": RewardTermCfg(func=mdp.action_rate_l2, weight=-0.01),
        "copper_loss": RewardTermCfg(func=copper_loss, weight=-0.05),
        "joint_limits": RewardTermCfg(func=mdp.joint_pos_limits, weight=-1.0),
        "fall": RewardTermCfg(func=mdp.is_terminated, weight=-20.0),
    }
    if not play:
        cfg.events["push"] = EventTermCfg(
            func=mdp.push_by_setting_velocity, mode="interval", interval_range_s=(2.0, 5.0),
            params={"velocity_range": {"x": (-0.15, 0.15), "y": (-0.15, 0.15), "yaw": (-0.5, 0.5)}})
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
