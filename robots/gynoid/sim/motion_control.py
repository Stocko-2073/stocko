"""Recovery, reaching and weight-transfer controllers with planned equilibria."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import mujoco
import numpy as np
from scipy.optimize import least_squares

from sim.balance_controller import PlantedBalanceController
from sim.motion_env import GynoidMotionEnv


class EquilibriumPlanner:
    """Plan a pose and holding torques with fixed feet and a vertical torso."""

    def __init__(self, *, right_shoulder_upper=0.8, clearance_m=0.0, extra_arm_clearance=False):
        self.env = GynoidMotionEnv(right_shoulder_upper=right_shoulder_upper)
        self.clearance_m = float(clearance_m)
        self.model, self.data = self.env.model, self.env.data
        self.env.reset(seed=0)
        self.q0 = self.env.initial_qpos.copy()
        # Let the other arm joints clear the hips during weight transfer.
        # Neck coordinates stay together to preserve the parallel linkage.
        free_motors = [i for i, name in enumerate(self.env.joint_names)
                       if name != "right_shoulder_1" and not name.endswith("_neck")]
        self.variables = np.r_[np.arange(6), self.env.dof_ids[free_motors]]
        self.previous = np.zeros(len(self.variables))
        self.motor_columns = np.eye(self.model.nv)[:, self.env.dof_ids]
        self.shoulder = self.model.joint("right_shoulder_1").qposadr[0]
        bounds = [(-0.05, 0.05)] * 3 + [(-0.3, 0.3)] * 3
        bounds.extend(tuple(self.model.jnt_range[self.env.joint_ids[i]] - self.env.neutral[i])
                      for i in free_motors)
        self.bounds = np.array(bounds).T
        self.clearance_pairs = [(self.model.geom(thumb).id, self.model.geom(hip).id)
                                for thumb, hip in (("part_20_thumb_collision", "part_39_xl330_collision"),
                                                   ("part_32_thumb_collision", "part_49_xl330_collision"))]
        if extra_arm_clearance:
            self.clearance_pairs.extend((self.model.geom(a).id, self.model.geom(b).id)
                                        for a, b in (("part_17_pole", "part_38_u_bracket"),
                                                     ("part_29_pole", "part_48_u_bracket")))

    def set_pose(self, variables, arm):
        self.data.qpos[:] = self.q0
        tangent = np.zeros(self.model.nv)
        tangent[self.variables] = variables
        mujoco.mj_integratePos(self.model, self.data.qpos, tangent, 1)
        self.data.qpos[self.shoulder] += arm
        self.data.qvel[:] = 0
        mujoco.mj_forward(self.model, self.data)

    def holding_torque(self, left_load):
        model, data, env = self.model, self.data, self.env
        external = np.zeros(model.nv)
        weight = model.body_mass.sum() * 9.81
        for foot, fraction in zip(env.feet, (left_load, 1 - left_load)):
            mujoco.mj_applyFT(model, data, np.array([0., 0., weight * fraction]), np.zeros(3),
                             data.site_xpos[foot], int(model.site_bodyid[foot]), external)
        columns = self.motor_columns.copy()
        for side in ("left", "right"):
            end, stem = np.zeros((3, model.nv)), np.zeros((3, model.nv))
            mujoco.mj_jacSite(model, data, end, None, model.site(f"{side}_rod_end").id)
            mujoco.mj_jacSite(model, data, stem, None, model.site(f"{side}_stem").id)
            columns = np.column_stack((columns, (end - stem).T))
        required = data.qfrc_bias - external
        forces = np.linalg.lstsq(columns, required, rcond=1e-10)[0]
        if np.linalg.norm(required - columns @ forces) > 1e-5:
            raise ValueError("Planned pose cannot support the requested load distribution")
        return forces[:model.nu]

    def solve(self, *, arm=0.0, left_load=0.5):
        if not 0 < left_load < 1:
            raise ValueError("This planner requires both feet to support weight")
        target_com = self.env.anchors[0, :2] * left_load + self.env.anchors[1, :2] * (1 - left_load)

        def constraints(variables):
            self.set_pose(variables, arm)
            rotation = self.data.xmat[self.env.torso].reshape(3, 3)
            return np.r_[(self.data.site_xpos[self.env.feet] - self.env.anchors).ravel() * 100,
                         (self.data.subtree_com[self.env.pelvis, :2] - target_com) * 100,
                         rotation[:2, 2], variables[5]]

        def objective(variables):
            errors = constraints(variables)
            clearances = [min(mujoco.mj_geomDistance(self.model, self.data, a, b, 0.01, None)
                              - self.clearance_m, 0)
                          for a, b in self.clearance_pairs]
            # Strong geometric constraints, with posture and height selecting
            # among redundant configurations. Tolerances are checked afterward.
            return np.r_[errors * 1000, variables[3:], variables[:3] * 10,
                         (self.data.qpos[2] - self.q0[2]) * 100, np.array(clearances) * 1e5]

        result = least_squares(objective, self.previous, bounds=self.bounds, x_scale="jac",
                               max_nfev=150, ftol=1e-8, xtol=1e-8, gtol=1e-8)
        error = np.max(np.abs(constraints(result.x)))
        # Feasibility is required; the posture regularizer need not reach an
        # optimum at the nonsmooth boundary of a collision proxy.
        if not np.isfinite(result.x).all() or error > 1e-5:
            raise ValueError(f"Unable to plan equilibrium: {result.message}; error {error}")
        if self.data.qpos[2] < self.q0[2] - 0.005:
            raise ValueError("Planned motion lowers the pelvis more than 5 mm")
        if any(c.dist < -1e-5 for c in self.data.contact if self.env.floor not in (c.geom1, c.geom2)):
            raise ValueError("Planned motion has a self collision")
        self.previous = result.x
        self.set_pose(result.x, arm)
        return self.data.qpos.copy(), self.holding_torque(left_load)

    def close(self):
        self.env.close()


class MotionController(PlantedBalanceController):
    task = "motion"
    controller_name = "motion_lqr"

    def __init__(self, *args, poses, torques, coordinates, times, values, motion,
                 command_scale=2.0, target_speed=8.0, right_shoulder_upper=0.8,
                 gain_coordinates=None, gains=None,
                 acceleration_states=None, acceleration_inputs=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.poses, self.torques = np.asarray(poses), np.asarray(torques)
        self.coordinates = np.asarray(coordinates)
        self.times, self.values = np.asarray(times), np.asarray(values)
        self.motion = str(motion)
        self.command_scale, self.target_speed = float(command_scale), float(target_speed)
        self.right_shoulder_upper = float(right_shoulder_upper)
        self.gain_coordinates = np.array([0.]) if gain_coordinates is None else np.asarray(gain_coordinates)
        self.gains = np.array([self.gain]) if gains is None else np.asarray(gains)
        self.acceleration_states = (np.array([self.acceleration_state]) if acceleration_states is None
                                    else np.asarray(acceleration_states))
        self.acceleration_inputs = (np.array([self.acceleration_input]) if acceleration_inputs is None
                                    else np.asarray(acceleration_inputs))

    @classmethod
    def build(cls, motion):
        if motion not in ("recovery", "reach", "weight_shift", "overhead"):
            raise ValueError("Unknown motion")
        base = PlantedBalanceController.design(command_cost=100, torso_cost=1000)
        shoulder_upper = 3.0 if motion == "overhead" else 0.8
        planner = EquilibriumPlanner(right_shoulder_upper=shoulder_upper,
                                     clearance_m=0.001 if motion == "overhead" else 0,
                                     extra_arm_clearance=motion == "overhead")
        try:
            coordinates = np.linspace(-1, 1, 81) if motion == "weight_shift" else np.linspace(0, 1, 41)
            if motion == "overhead":
                coordinates = np.linspace(0, 1, 105)
            if motion == "recovery":
                coordinates = np.array([0., 1.])
            poses, torques = [], []
            # Start at zero and walk outward to keep IK on a continuous branch.
            solved = {}
            for sign in (1, -1):
                planner.previous.fill(0)
                for coordinate in sorted((v for v in coordinates if v * sign >= 0), key=abs):
                    arm = (2.6 if motion == "overhead" else 0.25) * coordinate if motion in ("reach", "overhead") else 0
                    load = 0.5 + 0.2 * coordinate if motion == "weight_shift" else 0.5
                    solved[float(coordinate)] = planner.solve(arm=arm, left_load=load)
            for coordinate in coordinates:
                pose, torque = solved[float(coordinate)]
                poses.append(pose)
                torques.append(torque)
            if motion == "recovery":
                times, values = [0, 60], [0, 0]
            elif motion == "reach":
                times, values = [0, 2, 8, 10, 16, 20], [0, 0, 1, 1, 0, 0]
            elif motion == "overhead":
                times, values = [0, 2, 12, 15, 25, 30], [0, 0, 1, 1, 0, 0]
            else:
                times, values = [0, 2, 8, 10, 14, 20, 22, 28, 32], [0, 0, 1, 1, 0, -1, -1, 0, 0]
            gain_indices = ([0] if motion == "recovery" else
                            np.linspace(0, len(coordinates) - 1, 9 if motion == "overhead" else 5).astype(int))
            controllers = [PlantedBalanceController.design(command_cost=100, torso_cost=1000,
                           reference_pose=poses[i], holding_torque=torques[i]) for i in gain_indices]
            return cls(**vars(base), poses=np.array(poses), torques=np.array(torques),
                       coordinates=coordinates, times=times, values=values, motion=motion,
                       right_shoulder_upper=shoulder_upper,
                       gain_coordinates=coordinates[gain_indices],
                       gains=np.array([c.gain for c in controllers]),
                       acceleration_states=np.array([c.acceleration_state for c in controllers]),
                       acceleration_inputs=np.array([c.acceleration_input for c in controllers]))
        finally:
            planner.close()

    @classmethod
    def source_digest(cls):
        digest = hashlib.sha256()
        for name in ("balance_controller.py", "motion_control.py"):
            digest.update(Path(__file__).with_name(name).read_bytes())
        return digest.hexdigest()

    def environment_kwargs(self):
        return dict(**super().environment_kwargs(), command_scale=self.command_scale,
                    target_speed=self.target_speed, right_shoulder_upper=self.right_shoulder_upper,
                    episode_seconds=float(self.times[-1]))

    def reference(self, model, time, include_coordinate=False):
        segment = np.clip(np.searchsorted(self.times, time, side="right") - 1, 0, len(self.times) - 2)
        duration = self.times[segment + 1] - self.times[segment]
        fraction = np.clip((time - self.times[segment]) / duration, 0, 1)
        smooth = fraction ** 3 * (10 - 15 * fraction + 6 * fraction ** 2)
        speed = 30 * fraction ** 2 * (1 - fraction) ** 2 / duration
        difference = self.values[segment + 1] - self.values[segment]
        coordinate = self.values[segment] + difference * smooth
        coordinate_speed = difference * speed
        knot = np.clip(np.searchsorted(self.coordinates, coordinate, side="right") - 1,
                       0, len(self.coordinates) - 2)
        spacing = self.coordinates[knot + 1] - self.coordinates[knot]
        fraction = (coordinate - self.coordinates[knot]) / spacing
        direction = np.zeros(model.nv)
        mujoco.mj_differentiatePos(model, direction, 1, self.poses[knot], self.poses[knot + 1])
        pose = self.poses[knot].copy()
        mujoco.mj_integratePos(model, pose, direction, fraction)
        velocity = direction * coordinate_speed / spacing
        torque = self.torques[knot] * (1 - fraction) + self.torques[knot + 1] * fraction
        result = (pose, velocity, torque)
        return result + (coordinate,) if include_coordinate else result

    def feedback(self, coordinate):
        if len(self.gain_coordinates) == 1:
            return self.gains[0], self.acceleration_states[0], self.acceleration_inputs[0]
        index = np.clip(np.searchsorted(self.gain_coordinates, coordinate, side="right") - 1,
                        0, len(self.gain_coordinates) - 2)
        fraction = ((coordinate - self.gain_coordinates[index])
                    / (self.gain_coordinates[index + 1] - self.gain_coordinates[index]))
        return tuple(array[index] * (1 - fraction) + array[index + 1] * fraction
                     for array in (self.gains, self.acceleration_states, self.acceleration_inputs))

    def predict(self, env):
        pose, velocity, torque, coordinate = self.reference(env.model, env.data.time, include_coordinate=True)
        env.command_center[:] = pose[env.qpos_ids] + (torque + env.kt ** 2 / env.resistance
                                                     * velocity[env.dof_ids]) / self.stiffness
        error = np.zeros(env.model.nv)
        mujoco.mj_differentiatePos(env.model, error, 1, pose, env.data.qpos)
        state = np.r_[error, env.data.qvel - velocity]
        gain, acceleration_state, acceleration_input = self.feedback(coordinate)
        offset = -gain @ state
        acceleration = acceleration_state @ state + acceleration_input @ offset
        predicted_velocity = env.data.qvel[env.dof_ids] + self.prediction_seconds * acceleration[env.dof_ids]
        offset += (self.friction_fraction * env.model.dof_frictionloss[env.dof_ids] / self.stiffness
                   * np.tanh(predicted_velocity / self.velocity_softness))
        return np.clip(offset / env.action_scale, -1, 1)

    def assess(self, samples):
        """Check that the requested motion happened and returned to standing."""
        if self.motion == "recovery":
            return dict(motion_success=True, motion_failures=[])
        failures = []
        if samples[-1]["elapsed_seconds"] < self.times[-1] - 1e-6:
            failures.append("motion_incomplete")
        metrics = {}
        if self.motion == "reach":
            hold = [s for s in samples if 8.5 <= s["elapsed_seconds"] <= 9.5]
            metrics["held_shoulder_rad"] = float(np.mean([s["right_shoulder_offset_rad"] for s in hold])) if hold else 0.
            metrics["held_hand_forward_m"] = float(np.mean([s["right_hand_forward_m"] for s in hold])) if hold else 0.
            if metrics["held_shoulder_rad"] < 0.20 or metrics["held_hand_forward_m"] < 0.02:
                failures.append("reach_target_missed")
            if abs(samples[-1]["right_shoulder_offset_rad"]) > 0.04:
                failures.append("arm_did_not_return")
        elif self.motion == "weight_shift":
            for side, start, end in (("left", 8.5, 9.5), ("right", 20.5, 21.5)):
                hold = [s for s in samples if start <= s["elapsed_seconds"] <= end]
                metrics[f"{side}_hold_com_m"] = float(np.mean([s["com_lateral_m"] for s in hold])) if hold else 0.
                metrics[f"{side}_hold_left_load_fraction"] = float(np.mean([s["left_load_fraction"] for s in hold])) if hold else 0.5
            if metrics["left_hold_com_m"] < 0.007 or metrics["left_hold_left_load_fraction"] < 0.65:
                failures.append("left_shift_target_missed")
            if metrics["right_hold_com_m"] > -0.007 or metrics["right_hold_left_load_fraction"] > 0.35:
                failures.append("right_shift_target_missed")
            if abs(samples[-1]["com_lateral_m"]) > 0.002:
                failures.append("weight_did_not_return")
        elif self.motion == "overhead":
            hold = [s for s in samples if 12.5 <= s["elapsed_seconds"] <= 14.5]
            metrics["held_hand_above_head_m"] = float(np.mean([s["right_hand_above_head_m"] for s in hold])) if hold else 0.
            metrics["held_lowest_hand_clearance_m"] = min((s["right_hand_lowest_above_head_m"] for s in hold), default=0.)
            if metrics["held_hand_above_head_m"] < 0.03 or metrics["held_lowest_hand_clearance_m"] < 0.01:
                failures.append("overhead_target_missed")
            if abs(samples[-1]["right_shoulder_offset_rad"]) > 0.04:
                failures.append("arm_did_not_return")
        return dict(motion_success=not failures, motion_failures=failures, motion_measurements=metrics)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--motion", choices=["recovery", "reach", "weight_shift", "overhead"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.suffix != ".npz" or args.output.exists():
        parser.error("Choose a new .npz output path")
    MotionController.build(args.motion).save(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
