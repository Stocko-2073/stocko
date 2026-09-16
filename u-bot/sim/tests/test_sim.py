import gymnasium as gym
import mujoco
import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env

import ubot_sim
from ubot_sim.env import UBotNavigationEnv, baseline_action


def test_gym_contract():
    env = UBotNavigationEnv()
    try:
        check_env(env, skip_render_check=True)
        assert env.model.nu == 2
        assert sum("_lug_" in (mujoco.mj_id2name(env.model, mujoco.mjtObj.mjOBJ_GEOM, i) or "")
                   for i in range(env.model.ngeom)) == 80
        assert env.model.njnt == 9  # free base, two drive, two swivel, four roller
    finally:
        env.close()
    with gym.make("UBotNavigation-v0") as registered:
        assert registered.reset(seed=1)[0].shape == (22,)


@pytest.mark.parametrize("action, expected", [([0.4, 0.4], "forward"), ([-0.4, -0.4], "reverse"), ([-0.3, 0.3], "left")])
def test_motion(action, expected):
    env = UBotNavigationEnv()
    env.reset(seed=0, options={"yaw": 0, "goal": [3, 0]})
    start = env.data.xpos[env.base].copy()
    headings = [np.arctan2(env.data.xmat[env.base, 3], env.data.xmat[env.base, 0])]
    for _ in range(150):
        obs, _, terminated, _, _ = env.step(action)
        assert np.isfinite(obs).all()
        assert not terminated
        headings.append(np.arctan2(env.data.xmat[env.base, 3], env.data.xmat[env.base, 0]))
    rotation = env.data.xmat[env.base].reshape(3, 3)
    if expected == "forward":
        assert env.data.xpos[env.base, 0] - start[0] > 0.4
    elif expected == "reverse":
        assert env.data.xpos[env.base, 0] - start[0] < -0.4
    else:
        # Preserve turn direction when the heading crosses +pi to -pi.
        assert np.unwrap(headings)[-1] - headings[0] > 0.5
    assert rotation[2, 2] > 0.95
    assert abs(env.data.xpos[env.base, 2] - 0.1075) < 0.01
    assert not any(w.number for w in env.data.warning)
    env.close()


@pytest.mark.parametrize("seed", range(5))
def test_baseline_reaches_goal(seed):
    env = UBotNavigationEnv(randomize=True)
    obs, _ = env.reset(seed=seed)
    for _ in range(env.max_steps):
        obs, _, terminated, truncated, info = env.step(baseline_action(obs))
        if terminated or truncated:
            break
    assert info["is_success"], info
    env.close()


def test_limits_and_reset():
    env = UBotNavigationEnv(max_steps=2, randomize=True)
    first, _ = env.reset(seed=9)
    env.step([1, -1])
    assert np.max(np.abs(env.data.ctrl)) <= 8 * 2 * np.pi * env.dt + 1e-8
    assert env.step([1, -1])[3]
    second, _ = env.reset(seed=9)
    np.testing.assert_allclose(first, second)
    with pytest.raises(ValueError):
        env.step([np.nan, 0])
    env.close()


@pytest.mark.parametrize("timestep", [0.002, 0.001])
def test_firmware_velocity_ramp(timestep):
    with UBotNavigationEnv(timestep=timestep) as env:
        env.reset(seed=0)
        # Opposite wheel directions must have symmetric acceleration.
        env.step([1, -1])
        np.testing.assert_allclose(env.command / (2 * np.pi), [0.16, -0.16])
        # Each wheel chooses its own rate: left slows while right speeds up.
        env.step([0.1, -1])
        np.testing.assert_allclose(env.command / (2 * np.pi), [0.12, -0.32])
        env.step([0.1, -1])
        np.testing.assert_allclose(env.command / (2 * np.pi), [0.1, -0.48])
        # Reversal brakes even when the new target has a larger magnitude.
        env.step([-1, 1])
        np.testing.assert_allclose(env.command / (2 * np.pi), [0.06, -0.44])
        env.step([-1, 1])
        np.testing.assert_allclose(env.command / (2 * np.pi), [0.02, -0.40])
        env.step([-1, 1])
        # Zero crossing is quantized to one physics tick, as in firmware.
        assert -0.08 - 1e-10 <= env.command[0] / (2 * np.pi) <= -0.06 + 1e-10
        assert env.command[1] / (2 * np.pi) == pytest.approx(-0.36)
        before = env.command.copy()
        env.step([-1, 1])
        np.testing.assert_allclose((env.command - before) / (2 * np.pi), [-0.16, 0.04])
        # A zero target snaps the deceleration tail to standstill.
        for _ in range(10):
            obs, *_ = env.step([0, 0])
        np.testing.assert_array_equal(env.command, [0, 0])
        np.testing.assert_array_equal(env.data.ctrl, [0, 0])
        np.testing.assert_array_equal(obs[18:20], [0, 0])
        env.step([1, -1])
        env.reset(seed=0)
        np.testing.assert_array_equal(env.command, [0, 0])
        np.testing.assert_array_equal(env.data.ctrl, [0, 0])
        env.step([0.06, -0.06])
        env.step([0, 0])
        np.testing.assert_array_equal(env.command, [0, 0])
        # Small nonzero targets are not subject to the standstill snap.
        env.step([0.01, -0.01])
        np.testing.assert_allclose(env.command / (2 * np.pi), [0.01, -0.01])


def test_waypoints_preserve_simulation_and_finish_route():
    from ubot_sim.waypoints import UBotWaypointsEnv
    env = UBotWaypointsEnv()
    obs, _ = env.reset(seed=0, options={"yaw": 0})
    reached = []
    for step in range(env.max_steps):
        obs, _, terminated, truncated, info = env.step(baseline_action(obs))
        assert env.steps == step + 1
        assert env.data.time == pytest.approx((step + 1) * env.dt)
        if info["waypoint_reached"]:
            reached.append(info["waypoints_reached"])
            assert np.linalg.norm(env.data.xpos[env.base, :2] - env.waypoints[reached[-1] - 1]) < 0.12
            if reached[-1] < len(env.waypoints):
                assert not terminated
                assert not info["is_success"]
                np.testing.assert_allclose(env.goal, env.waypoints[reached[-1]])
                assert env.success_steps == 0
        if terminated or truncated:
            break
    assert info["is_success"]
    assert reached == list(range(1, len(env.waypoints) + 1))
    env.reset(seed=0)
    assert env.waypoint_index == 0
    env.close()


def test_invalid_waypoint_route():
    from ubot_sim.waypoints import UBotWaypointsEnv
    for route in ([], [[1]], [[np.nan, 0]]):
        with pytest.raises(ValueError):
            UBotWaypointsEnv(waypoints=route)


@pytest.mark.parametrize("terrain", ["flat", "bumps"])
def test_lug_contacts_mass_and_navigation(terrain):
    from ubot_sim.waypoints import UBotWaypointsEnv
    smooth = UBotWaypointsEnv(wheel_contact="smooth", terrain=terrain)
    lugged = UBotWaypointsEnv(wheel_contact="lugs", terrain=terrain)
    assert lugged.model.ngeom == smooth.model.ngeom + 80
    assert lugged.model.nbody == smooth.model.nbody
    assert lugged.model.nv == smooth.model.nv
    np.testing.assert_allclose(lugged.model.body_mass, smooth.model.body_mass)
    np.testing.assert_allclose(lugged.model.body_inertia, smooth.model.body_inertia)
    lug_ids = {i for i in range(lugged.model.ngeom)
               if "_lug_" in (mujoco.mj_id2name(lugged.model, mujoco.mjtObj.mjOBJ_GEOM, i) or "")}
    obs, _ = lugged.reset(seed=0, options={"yaw": 0})
    contacted = False
    for _ in range(lugged.max_steps):
        obs, _, terminated, truncated, info = lugged.step(baseline_action(obs))
        contacted |= any(c.geom1 in lug_ids or c.geom2 in lug_ids for c in lugged.data.contact)
        assert np.isfinite(obs).all()
        assert lugged.data.xmat[lugged.base, 8] > 0.9
        if terminated or truncated:
            break
    assert contacted
    assert info["is_success"]
    assert not any(w.number for w in lugged.data.warning)
    smooth.close()
    lugged.close()


def test_contact_options_and_smaller_timestep():
    env = UBotNavigationEnv(wheel_contact="lugs", timestep=0.001)
    assert env.frame_skip == 20
    assert env.dt == pytest.approx(0.02)
    env.close()
    for options in ({"wheel_contact": "bad"}, {"terrain": "bad"}, {"timestep": 0.003}):
        with pytest.raises(ValueError):
            UBotNavigationEnv(**options)
