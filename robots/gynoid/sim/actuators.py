"""XL330 BAM M6 adapter for MuJoCo, including floating-base friction indexing."""

from importlib.metadata import version
from pathlib import Path

from bam.model import load_model
import mujoco
import numpy as np

PARAMETERS = Path(__file__).with_name("assets") / "xl330_m6.json"


class BamActuators:
    def __init__(self, model, data, *, voltage=5.0, kp=200.0):
        if not np.isfinite([voltage, kp]).all() or voltage <= 0 or kp <= 0:
            raise ValueError("BAM voltage and firmware gain must be finite and positive")
        self.model, self.data = model, data
        self.bam = load_model(str(PARAMETERS))
        self.motor = self.bam.actuator
        self.motor.vin, self.motor.kp = voltage, kp
        self.motor.max_current = 1.75
        self.joints = model.actuator_trnid[:, 0]
        self.qpos = model.jnt_qposadr[self.joints]
        self.dofs = model.jnt_dofadr[self.joints]
        if not np.all(model.actuator_gear[:, 0] == 1):
            raise ValueError("BAM expects unit-gear torque actuators")
        if np.any(model.actuator_ctrllimited) or np.any(model.actuator_forcelimited):
            raise ValueError("BAM owns the electrical torque limits; remove MJCF clipping")
        model.dof_armature[self.dofs] = self.motor.get_extra_inertia()
        mujoco.mj_setConst(model, data)
        self.control_voltage = np.zeros(model.nu)
        self.reset()

    def reset(self):
        # XL330's BAM P controller is stateless. Clear dynamic friction too, so
        # a reset cannot inherit the previous episode's load-dependent budget.
        self.control_voltage.fill(0)
        self.peak_current_a = 0.0
        self.peak_torque_nm = 0.0
        self.peak_voltage_v = 0.0
        self.saturated_updates = 0
        self.data.ctrl[:] = 0
        friction, damping = self.bam.compute_frictions(0.0, 0.0, 0.0)
        self.model.dof_frictionloss[self.dofs] = friction
        self.model.dof_damping[self.dofs] = damping

    def external_torque(self):
        external = -self.data.qfrc_bias[self.dofs] + self.data.qfrc_constraint[self.dofs]
        # BAM 1.0.2's MujocoController compares efc_id with joint IDs. For
        # mjCNSTR_FRICTION_DOF these are DOF IDs (e.g. 6 after a free joint).
        # Remove each DOF's own dry friction, avoiding load/friction feedback.
        mask = self.data.efc_type == mujoco.mjtConstraint.mjCNSTR_FRICTION_DOF
        own_friction = np.bincount(self.data.efc_id[mask],
                                   weights=self.data.efc_force[mask], minlength=self.model.nv)
        return external - own_friction[self.dofs]

    def update(self, target):
        q, dq = self.data.qpos[self.qpos], self.data.qvel[self.dofs]
        self.control_voltage[:] = self.motor.compute_control(target, q, dq, self.model.opt.timestep)
        self.data.ctrl[:] = self.motor.compute_torque(self.control_voltage, True, q, dq)
        current = float(np.max(np.abs(self.data.ctrl / self.bam.kt.value)))
        voltage = float(np.max(np.abs(self.control_voltage)))
        self.peak_current_a = max(self.peak_current_a, current)
        self.peak_torque_nm = max(self.peak_torque_nm, float(np.max(np.abs(self.data.ctrl))))
        self.peak_voltage_v = max(self.peak_voltage_v, voltage)
        self.saturated_updates += int(current >= self.motor.max_current - 1e-8
                                      or voltage >= self.motor.vin - 1e-8)
        # As in BAM's CPU controller, use forces from the last completed solver
        # step for the load-dependent friction budget; MuJoCo resolves stiction.
        friction, damping = self.bam.compute_frictions(
            self.data.qfrc_actuator[self.dofs], self.external_torque(), dq)
        self.model.dof_frictionloss[self.dofs] = friction
        self.model.dof_damping[self.dofs] = damping

    def configuration(self):
        return dict(backend="bam", package_version=version("better-actuator-models"),
                    motor="xl330", friction_model="m6", voltage=self.motor.vin,
                    kp_fw=self.motor.kp, max_current_a=self.motor.max_current,
                    armature_kg_m2=self.motor.get_extra_inertia(),
                    command_delay_seconds=0, voltage_sag=False, backlash=False)
