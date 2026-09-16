import gymnasium as gym
import mujoco
import numpy as np
import pytest

from ubot_sim.contact_model import TerrainContact, TerrainPatch, TerrainRegion, SURFACE_PRESETS
from ubot_sim.env import UBotNavigationEnv, baseline_action
from ubot_sim.waypoints import UBotWaypointsEnv


@pytest.mark.parametrize("wheel_contact", ["smooth", "lugs"])
@pytest.mark.parametrize("timestep", [0.001, 0.002])
def test_grass_route_crosses_all_grips(wheel_contact, timestep):
    with UBotWaypointsEnv(surface="short_grass", wheel_contact=wheel_contact,
                         timestep=timestep, max_steps=2250) as env:
        obs, _ = env.reset(seed=0, options={"yaw": 0})
        grips = set()
        for _ in range(env.max_steps):
            obs, _, terminated, truncated, info = env.step(baseline_action(obs))
            assert np.isfinite(obs).all()
            for c in env.data.contact:
                if any(env.model.geom(g).name.startswith(("left_tire", "right_tire", "left_lug", "right_lug"))
                       for g in (c.geom1, c.geom2)):
                    grips.add(round(float(c.friction[0]), 2))
                    assert c.dim == 6
                    np.testing.assert_allclose(c.friction[2:], [0.002, 0.002, 0.002])
                    np.testing.assert_allclose(c.solref, [0.02, 1])
            if terminated or truncated:
                break
        assert info["is_success"] and not info["failed"] and not truncated
        assert grips == {0.55, 0.65, 0.75}
        assert not any(w.number for w in env.data.warning)


def test_grass_shared_edges_elevation_dynamics_and_randomization():
    with gym.make("UBotNavigation-v0", surface="short_grass", randomize=True) as wrapped, UBotNavigationEnv() as baseline:
        env = wrapped.unwrapped
        np.testing.assert_array_equal(env.model.body_mass, baseline.model.body_mass)
        np.testing.assert_array_equal(env.model.body_inertia, baseline.model.body_inertia)
        assert env.model.njnt == baseline.model.njnt
        assert env.model.nhfield == 9
        assert np.all(env.model.hfield_size[:, 2] == 0.008)
        arrays = {}
        for row in range(3):
            for col in range(3):
                h = env.model.hfield(f"grass_{row}_{col}").id
                nr, nc, offset = env.model.hfield_nrow[h], env.model.hfield_ncol[h], env.model.hfield_adr[h]
                arrays[row, col] = env.model.hfield_data[offset:offset + nr * nc].reshape(nr, nc)
                if row:
                    np.testing.assert_array_equal(arrays[row - 1, col][-1], arrays[row, col][0])
                if col:
                    np.testing.assert_array_equal(arrays[row, col - 1][:, -1], arrays[row, col][:, 0])
        heights = env.model.hfield_data.copy()
        assert 0 <= heights.min() < heights.max() <= 1
        env.reset(seed=9, options={"position": [0.5, 0.7], "goal": [1, 1]})
        friction = env.model.geom_friction.copy()
        env.reset(seed=10)
        assert not np.array_equal(friction, env.model.geom_friction)
        env.reset(seed=9, options={"position": [0.5, 0.7], "goal": [1, 1]})
        np.testing.assert_array_equal(friction, env.model.geom_friction)
        np.testing.assert_array_equal(heights, env.model.hfield_data)
        assert env.terrain_height([0, 0]) == pytest.approx(0)
        assert env.data.mocap_pos[0, 2] == pytest.approx(env.terrain_height([1, 1]) + 0.005)
        # Shared edges have no elevation step, including where four tiles meet.
        for x, y in [(0.5, 0.7), (-0.5, -0.5), (0.5, 0.5)]:
            z = [env.terrain_height([x + dx, y + dy]) for dx in (-1e-7, 1e-7) for dy in (-1e-7, 1e-7)]
            assert max(z) - min(z) < 1e-7
        assert env.terrain_height([3.1, 0]) is None
        assert SURFACE_PRESETS["short_grass"].rolling_friction > SURFACE_PRESETS["concrete"].rolling_friction


@pytest.mark.parametrize("kwargs", [
    {"terrain": "bumps"}, {"terrain_contact": TerrainContact()},
    {"patches": [TerrainPatch((0, 0), (1, 1))]},
    {"regions": [TerrainRegion((0, 0), (1, 1), TerrainContact())]},
])
def test_grass_rejects_conflicting_options(kwargs):
    with pytest.raises(ValueError):
        UBotNavigationEnv(surface="short_grass", **kwargs)
