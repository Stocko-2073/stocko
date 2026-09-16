"""A single continuous episode through a sequence of navigation goals."""
import mujoco
import numpy as np

from ubot_sim.env import UBotNavigationEnv

DEFAULT_ROUTE = [[0.8, 0.0], [1.0, 0.8], [0.2, 1.0], [-0.5, 0.5], [0.0, 0.0]]


class UBotWaypointsEnv(UBotNavigationEnv):
    """Stop briefly at each waypoint; terminate only after the complete route."""

    def __init__(self, waypoints=None, **kwargs):
        self.waypoints = np.array(DEFAULT_ROUTE if waypoints is None else waypoints, dtype=float)
        if (self.waypoints.ndim != 2 or self.waypoints.shape[1] != 2
                or len(self.waypoints) == 0 or not np.isfinite(self.waypoints).all()):
            raise ValueError("waypoints must be a nonempty list of finite [x, y] positions")
        kwargs.setdefault("max_steps", 1500 * len(self.waypoints))
        self.waypoint_index = 0
        super().__init__(**kwargs)

    def reset(self, *, seed=None, options=None):
        self.waypoint_index = 0
        options = dict(options or {})
        options["goal"] = self.waypoints[0].copy()
        obs, info = super().reset(seed=seed, options=options)
        info.update(waypoints_reached=0, waypoint_count=len(self.waypoints))
        return obs, info

    def step(self, action):
        obs, reward, terminated, truncated, info = super().step(action)
        reached = info["is_success"] and not info["failed"]
        if reached:
            self.waypoint_index += 1
            if self.waypoint_index < len(self.waypoints):
                # Preserve physical state, controls, simulation time, and route
                # time budget. Only goal-dependent bookkeeping changes.
                self.goal = self.waypoints[self.waypoint_index].copy()
                self._place_goal()
                self.success_steps = 0
                self.previous_distance = np.linalg.norm(self.goal - self.data.xpos[self.base, :2])
                mujoco.mj_forward(self.model, self.data)
                obs = self._obs()
                terminated = False
                info["distance"] = float(self.previous_distance)
        info.update(waypoint_reached=bool(reached), waypoints_reached=self.waypoint_index,
                    waypoint_count=len(self.waypoints),
                    is_success=self.waypoint_index == len(self.waypoints))
        return obs, reward, terminated, truncated, info
