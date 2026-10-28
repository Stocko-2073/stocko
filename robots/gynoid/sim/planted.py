"""All-joint balancing around an optimized pose with stationary, unwelded feet."""

import hashlib
import json

import gymnasium as gym
from gymnasium import spaces
import mujoco
import numpy as np

from sim.env import GynoidBalanceEnv
from sim.rest_pose import MODEL_PATH, REST_PATH


class GynoidPlantedEnv(GynoidBalanceEnv):
    def __init__(self, render_mode=None, episode_seconds=10.0, reset_noise=0.002,
                 push_force=0.0, voltage=5.0, kp=200.0):
        super().__init__(render_mode, episode_seconds, reset_noise, push_force,
                         stance="cad", voltage=voltage, kp=kp, model_path=MODEL_PATH)
        rest = json.loads(REST_PATH.read_text())
        if rest["model_sha256"] != hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest():
            raise ValueError("Rest pose is stale; run python -m sim.rest_pose")
        self.stance = "optimized_planted"
        self.initial_qpos = np.array(rest["qpos"])
        self.nominal_height = float(self.initial_qpos[2])
        self.neutral = self.initial_qpos[self.qpos_ids].copy()
        self.anchors = np.array(rest["foot_anchors_m"])
        self.action_scale = np.array([0.12 if any(s in n for s in ("hip", "knee", "thigh"))
                                      else 0.20 for n in self.joint_names])
        self.pose_scale = np.full(self.model.nu, 0.4)
        self.action_range = "planted_residual"
        self.target_speed = 1.5
        self.holding_torque = np.array(rest["optimized"]["holding_torque_nm"])
        # At zero velocity BAM's P command generates kt/R * Vin * Kp * gain * error.
        parameters = json.loads(MODEL_PATH.with_name("assets").joinpath("xl330_m6.json").read_text())
        motor = self.actuators.motor
        stiffness = parameters["kt"] / parameters["R"] * motor.vin * motor.kp * motor.error_gain
        self.command_center = self.neutral + self.holding_torque / stiffness
        self.target[:] = self.command_center
        self.kt, self.resistance = parameters["kt"], parameters["R"]
        self.observation_space = spaces.Box(-np.inf, np.inf, (110,), dtype=np.float32)
        self.foot_velocity = np.zeros((2, 3))

    def configuration(self):
        return dict(**super().configuration(), task="planted", reset_noise=self.reset_noise,
                    foot_anchors_m=self.anchors.tolist(), max_foot_drift_m=0.008,
                    max_foot_lift_m=0.004, command_center_rad=self.command_center.tolist(),
                    gravity_holding_torque_nm=self.holding_torque.tolist(),
                    rest_pose_sha256=hashlib.sha256(REST_PATH.read_bytes()).hexdigest())

    def _observation(self):
        base = super()._observation()
        foot_error = self.data.site_xpos[self.feet] - self.anchors
        return np.r_[base, foot_error.ravel() * 100, self.foot_velocity.ravel() * 10].astype(np.float32)

    def reset(self, *, seed=None, options=None):
        # Reset every kinematic coordinate together; independent joint noise
        # would break the parallel neck and move the planted feet.
        gym.Env.reset(self, seed=seed)
        mujoco.mj_resetData(self.model, self.data)
        self.actuators.reset()
        self.data.qpos[:] = self.initial_qpos
        self.data.qpos[2] += 0.0001  # Allow an unforced, tiny contact settling drop.
        self.data.qvel[:6] = self.np_random.uniform(-self.reset_noise, self.reset_noise, 6)
        self.previous_action.fill(0)
        self.target[:] = self.command_center
        self.foot_velocity.fill(0)
        self.steps = 0
        mujoco.mj_forward(self.model, self.data)
        return self._observation(), {}

    def step(self, action):
        action = np.asarray(action, dtype=float)
        if action.shape != self.action_space.shape or not np.isfinite(action).all():
            raise ValueError(f"Action must contain {self.model.nu} finite values")
        action = np.clip(action, -1, 1)
        desired = self.command_center + action * self.action_scale
        self.target += np.clip(desired - self.target, -self.target_speed * self.dt,
                               self.target_speed * self.dt)
        self.data.xfrc_applied[:] = 0
        if self.push_force and self.steps >= 100 and self.steps % 100 < 5:
            angle = (self.steps // 100) * 2.399963229728653
            self.data.xfrc_applied[self.torso, :2] = self.push_force * np.array([np.cos(angle), np.sin(angle)])
        loss = 0.0
        for _ in range(self.frame_skip):
            self.actuators.update(self.target)
            loss += np.sum((self.data.ctrl / self.kt) ** 2) * self.resistance
            mujoco.mj_step(self.model, self.data)
        self.steps += 1
        mujoco.mj_forward(self.model, self.data)
        for i, foot in enumerate(self.feet):
            velocity = np.zeros(6)
            mujoco.mj_objectVelocity(self.model, self.data, mujoco.mjtObj.mjOBJ_SITE, foot, velocity, 0)
            self.foot_velocity[i] = velocity[3:]
        error = self.data.site_xpos[self.feet] - self.anchors
        drift = float(np.max(np.linalg.norm(error[:, :2], axis=1)))
        lift = float(np.max(error[:, 2]))
        contacts, forbidden = self._contacts()
        upright = float(self.data.xmat[self.torso].reshape(3, 3)[2, 2])
        support_error = self.data.subtree_com[self.pelvis, :2] - self.anchors[:, :2].mean(0)
        pose = (self.data.qpos[self.qpos_ids] - self.neutral) / self.pose_scale
        terms = dict(alive=1.0, upright=1.0 * np.exp(-20 * (1 - upright)),
                     height=np.exp(-((self.data.qpos[2] - self.nominal_height) / 0.015) ** 2),
                     centered=np.exp(-np.sum((support_error / 0.008) ** 2)),
                     planted=2 * np.exp(-np.sum((error / 0.003) ** 2)),
                     contacts=0.5 * float(contacts.mean()),
                     foot_speed=-0.02 * float(np.sum((self.foot_velocity / 0.05) ** 2)),
                     pose=-0.03 * float(np.mean(pose ** 2)),
                     speed=-0.05 * float(np.sum(self.data.qvel[:6] ** 2)),
                     effort=-0.1 * loss / self.frame_skip,
                     smoothness=-0.1 * float(np.mean((action - self.previous_action) ** 2)))
        failures = dict(nonfinite=not np.isfinite(self.data.qpos).all() or not np.isfinite(self.data.qvel).all(),
                        body_contact=forbidden, tilt=upright < 0.9,
                        height=self.data.qpos[2] < self.nominal_height - 0.025,
                        foot_drift=drift > 0.008, foot_lift=self.steps > 10 and lift > 0.004)
        terminated, truncated = any(failures.values()), self.steps >= self.max_steps
        self.previous_action[:] = action
        info = dict(reward_terms=terms, upright=upright, height=float(self.data.qpos[2]),
                    support_error_m=float(np.linalg.norm(support_error)),
                    foot_contacts=contacts.tolist(), foot_drift_m=drift, foot_lift_m=lift,
                    copper_loss_w=float(loss / self.frame_skip), elapsed_seconds=self.steps * self.dt,
                    success=bool(truncated and not terminated),
                    termination_reasons=[k for k, v in failures.items() if v])
        return self._observation(), float(sum(terms.values()) - 5 * terminated), bool(terminated), bool(truncated), info
