"""Terrain-relative placement and termination regressions."""
import mujoco
import numpy as np
import pytest

from ubot_sim.contact_model import TerrainObstacle
from ubot_sim.env import UBotNavigationEnv, baseline_action
from ubot_sim.waypoints import UBotWaypointsEnv


@pytest.mark.parametrize("wheel", ["smooth", "lugs"])
@pytest.mark.parametrize("timestep", [0.001, 0.002])
def test_raised_platform_route(wheel, timestep):
    platform = TerrainObstacle("edge", (0, 0, 0.15), (1.5, 1, 0.15))
    env = UBotWaypointsEnv(waypoints=[[0.5, 0], [0, 0]], obstacles=[platform],
                           wheel_contact=wheel, timestep=timestep)
    try:
        obs, _ = env.reset(seed=0, options={"yaw": 0})
        assert env.data.xpos[env.base, 2] > 0.39
        assert env.data.mocap_pos[0, 2] == pytest.approx(0.305)
        assert env.terrain_height([0, 0]) == pytest.approx(0.3)
        for _ in range(env.max_steps):
            obs, _, terminated, truncated, info = env.step(baseline_action(obs))
            assert not info["failed"]
            assert env.data.mocap_pos[0, 2] == pytest.approx(0.305)
            if terminated or truncated:
                break
        assert info["is_success"]
        assert sum(w.number for w in env.data.warning) == 0
    finally:
        env.close()


@pytest.mark.parametrize("terrain", ["bumps", "rough_concrete"])
def test_heightfield_spawn_and_marker(terrain):
    kwargs = {"surface": terrain} if terrain == "rough_concrete" else {"terrain": terrain}
    env = UBotNavigationEnv(**kwargs)
    try:
        env.reset(seed=1, options={"position": [1.6, 1.5], "goal": [1.7, 1.5], "yaw": 0.7})
        height = env.terrain_height(env.goal)
        assert 0 < height < (0.004 if terrain == "rough_concrete" else 0.012)
        assert env.data.mocap_pos[0, 2] == pytest.approx(height + 0.005)
        assert env.data.xpos[env.base, 2] > height + 0.09
        assert np.isfinite(env.step([0, 0])[0]).all()
        assert env.terrain_height([3.2, 0]) is None
        with pytest.raises(ValueError, match="spawn position"):
            env.reset(options={"position": [3.2, 0], "goal": [0, 0]})
        with pytest.raises(ValueError, match="goal position"):
            env.reset(options={"goal": [3.2, 0]})
    finally:
        env.close()


def test_relative_failure_and_missing_ground():
    env = UBotNavigationEnv(terrain="bumps")
    try:
        # Translate the entire surface down: a healthy robot below world Z=0
        # must remain healthy, while insufficient relative clearance must fail.
        env.model.geom_pos[env.model.geom("floor").id, 2] = -0.2
        env.reset(seed=0)
        assert not env.step([0, 0])[4]["failed"]
        env.data.qpos[0] = 3.2
        mujoco.mj_forward(env.model, env.data)
        assert env.step([0, 0])[4]["failed"]
        env.reset(seed=0)
        # Disable contacts so the solver cannot eject a deliberately sunk robot.
        env.model.geom_contype[:] = 0
        env.model.geom_conaffinity[:] = 0
        env.data.qpos[2] = -0.17
        mujoco.mj_forward(env.model, env.data)
        assert env.step([0, 0])[4]["failed"]
    finally:
        env.close()


def test_thin_obstacle_lifts_footprint_and_goal_switches_height():
    obstacle = TerrainObstacle("seam", (0, 0.15, 0.1), (0.001, 0.02, 0.1))
    env = UBotWaypointsEnv(waypoints=[[0, 0], [0, 0.15]], obstacles=[obstacle])
    try:
        mujoco.mj_forward(env.model, env.data)
        assert env.elevation.spawn_lift(env.data) > 0.19
        # Exercise waypoint bookkeeping without the obstructed spawn settling.
        env.goal = np.array([0., 0.])
        env.previous_distance = 0
        env.success_steps = 14
        _, _, _, _, info = env.step([0, 0])
        assert info["waypoint_reached"]
        assert env.data.mocap_pos[0, 2] == pytest.approx(0.205)
    finally:
        env.close()
