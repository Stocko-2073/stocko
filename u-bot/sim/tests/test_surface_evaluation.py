import mujoco
import numpy as np
import pytest

from ubot_sim.env import UBotNavigationEnv
from ubot_sim.waypoints import UBotWaypointsEnv
from ubot_sim.surface_evaluation import RouteMetrics, segment_distance, tangential_speed


def test_tracking_uses_finite_segments():
    assert segment_distance(np.array([0.5, 0.3]), [0, 0], [1, 0]) == pytest.approx(0.3)
    assert segment_distance(np.array([1.3, 0.4]), [0, 0], [1, 0]) == pytest.approx(0.5)
    assert segment_distance(np.array([0.3, 0.4]), [0, 0], [0, 0]) == pytest.approx(0.5)


def test_contact_slip_distinguishes_tangent_normal_and_rolling_motion():
    with UBotNavigationEnv(wheel_contact="smooth") as env:
        env.reset(seed=0, options={"yaw": 0})
        wheel = env.model.geom("left_tire").id
        contact = next(c for c in env.data.contact if wheel in (c.geom1, c.geom2))
        body = env.model.geom_bodyid[wheel]
        jac = np.zeros((3, env.model.nv))
        env.data.qvel[:] = 0
        assert tangential_speed(env.model, env.data, contact, body, jac) == 0
        env.data.qvel[:3] = contact.frame[:3]  # 1 m/s normal motion is not slip.
        assert tangential_speed(env.model, env.data, contact, body, jac) < 1e-10
        env.data.qvel[:3] = contact.frame[3:6]
        assert tangential_speed(env.model, env.data, contact, body, jac) == pytest.approx(1)
        env.data.qvel[:] = 0
        env.data.qvel[env.drive_dof[0]] = 2
        wheel_only = jac @ env.data.qvel
        # Translation that cancels wheel rotation at the contact gives no slip.
        env.data.qvel[:3] = -wheel_only
        assert tangential_speed(env.model, env.data, contact, body, jac) < 1e-10


def test_completed_route_measures_stops_and_no_reset():
    with UBotWaypointsEnv(surface="concrete", waypoints=[[0.5, 0], [0, 0]]) as env:
        obs, _ = env.reset(seed=0, options={"yaw": 0})
        metrics = RouteMetrics(env, obs)
        while not metrics.done:
            metrics.step()
        report = metrics.report()
        assert report["is_success"] and report["completion_seconds"] > 0
        assert report["slip_contact_samples"] > report["slip_control_steps"] > 0
        assert 0 <= report["slip_rms_mps"] < 0.5
        assert report["path_length_m"] > 0.7
        assert len(report["stops"]) == 2
        assert report["stops"][1]["arrival_seconds"] > report["stops"][0]["arrival_seconds"]
        for stop in report["stops"]:
            assert stop["goal_error_m"] < 0.12
            assert stop["arrival_speed_mps"] < 0.08
            assert stop["travel_after_command_m"] >= 0
            assert stop["settle_seconds"] > 0
        with pytest.raises(RuntimeError):
            metrics.step()


def test_timeouts_and_no_contact_do_not_become_success_or_zero_slip():
    with UBotWaypointsEnv(max_steps=1) as env:
        obs, _ = env.reset(seed=0, options={"yaw": 0})
        env.data.qpos[2] += 1
        mujoco.mj_forward(env.model, env.data)
        metrics = RouteMetrics(env, obs)
        metrics.step()
        report = metrics.report()
        assert metrics.done and report["truncated"] and not report["is_success"]
        assert report["completion_seconds"] is None
        assert report["slip_rms_mps"] is None and report["slip_contact_samples"] == 0
        assert report["stops"] == []
