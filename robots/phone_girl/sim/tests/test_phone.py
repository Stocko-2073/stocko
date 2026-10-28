"""The phone's IMU and cameras as the app sees them."""

import numpy as np
import pytest
import torch

from mjlab.envs import ManagerBasedRlEnv
from mjlab.tasks.registry import load_env_cfg

from phone_girl.phone import with_camera


@pytest.fixture(scope="module")
def env():
    cfg = with_camera(load_env_cfg("PhoneGirl-Stand"), kind="depth", fps=30.0, latency_s=(0.045, 0.045))
    cfg.scene.num_envs = 2
    env = ManagerBasedRlEnv(cfg, device="cpu")
    env.reset()
    yield env
    env.close()


def test_gravity_points_down_the_screen_at_rest(env):
    """Standing, the phone is upright in portrait: CoreMotion gravity is about (0, -1, 0)."""
    gravity = env.scene["phone_imu"].data["gravity"]
    np.testing.assert_allclose(gravity[:, 1].numpy(), -1.0, atol=0.06)
    assert torch.all(gravity.norm(dim=-1).sub(1).abs() < 1e-3)


def test_imu_samples_arrive_at_coremotion_rate(env):
    """Between new 100 Hz samples the app keeps reading the same values."""
    imu = env.scene["phone_imu"]
    readings = []
    for step in range(30):
        env.sim.step()
        env.scene.update(env.physics_dt)
        if step >= 18:  # past the longest latency, 10 steps after a reset
            readings.append(imu.data["gyro"][0].clone())
    changes = sum(not torch.equal(a, b) for a, b in zip(readings, readings[1:]))
    assert 2 <= changes <= 3  # 11 physics steps of 2.5 ms span two or three 10 ms samples


def test_camera_frames_are_held_and_late(env):
    """At 30 fps and 66.7 Hz control a frame is held for two steps, 45 ms (3 steps) late."""
    frames = []
    for _ in range(10):
        obs, *_ = env.step(torch.zeros(2, env.action_manager.total_action_dim))
        frames.append(obs["camera"][0].clone())
    assert frames[-1].shape == (1, 64, 48)
    same = [torch.equal(a, b) for a, b in zip(frames, frames[1:])]
    assert any(same) and not all(same)
