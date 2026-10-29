"""phone_girl as an mjlab entity: the generated MJCF, XL330 servos and the home pose.

Joint order is MuJoCo's depth-first order (waist, right leg, left leg, right arm,
left arm). Actions, observations and the servo bus all use it; Dynamixel ID is
the slot plus one.
"""

from __future__ import annotations

import functools
import json
import re

import mujoco
import numpy as np
import torch

from mjlab.entity import EntityArticulationInfoCfg, EntityCfg
from mjlab.managers.event_manager import requires_model_fields

from phone_girl import MJCF
from phone_girl.xl330 import Xl330ActuatorCfg

REPORT = json.loads(MJCF.with_name("model_report.json").read_text())
_MODEL = mujoco.MjModel.from_xml_path(str(MJCF))
JOINTS = tuple(_MODEL.joint(i).name for i in range(1, _MODEL.njnt))
# The model is built standing in the CAD's default pose, so qpos0 is home.
HOME_HEIGHT = float(_MODEL.qpos0[2])
HOME = {name: float(_MODEL.qpos0[_MODEL.joint(name).qposadr[0]]) for name in JOINTS}
LIMITS = {name: tuple(map(float, _MODEL.joint(name).range)) for name in JOINTS}
FEET = ("left_foot", "right_foot")
# The robot's own site and geom ids, which are the entity's local ids in mjlab.
FOOT_SITES = tuple(_MODEL.site(f).id for f in FEET)
FOOT_GEOMS = tuple(_MODEL.geom(f).id for f in FEET)
# Every other collision geom: the parts' boxes and capsules, named <link>_<part>_<n>.
BODY_GEOMS = tuple(i for i in range(_MODEL.ngeom) if re.fullmatch(r".*_[0-9]+", _MODEL.geom(i).name))


@functools.cache
def index(ids: tuple[int, ...], device: str) -> torch.Tensor:
    """An index tensor, built once per device: building it every step would stall the GPU."""
    return torch.tensor(ids, device=device)


def _mirror() -> dict[str, tuple[str, float]]:
    """Each joint's mirror image and sign: the mirrored motion of q on one side is
    sign*q on the other. A rotation about a is mirrored to the opposite rotation
    about M a, with M the reflection through the sagittal plane."""
    reflect = np.diag([1.0, -1, 1])
    axes = {j["name"]: np.array(j["axis_sim"]) for j in REPORT["joints"]}
    out = {}
    for name in JOINTS:
        other = name.replace("left_", "@").replace("right_", "left_").replace("@", "right_")
        out[name] = (other, float(-np.sign(axes[other] @ reflect @ axes[name])))
    return out


MIRROR = _mirror()


def spec() -> mujoco.MjSpec:
    return mujoco.MjSpec.from_file(str(MJCF))


def servos(**overrides) -> Xl330ActuatorCfg:
    return Xl330ActuatorCfg(target_names_expr=JOINTS, **overrides)


def robot_cfg(**servo_overrides) -> EntityCfg:
    return EntityCfg(
        init_state=EntityCfg.InitialStateCfg(pos=(0.0, 0.0, HOME_HEIGHT), joint_pos=dict(HOME),
                                             joint_vel={".*": 0.0}),
        spec_fn=spec,
        articulation=EntityArticulationInfoCfg(actuators=(servos(**servo_overrides),)),
    )


@requires_model_fields("dof_frictionloss", "dof_damping")
def servo_friction_fields(env, env_ids=None) -> None:
    """Startup event: the servos write friction per world, so those fields must be per world."""
    del env, env_ids
