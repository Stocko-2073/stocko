"""The generated MJCF against the CAD it came from.

The CAD comparisons need robots/phone_girl/phone_girl.scad and mass.py, and skip
without them; the generated model and its other tests don't.
"""

import hashlib
import json
import shutil

import mujoco
import numpy as np
import pytest

from phone_girl import ASSETS, CAD, CAD_TO_SIM, MJCF

MANIFEST = json.loads((ASSETS / "cad_manifest.json").read_text())
REPORT = json.loads(MJCF.with_name("model_report.json").read_text())
needs_cad = pytest.mark.skipif(not CAD.exists(), reason="needs phone_girl.scad")


@pytest.fixture(scope="module")
def model():
    return mujoco.MjModel.from_xml_path(str(MJCF))


def body_of(part):
    if part["joint"] is None:
        return "torso"
    name = MANIFEST["joints"][part["joint"]]["name"]
    return "pelvis" if name == "waist" else f"{name}_link"


def predicted(model, data, part):
    """A part's CAD frame, moved by its body from the default pose. Returns sim-frame (R, p)."""
    home = np.array(part["transform"])
    rotation0, position0 = CAD_TO_SIM @ home[:3, :3], CAD_TO_SIM @ home[:3, 3] * 1e-3
    body = data.body(body_of(part))
    # At qpos0 every body frame is world-aligned and sits on its joint's shaft, and
    # the whole robot is raised to stand on the floor.
    pivot = np.zeros(3) if part["joint"] is None else \
        CAD_TO_SIM @ np.array(MANIFEST["joints"][part["joint"]]["pivot_mm"]) * 1e-3
    rotation = body.xmat.reshape(3, 3)
    return rotation @ rotation0, rotation @ (position0 - pivot) + body.xpos - model.qpos0[:3]


def check_against(model, data, transforms):
    for part, transform in zip(MANIFEST["parts"], transforms):
        rotation, position = predicted(model, data, part)
        expected = np.array(transform)
        np.testing.assert_allclose(position, CAD_TO_SIM @ expected[:3, 3] * 1e-3, atol=2e-6,
                                   err_msg=f"part {part['index']} {part['module']} position")
        np.testing.assert_allclose(rotation, CAD_TO_SIM @ expected[:3, :3], atol=2e-5,
                                   err_msg=f"part {part['index']} {part['module']} rotation")


@needs_cad
def test_manifest_matches_cad():
    assert MANIFEST["cad_sha256"] == hashlib.sha256(CAD.read_bytes()).hexdigest(), \
        "phone_girl.scad changed: run phone-girl-export and phone-girl-build"
    assert REPORT["cad_sha256"] == MANIFEST["cad_sha256"]


def test_joint_angles_are_servo_angles(model):
    """qpos0 is the CAD default pose, and each joint's angle there is its servo's."""
    for joint in MANIFEST["joints"]:
        # The XML keeps six significant digits: microradians, far below one encoder tick.
        assert model.qpos0[model.joint(joint["name"]).qposadr[0]] == pytest.approx(joint["default_rad"], abs=1e-5)


@pytest.mark.cad
@needs_cad
@pytest.mark.skipif(shutil.which("openscad") is None, reason="needs OpenSCAD with BOSL2")
def test_random_pose_matches_cad(model):
    """An independent OpenSCAD run at random knobs agrees with the model's kinematics."""
    from phone_girl import cad  # imports the robot's mass.py, beside the CAD

    rng = np.random.default_rng(7)
    knobs = [v + rng.uniform(-30, 30) for v in MANIFEST["default_pose"]]
    rows, _ = cad.echoes(cad.instrument(CAD.read_text()), knobs)
    data = mujoco.MjData(model)  # qpos starts at qpos0
    for joint in MANIFEST["joints"]:
        drive = rows[joint["servo_part"]]["params"]["drive"]
        data.joint(joint["name"]).qpos[0] = np.radians(joint["handedness"] * drive)
    mujoco.mj_kinematics(model, data)
    check_against(model, data, [r["transform"] for r in rows])


def test_mass_and_inertia(model):
    parts = sum(MANIFEST["variants"][p["variant"]]["mass"]["mass_g"] for p in MANIFEST["parts"])
    assert model.body_mass.sum() == pytest.approx(parts * 1e-3)
    assert 0.6 < model.body_mass.sum() < 0.9
    inertia = model.body_inertia[1:]
    assert np.all(inertia > 0) and np.all(2 * inertia.max(axis=1) <= inertia.sum(axis=1) + 1e-12)


def test_home_stands_on_its_tips(model):
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    feet = [model.geom(f"{side}_foot").id for side in ("left", "right")]
    lowest = [data.geom_xpos[g, 2] - model.geom_size[g, 0] for g in range(model.ngeom)
              if model.geom_contype[g] or model.geom_conaffinity[g]]
    np.testing.assert_allclose(data.geom_xpos[feet, 2] - model.geom_size[feet, 0], 0, atol=1e-4)
    assert min(lowest) > -1e-6
    assert data.ncon == 0  # no proxies overlap in the CAD pose
    assert data.site("left_foot").xpos[1] > data.site("right_foot").xpos[1]


def test_imu_and_cameras_follow_the_phone(model):
    """The IMU frame is CoreMotion's: x to the robot's left, y up, z forward out of the screen."""
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    imu = data.site("imu").xmat.reshape(3, 3)
    np.testing.assert_allclose(imu, [[0, 0, 1], [1, 0, 0], [0, 1, 0]], atol=1e-6)
    front = data.camera("front").xmat.reshape(3, 3)
    np.testing.assert_allclose(-front[:, 2], [1, 0, 0], atol=1e-6)  # looks forward
    np.testing.assert_allclose(front[:, 1], [0, 0, 1], atol=1e-6)  # image up is up
    rear = data.camera("rear_main").xmat.reshape(3, 3)
    np.testing.assert_allclose(-rear[:, 2], [-1, 0, 0], atol=1e-6)


def test_view_stand_holds_home():
    """phone-girl-view's stand: nothing touches at home, and the torso and joints hold still."""
    from phone_girl.view import model as stand

    m = stand()
    data = mujoco.MjData(m)
    for _ in range(500):  # 1 s
        mujoco.mj_step(m, data)
    assert data.ncon == 0
    assert np.abs(data.qpos[7:] - m.qpos0[7:]).max() < np.radians(0.1)
    assert np.linalg.norm(data.qpos[:3] - m.qpos0[:3]) < 1e-4
