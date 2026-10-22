"""Experimental grass-canopy drag and independent illustrative blade bending."""
from dataclasses import dataclass

import mujoco
import numpy as np

from ubot_sim.grass import GRASS_CUTS, GRASS_HEIGHT


@dataclass(frozen=True)
class GrassCanopy:
    """Estimated bulk resistance, not measured blade stiffness.

    Height in metres; resistance in N per metre of wheel width; speed in m/s.
    With explicit density, resistance is specified at 60,000 blades/m².
    Recovery time affects illustrative blades only, not physical drag.
    """
    height: float = 0.05
    resistance: float = 30.0
    transition_speed: float = 0.05
    recovery_seconds: float = 1.5
    # None retains the original sparse illustration and density-independent drag.
    shoot_density: float | None = None  # shoots per square metre
    blades_per_shoot: int = 3

    @property
    def density_scale(self):
        """Estimated linear blade-density scaling; reference is 20k shoots × 3."""
        return (1.0 if self.shoot_density is None else
                self.shoot_density * self.blades_per_shoot / 60000.0)

    def __post_init__(self):
        if self.shoot_density is not None and (
                not np.isfinite(self.shoot_density) or not 0 <= self.shoot_density <= 100000):
            raise ValueError("shoot_density must be finite and between 0 and 100000 shoots/m²")
        if (isinstance(self.blades_per_shoot, bool)
                or not isinstance(self.blades_per_shoot, int)
                or not 1 <= self.blades_per_shoot <= 8):
            raise ValueError("blades_per_shoot must be an integer between 1 and 8")
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
            magnitude = (self.settings.resistance * self.settings.density_scale * width
                         * fraction * np.tanh(speed / self.settings.transition_speed))
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
            self.visual = (CanopyVisual(self) if self.settings.shoot_density is None
                           else DensityCanopyVisual(self))
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


class DensityCanopyVisual(CanopyVisual):
    """Explicit shoots and blades, culled by distance and scene capacity.

    The full field stores shoot roots; only displayed shoots are brushed.
    Display culling never changes physical density or forces.
    """
    def __init__(self, canopy):
        self.canopy = canopy
        settings = canopy.settings
        # Round total count through grid dimensions; report realized density.
        n = round(6 * np.sqrt(settings.shoot_density))
        self.realized_shoot_density = n * n / 36
        rng = np.random.default_rng(17)
        if n:
            spacing = 6 / n
            axis = -3 + (np.arange(n) + 0.5) * spacing
            x, y = np.meshgrid(axis, axis)
            xy = np.c_[x.ravel(), y.ravel()] + rng.uniform(-0.4, 0.4, (n*n, 2)) * spacing
        else:
            xy = np.empty((0, 2))
        uv = (xy + 3) / 0.025
        ij = np.minimum(np.floor(uv).astype(int), 239)
        a, b = (uv - ij).T
        i, j = ij.T
        z = canopy.heights
        soil = ((1-a)*(1-b)*z[j, i] + a*(1-b)*z[j, i+1]
                + (1-a)*b*z[j+1, i] + a*b*z[j+1, i+1])
        self.roots = np.c_[xy, soil]
        self.lean = rng.uniform(-0.012, 0.012, (n*n, 2))
        self.colors = np.c_[rng.uniform(0.18, 0.32, n*n), rng.uniform(0.35, 0.55, n*n),
                            rng.uniform(0.07, 0.14, n*n), np.ones(n*n)]
        self.bend = np.zeros((n*n, 2))
        self.time = 0.0
        self.active = np.empty(0, dtype=int)
        self.drawn_shoots = 0

    def update(self, data):
        dt = max(0, float(data.time) - self.time)
        self.time = float(data.time)
        self.bend *= np.exp(-dt / self.canopy.settings.recovery_seconds)
        for geom in self.canopy.geoms:
            engaged = self.canopy.engagement(data, geom)
            if engaged is None:
                continue
            point, fraction, width = engaged
            delta = self.roots[self.active, :2] - point[:2]
            nearby = self.active[np.sum(delta**2, axis=1) < (0.06 + width / 2)**2]
            mujoco.mj_jac(self.canopy.model, data, self.canopy.jac, None, point,
                          self.canopy.model.geom_bodyid[geom])
            velocity = (self.canopy.jac @ data.qvel)[:2]
            speed = np.linalg.norm(velocity)
            if speed > 0.005:
                self.bend[nearby] = velocity / speed * self.canopy.settings.height * 0.85 * fraction

    def draw(self, scene, data, center):
        distance2 = np.sum((self.roots[:, :2] - np.asarray(center)[:2])**2, axis=1)
        indices = np.flatnonzero(distance2 < 0.7**2)
        leaves = self.canopy.settings.blades_per_shoot
        budget = max(0, (scene.maxgeom - scene.ngeom) // leaves)
        self.active = indices[np.argsort(distance2[indices])][:budget]
        self.drawn_shoots = len(self.active)
        height = self.canopy.settings.height
        roots = np.repeat(self.roots[self.active], leaves, axis=0)
        angles = np.tile(np.arange(leaves) * 2 * np.pi / leaves, len(self.active))
        bends = np.repeat(self.bend[self.active] + self.lean[self.active], leaves, axis=0)
        bends += 0.009 * np.c_[np.cos(angles), np.sin(angles)]
        # Preserve blade length even when imposed deflection plus lean is large.
        lengths = np.linalg.norm(bends, axis=1)
        bends *= np.minimum(1, 0.97 * height / np.maximum(lengths, 1e-12))[:, None]
        vertical = np.sqrt(height**2 - np.sum(bends**2, axis=1))
        tips = roots + np.c_[bends, vertical]
        colors = np.repeat(self.colors[self.active], leaves, axis=0)
        zero, identity = np.zeros(3), np.eye(3).ravel()
        geoms = scene.geoms
        for root, tip, color in zip(roots, tips, colors):
            geom = geoms[scene.ngeom]
            mujoco.mjv_initGeom(geom, mujoco.mjtGeom.mjGEOM_CAPSULE,
                              zero, zero, identity, color)
            mujoco.mjv_connector(geom, mujoco.mjtGeom.mjGEOM_CAPSULE, 0.0005, root, tip)
            scene.ngeom += 1
