"""Server-side analysis of a delivered still: find the page in the photo itself
and solve the camera pose from it, independently of the phone's tracking.

`solve_board` is the same algorithm as the phone's `ac_solve_board`
(agentcam/Packages/AgentCamVision/Sources/ArucoBridge/ArucoBridge.cpp):
RANSAC (AP3P) over all corners, a marker kept only if all four of its corners
are inliers, then IPPE + Levenberg-Marquardt on the kept markers. Duplicate
IDs are left in, so RANSAC keeps the real copy and drops the false one.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image as PILImage

from .board import Board
from .geometry import invert, pose_difference, rotation_matrix_cw

log = logging.getLogger(__name__)

PREVIEW_PX = 1600


@dataclass
class BoardSolution:
    camera_to_page: np.ndarray
    rms_px: float


@dataclass
class BoardFit:
    ids: np.ndarray                 # every detection, in detector order
    image_corners: np.ndarray       # (n, 4, 2)
    inliers: np.ndarray             # (n,) bool
    solutions: list[BoardSolution]  # 0-2, lowest rms first

    def choose(self, prior: np.ndarray | None = None) -> BoardSolution | None:
        """The lower-error solution, unless the two are close and a prior
        pose says otherwise (a planar target seen from afar is ambiguous)."""
        if not self.solutions:
            return None
        if prior is not None and len(self.solutions) == 2 and self.solutions[1].rms_px < 1.2 * self.solutions[0].rms_px:
            return min(self.solutions, key=lambda s: pose_difference(s.camera_to_page, prior)[1])
        return self.solutions[0]


def threshold_px(image_corners: np.ndarray) -> float:
    """RANSAC inlier threshold: 35% of the median marker side (3.5 mm on the
    paper), generous enough for a curled page, far below a misplaced marker."""
    sides = np.linalg.norm(image_corners[:, 0] - image_corners[:, 1], axis=1)
    return max(4.0, 0.35 * float(np.median(sides)))


def solve_board(board: Board, ids: np.ndarray, image_corners: np.ndarray, k: np.ndarray) -> BoardFit:
    ids = np.asarray(ids).ravel()
    image_corners = np.asarray(image_corners, float).reshape(-1, 4, 2)
    known = np.array([i in board.corners for i in ids], bool)
    inliers = np.zeros(len(ids), bool)
    fit = BoardFit(ids, image_corners, inliers, [])
    if known.sum() == 0:
        return fit
    idx = np.where(known)[0]
    obj = board.object_points(ids[idx])
    img = image_corners[idx].reshape(-1, 2)
    if len(idx) == 1:
        keep = np.array([True])
    else:
        ok, _, _, inl = cv2.solvePnPRansac(obj, img, k, None, iterationsCount=200,
                                           reprojectionError=threshold_px(image_corners[idx]),
                                           confidence=0.999, flags=cv2.SOLVEPNP_AP3P)
        corner_ok = np.zeros(len(obj), bool)
        if ok and inl is not None:
            corner_ok[inl.ravel()] = True
        keep = corner_ok.reshape(-1, 4).all(1)
    inliers[idx[keep]] = True
    if inliers.sum() == 0:
        return fit
    # RANSAC's inliers come from its best minimal sample; re-sort every marker
    # against the refined pose, which recovers good markers far from that sample.
    threshold = threshold_px(image_corners[idx])
    for _ in range(3):
        fit.solutions = planar_solutions(board.object_points(ids[inliers]), image_corners[inliers].reshape(-1, 2), k)
        if not fit.solutions:
            return fit
        cam_from_page = invert(fit.solutions[0].camera_to_page)
        again = np.zeros_like(inliers)
        for j in idx:
            d = project(board.corners[ids[j]], cam_from_page, k) - image_corners[j]
            again[j] = np.sqrt((d ** 2).sum(1)).max() < threshold
        if not again.any() or (again == inliers).all():
            break
        inliers[:] = again
    _drop_duplicate_ids(fit, board, k)
    return fit


def planar_solutions(obj: np.ndarray, img: np.ndarray, k: np.ndarray) -> list[BoardSolution]:
    try:
        _, rvecs, tvecs, _ = cv2.solvePnPGeneric(obj, img, k, None, flags=cv2.SOLVEPNP_IPPE)
    except cv2.error:
        return []
    out = []
    for rv, tv in zip(rvecs, tvecs):
        rv, tv = cv2.solvePnPRefineLM(obj, img, k, None, rv, tv)
        proj, _ = cv2.projectPoints(obj, rv, tv, k, None)
        rms = float(np.sqrt(np.mean(np.sum((proj.reshape(-1, 2) - img) ** 2, axis=1))))
        cam_from_page = np.eye(4)
        cam_from_page[:3, :3] = cv2.Rodrigues(rv)[0]
        cam_from_page[:3, 3] = tv.ravel()
        out.append(BoardSolution(invert(cam_from_page), rms))
    return sorted(out, key=lambda s: s.rms_px)


def _drop_duplicate_ids(fit: BoardFit, board: Board, k: np.ndarray) -> None:
    """Two copies of one id can't both be on the page; keep the one that fits."""
    ids = fit.ids
    dupes = {i for i in ids[fit.inliers] if (ids[fit.inliers] == i).sum() > 1}
    if not dupes:
        return
    cam_from_page = invert(fit.solutions[0].camera_to_page)
    for i in dupes:
        rows = np.where(fit.inliers & (ids == i))[0]
        errs = [marker_rms(board.corners[i], fit.image_corners[r], cam_from_page, k) for r in rows]
        for j, r in enumerate(rows):
            fit.inliers[r] = j == int(np.argmin(errs))
    fit.solutions = planar_solutions(board.object_points(ids[fit.inliers]),
                                     fit.image_corners[fit.inliers].reshape(-1, 2), k)


def project(points_page: np.ndarray, cam_from_page: np.ndarray, k: np.ndarray) -> np.ndarray:
    pts = np.c_[points_page, np.zeros(len(points_page))] if points_page.shape[1] == 2 else points_page
    cam = pts @ cam_from_page[:3, :3].T + cam_from_page[:3, 3]
    uv = cam @ k.T
    return uv[:, :2] / uv[:, 2:3]


def marker_rms(corners_page: np.ndarray, corners_px: np.ndarray, cam_from_page: np.ndarray, k: np.ndarray) -> float:
    d = project(corners_page, cam_from_page, k) - corners_px
    return float(np.sqrt(np.mean(np.sum(d ** 2, axis=1))))


def analyze(image_path: Path, board: Board, k: np.ndarray, phone_pose: np.ndarray | None) -> dict:
    """Detection + pose from the still on its stored (sensor) grid."""
    gray = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE | cv2.IMREAD_IGNORE_ORIENTATION)
    if gray is None:
        return {"error": f"could not read {image_path.name}"}
    corners, ids, _ = board.detector().detectMarkers(gray)
    out: dict = {"detector": f"cv2 {cv2.__version__} {board.dictionary} subpix",
                 "image_size": [gray.shape[1], gray.shape[0]], "markers_detected": 0 if ids is None else len(ids)}
    if ids is None:
        out["pnp"] = None
        return out
    fit = solve_board(board, ids, np.array(corners).reshape(-1, 4, 2), k)
    best = fit.choose(phone_pose)
    out["markers_used"] = int(fit.inliers.sum())
    out["markers_rejected"] = sorted(int(i) for i in fit.ids[~fit.inliers])
    if best is None:
        out["pnp"] = None
        return out
    cam_from_page = invert(best.camera_to_page)
    per_marker = {str(int(i)): round(marker_rms(board.corners[int(i)], c, cam_from_page, k), 2)
                  for i, c in zip(fit.ids[fit.inliers], fit.image_corners[fit.inliers])}
    out["pnp"] = {"camera_to_page": np.round(best.camera_to_page, 6).tolist(), "rms_px": round(best.rms_px, 3),
                  "ambiguous": len(fit.solutions) == 2 and fit.solutions[1].rms_px < 1.2 * fit.solutions[0].rms_px,
                  "per_marker_rms_px": per_marker}
    if phone_pose is not None:
        dt, dr = pose_difference(best.camera_to_page, phone_pose)
        out["phone_vs_pnp"] = {"dt_mm": round(dt, 2), "dr_deg": round(dr, 3)}
    return out


def write_preview(image_path: Path, out_path: Path, rotation_cw: int, px: int = PREVIEW_PX) -> dict:
    """Upright, downscaled JPEG for the model to look at. `preview_to_full`
    maps preview pixels back to the stored (sensor) grid."""
    with PILImage.open(image_path) as im:
        im = im.convert("RGB")     # PIL ignores EXIF orientation unless asked
        w, h = im.size
        rotated = im.rotate(-rotation_cw, expand=True) if rotation_cw else im
        scale = min(1.0, px / max(rotated.size))
        size = (max(1, round(rotated.width * scale)), max(1, round(rotated.height * scale)))
        preview = rotated.resize(size, PILImage.LANCZOS)
        preview.save(out_path, "JPEG", quality=85)
    sx, sy = size[0] / rotated.width, size[1] / rotated.height
    # full -> rotated -> scaled (pixel centres), then invert.
    s = np.array([[sx, 0, (sx - 1) / 2], [0, sy, (sy - 1) / 2], [0, 0, 1]])
    full_to_preview = s @ rotation_matrix_cw(rotation_cw, w, h)
    return {"file": out_path.name, "size": list(size), "rotation_cw_deg": rotation_cw,
            "preview_to_full": np.round(np.linalg.inv(full_to_preview), 6).tolist()}


def jpeg_bytes(path: Path, px: int, crop: tuple[int, int, int, int] | None = None, rotation_cw: int = 0) -> bytes:
    with PILImage.open(path) as im:
        im = im.convert("RGB")
        if crop:
            x, y, w, h = crop
            im = im.crop((x, y, x + w, y + h))
        if rotation_cw:
            im = im.rotate(-rotation_cw, expand=True)
        scale = min(1.0, px / max(im.size))
        if scale < 1:
            im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), PILImage.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
        return buf.getvalue()
