import mujoco
import numpy as np
import pytest

from ubot_sim.contact_model import TerrainContact, TerrainObstacle
from ubot_sim.env import UBotNavigationEnv


@pytest.mark.parametrize("wheel_contact", ["smooth", "lugs"])
@pytest.mark.parametrize("terrain", ["flat", "bumps"])
@pytest.mark.parametrize("kind,size", [
    ("rock", (0.025, 0.23, 0.014)), ("root", (0.014, 0.23)),
    ("seam", (0.01, 0.25, 0.008)), ("edge", (0.06, 0.25, 0.012)),
])
def test_drive_encounters_obstacle(wheel_contact, terrain, kind, size):
    obstacle = TerrainObstacle(kind, (0.5, 0, 0.01), size,
                               contact=TerrainContact(sliding_friction=0.25, time_constant=0.02))
    with UBotNavigationEnv(wheel_contact=wheel_contact, terrain=terrain,
                           obstacles=[obstacle]) as env:
        env.reset(seed=0, options={"yaw": 0, "goal": [3, 0]})
        obstacle_id = env.model.geom("terrain_obstacle_0").id
        assert env.model.geom_bodyid[obstacle_id] == 0
        touched = False
        for _ in range(200):
            obs, _, terminated, truncated, info = env.step([0.3, 0.3])
            assert np.isfinite(obs).all()
            assert not terminated and not truncated, info
            for c in env.data.contact:
                if obstacle_id in (c.geom1, c.geom2):
                    other = c.geom2 if c.geom1 == obstacle_id else c.geom1
                    name = env.model.geom(other).name
                    touched |= "tire" in name or "lug" in name
                    np.testing.assert_allclose(c.friction[:2], 0.25)
                    np.testing.assert_allclose(c.solref, [0.02, 1])
        assert touched, "Drive wheels never contacted the obstacle"
        # Crossing is not guaranteed: getting stuck is a valid obstacle response.
        assert not any(w.number for w in env.data.warning)


def test_obstacle_placement_and_inherited_surface():
    obstacles = [TerrainObstacle("root", (1, 2, 0.1), (0.03, 0.2), yaw=np.pi / 2),
                 TerrainObstacle("edge", (2, 1, 0.02), (0.1, 0.3, 0.02), yaw=np.pi / 4)]
    with UBotNavigationEnv(obstacles=obstacles,
                           terrain_contact=TerrainContact(sliding_friction=0.15)) as env:
        with UBotNavigationEnv() as baseline:
            assert env.model.nbody == baseline.model.nbody
            assert env.model.njnt == baseline.model.njnt
            np.testing.assert_array_equal(env.model.body_mass, baseline.model.body_mass)
            np.testing.assert_array_equal(env.model.body_inertia, baseline.model.body_inertia)
        for i, obstacle in enumerate(obstacles):
            geom = env.model.geom(f"terrain_obstacle_{i}")
            np.testing.assert_allclose(geom.pos, obstacle.position)
            assert geom.friction[0] == pytest.approx(0.15)
        root = env.model.geom("terrain_obstacle_0")
        rotation = np.zeros(9)
        mujoco.mju_quat2Mat(rotation, root.quat)
        np.testing.assert_allclose(np.abs(rotation.reshape(3, 3)[:, 2]), [1, 0, 0], atol=1e-12)


@pytest.mark.parametrize("kind,position,size,yaw", [
    ("bad", (0, 0, 0), (1, 1, 1), 0),
    ("rock", (0, 0), (1, 1, 1), 0),
    ("root", (0, 0, 0), (1, 1, 1), 0),
    ("edge", (0, 0, 0), (1, 0, 1), 0),
    ("seam", (0, 0, 0), (1, 1, np.nan), 0),
    ("root", (0, 0, 0), (0.1, 1), np.inf),
])
def test_invalid_obstacles(kind, position, size, yaw):
    with pytest.raises(ValueError):
        TerrainObstacle(kind, position, size, yaw)
