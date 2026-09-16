"""Experimental grass-canopy drag and independent illustrative blade bending."""
from dataclasses import dataclass

import mujoco
import numpy as np

from ubot_sim.grass import GRASS_CUTS, GRASS_HEIGHT


@dataclass(frozen=True)
class GrassCanopy:
    """Estimated bulk resistance, not measured blade stiffness.

    Height in metres; resistance in N per metre of wheel width; speed in m/s.
    Recovery time affects illustrative blades only, not physical drag.
    """
    height: float = 0.05
    resistance: float = 30.0
    transition_speed: float = 0.05
    recovery_seconds: float = 1.5

    def __post_init__(self):
        values = (self.height, self.resistance, self.transition_speed, self.recovery_seconds)
        if not np.isfinite(values).all() or min(values) < 0:
            raise ValueError("canopy parameters must be finite and nonnegative")
        if self.height <= 0 or self.transition_speed <= 0 or self.recovery_seconds <= 0:
            raise ValueError("canopy height, transition_speed and recovery_seconds must be positive")


class CanopyModel:
    def __init__(self, model, settings):
        self.model, self.settings = model, settings
        self.heights = np.zeros((241, 241))
        for row, (y0, y1) in enumerate(zip(GRASS_CUTS[:-1], GRASS_CUTS[1:])):
            for col, (x0, x1) in enumerate(zip(GRASS_CUTS[:-1], GRASS_CUTS[1:])):
                h = model.hfield(f"grass_{row}_{col}").id
                offset = model.hfield_adr[h]
                shape = (y1 - y0 + 1, x1 - x0 + 1)
                self.heights[y0:y1+1, x0:x1+1] = model.hfield_data[offset:offset + np.prod(shape)].reshape(shape) * GRASS_HEIGHT
        names = [f"{side}_{part}" for side in ("left", "right")
                 for part in ("tire", "contact_a", "contact_b")]
        self.geoms = [model.geom(name).id for name in names]
        self.jac = np.zeros((3, model.nv))
        self.force = np.zeros(model.nv)
        self.power = 0.0
        self.force_norm = 0.0
        self.visual = None

    def ground_height(self, xy):
        """Bilinear soil estimate for drag only; collision heights are untouched."""
        xy = np.asarray(xy)
        if np.any(np.abs(xy) > 3):
            return None
        uv = (xy + 3) / 0.025
        i, j = np.minimum(np.floor(uv).astype(int), 239)
        a, b = uv - [i, j]
        z = self.heights
        return float((1-a)*(1-b)*z[j, i] + a*(1-b)*z[j, i+1]
                     + (1-a)*b*z[j+1, i] + a*b*z[j+1, i+1])

    def engagement(self, data, geom):
        center = data.geom_xpos[geom]
        ground = self.ground_height(center[:2])
        if ground is None:
            return None
        rotation = data.geom_xmat[geom].reshape(3, 3)
        if self.model.geom_type[geom] == mujoco.mjtGeom.mjGEOM_CYLINDER:
            # Include lug tips in the drive-wheel envelope, for either model.
            radius, half_width = 0.1075, self.model.geom_size[geom, 1]
            axis_z = rotation[2, 2]
            extent = radius * np.sqrt(max(0, 1 - axis_z**2)) + half_width * abs(axis_z)
            width = 0.024  # Nominal effective brush width, shared by wheel approximations.
        else:
            extent = np.linalg.norm(rotation[2] * self.model.geom_size[geom])
            width = 2 * self.model.geom_size[geom, 1]
        bottom = center[2] - extent
        lower = max(bottom, ground)
        upper = min(center[2] + extent, ground + self.settings.height)
        depth = max(0.0, upper - lower)
        if depth <= 0:
            return None
        point = center.copy()
        point[2] = lower + depth / 2
        return point, float(min(depth / self.settings.height, 1)), width

    def forces(self, data):
        """Dissipative horizontal bulk drag at each immersed wheel's lower volume.

        Point velocity includes wheel spin and caster swivel. Applying through
        its Jacobian gives both translational forces and resisting moments.
        No vertical support, static holding force, or global MuJoCo callback.
        """
        self.force[:] = 0
        self.power = self.force_norm = 0.0
        for geom in self.geoms:
            engaged = self.engagement(data, geom)
            if engaged is None:
                continue
            point, fraction, width = engaged
            body = self.model.geom_bodyid[geom]
            mujoco.mj_jac(self.model, data, self.jac, None, point, body)
            velocity = self.jac @ data.qvel
            velocity[2] = 0
            speed = np.linalg.norm(velocity)
            if speed < 1e-12:
                continue
            magnitude = self.settings.resistance * width * fraction * np.tanh(speed / self.settings.transition_speed)
            force = -magnitude * velocity / speed
            self.force += self.jac.T @ force
            self.power += float(force @ velocity)
            self.force_norm += float(magnitude)
        return self.force

    def reset_visual(self):
        if self.visual is not None:
            self.visual.bend[:] = 0
            self.visual.time = 0.0

    def update_visual(self, data):
        if self.visual is not None:
            self.visual.update(data)

    def draw(self, scene, data, center):
        if self.visual is None:
            self.visual = CanopyVisual(self)
        self.visual.draw(scene, data, center)


class CanopyVisual:
    """Sampled, non-colliding blades; bending never feeds forces or soil height."""
    def __init__(self, canopy):
        self.canopy = canopy
        rng = np.random.default_rng(17)
        x, y = np.meshgrid(np.arange(-2.975, 3, 0.075), np.arange(-2.975, 3, 0.075))
        xy = np.c_[x.ravel(), y.ravel()] + rng.uniform(-0.018, 0.018, (x.size, 2))
        self.roots = np.c_[xy, [canopy.ground_height(p) for p in xy]]
        self.lean = rng.uniform(-0.004, 0.004, (x.size, 2))
        self.colors = np.c_[rng.uniform(0.22, 0.38, x.size), rng.uniform(0.42, 0.62, x.size),
                            rng.uniform(0.10, 0.18, x.size), np.ones(x.size)]
        self.bend = np.zeros((x.size, 2))
        self.time = 0.0

    def update(self, data):
        dt = max(0, float(data.time) - self.time)
        self.time = float(data.time)
        self.bend *= np.exp(-dt / self.canopy.settings.recovery_seconds)
        for geom in self.canopy.geoms:
            engaged = self.canopy.engagement(data, geom)
            if engaged is None:
                continue
            point, fraction, width = engaged
            delta = self.roots[:, :2] - point[:2]
            # A sampled brush footprint, widened slightly to reach sparse blades.
            nearby = np.sum(delta**2, axis=1) < (0.06 + width / 2)**2
            mujoco.mj_jac(self.canopy.model, data, self.canopy.jac, None, point,
                          self.canopy.model.geom_bodyid[geom])
            velocity = (self.canopy.jac @ data.qvel)[:2]
            speed = np.linalg.norm(velocity)
            if speed > 0.005:
                self.bend[nearby] = velocity / speed * self.canopy.settings.height * 0.85 * fraction

    def draw(self, scene, data, center):
        # Limit rendering cost and gracefully respect a viewer's geometry budget.
        distance = np.linalg.norm(self.roots[:, :2] - np.asarray(center)[:2], axis=1)
        indices = np.flatnonzero(distance < 1.6)
        indices = indices[np.argsort(distance[indices])][:(scene.maxgeom - scene.ngeom) // 2]
        height = self.canopy.settings.height
        for i in indices:
            root = self.roots[i]
            bend = self.bend[i] + self.lean[i]
            tip = root + np.r_[bend, np.sqrt(max(height**2 - float(bend @ bend), height**2 * 0.05))]
            middle = root + (tip - root) * 0.52
            middle[:2] -= bend * 0.18
            for a, b, radius in ((root, middle, 0.0014), (middle, tip, 0.0008)):
                geom = scene.geoms[scene.ngeom]
                mujoco.mjv_initGeom(geom, mujoco.mjtGeom.mjGEOM_CAPSULE,
                                  np.zeros(3), np.zeros(3), np.eye(3).ravel(), self.colors[i])
                mujoco.mjv_connector(geom, mujoco.mjtGeom.mjGEOM_CAPSULE, radius, a, b)
                scene.ngeom += 1
