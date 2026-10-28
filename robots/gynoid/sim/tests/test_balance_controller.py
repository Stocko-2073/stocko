import mujoco
import numpy as np
import pytest

from sim.balance_controller import PlantedBalanceController
from sim.planted import GynoidPlantedEnv


@pytest.fixture(scope="module")
def controller():
    return PlantedBalanceController.design()


@pytest.mark.parametrize("seed", [1000, 1001])
def test_balances_with_original_bam_contacts_and_action_limits(controller, seed):
    env = GynoidPlantedEnv()
    try:
        env.reset(seed=seed)
        peak_drift = 0
        for _ in range(env.max_steps):
            action = controller.predict(env)
            assert action.shape == (21,) and np.isfinite(action).all()
            assert np.abs(action).max() <= 1
            _, _, terminated, truncated, info = env.step(action)
            peak_drift = max(peak_drift, info["foot_drift_m"])
            assert not terminated, info
        assert truncated and info["success"]
        assert peak_drift < 0.001
        assert info["height"] > env.nominal_height - 0.002
        assert env.model.neq == 2  # Neck closures only, no floor welds.
        assert np.all(env.model.dof_frictionloss[env.dof_ids] > 0)
        assert not env.data.warning.number.any()
        assert not env.data.xfrc_applied.any()
    finally:
        env.close()


def test_controller_round_trip_and_model_guard(controller, tmp_path, monkeypatch):
    path = tmp_path / "controller.npz"
    controller.save(path)
    loaded, config = PlantedBalanceController.load(path)
    env = GynoidPlantedEnv(**config["env_kwargs"])
    try:
        env.reset(seed=1003)
        np.testing.assert_array_equal(loaded.predict(env), controller.predict(env))
        monkeypatch.setattr("sim.balance_controller.model_hash", lambda task: "changed")
        with pytest.raises(ValueError, match="simulation differ"):
            PlantedBalanceController.load(path)
    finally:
        env.close()
