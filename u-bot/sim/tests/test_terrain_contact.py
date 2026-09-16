import numpy as np
import pytest

from ubot_sim.contact_model import TerrainContact
from ubot_sim.env import UBotNavigationEnv


@pytest.mark.parametrize("terrain", ["flat", "bumps"])
@pytest.mark.parametrize("wheel_contact", ["smooth", "lugs"])
@pytest.mark.parametrize("condim", [3, 4, 6])
def test_surface_controls_actual_contacts(terrain, wheel_contact, condim):
    contact = TerrainContact(sliding_friction=0.12, torsional_friction=0.001,
                             rolling_friction=0.00005, condim=condim,
                             time_constant=0.025, damping_ratio=0.8)
    with UBotNavigationEnv(terrain=terrain, wheel_contact=wheel_contact,
                           terrain_contact=contact) as env:
        env.reset(seed=0)
        floor = env.model.geom("floor").id
        # The wheels retain their higher coefficients, so inspecting only the
        # floor's XML would miss the max-friction mixing regression.
        assert env.model.geom("left_tire").friction[0] == pytest.approx(0.8)
        contacts = [c for c in env.data.contact if floor in (c.geom1, c.geom2)]
        assert contacts
        contacted = {g for c in contacts for g in (c.geom1, c.geom2)}
        assert any(env.model.geom(g).name.startswith(("left_contact", "right_contact"))
                   for g in contacted)
        drive_prefix = ("left_lug", "right_lug") if wheel_contact == "lugs" else ("left_tire", "right_tire")
        assert any(env.model.geom(g).name.startswith(drive_prefix) for g in contacted)
        for c in contacts:
            assert c.dim == condim
            np.testing.assert_allclose(c.friction, [0.12, 0.12, 0.001, 0.00005, 0.00005])
            np.testing.assert_allclose(c.solref, [0.025, 0.8])
            np.testing.assert_allclose(c.solimp, [0.9, 0.95, 0.001, 0.5, 2])


def test_surface_randomization_is_seeded_and_does_not_compound():
    with UBotNavigationEnv(randomize=True,
                           terrain_contact=TerrainContact(sliding_friction=0.1)) as env:
        env.reset(seed=9)
        first = env.model.geom_friction.copy()
        env.reset(seed=10)
        assert not np.array_equal(env.model.geom_friction, first)
        env.reset(seed=9)
        np.testing.assert_array_equal(env.model.geom_friction, first)
        floor = env.model.geom("floor").id
        friction = env.model.geom_friction[floor, 0]
        assert 0.07 <= friction <= 0.13
        contacts = [c for c in env.data.contact if floor in (c.geom1, c.geom2)]
        assert contacts
        for c in contacts:
            np.testing.assert_allclose(c.friction[:2], friction)
            np.testing.assert_allclose(c.friction[2:], [0.002, 0.0001, 0.0001])


@pytest.mark.parametrize("options", [
    {"sliding_friction": -0.1}, {"torsional_friction": np.nan},
    {"rolling_friction": np.inf}, {"condim": 5},
    {"time_constant": 0}, {"damping_ratio": -1},
])
def test_invalid_surface_settings(options):
    with pytest.raises(ValueError):
        TerrainContact(**options)
