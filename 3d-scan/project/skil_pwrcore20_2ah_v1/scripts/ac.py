"""Shared helpers for measuring the battery from AgentCam captures.

Frames: mat frame in mm (origin mat center, +z up). Cameras are OpenCV on the stored
sensor grid, with the phone's ARKit K and the server's still-PnP pose. A shared Brown
distortion fit across the first six views only overfit (rms 3.6 -> 3.3 px with wild
coefficients), so no distortion is modeled.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]          # 3d-scan/
CAPTURES = ROOT / "captures"
PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / "out"


@lru_cache(None)
def mat_corners() -> dict[int, np.ndarray]:
    layout = json.loads((CAPTURES / "mat_layout.json").read_text())
    return {m["id"]: np.array(m["corners"], float) for m in layout["markers"]}


def detector() -> cv2.aruco.ArucoDetector:
    p = cv2.aruco.DetectorParameters()
    p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    return cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100), p)


def capture_dir(req: str) -> Path:
    dirs = sorted(d for d in (CAPTURES / req).iterdir() if d.is_dir())
    return dirs[-1]


class Capture:
    def __init__(self, req: str):
        self.req = req
        self.dir = capture_dir(req)
        self.meta = json.loads((self.dir / "meta.json").read_text())
        self.analysis = json.loads((self.dir / "analysis.json").read_text())
        self.K0 = np.array(self.meta["intrinsics"]["K"], float)
        self.rot_cw = self.meta["image"]["upright_rotation_cw_deg"]
        self._img = None
        self._det = None

    @property
    def image(self) -> np.ndarray:
        if self._img is None:
            self._img = cv2.imread(str(self.dir / "image.jpg"), cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
        return self._img

    def detections(self) -> tuple[np.ndarray, np.ndarray]:
        """(ids, corners (n,4,2)) of mat markers, cached next to the capture."""
        if self._det is None:
            cache = OUT / "det" / f"{self.req}.npz"
            if cache.exists():
                z = np.load(cache)
                self._det = (z["ids"], z["corners"])
            else:
                gray = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)
                corners, ids, _ = detector().detectMarkers(gray)
                mc = mat_corners()
                keep = [i for i, v in enumerate(ids.ravel()) if int(v) in mc]
                ids = ids.ravel()[keep]
                corners = np.array(corners).reshape(-1, 4, 2)[keep]
                cache.parent.mkdir(parents=True, exist_ok=True)
                np.savez(cache, ids=ids, corners=corners)
                self._det = (ids, corners)
        return self._det

    @property
    def K(self) -> np.ndarray:
        return self.K0

    @property
    def dist(self) -> np.ndarray:
        return np.zeros(5)

    @property
    def cam_from_mat(self) -> np.ndarray:
        # The still's own PnP, unless too few markers were seen for it to be trusted.
        pnp = self.analysis.get("pnp")
        use_pnp = pnp is not None and self.analysis.get("markers_used", 0) >= 10
        T = np.array(pnp["camera_to_mat"] if use_pnp else self.meta["pose"]["camera_to_mat"])
        return np.linalg.inv(T)

    @property
    def eye(self) -> np.ndarray:
        T = self.cam_from_mat
        return -T[:3, :3].T @ T[:3, 3]

    def project(self, pts: np.ndarray) -> np.ndarray:
        pts = np.asarray(pts, float).reshape(-1, 3)
        T = self.cam_from_mat
        rv = cv2.Rodrigues(T[:3, :3])[0]
        uv, _ = cv2.projectPoints(pts, rv, T[:3, 3], self.K, self.dist)
        return uv.reshape(-1, 2)

    def rays(self, uv: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Mat-frame (origin, unit direction) for stored-grid pixels."""
        uv = np.asarray(uv, float).reshape(-1, 1, 2)
        n = cv2.undistortPoints(uv, self.K, self.dist).reshape(-1, 2)
        d_cam = np.c_[n, np.ones(len(n))]
        R = self.cam_from_mat[:3, :3]
        d = d_cam @ R          # R^T d for each row
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        return np.repeat(self.eye[None], len(d), 0), d

    def on_plane_z(self, uv: np.ndarray, z: float) -> np.ndarray:
        o, d = self.rays(uv)
        t = (z - o[:, 2]) / d[:, 2]
        return o + t[:, None] * d


def triangulate(obs: list[tuple[Capture, tuple[float, float]]]) -> tuple[np.ndarray, float]:
    """Least-squares point closest to all rays; returns (point, rms ray distance mm)."""
    A = np.zeros((3, 3)); b = np.zeros(3); rays = []
    for cap, uv in obs:
        o, d = cap.rays(np.array([uv]))
        o, d = o[0], d[0]
        P = np.eye(3) - np.outer(d, d)
        A += P; b += P @ o; rays.append((o, d))
    X = np.linalg.solve(A, b)
    res = [np.linalg.norm((np.eye(3) - np.outer(d, d)) @ (X - o)) for o, d in rays]
    return X, float(np.sqrt(np.mean(np.square(res))))


def to_upright(img: np.ndarray, rot_cw: int) -> np.ndarray:
    k = {0: None, 90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}[rot_cw % 360]
    return img if k is None else cv2.rotate(img, k)


# --- Battery frame (for the 'up' placement, whose mat frame is the object frame) --------------
# +Y toward the terminal end (front), +X to the right looking from the back toward the front,
# +Z up, origin on the mat under the middle of the body. Axis from the side-wall SIFT points
# (label panels, z 4-27), which leaned 1.2 deg off the first hull-PCA axis.
_f0 = np.array([-0.5789, -0.8154]); _x0 = np.array([_f0[1], -_f0[0]])
_f = _f0 - 0.0208 * _x0; BAT_F = _f / np.linalg.norm(_f)
BAT_X = np.array([BAT_F[1], -BAT_F[0]])
BAT_C = np.array([-3.476, -3.722]) + 0.32 * _x0


def bat_to_obj(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, float).reshape(-1, 3)
    return np.c_[BAT_C + np.outer(p[:, 0], BAT_X) + np.outer(p[:, 1], BAT_F), p[:, 2]]


def obj_to_bat(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, float).reshape(-1, 3)
    d = p[:, :2] - BAT_C
    return np.c_[d @ BAT_X, d @ BAT_F, p[:, 2]]
