"""Standing/balance task with bounded servo position targets at 50 Hz."""

from __future__ import annotations

from pathlib import Path

import gymnasium as gym
from gymnasium import spaces
import mujoco
import numpy as np

from sim.actuators import BamActuators
from sim.stance import standing_pose

MODEL_PATH = Path(__file__).resolve().with_name("gynoid.xml")


class GynoidBalanceEnv(gym.Env):
    metadata = {"render_modes": ["rgb_array"], "render_fps": 50}

    def __init__(self, render_mode=None, episode_seconds=10.0, reset_noise=0.01,
                 push_force=0.0, stance="centered", voltage=5.0, kp=200.0,
                 action_range="baseline", model_path=MODEL_PATH):
        super().__init__()
        if render_mode not in (None, "rgb_array"):
            raise ValueError("Use render_mode='rgb_array' or the sim.evaluate viewer")
        if episode_seconds <= 0 or reset_noise < 0 or push_force < 0:
            raise ValueError("Invalid episode duration, reset noise or push force")
        self.render_mode = render_mode
        self.model = mujoco.MjModel.from_xml_path(str(model_path))
        self.data = mujoco.MjData(self.model)
        self.frame_skip = 10
        self.dt = self.model.opt.timestep * self.frame_skip
        self.max_steps = int(np.ceil(episode_seconds / self.dt))
        self.reset_noise = reset_noise
        self.push_force = push_force
        self.joint_ids = self.model.actuator_trnid[:, 0]
        self.qpos_ids = self.model.jnt_qposadr[self.joint_ids]
        self.dof_ids = self.model.jnt_dofadr[self.joint_ids]
        self.joint_names = [self.model.joint(int(i)).name for i in self.joint_ids]
        if action_range not in ("baseline", "wide"):
            raise ValueError("Action range must be 'baseline' or 'wide'")
        self.action_range = action_range
        self.pose_scale = np.array([0.25 if name == "waist" else 0.35 for name in self.joint_names])
        self.action_scale = (self.pose_scale.copy() if action_range == "baseline" else
                             np.array([0.45 if name == "waist" else 1.0 for name in self.joint_names]))
        self.actuators = BamActuators(self.model, self.data, voltage=voltage, kp=kp)
        self.stance = stance
        self.initial_qpos = standing_pose(self.model, stance)
        self.neutral = self.initial_qpos[self.qpos_ids].copy()
        self.target = self.neutral.copy()
        self.previous_action = np.zeros(self.model.nu)
        self.torque_scale = 0.52  # Retain the baseline's reward normalization.
        self.target_speed = 4.0  # Assumed command slew, rad/s.
        self.pelvis = self.model.body("pelvis").id
        self.torso = self.model.body("waist").id
        self.feet = [self.model.site(f"{side}_foot").id for side in ("left", "right")]
        self.floor = self.model.geom("floor").id
        self.foot_geoms = [self.model.geom("part_53_leg_collision").id,
                           self.model.geom("part_43_leg_collision").id]
        self.action_space = spaces.Box(-1.0, 1.0, (self.model.nu,), dtype=np.float32)
        # gravity, base linear/angular velocity, joint position/velocity,
        # last action, target state, height, COM/support error, foot contacts.
        self.observation_space = spaces.Box(-np.inf, np.inf, (14 + 4 * self.model.nu,), dtype=np.float32)
        self.renderer = None
        self.steps = 0
        self.nominal_height = float(self.initial_qpos[2])

    def configuration(self):
        return dict(actuators=self.actuators.configuration(), stance=self.stance,
                    action_range=self.action_range, target_offsets_rad=self.action_scale.tolist(),
                    neutral_joint_rad=dict(zip(self.joint_names, self.neutral.tolist())),
                    nominal_height_m=self.nominal_height, physics_dt=self.model.opt.timestep,
                    policy_dt=self.dt)

    def _contacts(self):
        touching = np.zeros(2)
        forbidden = False
        for contact in self.data.contact:
            if contact.dist > 0:
                continue
            pair = (contact.geom1, contact.geom2)
            if self.floor not in pair:
                continue
            other = pair[1] if pair[0] == self.floor else pair[0]
            if other in self.foot_geoms:
                touching[self.foot_geoms.index(other)] = 1
            else:
                forbidden = True
        return touching, forbidden

    def _support_error(self):
        midpoint = self.data.site_xpos[self.feet].mean(axis=0)
        return self.data.subtree_com[self.pelvis, :2] - midpoint[:2]

    def _observation(self):
        rotation = self.data.xmat[self.pelvis].reshape(3, 3)
        velocity = np.empty(6)
        mujoco.mj_objectVelocity(self.model, self.data, mujoco.mjtObj.mjOBJ_BODY,
                                self.pelvis, velocity, 1)
        contacts, _ = self._contacts()
        return np.concatenate((
            rotation.T @ [0, 0, -1], velocity[3:] * 2, velocity[:3] * 0.25,
            (self.data.qpos[self.qpos_ids] - self.neutral) / self.pose_scale,
            self.data.qvel[self.dof_ids] * 0.1, self.previous_action,
            (self.target - self.neutral) / self.action_scale,
            [self.data.qpos[2] / self.nominal_height], self._support_error() * 10, contacts,
        )).astype(np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        mujoco.mj_resetData(self.model, self.data)
        self.actuators.reset()
        self.data.qpos[:] = self.initial_qpos
        noise = self.reset_noise
        self.data.qpos[self.qpos_ids] += self.np_random.uniform(-noise, noise, self.model.nu)
        tilt = self.np_random.uniform(-noise, noise, 3)
        tilt[2] = 0
        mujoco.mju_quatIntegrate(self.data.qpos[3:7], tilt, 1.0)
        self.data.qvel[:] = self.np_random.uniform(-noise, noise, self.model.nv)
        self.previous_action.fill(0)
        self.target[:] = self.neutral
        self.steps = 0
        mujoco.mj_forward(self.model, self.data)
        # Raise the perturbed pose only enough to prevent a penetrating reset.
        foot_bottom = min(self.data.site_xpos[self.feet, 2]) - 0.0025
        self.data.qpos[2] += max(0.0, 0.0003 - foot_bottom)
        mujoco.mj_forward(self.model, self.data)
        return self._observation(), {}

    def step(self, action):
        action = np.asarray(action, dtype=np.float64)
        if action.shape != self.action_space.shape or not np.isfinite(action).all():
            raise ValueError(f"Action must contain {self.model.nu} finite values")
        action = np.clip(action, -1, 1)
        desired = self.neutral + action * self.action_scale
        self.target += np.clip(desired - self.target, -self.target_speed * self.dt,
                               self.target_speed * self.dt)
        self.data.xfrc_applied[:] = 0
        # Optional repeatable, bounded horizontal pushes for a later curriculum.
        if self.push_force and self.steps % 100 < 5 and self.steps >= 100:
            angle = (self.steps // 100) * 2.399963229728653
            self.data.xfrc_applied[self.torso, :2] = self.push_force * np.array([np.cos(angle), np.sin(angle)])
        torque_cost = 0.0
        for _ in range(self.frame_skip):
            self.actuators.update(self.target)
            torque_cost += float(np.mean((self.data.ctrl / self.torque_scale) ** 2))
            mujoco.mj_step(self.model, self.data)
        self.steps += 1
        # mj_step leaves position-dependent quantities at the last substep.
        mujoco.mj_forward(self.model, self.data)
        contacts, forbidden = self._contacts()
        upright = float(self.data.xmat[self.torso].reshape(3, 3)[2, 2])
        support_error = self._support_error()
        pose = (self.data.qpos[self.qpos_ids] - self.neutral) / self.pose_scale
        terms = {
            "upright": 1.5 * np.exp(-8 * (1 - upright)),
            "height": np.exp(-100 * (self.data.qpos[2] - self.nominal_height) ** 2),
            "centered": np.exp(-np.sum((support_error / 0.035) ** 2)),
            "feet": 0.25 * float(contacts.mean()),
            "pose": -0.05 * float(np.mean(pose * pose)),
            "speed": -0.02 * float(np.sum(self.data.qvel[:6] ** 2)),
            "effort": -0.02 * torque_cost / self.frame_skip,
            "smoothness": -0.02 * float(np.mean((action - self.previous_action) ** 2)),
        }
        finite = np.isfinite(self.data.qpos).all() and np.isfinite(self.data.qvel).all()
        failures = dict(nonfinite=not finite, body_contact=forbidden, tilt=upright < 0.65,
                        height=self.data.qpos[2] < self.nominal_height * 0.65,
                        displacement=np.linalg.norm(self.data.qpos[:2] - self.initial_qpos[:2]) > 0.3)
        terminated = bool(any(failures.values()))
        truncated = self.steps >= self.max_steps
        reward = float(sum(terms.values()) - (2.0 if terminated else 0.0))
        self.previous_action[:] = action
        info = dict(reward_terms=terms, upright=upright, height=float(self.data.qpos[2]),
                    support_error_m=float(np.linalg.norm(support_error)),
                    foot_contacts=contacts.tolist(), elapsed_seconds=self.steps * self.dt,
                    success=bool(truncated and not terminated),
                    termination_reasons=[key for key, value in failures.items() if value])
        return self._observation(), reward, terminated, truncated, info

    def render(self):
        if self.render_mode != "rgb_array":
            return None
        if self.renderer is None:
            self.renderer = mujoco.Renderer(self.model, height=720, width=960)
        camera = mujoco.MjvCamera()
        camera.lookat[:] = [0, 0, 0.24]
        camera.distance = 0.85
        camera.azimuth = 135
        camera.elevation = -12
        options = mujoco.MjvOption()
        options.geomgroup[3] = 0
        self.renderer.update_scene(self.data, camera=camera, scene_option=options)
        return self.renderer.render()

    def close(self):
        if self.renderer is not None:
            self.renderer.close()
            self.renderer = None
