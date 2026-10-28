"""Local whole-body LQR with BAM friction compensation for planted standing.

The design model projects onto rigid tip/neck constraints and removes free rod
spin. These constraints are only a local control approximation: rollout physics
continues to use the original contacts, parallel linkage and BAM actuators.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np
from scipy import linalg

from sim.actuators import PARAMETERS
from sim.planted import GynoidPlantedEnv
from sim.train import model_hash


def source_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class PlantedBalanceController:
    task = "planted"
    controller_name = "lqr_bam_friction"

    def __init__(self, qref, gain, acceleration_state, acceleration_input, stiffness,
                 friction_fraction=0.7, prediction_seconds=0.02, velocity_softness=0.001,
                 voltage=5.0, firmware_kp=200.0):
        self.qref = qref
        self.gain = gain
        self.acceleration_state = acceleration_state
        self.acceleration_input = acceleration_input
        self.stiffness = float(stiffness)
        self.friction_fraction = float(friction_fraction)
        self.prediction_seconds = float(prediction_seconds)
        self.velocity_softness = float(velocity_softness)
        self.voltage = float(voltage)
        self.firmware_kp = float(firmware_kp)

    @classmethod
    def design(cls, *, voltage=5.0, kp=200.0, command_cost=100.0, torso_cost=0.0,
               reference_pose=None, holding_torque=None, support_feet=("left", "right"),
               swing_foot_cost=0.0):
        if command_cost <= 0 or torso_cost < 0:
            raise ValueError("Command cost must be positive and torso cost nonnegative")
        env = GynoidPlantedEnv(voltage=voltage, kp=kp, reset_noise=0)
        try:
            model, data = env.model, env.data
            env.reset(seed=0)
            data.qpos[:] = env.initial_qpos if reference_pose is None else reference_pose
            if holding_torque is not None:
                env.holding_torque = np.asarray(holding_torque)
            if not support_feet or any(side not in ("left", "right") for side in support_feet):
                raise ValueError("At least one valid support foot is required")
            env.feet = [model.site(f"{side}_foot").id for side in support_feet]
            data.qvel[:] = 0
            mujoco.mj_forward(model, data)
            qref = data.qpos.copy()
            nv, nu = model.nv, model.nu
            selector = np.eye(nv)[env.dof_ids]
            parameters = json.loads(PARAMETERS.read_text())
            stiffness = (env.kt / env.resistance * voltage * kp
                         * env.actuators.motor.error_gain)

            def constraint_jacobian():
                rows = []
                for site in env.feet:
                    jac = np.zeros((3, nv))
                    mujoco.mj_jacSite(model, data, jac, None, site)
                    rows.extend(jac)
                for side in ("left", "right"):
                    end, stem = np.zeros((3, nv)), np.zeros((3, nv))
                    mujoco.mj_jacSite(model, data, end, None, model.site(f"{side}_rod_end").id)
                    mujoco.mj_jacSite(model, data, stem, None, model.site(f"{side}_stem").id)
                    rows.extend(end - stem)
                return np.array(rows)

            jac = constraint_jacobian()
            # Axial twist of each passive rod is irrelevant to balancing and
            # nearly uncontrollable. Including it produces excessive gains.
            spin = np.zeros((2, nv))
            for i, side in enumerate(("right", "left")):
                dof = model.joint(f"{side}_rod").dofadr[0]
                direction = model.site(f"{side}_rod_end").pos
                spin[i, dof:dof + 3] = direction / np.linalg.norm(direction)
            if len(support_feet) == 1:
                # A point contact cannot regulate total vertical angular
                # momentum. Remove global yaw from this local design only.
                yaw = np.zeros((1, nv))
                yaw[0, 3:6] = data.xmat[env.pelvis].reshape(3, 3)[2]
                spin = np.vstack((spin, yaw))
            basis = linalg.null_space(np.vstack((jac, spin)), rcond=1e-8)
            transform = linalg.block_diag(basis, basis)
            reduced_nv = basis.shape[1]
            reactions = linalg.lstsq(jac.T, data.qfrc_bias - selector.T @ env.holding_torque)[0]
            residual = data.qfrc_bias - selector.T @ env.holding_torque - jac.T @ reactions
            if np.linalg.norm(residual) > 1e-6:
                raise ValueError("Reference pose is not a static equilibrium")
            mass = np.zeros((nv, nv))
            mujoco.mj_fullM(model, data, mass)
            # Linearize gravity and the geometric stiffness of contact/linkage
            # reactions in MuJoCo tangent coordinates, including free quaternions.
            hessian = np.zeros((nv, nv))
            epsilon = 1e-6
            for dof in range(nv):
                samples = []
                for sign in (1, -1):
                    data.qpos[:] = qref
                    delta = np.zeros(nv)
                    delta[dof] = sign * epsilon
                    mujoco.mj_integratePos(model, data.qpos, delta, 1)
                    mujoco.mj_forward(model, data)
                    samples.append(data.qfrc_bias - constraint_jacobian().T @ reactions)
                hessian[:, dof] = (samples[0] - samples[1]) / (2 * epsilon)
            data.qpos[:] = qref
            mujoco.mj_forward(model, data)
            reduced_mass = basis.T @ mass @ basis
            motor_map = basis.T @ selector.T
            damping = selector.T @ selector * (env.kt ** 2 / env.resistance
                                               + parameters["friction_viscous"])
            # The inner servo P loop runs at 500 Hz. Design a continuous local
            # approximation, then discretize for held 50 Hz target commands.
            a = np.block([
                [np.zeros((reduced_nv, reduced_nv)), np.eye(reduced_nv)],
                [-linalg.solve(reduced_mass, basis.T @ hessian @ basis
                               + stiffness * motor_map @ motor_map.T),
                 -linalg.solve(reduced_mass, basis.T @ damping @ basis)],
            ])
            b = np.vstack((np.zeros((reduced_nv, nu)),
                           stiffness * linalg.solve(reduced_mass, motor_map)))
            discrete = linalg.expm(np.block([[a, b], [np.zeros((nu, 2 * reduced_nv + nu))]]) * env.dt)
            ad, bd = discrete[:2 * reduced_nv, :2 * reduced_nv], discrete[:2 * reduced_nv, 2 * reduced_nv:]
            q = np.diag(np.r_[[1e5, 1e5, 1e5, 200, 200, 50], np.ones(nv - 6),
                              np.ones(3) * 10, np.ones(3), np.ones(nv - 6) * 0.01])
            com_jac = np.zeros((3, nv))
            mujoco.mj_jacSubtreeCom(model, data, com_jac, env.pelvis)
            q[:nv, :nv] += com_jac.T @ np.diag([1e6, 1e6, 1e4]) @ com_jac
            torso_jac = np.zeros((3, nv))
            mujoco.mj_jacBody(model, data, None, torso_jac, env.torso)
            q[:nv, :nv] += torso_jac.T @ np.diag([torso_cost, torso_cost, 0]) @ torso_jac
            for side in ("left", "right"):
                if side not in support_feet:
                    foot_jac = np.zeros((3, nv))
                    mujoco.mj_jacSite(model, data, foot_jac, None, model.site(f"{side}_foot").id)
                    q[:nv, :nv] += swing_foot_cost * foot_jac.T @ foot_jac
            q = transform.T @ q @ transform
            r = np.eye(nu) * command_cost
            p = linalg.solve_discrete_are(ad, bd, q, r)
            gain = linalg.solve(r + bd.T @ p @ bd, bd.T @ p @ ad)
            if max(abs(linalg.eigvals(ad - bd @ gain))) >= 1:
                raise ValueError("Local controller is unstable")
            return cls(qref, gain @ transform.T,
                       basis @ a[reduced_nv:] @ transform.T,
                       basis @ b[reduced_nv:], stiffness, voltage=voltage, firmware_kp=kp)
        finally:
            env.close()

    def predict(self, env):
        position_error = np.zeros(env.model.nv)
        mujoco.mj_differentiatePos(env.model, position_error, 1, self.qref, env.data.qpos)
        state = np.r_[position_error, env.data.qvel]
        offset = -self.gain @ state
        acceleration = self.acceleration_state @ state + self.acceleration_input @ offset
        predicted_velocity = (env.data.qvel[env.dof_ids]
                              + self.prediction_seconds * acceleration[env.dof_ids])
        # Compensate through ordinary servo targets. The original BAM model
        # still computes friction, electrical limits and the resulting torque.
        offset += (self.friction_fraction * env.model.dof_frictionloss[env.dof_ids]
                   / self.stiffness * np.tanh(predicted_velocity / self.velocity_softness))
        return np.clip(offset / env.action_scale, -1, 1)

    @classmethod
    def source_digest(cls):
        return source_hash()

    def environment_kwargs(self):
        return dict(voltage=self.voltage, kp=self.firmware_kp, reset_noise=0.002, push_force=0.0)

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        config = dict(task=self.task, controller=self.controller_name, model_sha256=model_hash(self.task),
                      controller_sha256=self.source_digest(), env_kwargs=self.environment_kwargs())
        np.savez(path, **vars(self), config=json.dumps(config))
        path.with_suffix(".json").write_text(json.dumps(config, indent=2) + "\n")

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as archive:
            config = json.loads(str(archive["config"]))
            if cls is PlantedBalanceController and config["controller"] == "motion_lqr":
                from sim.motion_control import MotionController
                return MotionController.load(path)
            if config["model_sha256"] != model_hash(config["task"]):
                raise ValueError("Controller and simulation differ; use its original snapshot")
            if config["controller_sha256"] != cls.source_digest():
                raise ValueError("Controller source differs; rebuild or use its original snapshot")
            controller = cls(**{key: archive[key].copy() for key in archive.files if key != "config"})
        return controller, config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("sim/runs/planted-lqr-v1/controller.npz"))
    args = parser.parse_args()
    if args.output.suffix != ".npz" or args.output.exists():
        parser.error("Choose a new .npz output path")
    PlantedBalanceController.design().save(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
