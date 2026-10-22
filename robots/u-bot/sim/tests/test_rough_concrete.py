import gymnasium as gym
import mujoco
import numpy as np
import pytest

from ubot_sim.contact_model import TerrainContact, TerrainObstacle, TerrainPatch
from ubot_sim.env import UBotNavigationEnv, baseline_action
from ubot_sim.waypoints import UBotWaypointsEnv


@pytest.mark.parametrize("wheel_contact", ["smooth", "lugs"])
@pytest.mark.parametrize("timestep", [0.001, 0.002])
def test_rough_route_contacts_all_features_and_completes(wheel_contact, timestep):
    with UBotWaypointsEnv(surface="rough_concrete", wheel_contact=wheel_contact,
                         timestep=timestep, max_steps=2250) as env:
        obs, _ = env.reset(seed=0, options={"yaw": 0})
        floor = env.model.geom("floor").id
        assert env.model.geom_type[floor] == mujoco.mjtGeom.mjGEOM_HFIELD
        features = {env.model.geom(f"surface_obstacle_{i}").id for i in range(3)}
        touched = set()
        for _ in range(env.max_steps):
            obs, _, terminated, truncated, info = env.step(baseline_action(obs))
            assert np.isfinite(obs).all()
            for c in env.data.contact:
                pair = {c.geom1, c.geom2}
                if pair & features:
                    # Require a drive-wheel encounter, not just incidental
                    # chassis/caster contact near a route feature.
                    if any(env.model.geom(g).name.startswith(
                        ("left_tire", "right_tire", "left_lug", "right_lug")) for g in pair):
                        touched |= pair & features
                if pair & (features | {floor}):
                    assert c.dim == 6
                    np.testing.assert_allclose(c.friction, [0.8, 0.8, 0.002, 0.0001, 0.0001])
                    np.testing.assert_allclose(c.solref, [0.01, 1])
            if terminated or truncated:
                break
        assert touched == features
        assert info["is_success"] and not info["failed"] and not truncated
        assert info["waypoints_reached"] == 5
        assert not any(w.number for w in env.data.warning)


def test_rough_geometry_is_fixed_and_preserves_robot_dynamics():
    extra = TerrainObstacle("rock", (2, 2, 0.01), (0.02, 0.02, 0.02))
    with gym.make("UBotNavigation-v0", surface="rough_concrete", randomize=True,
                  obstacles=[extra]) as wrapped, UBotNavigationEnv() as baseline:
        env = wrapped.unwrapped
        np.testing.assert_array_equal(env.model.body_mass, baseline.model.body_mass)
        np.testing.assert_array_equal(env.model.body_inertia, baseline.model.body_inertia)
        assert env.model.njnt == baseline.model.njnt
        np.testing.assert_allclose(env.model.geom("terrain_obstacle_0").pos, extra.position)
        np.testing.assert_array_equal(env.model.hfield_nrow, [257])
        np.testing.assert_array_equal(env.model.hfield_ncol, [257])
        np.testing.assert_allclose(env.model.hfield_size[0], [3, 3, 0.004, 0.1])
        heights = env.model.hfield_data.copy()
        assert 0 <= heights.min() < heights.max() <= 1
        x, y = np.meshgrid(np.linspace(-3, 3, 257), np.linspace(-3, 3, 257))
        assert not heights.reshape(257, 257)[np.hypot(x, y) < 0.3].any()
        tops = [env.model.geom(f"surface_obstacle_{i}").pos[2]
                + env.model.geom(f"surface_obstacle_{i}").size[2] for i in range(3)]
        np.testing.assert_allclose(tops, [0.004, 0.008, 0.004])
        env.reset(seed=9)
        friction = env.model.geom_friction.copy()
        env.reset(seed=10)
        assert not np.array_equal(friction, env.model.geom_friction)
        env.reset(seed=9)
        np.testing.assert_array_equal(friction, env.model.geom_friction)
        np.testing.assert_array_equal(heights, env.model.hfield_data)


@pytest.mark.parametrize("options", [
    {"terrain": "bumps"}, {"terrain_contact": TerrainContact()},
    {"patches": [TerrainPatch((0, 0), (1, 1))]},
])
def test_rough_preset_rejects_conflicting_geometry_or_contact(options):
    with pytest.raises(ValueError):
        UBotNavigationEnv(surface="rough_concrete", **options)
