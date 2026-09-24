"""Regenerate agentcam/protocol/fixtures/aruco_border.json, the reference solution for
the real photo of the printed mat (aruco_border.jpeg, 12 MP, portrait hold).

    uv run python tests/make_aruco_fixture.py

The photo is on its stored (sensor) grid, 4032x3024. Its focal length isn't
known exactly (it was the ultra-wide, digitally cropped to 1x), so f is fitted
here with the principal point fixed at the center and no distortion; the pose
is then solved with that K. The Swift tests check that the phone's solver
agrees with these numbers.
"""

import json
from pathlib import Path

import cv2
import numpy as np

from agentcam.mat import MatLayout
from agentcam.analysis import solve_mat

FIXTURES = Path(__file__).resolve().parents[2] / "protocol" / "fixtures"


def main() -> None:
    mat = MatLayout.load()
    gray = cv2.imread(str(FIXTURES / "aruco_border.jpeg"), cv2.IMREAD_GRAYSCALE | cv2.IMREAD_IGNORE_ORIENTATION)
    h, w = gray.shape
    corners, ids, _ = mat.detector().detectMarkers(gray)
    ids = ids.ravel()
    corners = np.array(corners).reshape(-1, 4, 2).astype(np.float64)
    # A first fit with a nominal f to find the inliers, then fit f on them.
    guess = np.array([[2600.0, 0, (w - 1) / 2], [0, 2600.0, (h - 1) / 2], [0, 0, 1]])
    fit = solve_mat(mat, ids, corners, guess)
    obj = mat.object_points(ids[fit.inliers]).astype(np.float32)
    img = corners[fit.inliers].reshape(-1, 2).astype(np.float32)
    flags = (cv2.CALIB_USE_INTRINSIC_GUESS | cv2.CALIB_FIX_PRINCIPAL_POINT | cv2.CALIB_FIX_ASPECT_RATIO
             | cv2.CALIB_ZERO_TANGENT_DIST | cv2.CALIB_FIX_K1 | cv2.CALIB_FIX_K2 | cv2.CALIB_FIX_K3)
    _, k, *_ = cv2.calibrateCamera([obj], [img], (w, h), guess.copy(), None, flags=flags)
    fit = solve_mat(mat, ids, corners, k)
    best = fit.choose()
    out = {
        "image": "aruco_border.jpeg", "size": [w, h], "dictionary": mat.dictionary,
        "K": np.round(k, 6).tolist(),
        "detections": [{"id": int(i), "corners": np.round(c, 4).tolist()} for i, c in zip(ids, corners)],
        "inliers": [bool(v) for v in fit.inliers],
        "rejected_ids": sorted(int(i) for i in ids[~fit.inliers]),
        "camera_to_mat": np.round(best.camera_to_mat, 9).tolist(),
        "rms_px": round(best.rms_px, 6),
        "solutions": [{"camera_to_mat": np.round(s.camera_to_mat, 9).tolist(), "rms_px": round(s.rms_px, 6)}
                      for s in fit.solutions],
    }
    (FIXTURES / "aruco_border.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(ids)} detections, {int(fit.inliers.sum())} inliers, rejected {out['rejected_ids']}, "
          f"f {k[0, 0]:.1f} px, rms {best.rms_px:.2f} px, camera at {best.camera_to_mat[:3, 3].round(1)} mm")


if __name__ == "__main__":
    main()
