import gymnasium as gym
import mujoco
import numpy as np
import pytest

from ubot_sim.contact_model import TerrainContact
from ubot_sim.env import UBotNavigationEnv, baseline_action
from ubot_sim.waypoints import UBotWaypointsEnv


@pytest.mark.parametrize("wheel_contact", ["smooth", "lugs"])
def test_concrete_contacts_and_complete_route(wheel_contact):
    with UBotWaypointsEnv(surface="concrete", wheel_contact=wheel_contact) as env:
        obs, _ = env.reset(seed=0, options={"yaw": 0})
        floor = env.model.geom("floor").id
        assert env.model.geom_type[floor] == mujoco.mjtGeom.mjGEOM_PLANE
        contacts = [c for c in env.data.contact if floor in (c.geom1, c.geom2)]
        assert contacts
        for contact in contacts:
            assert contact.dim == 6
            np.testing.assert_allclose(contact.friction, [0.8, 0.8, 0.002, 0.0001, 0.0001])
            np.testing.assert_allclose(contact.solref, [0.01, 1])
        for _ in range(env.max_steps):
            obs, _, terminated, truncated, info = env.step(baseline_action(obs))
            assert np.isfinite(obs).all()
            if terminated or truncated:
                break
        assert info["is_success"] and not info["failed"] and not truncated
        assert info["waypoints_reached"] == 5
        assert sum(int(w.number) for w in env.data.warning) == 0


def test_concrete_gym_randomization_and_default_compatibility():
    with gym.make("UBotNavigation-v0", surface="concrete", randomize=True) as wrapped:
        env = wrapped.unwrapped
        env.reset(seed=9)
        friction = env.model.geom_friction.copy()
        env.reset(seed=10)
        assert not np.array_equal(friction, env.model.geom_friction)
        env.reset(seed=9)
        np.testing.assert_array_equal(friction, env.model.geom_friction)
        assert 0.56 <= env.model.geom("floor").friction[0] <= 1.04
        assert env.model.geom("floor").friction[2] == 0.0001
    with UBotNavigationEnv() as env:
        assert env.model.geom("floor").condim == 4


@pytest.mark.parametrize("options", [
    {"surface": "unknown"},
    {"surface": "concrete", "terrain": "bumps"},
    {"surface": "concrete", "terrain_contact": TerrainContact()},
])
def test_invalid_or_conflicting_surface_options(options):
    with pytest.raises(ValueError):
        UBotNavigationEnv(**options)
