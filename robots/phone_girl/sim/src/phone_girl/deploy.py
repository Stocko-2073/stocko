"""Policies the phone can run: ONNX with the robot contract attached.

Every checkpoint is also exported as ONNX (observation normalization included)
with a `phone_girl` metadata entry holding everything the app needs to run it:
joint order and servo IDs, the observation layout and history, the action
mapping, limits and tick encoding, and the control period.

Servos are calibrated so the home pose reads 2048 on every one (set each Homing
Offset with the robot in its home pose). Then for every joint

    goal ticks     = 2048 + round((home + scale * action - home) / tick), clipped to the soft limits
    joint_pos obs  = (Present Position - 2048) * tick

with tick = 2 pi / 4096. Positive is counterclockwise looking at the horn, which
is the model's joint axis for every servo.
"""

from __future__ import annotations

import json

import onnx

from mjlab.rl.runner import MjlabOnPolicyRunner

from phone_girl.observations import NOMINAL_VOLTAGE
from phone_girl.robot import HOME, JOINTS, LIMITS, REPORT
from phone_girl.xl330 import TICK

CONTRACT_VERSION = 1


def contract(env) -> dict:
    manager = env.observation_manager
    names = manager.active_terms["actor"]
    dims = manager.group_obs_term_dim["actor"]
    group = env.cfg.observations["actor"]
    history = group.history_length or 1
    action = env.cfg.actions["joint_pos"]
    by_name = {j["name"]: j for j in REPORT["joints"]}
    effort = next(t.func for n, t in group.terms.items() if n == "joint_effort")
    return dict(
        version=CONTRACT_VERSION,
        control_period_s=env.step_dt,
        joints=[dict(name=j, slot=i, dynamixel_id=by_name[j]["dynamixel_id"], home_rad=HOME[j],
                     soft_limits_rad=list(LIMITS[j])) for i, j in enumerate(JOINTS)],
        tick_rad=TICK, home_ticks=2048,
        action=dict(scale=action.scale, target="home + scale * action, clipped to soft limits"),
        observation=dict(history=history, order="each term's history oldest to newest, term after term",
                         terms=[dict(name=n, size=int(d[0]) // history) for n, d in zip(names, dims)]),
        effort=dict(kt=effort.__globals__["BAM"].kt, resistance=effort.__globals__["BAM"].resistance,
                    formula="kt/R * (Present PWM/885 * Present Input Voltage - kt * Present Velocity)"),
        bus_voltage_offset=NOMINAL_VOLTAGE,
        imu="CoreMotion deviceMotion: gravity (g) and rotationRate (rad/s), device frame",
    )


def attach(onnx_path: str, metadata: dict) -> None:
    model = onnx.load(onnx_path)
    entry = model.metadata_props.add()
    entry.key, entry.value = "phone_girl", json.dumps(metadata)
    onnx.save(model, onnx_path)


def read(onnx_path: str) -> dict:
    model = onnx.load(onnx_path)
    return json.loads(next(p.value for p in model.metadata_props if p.key == "phone_girl"))


class PhoneGirlRunner(MjlabOnPolicyRunner):
    """Saves an ONNX policy with the robot contract next to every checkpoint."""

    def save(self, path: str, infos=None) -> None:
        super().save(path, infos)
        directory, filename, onnx_path = self._get_export_paths(path)
        filename = filename.replace(".onnx", f"_{self.current_learning_iteration}.onnx")
        self.export_policy_to_onnx(str(directory), filename)
        attach(str(directory / filename), contract(self.env.unwrapped))
