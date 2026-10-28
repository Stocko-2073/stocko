import hashlib
import json
import shutil

import mujoco
import numpy as np
import pytest
from stable_baselines3.common.env_checker import check_env

from sim.build_model import CAD_TO_SIM
from sim.env import GynoidBalanceEnv, MODEL_PATH
from sim.export_cad import CAD, extract_frames


def test_model_mass_and_inertias():
    model = mujoco.MjModel.from_xml_path(str(MODEL_PATH))
    report = json.loads(MODEL_PATH.with_name("model_report.json").read_text())
    assert report["cad_sha256"] == hashlib.sha256(CAD.read_bytes()).hexdigest()
    assert model.nu == 9 and model.nq == 16 and model.nv == 15
    assert model.body_mass.sum() == pytest.approx(report["total_mass_kg"])
    assert 0.6 < model.body_mass.sum() < 0.7
    assert np.all(model.body_inertia[1:] > 0)
    assert np.all(2 * model.body_inertia[1:].max(axis=1)
                  <= model.body_inertia[1:].sum(axis=1) + 1e-12)


def test_gym_api_seed_and_time_limit():
    env = GynoidBalanceEnv(episode_seconds=0.1)
    check_env(env)
    first, _ = env.reset(seed=7)
    second, _ = env.reset(seed=7)
    np.testing.assert_array_equal(first, second)
    for step in range(5):
        observation, reward, terminated, truncated, info = env.step(np.zeros(9))
        assert observation.shape == (50,)
        assert np.isfinite(observation).all() and np.isfinite(reward)
        assert not terminated
        assert truncated == (step == 4)
    assert info["success"]
    env.close()


def test_contacts_fall_and_actuator_limits():
    env = GynoidBalanceEnv(reset_noise=0)
    env.reset(seed=0)
    assert env.data.ncon == 0  # No hidden interpenetration in CAD rest pose.
    reached_contact = False
    for _ in range(500):
        _, _, terminated, truncated, info = env.step(np.zeros(9))
        reached_contact |= any(info["foot_contacts"])
        assert np.max(np.abs(env.actuators.control_voltage)) <= 5.0 + 1e-12
        if terminated or truncated:
            break
    assert reached_contact and terminated and not truncated
    assert not info["success"]
    assert not env.data.warning.number.any()
    with pytest.raises(ValueError):
        env.step(np.full(9, np.nan))
    env.close()


def test_random_rollouts_remain_finite():
    env = GynoidBalanceEnv()
    rng = np.random.default_rng(3)
    env.reset(seed=3)
    for _ in range(1000):
        obs, reward, terminated, truncated, _ = env.step(rng.uniform(-1, 1, 9))
        assert np.isfinite(obs).all() and np.isfinite(reward)
        assert not env.data.warning.number.any()
        if terminated or truncated:
            env.reset()
    env.close()


@pytest.mark.skipif(shutil.which("openscad") is None, reason="CAD comparison requires OpenSCAD+BOSL2")
@pytest.mark.parametrize("knob", ["ha", "ta", "wa", "yaw"])
def test_motion_matches_openscad(knob):
    """Compare all 54 part origins after an independent CAD pose change."""
    source = CAD.read_text()
    before = {"ha": "ha=4;", "ta": "ta=-7;", "wa": "wa=0;", "yaw": "xl330(drive=90,spin="}[knob]
    after = {"ha": "ha=5;", "ta": "ta=-6;", "wa": "wa=1;", "yaw": "xl330(drive=91,spin="}[knob]
    assert source.count(before) == (2 if knob == "yaw" else 1)
    changed = extract_frames(source.replace(before, after))
    report = json.loads(MODEL_PATH.with_name("model_report.json").read_text())
    env = GynoidBalanceEnv(reset_noise=0, stance="cad")
    env.reset(seed=0)
    delta = np.deg2rad(1)
    for joint in report["actuated_joints"]:
        name = joint["name"]
        value = 0
        if knob == "ha" and name.endswith("hip_roll"):
            value = delta
        elif knob == "ta" and name.endswith("hip_pitch"):
            value = delta
        elif knob == "ta" and name.endswith("knee"):
            value = -delta if name.startswith("left") else delta
        elif knob == "wa" and name == "waist":
            value = delta
        elif knob == "yaw" and name.endswith("thigh_yaw"):
            value = delta
        env.data.joint(name).qpos[0] = value
    if knob == "wa":
        # The CAD's waist knob holds the chest fixed and rotates the pelvis.
        mujoco.mju_quatIntegrate(env.data.qpos[3:7], np.array([0., delta, 0.]), 1)
    mujoco.mj_forward(env.model, env.data)
    original = json.loads((MODEL_PATH.parent / "assets/cad_manifest.json").read_text())["frames"]
    origins = {"pelvis": CAD_TO_SIM @ np.array(original[0]["transform_mm"])[:3, 3] * 1e-3}
    for joint in report["actuated_joints"]:
        frame = original[joint["cad_part_index"]]
        origins[joint["name"]] = CAD_TO_SIM @ np.array(frame["transform_mm"])[:3, 3] * 1e-3
    for part in report["parts"]:
        # Report is grouped by rigid body, so index rather than list order matters.
        frame = changed[part["index"]]
        body = env.data.body(part["link"])
        predicted = body.xpos + body.xmat.reshape(3, 3) @ (np.array(part["origin_m"]) - origins[part["link"]])
        expected = CAD_TO_SIM @ np.array(frame["transform_mm"])[:3, 3] * 1e-3
        expected[2] += report["floor_offset_m"]
        np.testing.assert_allclose(predicted, expected, atol=2e-6,
                                   err_msg=f"{knob}, part {part['index']} {part['module']}")
        old_rotation = CAD_TO_SIM @ np.array(original[part["index"]]["transform_mm"])[:3, :3]
        expected_rotation = CAD_TO_SIM @ np.array(frame["transform_mm"])[:3, :3]
        np.testing.assert_allclose(body.xmat.reshape(3, 3) @ old_rotation, expected_rotation,
                                   atol=3e-6, err_msg=f"{knob}, part {part['index']} rotation")
    env.close()
