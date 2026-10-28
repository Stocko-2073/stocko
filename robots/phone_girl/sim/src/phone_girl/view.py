"""Pose the robot by hand in a web viewer: the torso on a stand, a slider per joint.

Each actuator slider sets its joint's target as an offset from home, across the
joint's full travel. These are ideal position servos, not the BAM model, so this
is for checking the model: joint axes and directions, travel limits, collision
shapes and self-collisions. `uv run play PhoneGirl-Stand --agent zero` shows the
simulator as training sees it.
"""

from __future__ import annotations

import argparse

import mujoco
import viser
from mjviser import Viewer

from phone_girl.robot import HOME, LIMITS, spec
from phone_girl.xl330 import Bam

KP, KV = 10.0, 0.1  # N m/rad and N m s/rad: holds any limb against gravity to within a degree
LIFT = 0.05  # m above standing, so the stilts swing clear of the floor


def model() -> mujoco.MjModel:
    s = spec()
    # A weld, not a fixed torso: a body fixed to the world would collide with its
    # children, which a moving parent never does. Disable equality constraints in
    # the viewer to drop the robot.
    torso = s.body("torso")
    torso.pos = torso.pos + [0, 0, LIFT]
    weld = s.add_equality(type=mujoco.mjtEq.mjEQ_WELD, objtype=mujoco.mjtObj.mjOBJ_BODY, name1="torso")
    # Anchor at the torso, pose taken from qpos0 (zero quaternion), torque scale 1.
    weld.data = [0.0] * 10 + [1.0]
    weld.solref = [0.004, 1]
    s.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    s.worldbody.add_geom(name="floor", type=mujoco.mjtGeom.mjGEOM_PLANE, size=[0.5, 0.5, 0.01],
                         contype=1, conaffinity=1, rgba=[0.8, 0.8, 0.8, 1])
    armature = Bam.load().armature
    for actuator in s.actuators:  # one motor per joint, named after it
        name = actuator.target
        s.joint(name).armature = armature
        actuator.set_to_position(kp=KP, kv=KV)
        # Bias kp * home makes the force kp * (home + ctrl - q): ctrl 0 holds home.
        actuator.biasprm = [KP * HOME[name], -KP, -KV] + [0.0] * 7
        lo, hi = LIMITS[name]
        actuator.ctrlrange = [lo - HOME[name], hi - HOME[name]]
        actuator.ctrllimited = True
    return s.compile()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8081, help="web viewer port (play uses 8080)")
    args = parser.parse_args()
    m = model()
    Viewer(m, mujoco.MjData(m), server=viser.ViserServer(port=args.port, label="phone_girl")).run()


if __name__ == "__main__":
    main()
