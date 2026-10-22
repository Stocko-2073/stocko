import mujoco
import numpy as np
import pytest

from ubot_sim.canopy import GrassCanopy, CanopyVisual
from ubot_sim.env import UBotNavigationEnv


def test_canopy_is_separate_from_ground_and_robot_geometry():
    with UBotNavigationEnv(surface="short_grass") as env, UBotNavigationEnv(surface="short_grass", grass_canopy=False) as bare:
        env.reset(seed=0, options={"yaw": 0})
        bare.reset(seed=0, options={"yaw": 0})
        assert env.canopy.settings.height == 0.05
        for name in ("hfield_data", "geom_size", "body_mass", "body_inertia"):
            np.testing.assert_array_equal(getattr(env.model, name), getattr(bare.model, name))
        assert env.model.ngeom == bare.model.ngeom and env.model.nv == bare.model.nv
        assert env.terrain_height([0, 0]) == bare.terrain_height([0, 0]) == 0
        assert env.data.xpos[env.base, 2] < 0.12


def test_drag_is_passive_zero_at_rest_and_absent_above_canopy():
    with UBotNavigationEnv(surface="short_grass") as env:
        env.reset(seed=0, options={"yaw": 0})
        rng = np.random.default_rng(4)
        for _ in range(20):
            env.data.qvel[:] = rng.normal(size=env.model.nv)
            mujoco.mj_forward(env.model, env.data)
            force = env.canopy.forces(env.data)
            assert force @ env.data.qvel <= 1e-10
            assert force[2] == pytest.approx(0)  # No vertical grass support.
            assert env.canopy.power == pytest.approx(force @ env.data.qvel)
        env.data.qvel[:] = 0
        np.testing.assert_array_equal(env.canopy.forces(env.data), 0)
        env.data.qvel[0] = 0.3
        assert np.linalg.norm(env.canopy.forces(env.data)) > 0
        env.data.qpos[2] += 0.1
        mujoco.mj_forward(env.model, env.data)
        np.testing.assert_array_equal(env.canopy.forces(env.data), 0)
        env.data.qpos[2] = -1  # A buried wheel is outside the above-soil canopy.
        mujoco.mj_forward(env.model, env.data)
        np.testing.assert_array_equal(env.canopy.forces(env.data), 0)
        env.data.qpos[2] = 0.1085
        env.data.qpos[0] = 4
        mujoco.mj_forward(env.model, env.data)
        np.testing.assert_array_equal(env.canopy.forces(env.data), 0)


@pytest.mark.parametrize("timestep", [0.001, 0.002])
def test_zero_strength_matches_disabled_and_external_forces_survive(timestep):
    with UBotNavigationEnv(surface="short_grass", timestep=timestep, grass_canopy=GrassCanopy(resistance=0)) as zero, \
         UBotNavigationEnv(surface="short_grass", timestep=timestep, grass_canopy=False) as bare:
        for env in (zero, bare):
            env.reset(seed=0, options={"yaw": 0})
            env.data.qfrc_applied[0] = 0.1
        for _ in range(30):
            zero.step([0.4, 0.4])
            bare.step([0.4, 0.4])
        np.testing.assert_allclose(zero.data.qpos, bare.data.qpos, atol=1e-10)
        np.testing.assert_allclose(zero.data.qfrc_applied, bare.data.qfrc_applied, atol=1e-12)
    with UBotNavigationEnv(surface="short_grass") as env:
        env.reset(seed=0)
        env.data.qfrc_applied[0] = 0.1
        saved = env.data.qfrc_applied.copy()
        env.step([0.5, 0.5])
        np.testing.assert_allclose(env.data.qfrc_applied, saved, atol=1e-12)


def test_blades_bend_recover_and_do_not_change_physics():
    with UBotNavigationEnv(surface="short_grass") as visible, UBotNavigationEnv(surface="short_grass") as hidden:
        for env in (visible, hidden):
            env.reset(seed=0, options={"yaw": 0})
        visible.canopy.visual = CanopyVisual(visible.canopy)
        for _ in range(50):
            visible.step([0.5, 0.5])
            hidden.step([0.5, 0.5])
        np.testing.assert_array_equal(visible.data.qpos, hidden.data.qpos)
        visual = visible.canopy.visual
        maximum = np.max(np.linalg.norm(visual.bend, axis=1))
        assert maximum > 0.02
        visible.data.qpos[2] += 1
        mujoco.mj_forward(visible.model, visible.data)
        visible.data.time += 3
        visual.update(visible.data)
        assert np.max(np.linalg.norm(visual.bend, axis=1)) == pytest.approx(maximum * np.exp(-2))
        visible.reset(seed=0)
        assert not visual.bend.any()


@pytest.mark.parametrize("kwargs", [{"height": 0}, {"resistance": -1}, {"height": float("nan")},
                                    {"transition_speed": 0}, {"recovery_seconds": 0}])
def test_invalid_parameters(kwargs):
    with pytest.raises(ValueError):
        GrassCanopy(**kwargs)


def test_invalid_surface_and_canopy_type():
    with pytest.raises(ValueError, match="short_grass"):
        UBotNavigationEnv(grass_canopy=GrassCanopy())
    with pytest.raises(TypeError, match="grass_canopy"):
        UBotNavigationEnv(surface="short_grass", grass_canopy=True)


@pytest.mark.parametrize("wheel", ["smooth", "lugs"])
@pytest.mark.parametrize("timestep", [0.001, 0.002])
def test_canopy_reduces_powered_speed_and_passive_coasting(wheel, timestep):
    from ubot_sim.rolling_benchmark import coast_run
    results = []
    for canopy in (False, None):
        with UBotNavigationEnv(surface="short_grass", wheel_contact=wheel,
                               timestep=timestep, grass_canopy=canopy) as env:
            results.append(coast_run(env))
            assert results[-1]["finite"] and results[-1]["warning_count"] == 0
            assert results[-1]["contact_dimensions"] == [6]
    assert results[1]["entry_speed_mps"] < results[0]["entry_speed_mps"] * 0.95
    assert results[1]["path_length_3s_m"] < results[0]["path_length_3s_m"] * 0.8


@pytest.mark.parametrize('density', [0, 4000, 20000, 36000])
@pytest.mark.parametrize('blades', [1, 3])
def test_density_scales_drag_without_injecting_energy(density, blades):
    from dataclasses import replace
    with UBotNavigationEnv(surface='short_grass') as env:
        env.reset(seed=0, options={'yaw': 0})
        env.data.qvel[:] = np.random.default_rng(6).normal(size=env.model.nv)
        mujoco.mj_forward(env.model, env.data)
        original = env.canopy.forces(env.data).copy()
        env.canopy.settings = replace(env.canopy.settings, shoot_density=density, blades_per_shoot=blades)
        force = env.canopy.forces(env.data)
        np.testing.assert_allclose(force, original * density * blades / 60000, atol=1e-12)
        assert force @ env.data.qvel <= 0


@pytest.mark.parametrize('kwargs', [{'shoot_density': -1}, {'shoot_density': float('nan')},
                                   {'shoot_density': 100001}, {'blades_per_shoot': 0},
                                   {'blades_per_shoot': 2.5}])
def test_invalid_density_parameters(kwargs):
    with pytest.raises(ValueError):
        GrassCanopy(**kwargs)


def test_density_visual_counts_budget_and_physics_independence():
    from ubot_sim.canopy import DensityCanopyVisual
    settings = GrassCanopy(shoot_density=20000)
    with UBotNavigationEnv(surface='short_grass', grass_canopy=settings) as visible, \
         UBotNavigationEnv(surface='short_grass', grass_canopy=settings) as hidden:
        for env in (visible, hidden):
            env.reset(seed=0, options={'yaw': 0})
        visual = DensityCanopyVisual(visible.canopy)
        visible.canopy.visual = visual
        assert visual.realized_shoot_density == pytest.approx(20000, rel=0.002)
        count = np.sum(np.all(np.abs(visual.roots[:, :2]) < 0.25, axis=1))
        assert count / 0.25 == pytest.approx(20000, rel=0.02)
        scene = mujoco.MjvScene(visible.model, maxgeom=1000)
        visual.draw(scene, visible.data, visible.data.geom_xpos[visible.canopy.geoms[0]])
        assert scene.ngeom == 999
        assert visual.drawn_shoots == 333
        for _ in range(10):
            visible.step([0.5, 0.5])
            hidden.step([0.5, 0.5])
        np.testing.assert_array_equal(visible.data.qpos, hidden.data.qpos)
        maximum = np.max(np.linalg.norm(visual.bend, axis=1))
        assert maximum > 0
        scene.ngeom = 0
        visual.draw(scene, visible.data, visible.data.geom_xpos[visible.canopy.geoms[0]])
        assert all(2 * g.size[2] == pytest.approx(0.05) for g in scene.geoms[:scene.ngeom])
        visible.data.qpos[2] += 1
        mujoco.mj_forward(visible.model, visible.data)
        visible.data.time += 3
        visual.update(visible.data)
        assert np.max(np.linalg.norm(visual.bend, axis=1)) == pytest.approx(maximum * np.exp(-2))
        visible.reset(seed=0)
        assert not visual.bend.any()


def test_zero_density_has_no_blades():
    from ubot_sim.canopy import DensityCanopyVisual
    with UBotNavigationEnv(surface='short_grass', grass_canopy=GrassCanopy(shoot_density=0)) as env:
        env.reset(seed=0)
        visual = DensityCanopyVisual(env.canopy)
        scene = mujoco.MjvScene(env.model, maxgeom=10)
        visual.draw(scene, env.data, [0, 0])
        assert scene.ngeom == 0
