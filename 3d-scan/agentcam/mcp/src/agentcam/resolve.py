"""Pose specs -> targets, plus preflight warnings for the agent."""

from __future__ import annotations

import math

import numpy as np

from .board import Board
from .geometry import invert, look_at_pose, orbit_eye
from .models import PoseSpec, PhotoRequestSpec, Target

# Nominal lens models, used until the phone reports its own. Horizontal and
# vertical field of view on the 4:3 sensor grid, and closest focus.
DEFAULT_LENSES = {
    "wide": {"fov_deg": (71.6, 57.0), "min_focus_mm": 150},
    "ultrawide": {"fov_deg": (106.0, 90.0), "min_focus_mm": 20},
    "telephoto": {"fov_deg": (16.4, 12.3), "min_focus_mm": 600},
}
MIN_EYE_HEIGHT_MM = 5.0
LOW_ELEVATION_DEG = 20.0


def resolve_pose(spec: PoseSpec) -> tuple[np.ndarray, np.ndarray, float]:
    """(camera_to_page, eye, distance) for a pose spec."""
    look_at = np.asarray(spec.look_at, float)
    if spec.orbit is not None:
        eye = orbit_eye(look_at, spec.orbit.azimuth_deg, spec.orbit.elevation_deg, spec.orbit.distance_mm)
    else:
        eye = np.asarray(spec.eye, float)
    distance = float(np.linalg.norm(look_at - eye))
    if distance < 1:
        raise ValueError("eye and look_at coincide")
    return look_at_pose(eye, look_at, spec.hold, spec.roll_deg, spec.up_hint), eye, distance


def resolve(req: PhotoRequestSpec, board: Board, lenses: dict | None = None) -> tuple[Target | None, list[str]]:
    """Raises ValueError for impossible requests; returns warnings for doubtful ones."""
    if req.pose is None:
        return None, []
    t, eye, distance = resolve_pose(req.pose)
    warnings: list[str] = []
    if eye[2] < MIN_EYE_HEIGHT_MM:
        raise ValueError(f"the camera would be {eye[2]:.0f} mm above the paper, at or below the table")
    lens = (lenses or {}).get(req.options.lens) or DEFAULT_LENSES[req.options.lens]
    elevation = math.degrees(math.asin(max(-1.0, min(1.0, -t[2, 2]))))   # viewing direction below horizontal
    if elevation < LOW_ELEVATION_DEG:
        warnings.append(f"looking only {elevation:.0f} deg down: markers will be too foreshortened to see, "
                        "so the pose will come from AR tracking alone (roughly +/-3-5 mm)")
    min_focus = lens.get("min_focus_mm")
    if min_focus and distance < min_focus:
        warnings.append(f"{distance:.0f} mm is closer than the {req.options.lens} lens focuses ({min_focus:.0f} mm)")
    visible = visible_markers(t, board, lens["fov_deg"])
    if visible < 4:
        warnings.append(f"only {visible} markers predicted in view: no pose from the still itself")
    position_tol = req.tolerance.position_mm or max(8.0, 0.03 * distance)
    target = Target(camera_to_page=np.round(t, 6).tolist(), eye=tuple(np.round(eye, 3)),
                    look_at=req.pose.look_at, distance_mm=round(distance, 3),
                    position_tolerance_mm=round(position_tol, 2))
    return target, warnings


def visible_markers(camera_to_page: np.ndarray, board: Board, fov_deg: tuple[float, float]) -> int:
    """Markers whose four corners fall inside the frame, in front of the camera."""
    cam_from_page = invert(camera_to_page)
    tx, ty = (math.tan(math.radians(f / 2)) for f in fov_deg)
    count = 0
    for corners in board.corners.values():
        pts = np.c_[corners, np.zeros(4)] @ cam_from_page[:3, :3].T + cam_from_page[:3, 3]
        if (pts[:, 2] > 1).all() and (np.abs(pts[:, 0] / pts[:, 2]) < tx).all() and (np.abs(pts[:, 1] / pts[:, 2]) < ty).all():
            count += 1
    return count
