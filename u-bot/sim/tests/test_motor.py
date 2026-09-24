from dataclasses import replace
import math

import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env

from ubot_sim.env import UBotNavigationEnv
from ubot_sim.motor import DRIVE_PROFILES, DriveConfig, StepperDrive, drive_config


def synchronous_torque(config, tps, dt=0.000025):
    """Prescribed rotor speed, 90 degree electrical load angle, no fault latch."""
    config = replace(config, slip_protection=False, hold_current_rms=config.run_current_rms)
    motor = StepperDrive(config)
    delta = math.copysign(math.pi, tps or 1) / (2 * config.pole_pairs * config.gear_ratio)
    motor.reset([delta, delta])
    speed = tps * 2 * math.pi
    torques = []
    # Whole electrical periods avoid phase-dependent averaging bias.
    duration = 0.05 if not tps else max(0.05, 8 / (config.pole_pairs * config.gear_ratio * abs(tps)))
    count = math.ceil(duration / dt)
    for n in range(2 * count):
        torque = motor.advance([speed * n * dt] * 2, [speed] * 2, [speed] * 2, dt)
        if n >= count:
            torques.append(torque[0])
    return float(np.mean(torques))


def test_current_limited_holding_torque_and_rms_convention():
    for voltage in (12.8, 25.6):
        c = DriveConfig(driver="tmc2208", supply_voltage=voltage,
                        run_current_rms=1.5, hold_current_rms=1.5)
        assert synchronous_torque(c, 0) == pytest.approx(0.45 * c.gear_ratio, rel=1e-6)


def test_voltage_preserves_high_speed_torque_and_direction():
    low, high = (DRIVE_PROFILES[key] for key in ("eiiev_12v", "talentcell_24v"))
    assert synchronous_torque(low, 0.3) == pytest.approx(synchronous_torque(high, 0.3), rel=0.01)
    t_low, t_high = synchronous_torque(low, 2), synchronous_torque(high, 2)
    assert t_high > 1.4 * t_low > 0
    # Halving dt should leave a resolved electromagnetic solution, not change
    # the voltage advantage through numerical damping.
    assert synchronous_torque(low, 2, 0.0000125) == pytest.approx(t_low, rel=0.03)
    assert synchronous_torque(high, 2, 0.0000125) == pytest.approx(t_high, rel=0.03)
    assert synchronous_torque(low, -2) == pytest.approx(-t_low, rel=0.01)
    twelve = replace(high, supply_voltage=12)
    assert synchronous_torque(twelve, 3, 0.0000125) == pytest.approx(synchronous_torque(twelve, 3), rel=0.03)


def test_rl_transient_energy_and_voltage_bound():
    c = DriveConfig(hold_current_rms=1.0, slip_protection=False)
    m = StepperDrive(c)
    dt = c.max_timestep
    winding_heat = 0
    for _ in range(100):
        m.advance([0, 0], [0, 0], [0, 0], dt)
        assert np.max(np.abs(m.phase_voltages)) <= c.supply_voltage
        winding_heat += m.copper_power * dt
    magnetic_energy = 0.5 * c.inductance * np.sum(m.currents**2)
    resistive_energy = winding_heat * c.phase_resistance / c.resistance
    assert m.energy_j == pytest.approx(magnetic_energy + resistive_energy, rel=1e-9)
    np.testing.assert_allclose(m.currents[:, 0], math.sqrt(2), atol=1e-8)
    np.testing.assert_allclose(m.currents[:, 1], 0, atol=1e-8)


def test_stalled_rotor_can_lose_synchronism_and_fault_both_commands():
    m = StepperDrive(DriveConfig())
    dt = m.config.max_timestep
    for _ in range(round(0.4 / dt)):
        m.advance([0, 0], [0, 0], [2, 0], dt)
    assert m.slip_fault.tolist() == [True, False]
    stopped_command = m.command_position.copy()
    for _ in range(100):
        m.advance([0, 0], [0, 0], [2, 2], dt)
    np.testing.assert_array_equal(m.command_position, stopped_command)
    assert np.linalg.norm(m.currents) > 0  # fault holds, not freewheel
    m.enabled = False
    np.testing.assert_array_equal(m.advance([0, 0], [0, 0], [2, 2], dt), [0, 0])
    assert m.bus_power == 0
    m.reset([0.2, -0.3])
    assert not m.slip_fault.any()
    assert m.energy_j == 0


def test_run_to_hold_reduction_and_restart():
    c = DriveConfig(hold_delay=0.002, hold_ramp=0.004, slip_protection=False)
    m = StepperDrive(c)
    dt = c.max_timestep
    m.advance([0, 0], [0, 0], [0.1, -0.1], dt)
    for _ in range(round(0.02 / dt)):
        m.advance([0, 0], [0, 0], [0, 0], dt)
    np.testing.assert_allclose(np.linalg.norm(m.currents, axis=1), math.sqrt(2) * c.hold_current_rms)
    m.advance([0, 0], [0, 0], [0.1, -0.1], dt)
    np.testing.assert_allclose(np.linalg.norm(m.target_currents, axis=1), math.sqrt(2) * c.run_current_rms)


@pytest.mark.parametrize("profile", list(DRIVE_PROFILES))
def test_stepper_env_contract_reset_and_gentle_motion(profile):
    with UBotNavigationEnv(drive=profile, wheel_contact="smooth") as env:
        check_env(env, skip_render_check=True)
        first, _ = env.reset(seed=0, options={"yaw": 0, "goal": [3, 0]})
        assert env.model.opt.timestep <= 0.0001
        start = env.data.xpos[env.base, 0]
        for n in range(50):
            obs, _, done, _, info = env.step([min(0.3, (n + 1) * 0.01)] * 2)
            assert np.isfinite(obs).all()
            assert not done, info
        assert env.data.xpos[env.base, 0] - start > 0.1
        assert not any(w.number for w in env.data.warning)
        second, reset_info = env.reset(seed=0, options={"yaw": 0, "goal": [3, 0]})
        np.testing.assert_array_equal(first, second)
        assert reset_info["motor"]["net_energy_j"] == 0
        assert not any(reset_info["motor"]["slip_fault"])


def test_invalid_configuration():
    for kwargs in ({"supply_voltage": 29.2}, {"inductance": 0},
                   {"hold_current_rms": 2}, {"max_timestep": 0.002},
                   {"driver": "unknown"}, {"supply_voltage": float("nan")}):
        with pytest.raises(ValueError):
            DriveConfig(**kwargs)
    assert drive_config("talentcell_24v", 29.2).supply_voltage == 29.2
    with pytest.raises(ValueError):
        drive_config("unknown")
    with pytest.raises(ValueError):
        UBotNavigationEnv(supply_voltage=12)
