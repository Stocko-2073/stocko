import gymnasium as gym
import mujoco
import numpy as np
import pytest

from ubot_sim.contact_model import TerrainContact, TerrainPatch
from ubot_sim.env import UBotNavigationEnv, baseline_action
from ubot_sim.waypoints import UBotWaypointsEnv


def wheel_contacts(env, side):
    names = (f"{side}_tire", f"{side}_lug")
    return [c for c in env.data.contact
            if any(env.model.geom(g).name.startswith(names) for g in (c.geom1, c.geom2))]


@pytest.mark.parametrize("wheel_contact", ["smooth", "lugs"])
def test_split_grip_is_applied_to_actual_wheels_and_casters(wheel_contact):
    patch = TerrainPatch((0, 0.5), (2, 0.5))
    contact = TerrainContact(condim=6, rolling_friction=0.0003, time_constant=0.02)
    with UBotNavigationEnv(patches=[patch], terrain_contact=contact,
                           wheel_contact=wheel_contact) as env:
        env.reset(seed=0, options={"yaw": 0})
        for side, grip in [("left", 0.08), ("right", 0.8)]:
            contacts = wheel_contacts(env, side)
            assert contacts
            caster = [c for c in env.data.contact if any(
                env.model.geom(g).name.startswith(f"{side}_contact") for g in (c.geom1, c.geom2))]
            assert caster
            for c in contacts + caster:
                assert c.dim == 6
                np.testing.assert_allclose(c.friction, [grip, grip, 0.002, 0.0003, 0.0003])
                np.testing.assert_allclose(c.solref, [0.02, 1])
        assert env.model.geom("left_tire").friction[0] == 0.8


@pytest.mark.parametrize("wheel_contact", ["smooth", "lugs"])
@pytest.mark.parametrize("timestep", [0.001, 0.002])
def test_drive_crosses_dry_patch_dry_without_a_step(wheel_contact, timestep):
    with UBotNavigationEnv(patches=[TerrainPatch((0.6, 0), (0.2, 1))],
                           wheel_contact=wheel_contact, timestep=timestep) as env:
        env.reset(seed=0, options={"yaw": 0, "goal": [5, 0]})
        grips, heights = [], []
        for _ in range(300):
            obs, _, terminated, truncated, info = env.step([0.45, 0.45])
            assert np.isfinite(obs).all() and not terminated and not truncated, info
            contacts = wheel_contacts(env, "left")
            if contacts:
                grips.append(min(c.friction[0] for c in contacts))
            heights.append(env.data.xpos[env.base, 2])
        assert grips[0] == pytest.approx(0.8)
        assert 0.08 in grips
        assert grips[-1] == pytest.approx(0.8)
        assert env.data.xpos[env.base, 0] > 1.0
        assert np.ptp(heights) < 0.015
        assert not any(w.number for w in env.data.warning)


def test_patch_partition_has_no_overlaps_or_underlying_plane():
    patches = [TerrainPatch((0, 0.5), (1, 0.5)),
               TerrainPatch((0, -0.5), (1, 0.5), sliding_friction=0.2),
               TerrainPatch((3, 2), (0.2, 0.3))]
    with UBotNavigationEnv(patches=patches) as env, UBotNavigationEnv() as baseline:
        np.testing.assert_array_equal(env.model.body_mass, baseline.model.body_mass)
        np.testing.assert_array_equal(env.model.body_inertia, baseline.model.body_inertia)
        assert env.model.njnt == baseline.model.njnt
        ground = [i for i in range(env.model.ngeom)
                  if env.model.geom_bodyid[i] == 0 and env.model.geom_contype[i]]
        rects = []
        for i in ground:
            assert env.model.geom_type[i] == mujoco.mjtGeom.mjGEOM_BOX
            pos, size = env.model.geom_pos[i], env.model.geom_size[i]
            assert pos[2] + size[2] == 0
            rects.append((pos[:2] - size[:2], pos[:2] + size[:2]))
        assert sum(np.prod(hi - lo) for lo, hi in rects) == pytest.approx(16 * 16)
        for i, (lo, hi) in enumerate(rects):
            for other_lo, other_hi in rects[:i]:
                assert not np.all(np.minimum(hi, other_hi) - np.maximum(lo, other_lo) > 1e-12)


def test_patch_randomization_repeats_without_compounding():
    with gym.make("UBotNavigation-v0", surface="concrete", randomize=True,
                  patches=[TerrainPatch((0, 0.5), (2, 0.5))]) as wrapped:
        env = wrapped.unwrapped
        env.reset(seed=9)
        first = env.model.geom_friction.copy()
        env.reset(seed=10)
        assert not np.array_equal(first, env.model.geom_friction)
        env.reset(seed=9)
        np.testing.assert_array_equal(first, env.model.geom_friction)
        ratio = env.model.geom("terrain_patch_0").friction[0] / env.model.geom("floor").friction[0]
        assert ratio == pytest.approx(0.1)
        assert env.model.geom("terrain_patch_0").condim == 6


def test_waypoint_route_crosses_patch_continuously():
    with UBotWaypointsEnv(surface="concrete", patches=[TerrainPatch((0.4, 0), (0.1, 0.4))],
                         waypoints=[[0.8, 0], [0, 0]]) as env:
        obs, _ = env.reset(seed=0, options={"yaw": 0})
        times = []
        touched = False
        patch_id = env.model.geom("terrain_patch_0").id
        for _ in range(env.max_steps):
            obs, _, terminated, truncated, info = env.step(baseline_action(obs))
            touched |= any(patch_id in (c.geom1, c.geom2) for c in env.data.contact)
            if info["waypoint_reached"]:
                times.append(env.data.time)
            if terminated or truncated:
                break
        assert info["is_success"] and touched
        assert len(times) == 2 and times[1] > times[0] > 0
        assert not any(w.number for w in env.data.warning)


@pytest.mark.parametrize("kwargs", [
    {"center": (0, float("nan"))}, {"center": (0,)},
    {"half_size": (0, 1)}, {"half_size": (1, float("inf"))},
    {"sliding_friction": -1}, {"sliding_friction": float("nan")},
    {"center": (8, 0)},
])
def test_invalid_patch_dimensions_and_grip(kwargs):
    with pytest.raises(ValueError):
        TerrainPatch(**({"center": (0, 0), "half_size": (1, 1)} | kwargs))


def test_invalid_patch_combinations():
    patch = TerrainPatch((0, 0), (1, 1))
    with pytest.raises(ValueError, match="overlap"):
        UBotNavigationEnv(patches=[patch, patch])
    with pytest.raises(ValueError, match="flat"):
        UBotNavigationEnv(patches=[patch], terrain="bumps")
    with pytest.raises(TypeError, match="TerrainPatch"):
        UBotNavigationEnv(patches=[None])
