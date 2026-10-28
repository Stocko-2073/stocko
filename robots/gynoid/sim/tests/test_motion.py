import mujoco
import numpy as np
import pytest

from sim.balance_controller import PlantedBalanceController
from sim.motion_control import MotionController
from sim.motion_env import GynoidMotionEnv


@pytest.fixture(scope="module", params=["recovery", "reach", "weight_shift", "overhead"])
def motion(request):
    return MotionController.build(request.param)


def test_planned_poses_have_clearance_and_planted_feet(motion):
    env = GynoidMotionEnv(**motion.environment_kwargs())
    try:
        for pose in motion.poses:
            env.data.qpos[:] = pose
            mujoco.mj_forward(env.model, env.data)
            np.testing.assert_allclose(env.data.site_xpos[env.feet], env.anchors, atol=1e-7)
            np.testing.assert_allclose(env.data.xmat[env.torso].reshape(3, 3)[:, 2], [0, 0, 1], atol=1e-5)
            assert not any(c.dist < -1e-5 for c in env.data.contact
                           if env.floor not in (c.geom1, c.geom2))
    finally:
        env.close()


def test_motion_tracks_its_goal_and_returns(motion):
    kwargs = motion.environment_kwargs()
    if motion.motion == "recovery":
        kwargs.update(episode_seconds=10, push_force=0.1)
    env = GynoidMotionEnv(**kwargs)
    try:
        env.reset(seed=14000)
        samples = []
        for _ in range(env.max_steps):
            _, _, terminated, truncated, info = env.step(motion.predict(env))
            samples.append(info)
            assert not terminated, info
        assert truncated and info["success"]
        outcome = motion.assess(samples)
        assert outcome["motion_success"], outcome
        assert not env.data.warning.number.any()
        assert env.model.neq == 2
        if motion.motion == "overhead":
            assert env.actuators.saturated_updates == 0
            assert env.actuators.peak_current_a < 0.6
            assert env.model.jnt_range[env.model.joint("right_shoulder_1").id, 1] == 3.0
    finally:
        env.close()


def test_motion_round_trip_and_reset_during_a_motion(motion, tmp_path):
    path = tmp_path / "controller.npz"
    motion.save(path)
    loaded, config = PlantedBalanceController.load(path)
    assert isinstance(loaded, MotionController)
    env = GynoidMotionEnv(**config["env_kwargs"])
    try:
        env.reset(seed=14001)
        env.data.time = 7
        np.testing.assert_array_equal(motion.predict(env), loaded.predict(env))
        env.reset(seed=14001)
        np.testing.assert_array_equal(env.command_center, env.initial_command_center)
        np.testing.assert_array_equal(env.target, env.initial_command_center)
    finally:
        env.close()
