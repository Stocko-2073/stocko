"""Frames and pose math shared by the server, the fake phone and the tests.

Conventions (the app's AgentCamCore implements the same ones):

- Mat frame: millimeters, origin at the mat center, +x toward the right edge,
  +y toward the top edge (the row holding marker 0), +z up out of the paper.
- Camera frame: OpenCV (x right, y down, z forward) on the sensor-native
  landscape pixel grid. Pixel (0, 0) is the center of the top-left pixel.
- `camera_to_mat` is a 4x4 matrix mapping camera-frame points to mat-frame
  points; its columns are the camera's x, y, z axes and its center in the mat.
- The sensor grid is upright when the phone is held in landscape with its top
  to the left. Held upright in portrait, the device top is the image's -x.
"""

from __future__ import annotations

import math

import numpy as np

WORLD_UP = np.array([0.0, 0.0, 1.0])
MAT_TOP = np.array([0.0, 1.0, 0.0])
# Above this |forward . up| the view is within ~14 deg of straight down/up and
# "up" is taken from the mat's top edge instead.
NEAR_VERTICAL = 0.97


def normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    if n < 1e-12:
        raise ValueError("zero-length vector")
    return v / n


def orbit_eye(look_at, azimuth_deg: float, elevation_deg: float, distance_mm: float) -> np.ndarray:
    """Camera center on a sphere around `look_at`. Azimuth runs counterclockwise
    from +x as seen from above; elevation is measured up from the paper."""
    a, e = math.radians(azimuth_deg), math.radians(elevation_deg)
    return np.asarray(look_at, float) + distance_mm * np.array(
        [math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])


def look_at_pose(eye, look_at, hold: str = "landscape", roll_deg: float = 0.0, up_hint=None) -> np.ndarray:
    """camera_to_mat for a camera at `eye` looking at `look_at`.

    `hold` says how the phone is held: "landscape" (top to the left, so the
    sensor grid is upright) or "portrait" (top up). `roll_deg` then turns the
    camera about its viewing axis, clockwise as seen from behind the camera.
    """
    eye, target = np.asarray(eye, float), np.asarray(look_at, float)
    z = normalize(target - eye)
    if up_hint is not None:
        up = normalize(np.asarray(up_hint, float))
    else:
        up = MAT_TOP if abs(z @ WORLD_UP) > NEAR_VERTICAL else WORLD_UP
    u = up - (up @ z) * z
    if np.linalg.norm(u) < 1e-6:
        raise ValueError("up_hint is parallel to the viewing direction")
    u = normalize(u)
    if hold == "landscape":
        y = -u                      # image up is world up
        x = np.cross(y, z)
    elif hold == "portrait":
        x = -u                      # the device top (image -x) is world up
        y = np.cross(z, x)
    else:
        raise ValueError(f"hold must be landscape or portrait, not {hold!r}")
    r = math.radians(roll_deg)
    x, y = math.cos(r) * x + math.sin(r) * y, -math.sin(r) * x + math.cos(r) * y
    t = np.eye(4)
    t[:3, 0], t[:3, 1], t[:3, 2], t[:3, 3] = x, y, z, eye
    return t


def invert(t: np.ndarray) -> np.ndarray:
    r, p = t[:3, :3], t[:3, 3]
    out = np.eye(4)
    out[:3, :3] = r.T
    out[:3, 3] = -r.T @ p
    return out


def pose_difference(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """(translation mm, rotation deg) between two camera_to_mat transforms."""
    dt = float(np.linalg.norm(a[:3, 3] - b[:3, 3]))
    # |Ra - Rb| = 2*sqrt(2)*sin(angle/2); unlike acos of the trace, exact near zero.
    chord = float(np.linalg.norm(a[:3, :3] - b[:3, :3])) / (2 * math.sqrt(2))
    return dt, math.degrees(2 * math.asin(min(1.0, chord)))


def upright_rotation_cw_deg(camera_to_mat: np.ndarray) -> int:
    """Clockwise rotation (0/90/180/270) that turns the sensor-grid image
    upright, taking world up (or the mat top when looking straight down)."""
    r = camera_to_mat[:3, :3]
    up = MAT_TOP if abs(r[:, 2] @ WORLD_UP) > NEAR_VERTICAL else WORLD_UP
    ux, uy = (r.T @ up)[:2]         # world up in camera x, y
    # Image up is -y. Pick the quarter turn that best maps `up` onto -y.
    return {(0, -1): 0, (-1, 0): 90, (0, 1): 180, (1, 0): 270}[
        (0, int(np.sign(uy))) if abs(uy) >= abs(ux) else (int(np.sign(ux)), 0)]


def rotation_matrix_cw(deg: int, w: int, h: int) -> np.ndarray:
    """3x3 pixel map from the sensor grid (w x h) to the grid rotated `deg`
    clockwise, in OpenCV pixel-center coordinates."""
    return {
        0: np.eye(3),
        90: np.array([[0, -1, h - 1], [1, 0, 0], [0, 0, 1]], float),
        180: np.array([[-1, 0, w - 1], [0, -1, h - 1], [0, 0, 1]], float),
        270: np.array([[0, 1, 0], [-1, 0, w - 1], [0, 0, 1]], float),
    }[deg]
