"""Dynamixel XL330-M288-T servos as BAM models them, for mjlab on MuJoCo Warp.

Every physics step, for each servo: the firmware P controller turns the error
between goal and encoder, both in whole ticks, into a PWM duty; the firmware
current limiter narrows the duty; the bus voltage times the duty drives a DC
motor with back-EMF. Friction is BAM's M6 budget, written into MuJoCo's per-DOF
frictionloss and damping so the constraint solver handles stiction. One battery
feeds every servo, so their supply current sags the voltage they all see.

The servo telemetry the MCU reads back (position, velocity, current, PWM, input
voltage) is kept for a few physics steps, so observations can be read with the
bus and link latency, quantized to the servo's register units. The XL330
measures current at its power input, not the motor, so Present Current is
modelled as duty times motor current; check that, and its sign, on the bench.
When the link stalls the MCU keeps sending the last goal, which `stall` holds.

BAM: Duclusaud, Passault, Padois and Ly, "Extended Friction Models for the
Physics Simulation of Servo Actuators", ICRA 2025. Parameters and the reference
implementation are better-actuator-models 1.0.2 (Apache-2.0); this follows its
CPU model, bam.model.Model.compute_frictions, term for term.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import TYPE_CHECKING

from bam.model import load_model
import mujoco
import mujoco_warp as mjwarp
import torch

from mjlab.actuator.actuator import Actuator, ActuatorCfg, ActuatorCmd

if TYPE_CHECKING:
    from mjlab.entity import Entity

# Register units from the XL330-M288-T control table.
TICK = 2 * math.pi / 4096  # rad per position tick
VELOCITY_LSB = 0.229 * 2 * math.pi / 60  # rad/s per Present Velocity unit
CURRENT_LSB = 0.001  # A per Present Current unit
PWM_LIMIT = 885  # Present PWM at 100% duty
VOLTAGE_LSB = 0.1  # V per Present Input Voltage unit
# MuJoCo Warp has no noslip solver, so a soft joint-friction constraint lets a held
# joint creep. BAM stiffens it with these direct-form values (stiffness, damping).
FRICTION_SOLREF = (-5.0e4, -2.0e2)
FRICTION_SOLIMP = (0.99, 0.9999, 0.001, 0.5, 2.0)
FRICTION_DOF = int(mujoco.mjtConstraint.mjCNSTR_FRICTION_DOF)


@dataclass(frozen=True)
class Bam:
    """Identified XL330 M6 parameters and the firmware constants BAM uses."""

    kt: float
    resistance: float
    armature: float
    friction_base: float
    friction_stribeck: float
    load_motor: float
    load_external: float
    load_motor_stribeck: float
    load_external_stribeck: float
    load_motor_quad: float
    load_external_quad: float
    stribeck_velocity: float
    stribeck_alpha: float
    viscous: float
    error_gain: float  # duty per rad per unit of firmware Kp
    max_pwm: float
    max_current: float

    @classmethod
    def load(cls) -> Bam:
        model = load_model(motor_name="xl330", model="m6")
        actuator = model.actuator
        return cls(model.kt.value, model.R.value, model.armature.value, model.friction_base.value,
                   model.friction_stribeck.value, model.load_friction_motor.value,
                   model.load_friction_external.value, model.load_friction_motor_stribeck.value,
                   model.load_friction_external_stribeck.value, model.load_friction_motor_quad.value,
                   model.load_friction_external_quad.value, model.dtheta_stribeck.value, model.alpha.value,
                   model.friction_viscous.value, actuator.error_gain, actuator.max_pwm, actuator.max_current)


def motor(error_ticks, velocity, vin, kp, kt, resistance, error_gain, max_pwm, max_current):
    """Firmware P control, current limiter and DC motor. Returns duty, current (A), torque (Nm).

    The limiter can only bound the duty: it keeps (duty*vin - kt*w)/R within the
    current limit when the voltage allows, then the duty is clipped to max_pwm.
    """
    duty = error_ticks * TICK * kp * error_gain
    centre, span = kt * velocity / vin, resistance * max_current / vin
    duty = torch.clamp(torch.clamp(duty, centre - span, centre + span), -max_pwm, max_pwm)
    current = (duty * vin - kt * velocity) / resistance
    return duty, current, kt * current


def friction_budget(bam: Bam, motor_torque, external_torque, velocity):
    """BAM M6 dry-friction budget (Nm), as bam.model.Model.compute_frictions."""
    gearbox = torch.abs(external_torque * bam.load_external - motor_torque * bam.load_motor)
    gearbox_stribeck = torch.abs(external_torque * bam.load_external_stribeck
                                 - motor_torque * bam.load_motor_stribeck)
    stribeck = torch.exp(-torch.abs(velocity / bam.stribeck_velocity) ** bam.stribeck_alpha)
    driving = (torch.abs(external_torque) < torch.abs(motor_torque)).to(motor_torque.dtype)
    driven = (torch.abs(external_torque) > torch.abs(motor_torque)).to(motor_torque.dtype)
    opposed = (torch.sign(external_torque) != torch.sign(motor_torque)).to(motor_torque.dtype)
    quadratic = (driving * bam.load_external_quad * external_torque ** 2
                 + driven * bam.load_motor_quad * motor_torque ** 2) * opposed
    return (bam.friction_base + gearbox + stribeck * (bam.friction_stribeck + gearbox_stribeck + quadratic))


@dataclass(kw_only=True)
class Xl330ActuatorCfg(ActuatorCfg):
    """XL330 servos on one bus and one battery.

    kp is the firmware Position P Gain register (default 400). The supply is a
    battery of open-circuit voltage supply_voltage behind supply_resistance
    (cells, wiring and connectors); idle_current is drawn whatever the motors do.
    """

    kp: float = 400.0
    quantize: bool = True  # goal and encoder in whole ticks, as the firmware sees them
    current_sensing: str = "input"  # "input": duty * motor current, as the XL330 measures; or "motor"
    supply_voltage: float = 7.4  # 2S Li-ion, nominal
    supply_resistance: float = 0.15
    idle_current: float = 0.4
    telemetry_steps: int = 16
    compile: bool = True  # on CUDA, fuse each physics step's ~100 small kernels into a few

    def build(self, entity: Entity, target_ids: list[int], target_names: list[str]) -> Xl330Actuator:
        return Xl330Actuator(self, entity, target_ids, target_names)


class Xl330Actuator(Actuator[Xl330ActuatorCfg]):
    """BAM XL330 servos vectorized over (envs, servos), with a shared battery.

    Per-servo parameters (kt, resistance, kp, friction scales, error gain, current
    limit) and per-env supply parameters are tensors that domain randomization
    writes directly. dof_frictionloss and dof_damping must be expanded per world;
    phone_girl.robot requests that with a startup event.
    """

    def __init__(self, cfg, entity, target_ids, target_names):
        super().__init__(cfg, entity, target_ids, target_names)
        self.bam = Bam.load()

    def edit_spec(self, spec: mujoco.MjSpec, target_names: list[str]) -> None:
        existing = {a.target: a for a in spec.actuators}
        for name in target_names:
            actuator = existing.get(name) or spec.add_actuator(name=name, target=name,
                                                               trntype=mujoco.mjtTrn.mjTRN_JOINT)
            actuator.set_to_motor()
            actuator.gear = [1.0, 0, 0, 0, 0, 0]
            actuator.ctrllimited = actuator.forcelimited = False
            joint = spec.joint(name)
            joint.armature = self.bam.armature
            joint.damping = [0.0, 0.0, 0.0]  # MuJoCo 3.16 damping is a polynomial in velocity
            joint.frictionloss = 0.0
            joint.solref_friction = FRICTION_SOLREF
            joint.solimp_friction = FRICTION_SOLIMP
            self._mjs_actuators.append(actuator)

    def initialize(self, mj_model, model, data, device: str) -> None:
        super().initialize(mj_model, model, data, device)
        self._model, self._data, self._device = model, data, device
        joints = self.entity.indexing.joint_ids[self.target_ids]
        self.dof_ids = torch.as_tensor(mj_model.jnt_dofadr[joints.cpu().numpy()], device=device)
        shape = (data.nworld, len(self._target_names))
        bam, cfg = self.bam, self.cfg
        nominal = dict(kt=bam.kt, resistance=bam.resistance, kp=cfg.kp, error_gain=bam.error_gain,
                       max_pwm=bam.max_pwm, max_current=bam.max_current, friction_scale=1.0, viscous_scale=1.0)
        self.nominal = {k: torch.full(shape, v, device=device) for k, v in nominal.items()}
        for name, value in self.nominal.items():
            setattr(self, name, value.clone())
        envs = (data.nworld,)
        self.supply_voltage = torch.full(envs, cfg.supply_voltage, device=device)
        self.supply_resistance = torch.full(envs, cfg.supply_resistance, device=device)
        self.idle_current = torch.full(envs, cfg.idle_current, device=device)
        self.bus_voltage = self.supply_voltage.clone()
        self.supply_current = torch.zeros(envs, device=device)
        self.duty = torch.zeros(shape, device=device)
        self.current = torch.zeros(shape, device=device)
        self.torque = torch.zeros(shape, device=device)
        self.torque_enabled = torch.ones(shape, dtype=torch.bool, device=device)
        # Telemetry ring: position, velocity, current, duty per servo and bus voltage.
        steps = cfg.telemetry_steps
        self._ring = torch.zeros((steps, *shape, 4), device=device)
        self._ring_voltage = torch.zeros((steps, data.nworld), device=device)
        self._head = 0
        self._recorded = torch.zeros(envs, dtype=torch.long, device=device)
        self._arange = torch.arange(data.nworld, device=device)
        self._cache = None
        self.telemetry_age = torch.zeros(envs, dtype=torch.long, device=device)  # physics steps
        self.command_lag = torch.zeros(envs, dtype=torch.long, device=device)  # physics steps
        self.stall = torch.zeros(envs, dtype=torch.long, device=device)  # physics steps left holding
        self._held = torch.zeros(shape, device=device)
        if cfg.compile and device.startswith("cuda"):
            # Python launching many small kernels, not the GPU, limits small world counts.
            self.compute, self._sample = torch.compile(self.compute), torch.compile(self._sample)

    @property
    def command_field(self) -> str:
        return "position"

    def _own_friction(self) -> torch.Tensor:
        """Force each DOF's own friction constraint applied in the last solve, (envs, nv)."""
        efc = self._data.efc
        kind, ident, force = efc.type, efc.id, efc.force
        valid = torch.arange(kind.shape[1], device=self._device)[None] < self._data.nefc[:, None]
        mask = valid & (kind == FRICTION_DOF)
        out = torch.zeros_like(self._data.qfrc_bias)
        return out.scatter_add_(1, torch.where(mask, ident, 0).long(), torch.where(mask, force, 0))

    def compute(self, cmd: ActuatorCmd) -> torch.Tensor:
        bias = self.entity.data.encoder_bias[:, self.target_ids]
        # While the link stalls, the MCU keeps writing the last goal it received.
        holding = (self.stall > 0)[:, None]
        target = torch.where(holding, self._held, cmd.position_target)
        self._held = target
        self.stall = (self.stall - 1).clamp(min=0)
        # The servo controls its own encoder, which reads true angle plus calibration
        # error, in ticks counted from home (calibrated to read 2048 there).
        home = self.entity.data.default_joint_pos[:, self.target_ids]
        goal, position = (target + bias - home) / TICK, (cmd.pos + bias - home) / TICK
        if self.cfg.quantize:
            goal, position = torch.round(goal), torch.round(position)
        # Supply sag uses the previous step's current, like BAM's lagged load terms.
        self.bus_voltage = self.supply_voltage - self.supply_resistance * self.supply_current
        vin = self.bus_voltage[:, None]
        self.duty, self.current, self.torque = motor(
            goal - position, cmd.vel, vin, self.kp, self.kt, self.resistance, self.error_gain,
            self.max_pwm, self.max_current)
        enabled = self.torque_enabled.to(self.torque.dtype)
        self.duty, self.current, self.torque = self.duty * enabled, self.current * enabled, self.torque * enabled
        self.supply_current = torch.clamp((self.duty * self.current).sum(dim=1), min=0) + self.idle_current

        dofs = self.dof_ids
        data = self._data
        external = (-data.qfrc_bias[:, dofs] + data.qfrc_constraint[:, dofs] - self._own_friction()[:, dofs])
        applied = data.qfrc_actuator[:, dofs]  # last step's motor torque, as BAM does
        budget = friction_budget(self.bam, applied, external, cmd.vel) * self.friction_scale
        self._model.dof_frictionloss[:, dofs] = budget
        self._model.dof_damping[:, dofs] = self.bam.viscous * self.viscous_scale
        return self.torque

    def _sample(self) -> torch.Tensor:
        bias = self.entity.data.encoder_bias[:, self.target_ids]
        position = self.entity.data.joint_pos[:, self.target_ids] + bias
        velocity = self.entity.data.joint_vel[:, self.target_ids]
        current = self.duty * self.current if self.cfg.current_sensing == "input" else self.current
        return torch.stack((position, velocity, current, self.duty), dim=-1)

    def update(self, dt: float) -> None:
        """Record what the servos would report after this physics step."""
        self._ring[self._head] = self._sample()
        self._ring_voltage[self._head] = self.bus_voltage
        self._head = (self._head + 1) % self.cfg.telemetry_steps
        self._recorded += 1
        self._cache = None

    def telemetry(self) -> dict[str, torch.Tensor]:
        """Servo registers as the MCU read them telemetry_age physics steps ago, in SI units.

        Right after a reset, before any physics step, the servos report the present state.
        """
        if self._cache is None:
            steps = self.cfg.telemetry_steps
            age = torch.minimum(self.telemetry_age.clamp(0, steps - 1), (self._recorded - 1).clamp(min=0))
            index = (self._head - 1 - age) % steps
            fresh = (self._recorded == 0)
            sample = torch.where(fresh[:, None, None], self._sample(), self._ring[index, self._arange])
            voltage = torch.where(fresh, self.bus_voltage, self._ring_voltage[index, self._arange])
            home = self.entity.data.default_joint_pos[:, self.target_ids]
            self._cache = dict(position=home + torch.round((sample[..., 0] - home) / TICK) * TICK,
                               velocity=torch.round(sample[..., 1] / VELOCITY_LSB) * VELOCITY_LSB,
                               current=torch.round(sample[..., 2] / CURRENT_LSB) * CURRENT_LSB,
                               pwm=torch.round(sample[..., 3] * PWM_LIMIT) / PWM_LIMIT,
                               voltage=torch.round(voltage / VOLTAGE_LSB) * VOLTAGE_LSB)
        return self._cache

    def reset(self, env_ids=None) -> None:
        super().reset(env_ids)
        ids = slice(None) if env_ids is None else env_ids
        # mjlab clears joint targets to zero and computes the actuators once during a
        # reset, which would fill the command delay buffer with zero goals. Start
        # from the home pose instead, as the MCU does.
        data = self.entity.data
        home = data.default_joint_pos[ids][:, self.target_ids]
        rows = self._arange[ids][:, None]
        data.joint_pos_target[rows, self.target_ids] = home
        self._held[ids] = home
        self.supply_current[ids] = 0.0
        self.bus_voltage[ids] = self.supply_voltage[ids]
        self.duty[ids] = self.current[ids] = self.torque[ids] = 0.0
        self._recorded[ids] = 0
        self.stall[ids] = 0
        self._cache = None
