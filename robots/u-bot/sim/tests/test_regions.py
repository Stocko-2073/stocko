"""Contact-material transitions in one continuous episode."""
import gymnasium as gym
import mujoco
import numpy as np
import pytest

from ubot_sim.contact_model import TerrainContact, TerrainPatch, TerrainRegion, SURFACE_PRESETS
from ubot_sim.env import UBotNavigationEnv, baseline_action
from ubot_sim.waypoints import UBotWaypointsEnv

RESISTANT = TerrainContact(sliding_friction=0.8, rolling_friction=0.002,
                           condim=6, time_constant=0.02, damping_ratio=1.2)
SLIPPERY = TerrainContact(sliding_friction=0.12, rolling_friction=0.0001,
                          condim=4, time_constant=0.01)
REGIONS = [TerrainRegion((0.7, 0), (0.2, 0.7), RESISTANT),
           TerrainRegion((1.4, 0), (0.2, 0.7), SLIPPERY)]


def assert_contact(c, settings, grip_scale=1):
    assert c.dim == settings.condim
    np.testing.assert_allclose(c.friction[:3], [settings.sliding_friction * grip_scale] * 2
                               + [settings.torsional_friction])
    # MuJoCo may retain unused friction coefficients for lower-dimensional contacts.
    if c.dim == 6:
        np.testing.assert_allclose(c.friction[3:], [settings.rolling_friction] * 2)
    np.testing.assert_allclose(c.solref, [settings.time_constant, settings.damping_ratio])


@pytest.mark.parametrize("wheel_contact", ["smooth", "lugs"])
@pytest.mark.parametrize("timestep", [0.001, 0.002])
def test_materials_change_in_both_directions_without_reset(wheel_contact, timestep):
    with UBotWaypointsEnv(surface="concrete", regions=REGIONS, waypoints=[[2, 0], [0, 0]],
                         wheel_contact=wheel_contact, timestep=timestep, max_steps=1800) as env:
        obs, _ = env.reset(seed=0, options={"yaw": 0})
        surfaces = {env.model.geom(f"terrain_region_{i}").id: i for i in range(2)}
        seen = [set(), set()]
        arrivals = []
        previous_time = env.data.time
        for _ in range(env.max_steps):
            leg = env.waypoint_index
            obs, _, terminated, truncated, info = env.step(baseline_action(obs))
            assert env.data.time > previous_time
            previous_time = env.data.time
            assert np.isfinite(obs).all() and not info["failed"]
            for c in env.data.contact:
                for g, robot in [(c.geom1, c.geom2), (c.geom2, c.geom1)]:
                    name = env.model.geom(robot).name
                    if not name.startswith(("left_tire", "right_tire", "left_lug", "right_lug")):
                        continue
                    if g in surfaces:
                        index = surfaces[g]
                        seen[leg].add(index)
                        assert_contact(c, REGIONS[index].contact)
                    elif env.model.geom_bodyid[g] == 0:
                        seen[leg].add("base")
                        assert_contact(c, SURFACE_PRESETS["concrete"])
            if info["waypoint_reached"]:
                arrivals.append(env.data.time)
            if terminated or truncated:
                break
        assert info["is_success"] and not truncated
        assert seen == [{"base", 0, 1}, {"base", 0, 1}]
        assert len(arrivals) == 2 and arrivals[1] > arrivals[0]
        assert not any(w.number for w in env.data.warning)


@pytest.mark.parametrize("wheel_contact", ["smooth", "lugs"])
def test_split_materials_apply_to_drive_wheels_and_casters(wheel_contact):
    region = TerrainRegion((0, 0.5), (2, 0.5), RESISTANT)
    with UBotNavigationEnv(surface="concrete", regions=[region], wheel_contact=wheel_contact) as env:
        env.reset(seed=0, options={"yaw": 0})
        for side, settings in [("left", RESISTANT), ("right", SURFACE_PRESETS["concrete"])]:
            for prefix in [(f"{side}_tire", f"{side}_lug"), (f"{side}_contact",)]:
                contacts = [c for c in env.data.contact if any(
                    env.model.geom(g).name.startswith(prefix) for g in (c.geom1, c.geom2))]
                assert contacts
                for c in contacts:
                    assert_contact(c, settings)


def test_regions_and_patches_tile_once_and_randomize_reproducibly():
    patch = TerrainPatch((2, 0), (0.2, 0.7))
    with gym.make("UBotNavigation-v0", surface="concrete", regions=REGIONS,
                  patches=[patch], randomize=True) as wrapped, UBotNavigationEnv() as base:
        env = wrapped.unwrapped
        np.testing.assert_array_equal(env.model.body_mass, base.model.body_mass)
        np.testing.assert_array_equal(env.model.body_inertia, base.model.body_inertia)
        assert env.model.njnt == base.model.njnt
        ground = np.flatnonzero((env.model.geom_bodyid == 0) & (env.model.geom_contype != 0))
        rects = []
        for g in ground:
            assert env.model.geom_type[g] == mujoco.mjtGeom.mjGEOM_BOX
            pos, size = env.model.geom_pos[g], env.model.geom_size[g]
            assert pos[2] + size[2] == 0
            rects.append((pos[:2] - size[:2], pos[:2] + size[:2]))
        assert sum(np.prod(hi - lo) for lo, hi in rects) == pytest.approx(256)
        for i, (lo, hi) in enumerate(rects):
            for other_lo, other_hi in rects[:i]:
                assert not np.all(np.minimum(hi, other_hi) - np.maximum(lo, other_lo) > 1e-12)
        env.reset(seed=9)
        first = env.model.geom_friction.copy()
        env.reset(seed=10)
        assert not np.array_equal(first, env.model.geom_friction)
        env.reset(seed=9)
        np.testing.assert_array_equal(first, env.model.geom_friction)
        scale = env.model.geom("floor").friction[0] / 0.8
        for i, region in enumerate(REGIONS):
            geom = env.model.geom(f"terrain_region_{i}")
            assert geom.friction[0] == pytest.approx(region.contact.sliding_friction * scale)
            assert geom.friction[2] == region.contact.rolling_friction
            np.testing.assert_allclose(geom.solref, [region.contact.time_constant, region.contact.damping_ratio])


def test_region_validation_and_shared_edges():
    with pytest.raises(TypeError, match="contact"):
        TerrainRegion((0, 0), (1, 1), None)
    with pytest.raises(ValueError):
        TerrainRegion((8, 0), (1, 1), RESISTANT)
    with pytest.raises(TypeError, match="TerrainRegion"):
        UBotNavigationEnv(regions=[None])
    region = TerrainRegion((0, 0), (1, 1), RESISTANT)
    with pytest.raises(ValueError, match="overlap"):
        UBotNavigationEnv(regions=[region, region])
    with pytest.raises(ValueError, match="overlap"):
        UBotNavigationEnv(regions=[region], patches=[TerrainPatch((0, 0), (1, 1))])
    for kwargs in ({"terrain": "bumps"}, {"surface": "rough_concrete"}):
        with pytest.raises(ValueError, match="flat"):
            UBotNavigationEnv(regions=[region], **kwargs)
    with UBotNavigationEnv(regions=[region], patches=[TerrainPatch((2, 0), (1, 1))]) as env:
        env.reset(seed=0)
