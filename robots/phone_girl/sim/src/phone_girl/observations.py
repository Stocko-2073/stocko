"""Observations: what the phone has when it runs the policy, and what only the simulator knows.

The actor's terms are the robot's I/O contract. The phone app builds the same
vector from CoreMotion and the MCU's state notification, in SI units and in this
order, and feeds it to the exported policy (which normalizes internally):

    gravity        CMDeviceMotion.gravity, device frame, g                  3
    gyro           CMDeviceMotion.rotationRate, device frame, rad/s          3
    joint_pos      servo position minus the home pose, rad                  17
    joint_vel      servo Present Velocity, rad/s                            17
    joint_effort   motor torque estimate from the servo's registers, Nm     17
    bus_voltage    Present Input Voltage minus 7.4 V                         1
    last_action    the previous action                                      17
    command        twist command: forward m/s, left m/s, yaw rad/s           3

joint_effort is kt/R (pwm * voltage - kt * velocity) with BAM's nominal kt and R
and the servo's own Present PWM, Input Voltage and Velocity. It needs no current
sensor: the XL330 measures current at its power input, which says little about
torque. Joint order is phone_girl.robot.JOINTS; phone_girl.deploy attaches all
this to every exported policy.
"""

from __future__ import annotations

import torch

from mjlab.envs import mdp
from mjlab.managers.observation_manager import ObservationGroupCfg, ObservationTermCfg

from phone_girl.link import servos
from phone_girl.robot import FOOT_GEOMS, index
from phone_girl.xl330 import Bam

BAM = Bam.load()

NOMINAL_VOLTAGE = 7.4  # 2S Li-ion


def phone_gravity(env) -> torch.Tensor:
    return env.scene["phone_imu"].data["gravity"]


def phone_gyro(env) -> torch.Tensor:
    return env.scene["phone_imu"].data["gyro"]


def servo_position(env) -> torch.Tensor:
    actuator = servos(env)
    return actuator.telemetry()["position"] - actuator.entity.data.default_joint_pos[:, actuator.target_ids]


def servo_velocity(env) -> torch.Tensor:
    return servos(env).telemetry()["velocity"]


def servo_current(env) -> torch.Tensor:
    return servos(env).telemetry()["current"]


def servo_effort(env) -> torch.Tensor:
    t = servos(env).telemetry()
    return BAM.kt / BAM.resistance * (t["pwm"] * t["voltage"][:, None] - BAM.kt * t["velocity"])


def bus_voltage(env) -> torch.Tensor:
    return servos(env).telemetry()["voltage"][:, None] - NOMINAL_VOLTAGE


# Privileged: true state and the parameters the actor has to infer.

def motor_torque(env) -> torch.Tensor:
    return servos(env).torque


def supply(env) -> torch.Tensor:
    actuator = servos(env)
    return torch.stack((actuator.supply_voltage - NOMINAL_VOLTAGE, actuator.supply_resistance), dim=-1)


def foot_friction(env) -> torch.Tensor:
    robot = env.scene["robot"]
    return env.sim.model.geom_friction[:, robot.indexing.geom_ids[index(FOOT_GEOMS, env.device)], 0]


def feet_contact(env, sensor_name: str = "feet_ground") -> torch.Tensor:
    return env.scene[sensor_name].data.found.float().reshape(env.num_envs, -1)


ACTOR = {
    "gravity": phone_gravity,
    "gyro": phone_gyro,
    "joint_pos": servo_position,
    "joint_vel": servo_velocity,
    "joint_effort": servo_effort,
    "bus_voltage": bus_voltage,
}


def actor_group(command: str = "twist", history: int = 3) -> ObservationGroupCfg:
    terms = {name: ObservationTermCfg(func=func) for name, func in ACTOR.items()}
    terms["last_action"] = ObservationTermCfg(func=mdp.last_action)
    terms["command"] = ObservationTermCfg(func=mdp.generated_commands, params={"command_name": command})
    # The sensor models already add noise, bias, quantization and latency.
    return ObservationGroupCfg(terms=terms, concatenate_terms=True, enable_corruption=False,
                               history_length=history)


def critic_group(command: str = "twist") -> ObservationGroupCfg:
    terms = {name: ObservationTermCfg(func=func) for name, func in ACTOR.items()}
    terms.update(
        last_action=ObservationTermCfg(func=mdp.last_action),
        command=ObservationTermCfg(func=mdp.generated_commands, params={"command_name": command}),
        base_lin_vel=ObservationTermCfg(func=mdp.base_lin_vel),
        base_ang_vel=ObservationTermCfg(func=mdp.base_ang_vel),
        projected_gravity=ObservationTermCfg(func=mdp.projected_gravity),
        true_joint_pos=ObservationTermCfg(func=mdp.joint_pos_rel),
        true_joint_vel=ObservationTermCfg(func=mdp.joint_vel_rel),
        motor_torque=ObservationTermCfg(func=motor_torque),
        joint_current=ObservationTermCfg(func=servo_current),
        supply=ObservationTermCfg(func=supply),
        foot_friction=ObservationTermCfg(func=foot_friction),
        feet_contact=ObservationTermCfg(func=feet_contact),
    )
    return ObservationGroupCfg(terms=terms, concatenate_terms=True, enable_corruption=False)
