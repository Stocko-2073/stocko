"""Averaged two-phase stepper model. See MOTOR_MODEL.md for assumptions.

Currents are instantaneous phase amperes; driver settings are RMS amperes.
The ideal current regulator chooses a bridge voltage each integration step,
bounded by the supply. This is not a switching-level SpreadCycle emulator.
"""
from dataclasses import dataclass, replace
import math

import numpy as np


@dataclass(frozen=True)
class DriveConfig:
    driver: str = "tmc2209"
    supply_voltage: float = 12.8
    resistance: float = 2.3       # ohm / phase, motor datasheet
    inductance: float = 0.0044    # H / phase, motor datasheet
    # Two phases at 1.5 A produce 0.45 Nm: sinusoidal model approximation.
    torque_constant: float = 0.45 / (math.sqrt(2) * 1.5)
    rotor_inertia: float = 54e-7  # 54 g cm² -> kg m²
    pole_pairs: int = 50         # 1.8 degree full steps, four per electrical turn
    gear_ratio: float = 40 / 12
    sense_resistance: float = 0.11  # 2209 R110; provisional for 2208 carrier
    run_current_rms: float = 21 * 0.325 / (0.13 * math.sqrt(2) * 32)
    hold_current_rms: float = 10 * 0.325 / (0.13 * math.sqrt(2) * 32)
    # Approximate smooth run-to-hold reduction, not register-exact timing.
    hold_delay: float = 0.5
    hold_ramp: float = 2.0
    max_timestep: float = 0.000025
    slip_protection: bool = True
    slip_limit_steps: float = 200
    microsteps: int = 8

    def __post_init__(self):
        if self.driver not in ("tmc2208", "tmc2209"):
            raise ValueError("driver must be tmc2208 or tmc2209")
        positive = ("supply_voltage", "resistance", "inductance", "torque_constant",
                    "rotor_inertia", "pole_pairs", "gear_ratio", "run_current_rms",
                    "hold_ramp", "max_timestep", "slip_limit_steps", "microsteps")
        for name in positive:
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be finite and positive")
        for name in ("sense_resistance", "hold_current_rms", "hold_delay"):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.hold_current_rms > self.run_current_rms:
            raise ValueError("hold current must not exceed run current")
        if self.max_timestep > 0.0001:
            raise ValueError("stepper integration requires max_timestep <= 100 microseconds")
        upper = 36 if self.driver == "tmc2208" else 29
        if not 4.75 <= self.supply_voltage <= upper:
            raise ValueError(f"{self.driver} supply must be within 4.75–{upper} V")

    @property
    def bridge_resistance(self):
        # Typical high-side plus low-side RDSon at 25 C, chip specifications.
        return 0.57 if self.driver == "tmc2208" else 0.34

    @property
    def phase_resistance(self):
        return self.resistance + self.bridge_resistance + self.sense_resistance


DRIVE_PROFILES = {
    "eiiev_12v": DriveConfig(),
    "talentcell_24v": DriveConfig(driver="tmc2208", supply_voltage=25.6),
}


def drive_config(profile, voltage=None):
    """Resolve an immutable profile, optionally overriding ideal supply voltage."""
    if isinstance(profile, DriveConfig):
        config = profile
    elif isinstance(profile, str) and profile in DRIVE_PROFILES:
        config = DRIVE_PROFILES[profile]
    else:
        raise ValueError(f"drive must be a DriveConfig or one of {tuple(DRIVE_PROFILES)}")
    return config if voltage is None else replace(config, supply_voltage=voltage)


class StepperDrive:
    """Two rigidly geared motors, driven by wheel-speed commands in rad/s.

    MuJoCo owns mechanics. This object owns winding currents and commanded
    position; the rotor position is never reset to follow a motion command.
    """

    def __init__(self, config):
        self.config = config
        self.enabled = True
        self.reset(np.zeros(2))

    def reset(self, wheel_position):
        self.command_position = np.array(wheel_position, dtype=float, copy=True)
        self.origin = self.command_position.copy()
        self.currents = np.zeros((2, 2))
        self.target_currents = np.zeros((2, 2))
        self.phase_voltages = np.zeros((2, 2))
        self.torque = np.zeros(2)
        self.idle_seconds = np.full(2, self.config.hold_delay + self.config.hold_ramp)
        self.slip_reference = np.zeros(2)
        self.slip_steps = np.zeros(2)
        self.slip_fault = np.zeros(2, dtype=bool)
        self._monitor_seconds = 0.0
        self.bus_power = 0.0
        self.copper_power = 0.0
        self.energy_j = 0.0
        self.enabled = True

    def advance(self, wheel_position, wheel_velocity, command, dt):
        """Advance electrical state and return average output torque for dt.

        Disabled mode is ideal freewheel with immediate current removal;
        bridge-diode transients are outside this averaged model.
        """
        c = self.config
        if not math.isfinite(dt) or not 0 < dt <= c.max_timestep * (1 + 1e-9):
            raise ValueError("electrical step must be positive and <= max_timestep")
        position, velocity, command = (np.asarray(v, dtype=float) for v in
                                       (wheel_position, wheel_velocity, command))
        if any(v.shape != (2,) or not np.isfinite(v).all() for v in (position, velocity, command)):
            raise ValueError("positions, velocities and commands must be two finite values")
        if not self.enabled:
            self.currents[:] = self.target_currents[:] = self.phase_voltages[:] = 0
            self.torque[:] = 0
            self.bus_power = self.copper_power = 0.0
            return self.torque.copy()
        if np.any(self.slip_fault):
            command = np.zeros(2)  # both generators stop; energised hold remains
        moving = np.abs(command) > 1e-12
        self.idle_seconds = np.where(moving, 0, self.idle_seconds + dt)
        blend = np.clip((self.idle_seconds - c.hold_delay) / c.hold_ramp, 0, 1)
        amplitude = math.sqrt(2) * (c.run_current_rms + blend *
                                     (c.hold_current_rms - c.run_current_rms))
        electrical_ratio = c.pole_pairs * c.gear_ratio
        # Aim for the end-of-step reference; the integrated mean current then
        # aligns with the midpoint rotor, avoiding a timestep-sized phase lag.
        phase = electrical_ratio * (self.command_position + command * dt)
        rotor_phase = electrical_ratio * (position + velocity * dt / 2)
        self.command_position += command * dt
        self.target_currents = amplitude[:, None] * np.column_stack((np.cos(phase), np.sin(phase)))
        tangent = np.column_stack((-np.sin(rotor_phase), np.cos(rotor_phase)))
        # Reciprocity: sum(e*i) == motor torque * mechanical rotor speed.
        emf = c.torque_constant * c.gear_ratio * velocity[:, None] * tangent
        resistance = c.phase_resistance
        decay = math.exp(-resistance * dt / c.inductance)
        # Exact RL solution for constant voltage and frozen midpoint back EMF.
        requested = emf + resistance * (self.target_currents - decay * self.currents) / (1 - decay)
        self.phase_voltages = np.clip(requested, -c.supply_voltage, c.supply_voltage)
        equilibrium = (self.phase_voltages - emf) / resistance
        offset = self.currents - equilibrium
        mean_decay = (1 - decay) * c.inductance / (resistance * dt)
        average = equilibrium + offset * mean_decay
        mean_square = (equilibrium**2 + 2 * equilibrium * offset * mean_decay
                       + offset**2 * (1 - decay**2) * c.inductance / (2 * resistance * dt))
        self.currents = equilibrium + (self.currents - equilibrium) * decay
        self.torque = c.gear_ratio * c.torque_constant * np.sum(average * tangent, axis=1)
        self.bus_power = float(np.sum(self.phase_voltages * average))
        self.copper_power = float(c.resistance * np.sum(mean_square))
        self.energy_j += self.bus_power * dt
        self._monitor_seconds += dt
        if self._monitor_seconds >= 0.005 - 1e-12:
            # Firmware's 200 Hz high-pass mismatch detector, with ideal 12-bit
            # encoder quantization. Clock error, I2C latency and noise omitted.
            elapsed = self._monitor_seconds
            self._monitor_seconds = 0.0
            encoder = np.rint((position - self.origin) * 4096 / (2 * math.pi))
            steps_per_rad = 4 * c.pole_pairs * c.microsteps * c.gear_ratio / (2 * math.pi)
            raw = ((self.command_position - self.origin) * steps_per_rad
                   - encoder * (steps_per_rad * 2 * math.pi / 4096))
            if not np.any(self.slip_fault):
                self.slip_reference += (raw - self.slip_reference) * elapsed / 1.0
            self.slip_steps = raw - self.slip_reference
            if c.slip_protection:
                self.slip_fault |= np.abs(self.slip_steps) > c.slip_limit_steps
        return self.torque.copy()

    def telemetry(self):
        return {
            "driver": self.config.driver, "supply_voltage": self.config.supply_voltage,
            "phase_current_a": self.currents.tolist(), "wheel_torque_nm": self.torque.tolist(),
            "bus_power_w": self.bus_power, "bus_current_a": self.bus_power / self.config.supply_voltage,
            "winding_copper_power_w": self.copper_power, "net_energy_j": self.energy_j,
            "slip_steps": self.slip_steps.tolist(), "slip_fault": self.slip_fault.tolist(),
        }
