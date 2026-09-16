import numpy as np
import pytest

from ubot_sim.contact_model import TerrainContact
from ubot_sim.rolling_benchmark import coast_run
from ubot_sim.waypoints import UBotWaypointsEnv


@pytest.mark.parametrize("wheel_contact", ["smooth", "lugs"])
def test_rolling_friction_requires_six_dimensional_contacts(wheel_contact):
    results = []
    for dim, rolling in [(4, 0.0001), (4, 0.01), (6, 0.01)]:
        with UBotWaypointsEnv(wheel_contact=wheel_contact,
                             terrain_contact=TerrainContact(condim=dim, rolling_friction=rolling)) as env:
            gain, bias = env.model.actuator_gainprm.copy(), env.model.actuator_biasprm.copy()
            result = coast_run(env)
            np.testing.assert_array_equal(env.model.actuator_gainprm, gain)
            np.testing.assert_array_equal(env.model.actuator_biasprm, bias)
            assert result["finite"] and result["warning_count"] == 0
            assert result["contact_dimensions"] == [dim]
            results.append(result)
    # At condim=4 the rolling coefficient must have no physical effect.
    assert results[0]["path_length_3s_m"] == pytest.approx(results[1]["path_length_3s_m"], abs=1e-10)
    # With motors disabled, rolling friction materially shortens coast travel.
    assert results[2]["path_length_3s_m"] < results[0]["path_length_3s_m"] * 0.5
