import mujoco
import numpy as np
import pytest

from yaam.model.sg90 import Fixture, Params, build, simulate, simulate_voltage

LIGHT = Fixture(gravity=False)


def frictionless(**kw):
    return Params(coulomb=0.0, static=0.0, viscous=0.0, load_friction=0.0, **kw)


def test_free_speed_is_the_torque_speed_line():
    p = frictionless()
    t = np.arange(0, 0.5, 2.5e-4)
    angle = simulate_voltage(p, LIGHT, t, np.full(len(t), 4.7))
    speed = (angle[-1] - angle[-201]) / (t[-1] - t[-201])
    assert speed == pytest.approx(4.7 / (p.gear_ratio * p.kt), rel=0.01)


def test_nothing_moves_inside_the_dead_band():
    p = Params()
    widths = np.full(25, p.center_us + 0.6 * p.deadband_us)
    out = simulate(p, LIGHT, widths)
    assert not out["drive"].any()
    assert np.abs(out["angle"]).max() < 1e-6


def test_burst_starts_at_pulse_end_plus_latency():
    p = Params()
    widths = np.r_[np.full(5, 1500.0), np.full(10, 1600.0)]
    out = simulate(p, LIGHT, widths, sample_dt=2.5e-4)
    first = out["t"][np.flatnonzero(out["drive"])[0]]
    assert first == pytest.approx(5 * 0.020 + 1600e-6 + p.latency_us * 1e-6, abs=5e-4)


def test_backlash_is_a_dead_band_spring():
    p = Params()
    model, data = build(p, LIGHT)
    out_dof = model.jnt_dofadr[model.joint("output").id]
    out_q = model.jnt_qposadr[model.joint("output").id]
    for deflection, force in [(0.4 * p.backlash, 0.0), (p.backlash / 2 + 0.01, -p.mesh_stiffness * 0.01)]:
        data.qpos[:] = 0
        data.qpos[out_q] = deflection
        mujoco.mj_forward(model, data)
        assert data.qfrc_passive[out_dof] == pytest.approx(force, abs=1e-9)


def test_gear_friction_holds_a_light_load_and_not_a_heavy_one():
    p = Params()
    still = simulate(p, Fixture(), np.zeros(100), theta0=np.radians(20))
    # The gear holds; the horn only drops through its half of the backlash,
    # dipping briefly into the mesh spring as it lands.
    assert np.ptp(still["angle"]) < p.backlash / 2 + np.radians(0.05)
    heavy = Fixture(mass=0.2, com=0.08, inertia=0.2 * 0.08**2 + 1e-5)
    falls = simulate(p, heavy, np.zeros(25), theta0=np.radians(60))
    assert falls["angle"][-1] < np.radians(50)


def test_step_settles_on_target():
    p = Params()
    target = np.radians(30)
    widths = np.full(25, p.reference_us(target))
    out = simulate(p, LIGHT, widths)
    late = out["angle"][out["t"] > 0.3]
    tolerance = p.deadband_us / p.us_per_rad + p.backlash
    assert np.abs(late - target).max() < tolerance


@pytest.mark.parametrize("brake", [False, True])
def test_measured_voltage_reproduces_the_closed_loop(brake):
    p = Params(brake=brake)
    widths = np.r_[np.full(3, 1500.0), np.full(12, p.reference_us(np.radians(40))), np.full(10, 1500.0)]
    out = simulate(p, Fixture(), widths, sample_dt=2.5e-4)
    replay = simulate_voltage(p, Fixture(), out["t"], out["terminal_v"])
    assert np.abs(replay - out["angle"]).max() < np.radians(0.2)
