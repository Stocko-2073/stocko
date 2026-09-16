"""Goal navigation on flat ground with a free-body CAD-derived U-bot."""
from pathlib import Path

import gymnasium as gym
import mujoco
import numpy as np
from gymnasium import spaces
from ubot_sim.contact_model import load_model

MODEL = Path(__file__).parent / "assets" / "robot.xml"
WHEEL_RADIUS = 0.1075
TRACK = 0.3027
MAX_WHEEL_SPEED = 2 * np.pi
# StepperServo velocity-mode defaults, converted from output turns to radians.
WHEEL_ACCEL = 8 * 2 * np.pi
WHEEL_DECEL = 2 * 2 * np.pi
WHEEL_SETTLE_SPEED = (205 / 4096) * 2 * np.pi


class UBotNavigationEnv(gym.Env):
    metadata = {"render_modes": ["human", "rgb_array"], "render_fps": 50}

    def __init__(self, render_mode=None, max_steps=1500, randomize=False,
                 wheel_contact="lugs", terrain="flat", timestep=0.002,
                 terrain_contact=None, obstacles=(), surface=None):
        if render_mode not in (None, *self.metadata["render_modes"]):
            raise ValueError(f"Unsupported render mode: {render_mode}")
        self.render_mode = render_mode
        self.max_steps = max_steps
        self.randomize = randomize
        self.model = load_model(MODEL, wheel_contact, terrain, timestep, terrain_contact, obstacles, surface)
        self.data = mujoco.MjData(self.model)
        self.frame_skip = round(0.02 / self.model.opt.timestep)
        self.dt = self.model.opt.timestep * self.frame_skip
        self.action_space = spaces.Box(-1, 1, shape=(2,), dtype=np.float32)
        self.observation_space = spaces.Box(-np.inf, np.inf, shape=(22,), dtype=np.float32)
        self.base = self.model.body("base").id
        self.drive = [self.model.joint(f"{s}_drive").id for s in ("left", "right")]
        self.swivel = [self.model.joint(f"{s}_swivel").id for s in ("left", "right")]
        self.drive_dof = self.model.jnt_dofadr[self.drive]
        self.swivel_dof = self.model.jnt_dofadr[self.swivel]
        self.swivel_qpos = self.model.jnt_qposadr[self.swivel]
        self._friction = self.model.geom_friction.copy()
        self._mass = self.model.body_mass.copy()
        self._inertia = self.model.body_inertia.copy()
        self._renderer = None
        self._viewer = None
        self.goal = np.zeros(2)
        self.command = np.zeros(2)
        self.steps = 0
        self.success_steps = 0

    def _state(self):
        rotation = self.data.xmat[self.base].reshape(3, 3)
        velocity = np.zeros(6)
        mujoco.mj_objectVelocity(self.model, self.data, mujoco.mjtObj.mjOBJ_BODY, self.base, velocity, 1)
        delta = self.goal - self.data.xpos[self.base, :2]
        relative_goal = rotation.T @ np.r_[delta, 0.0]
        return rotation, velocity, delta, relative_goal

    def _obs(self):
        rotation, velocity, _, relative_goal = self._state()
        angles = self.data.qpos[self.swivel_qpos]
        return np.concatenate([
            relative_goal[:2], velocity[3:5], velocity[:3], rotation[2, :],
            self.data.qvel[self.drive_dof] / MAX_WHEEL_SPEED,
            np.sin(angles), np.cos(angles), self.data.qvel[self.swivel_dof],
            self.command / MAX_WHEEL_SPEED,
            [self.steps / self.max_steps, self.success_steps / 15],
        ]).astype(np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        options = options or {}
        mujoco.mj_resetData(self.model, self.data)
        self.model.geom_friction[:] = self._friction
        self.model.body_mass[:] = self._mass
        self.model.body_inertia[:] = self._inertia
        if self.randomize:
            self.model.geom_friction[:, 0] *= self.np_random.uniform(0.7, 1.3)
            factor = self.np_random.uniform(0.8, 1.2)
            self.model.body_mass[self.base] *= factor
            self.model.body_inertia[self.base] *= factor
        mujoco.mj_setConst(self.model, self.data)
        yaw = float(options.get("yaw", self.np_random.uniform(-np.pi, np.pi)))
        self.data.qpos[3:7] = [np.cos(yaw / 2), 0, 0, np.sin(yaw / 2)]
        self.data.qpos[self.swivel_qpos] = self.np_random.uniform(-np.pi, np.pi, 2)
        goal = options.get("goal")
        if goal is None:
            angle = self.np_random.uniform(-np.pi, np.pi)
            goal = self.np_random.uniform(0.75, 2.5) * np.array([np.cos(angle), np.sin(angle)])
        self.goal = np.asarray(goal, dtype=float)
        if self.goal.shape != (2,) or not np.isfinite(self.goal).all():
            raise ValueError("goal must contain two finite world coordinates in metres")
        self.data.mocap_pos[0, :2] = self.goal
        # Settle the free body before the episode starts.
        mujoco.mj_forward(self.model, self.data)
        for _ in range(round(0.3 / self.model.opt.timestep)):
            mujoco.mj_step(self.model, self.data)
        self.data.time = 0
        self.steps = 0
        self.success_steps = 0
        self.command[:] = 0
        self.previous_distance = np.linalg.norm(self.goal - self.data.xpos[self.base, :2])
        if self.render_mode == "human":
            self.render()
        return self._obs(), {"distance": float(self.previous_distance), "is_success": False}

    def step(self, action):
        action = np.asarray(action, dtype=float)
        if action.shape != (2,) or not np.isfinite(action).all():
            raise ValueError("action must contain two finite normalized wheel speeds")
        target = np.clip(action, -1, 1) * MAX_WHEEL_SPEED
        # Match StepperServo's velocity ramp at each physics tick. Reversals
        # brake through zero, then accelerate once command and target agree.
        for _ in range(self.frame_skip):
            slowing = (target * self.command < 0) | (np.abs(target) < np.abs(self.command))
            slew = np.where(slowing, WHEEL_DECEL, WHEEL_ACCEL) * self.model.opt.timestep
            self.command += np.clip(target - self.command, -slew, slew)
            self.command[(target == 0) & (np.abs(self.command) < WHEEL_SETTLE_SPEED)] = 0
            self.data.ctrl[:] = self.command
            mujoco.mj_step(self.model, self.data)
        mujoco.mj_forward(self.model, self.data)
        self.steps += 1
        rotation, velocity, delta, _ = self._state()
        distance = float(np.linalg.norm(delta))
        stopped_at_goal = distance < 0.12 and np.linalg.norm(velocity[3:5]) < 0.08 and abs(velocity[2]) < 0.2
        self.success_steps = self.success_steps + 1 if stopped_at_goal else 0
        success = self.success_steps >= 15
        failed = (rotation[2, 2] < 0.5 or self.data.xpos[self.base, 2] < 0.05
                  or np.linalg.norm(self.data.xpos[self.base, :2]) > 6
                  or not np.isfinite(self.data.qpos).all())
        reward = 10 * (self.previous_distance - distance) - 0.01 - 0.001 * float(np.square(np.clip(action, -1, 1)).sum())
        reward += 20.0 * success - 10.0 * failed
        self.previous_distance = distance
        if self.render_mode == "human":
            self.render()
        return self._obs(), float(reward), bool(success or failed), self.steps >= self.max_steps, {
            "distance": distance, "is_success": bool(success), "failed": bool(failed),
        }

    def render(self):
        if self.render_mode == "rgb_array":
            if self._renderer is None:
                self._renderer = mujoco.Renderer(self.model, height=480, width=640)
            self._renderer.update_scene(self.data, camera="follow")
            return self._renderer.render()
        if self.render_mode == "human":
            from mujoco import viewer
            if self._viewer is None:
                self._viewer = viewer.launch_passive(self.model, self.data)
                self._viewer.cam.distance = 2.5
                self._viewer.cam.elevation = -40
            self._viewer.cam.lookat[:] = self.data.xpos[self.base]
            self._viewer.sync()

    def close(self):
        for resource in (self._renderer, self._viewer):
            if resource is not None:
                resource.close()
        self._renderer = self._viewer = None


def baseline_action(observation):
    """Simple go-to-goal controller; normalized left/right output wheel speeds."""
    x, y = observation[:2]
    distance = np.hypot(x, y)
    heading = np.arctan2(y, x)
    if distance < 0.085:
        return np.zeros(2, dtype=np.float32)
    v = min(0.35, 0.8 * distance) * max(0, np.cos(heading))
    omega = np.clip(2.5 * heading, -1.8, 1.8)
    wheels = np.array([v - omega * TRACK / 2, v + omega * TRACK / 2]) / (WHEEL_RADIUS * MAX_WHEEL_SPEED)
    return np.clip(wheels, -1, 1).astype(np.float32)
