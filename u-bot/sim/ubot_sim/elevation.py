"""Elevation queries against static collision geometry, excluding robot/markers."""
import mujoco
import numpy as np


class TerrainElevation:
    def __init__(self, model):
        self.model = model
        self.geoms = np.flatnonzero((model.geom_bodyid == 0) & (model.geom_contype != 0))

    def bounds(self, data, geom):
        center, half = self.model.geom_aabb[geom].reshape(2, 3)
        rotation = data.geom_xmat[geom].reshape(3, 3)
        center = data.geom_xpos[geom] + rotation @ center
        half = np.abs(rotation) @ half
        return center - half, center + half

    def height(self, data, xy):
        """Topmost surface at XY, or None outside finite terrain coverage."""
        model = self.model
        top = max((self.bounds(data, g)[1][2] for g in self.geoms), default=0) + 1
        origin = np.array([*xy, top], dtype=float)
        direction = np.array([0., 0., -1.])
        hits = []
        for g in self.geoms:
            if model.geom_type[g] == mujoco.mjtGeom.mjGEOM_HFIELD:
                distance = mujoco.mj_rayHfield(model, data, g, origin, direction)
            else:
                distance = mujoco.mju_rayGeom(data.geom_xpos[g], data.geom_xmat[g],
                                             model.geom_size[g], origin, direction,
                                             model.geom_type[g])
            if distance >= 0:
                hits.append(top - distance)
        return max(hits) if hits else None

    def maximum(self, data, lower, upper):
        """Conservative height over an XY rectangle for safe spawning.

        Includes vertices of every overlapping heightfield cell and bounding
        boxes of primitives, so thin seams and roots cannot fall between samples.
        """
        model = self.model
        heights = []
        for g in self.geoms:
            kind = model.geom_type[g]
            if kind == mujoco.mjtGeom.mjGEOM_PLANE:
                heights.append(float(data.geom_xpos[g, 2]))
                continue
            lo, hi = self.bounds(data, g)
            if np.any(lower > hi[:2]) or np.any(upper < lo[:2]):
                continue
            if kind == mujoco.mjtGeom.mjGEOM_HFIELD:
                h = model.geom_dataid[g]
                rows, cols = model.hfield_nrow[h], model.hfield_ncol[h]
                sx, sy, sz, _ = model.hfield_size[h]
                origin = data.geom_xpos[g]
                # Supported heightfields are axis aligned.
                cell = np.array([2 * sx / (cols - 1), 2 * sy / (rows - 1)])
                start = np.floor((lower - origin[:2] + [sx, sy]) / cell).astype(int)
                stop = np.ceil((upper - origin[:2] + [sx, sy]) / cell).astype(int)
                start = np.clip(start, 0, [cols - 1, rows - 1])
                stop = np.clip(stop, 0, [cols - 1, rows - 1])
                offset = model.hfield_adr[h]
                values = model.hfield_data[offset:offset + rows * cols].reshape(rows, cols)
                heights.append(origin[2] + sz * values[start[1]:stop[1]+1, start[0]:stop[0]+1].max())
            else:
                heights.append(hi[2])
        return max(heights) if heights else None

    def spawn_lift(self, data):
        lift = -np.inf
        for g in np.flatnonzero((self.model.geom_bodyid != 0) & (self.model.geom_contype != 0)):
            lo, hi = self.bounds(data, g)
            height = self.maximum(data, lo[:2], hi[:2])
            if height is not None:
                lift = max(lift, height + 0.001 - lo[2])
        if not np.isfinite(lift):
            raise ValueError("spawn position has no terrain beneath the robot")
        return lift
