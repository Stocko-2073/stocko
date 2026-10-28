import json
import shutil

import mujoco
import numpy as np
import pytest
from scipy.optimize import least_squares
from stable_baselines3.common.env_checker import check_env

from sim.build_model import CAD_TO_SIM
from sim.export_cad import CAD, extract_frames
from sim.planted import GynoidPlantedEnv
from sim.rest_pose import MODEL_PATH, REST_PATH, RestPoseProblem


def test_full_model_preserves_mass_geometry_and_com():
    full = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
    old = mujoco.MjModel.from_xml_path(str(MODEL_PATH.with_name("gynoid.xml")))
    d, d0 = mujoco.MjData(full), mujoco.MjData(old)
    mujoco.mj_forward(full, d)
    mujoco.mj_forward(old, d0)
    assert (full.nu, full.nq, full.nv, full.neq) == (21, 38, 35, 2)
    assert full.body_mass.sum() == pytest.approx(old.body_mass.sum(), abs=1e-10)
    np.testing.assert_allclose(d.subtree_com[1], d0.subtree_com[1], atol=1e-10)
    for geom in range(old.ngeom):
        name = old.geom(geom).name
        np.testing.assert_allclose(d.geom(name).xpos, d0.geom(name).xpos, atol=2e-9)
        np.testing.assert_allclose(d.geom(name).xmat, d0.geom(name).xmat, atol=2e-9)
    np.testing.assert_allclose(d.efc_pos[:6], 0, atol=1e-10)
    assert d.ncon == 0


def test_rest_pose_constraints_and_inverse_statics():
    p = RestPoseProblem()
    rest = json.loads(REST_PATH.read_text())
    p.data.qpos[:] = rest["qpos"]
    mujoco.mj_forward(p.model, p.data)
    np.testing.assert_allclose(p.data.site_xpos[p.feet], p.anchors, atol=1e-8)
    np.testing.assert_allclose(p.data.subtree_com[p.pelvis, :2], p.anchors[:, :2].mean(0), atol=1e-8)
    np.testing.assert_allclose(p.data.xmat[p.torso].reshape(3, 3)[:, 2], [0, 0, 1], atol=1e-8)
    torque, residual = p.holding_torque()
    assert np.linalg.norm(residual) < 1e-7
    assert np.abs(torque).max() < 0.025
    assert rest["optimized"]["copper_loss_w"] < 0.4 * rest["centered_fixed_upper_body"]["copper_loss_w"]
    assert not any(c.dist < -1e-5 for c in p.data.contact)


def test_planted_api_reset_and_unwelded_feet():
    env = GynoidPlantedEnv(episode_seconds=0.1)
    check_env(env)
    a, _ = env.reset(seed=7)
    b, _ = env.reset(seed=7)
    np.testing.assert_array_equal(a, b)
    assert a.shape == (110,) and env.action_space.shape == (21,)
    # Only the neck is constrained; there are no foot/floor equality constraints.
    assert env.model.neq == 2
    for step in range(5):
        _, _, terminated, truncated, info = env.step(np.zeros(21))
        assert not terminated
        assert truncated == (step == 4)
        assert info["foot_drift_m"] < 0.001
    assert info["success"]
    env.reset(seed=7)
    env.data.qpos[0] += 0.02
    mujoco.mj_forward(env.model, env.data)
    _, _, terminated, _, info = env.step(np.zeros(21))
    assert terminated and "foot_drift" in info["termination_reasons"]
    assert not env.data.warning.number.any()
    env.close()


@pytest.mark.parametrize("neck_command", [0.0, 0.5])
def test_neck_holds_without_linkage_slack_and_can_still_move(neck_command):
    env = GynoidPlantedEnv(reset_noise=0)
    try:
        env.reset(seed=0)
        neck = [env.joint_names.index(f"{side}_neck") for side in ("right", "left")]
        pitch_id = env.model.joint("head_pitch").qposadr[0]
        pitches = [env.data.qpos[pitch_id]]
        for step in range(60):
            action = np.zeros(env.model.nu)
            if step >= 10:
                action[neck] = [neck_command, -neck_command]
            _, _, terminated, truncated, _ = env.step(action)
            for side in ("right", "left"):
                separation = np.linalg.norm(env.data.site(f"{side}_rod_end").xpos
                                            - env.data.site(f"{side}_stem").xpos)
                assert separation < 1e-5  # 0.01 mm, including contact settling.
            pitches.append(env.data.qpos[pitch_id])
            assert not terminated and not truncated
        travel_deg = np.rad2deg(np.ptp(pitches))
        if neck_command == 0:
            assert travel_deg < 0.05
        else:
            assert travel_deg > 1.0  # Tight constraints must not lock the mechanism.
        assert not env.data.warning.number.any()
    finally:
        env.close()


@pytest.mark.skipif(shutil.which("openscad") is None, reason="Requires OpenSCAD+BOSL2")
@pytest.mark.parametrize("knob", ["shoulder_1", "shoulder_2", "elbow", "wrist", "thumb", "neck", "neck_left"])
def test_new_joint_motion_matches_cad(knob):
    before, after = {
        "shoulder_1": ("xl330(drive=0) {", "xl330(drive=1) {"),
        "shoulder_2": ("xl330(drive=20,orient=FWD", "xl330(drive=21,orient=FWD"),
        "elbow": ("xl330(drive=40,idler_disk=true", "xl330(drive=41,idler_disk=true"),
        "wrist": ("xl330(drive=0,orient=FWD", "xl330(drive=1,orient=FWD"),
        "thumb": ("xl330(idler_disk=true,spin=90){", "xl330(drive=1,idler_disk=true,spin=90){"),
        "neck": ("neck(drive=[0,0]);", "neck(drive=[1,0]);"),
        "neck_left": ("neck(drive=[0,0]);", "neck(drive=[0,1]);"),
    }[knob]
    source = CAD.read_text()
    assert source.count(before) == (1 if knob.startswith("neck") else 2)
    changed = extract_frames(source.replace(before, after))
    model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
    data = mujoco.MjData(model)
    reference = mujoco.MjData(model)
    mujoco.mj_forward(model, reference)
    original = json.loads((MODEL_PATH.parent / "assets/cad_manifest.json").read_text())["frames"]
    if not knob.startswith("neck"):
        for side in ("left", "right"):
            data.joint(f"{side}_{knob}").qpos[0] = np.deg2rad(1)
    else:
        old_r = CAD_TO_SIM @ np.array(original[2]["transform_mm"])[:3, :3]
        target = CAD_TO_SIM @ np.array(changed[2]["transform_mm"])[:3, :3] @ old_r.T
        def head_rotation(angles):
            data.joint("head_yaw").qpos[0], data.joint("head_pitch").qpos[0] = angles
            mujoco.mj_forward(model, data)
            return (data.body("head").xmat.reshape(3, 3) - target).ravel()
        solved = least_squares(head_rotation, np.zeros(2), gtol=1e-13, ftol=1e-13, xtol=1e-13)
        assert np.linalg.norm(head_rotation(solved.x)) < 2e-6
        data.joint("left_neck" if knob == "neck_left" else "right_neck").qpos[0] = np.deg2rad(1)
        mujoco.mj_forward(model, data)
        for side in ("left", "right"):
            end, stem = model.site(f"{side}_rod_end").id, model.site(f"{side}_stem").id
            body = data.body(f"{side}_rod")
            direction = body.xmat.reshape(3, 3).T @ (data.site_xpos[stem] - body.xpos)
            a, b = model.site_pos[end].copy(), direction
            a /= np.linalg.norm(a)
            b /= np.linalg.norm(b)
            quat = np.r_[1 + a @ b, np.cross(a, b)]
            data.joint(f"{side}_rod").qpos[:] = quat / np.linalg.norm(quat)
    mujoco.mj_forward(model, data)
    report = json.loads(MODEL_PATH.with_name("full_model_report.json").read_text())
    links = {p["index"]: p["link"] for p in report["parts"]}
    for index, frame in enumerate(changed):
        transform = np.array(frame["transform_mm"])
        position = CAD_TO_SIM @ transform[:3, 3] * 1e-3
        position[2] += report["floor_offset_m"]
        old_transform = np.array(original[index]["transform_mm"])
        old_position = CAD_TO_SIM @ old_transform[:3, 3] * 1e-3
        old_position[2] += report["floor_offset_m"]
        body, before_body = data.body(links[index]), reference.body(links[index])
        predicted = body.xpos + body.xmat.reshape(3, 3) @ (old_position - before_body.xpos)
        np.testing.assert_allclose(predicted, position, atol=2e-6, err_msg=f"{knob}, part {index}")
        if frame["module"] == "neck_link_2":
            continue  # Axial rod twist is free; its endpoints define the linkage.
        rotation = CAD_TO_SIM @ transform[:3, :3]
        predicted_rotation = body.xmat.reshape(3, 3) @ CAD_TO_SIM @ old_transform[:3, :3]
        np.testing.assert_allclose(predicted_rotation, rotation, atol=4e-6,
                                   err_msg=f"{knob}, part {index} rotation")
    np.testing.assert_allclose(data.efc_pos[:6], 0, atol=2e-6)
