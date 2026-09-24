"""The printed marker mat, in the mat frame (see geometry.py)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

# agentcam/protocol/mats, next to this package in the checkout.
MATS_DIR = Path(__file__).resolve().parents[3] / "protocol" / "mats"
LAYOUT_FILES = {
    "DICT_4X4_100": "workmat_aruco_4x4_10mm.json",
    "DICT_APRILTAG_36h11": "workmat_apriltag_36h11_10mm.json",
}
CV_DICTIONARIES = {
    "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
    "DICT_APRILTAG_36h11": cv2.aruco.DICT_APRILTAG_36h11,
}


@dataclass
class MatLayout:
    dictionary: str
    marker_mm: float
    mat_mm: tuple[float, float]
    # id -> 4x2 corners (TL, TR, BR, BL as printed) in mat-frame mm, z = 0.
    corners: dict[int, np.ndarray]
    scale: tuple[float, float] = (1.0, 1.0)
    nominal_span_mm: tuple[float, float] = field(default=(0.0, 0.0))

    @classmethod
    def load(cls, dictionary: str = "DICT_4X4_100", scale: tuple[float, float] = (1.0, 1.0)) -> MatLayout:
        layout = json.loads((MATS_DIR / LAYOUT_FILES[dictionary]).read_text())
        w, h = layout["mat_mm"]
        sx, sy = scale
        corners = {
            m["id"]: np.array([[(x - w / 2) * sx, (h / 2 - y) * sy] for x, y in m["corners"]])
            for m in layout["markers"]
        }
        allpts = np.concatenate(list(corners.values()))
        span = tuple(float(v) for v in (allpts.max(0) - allpts.min(0)) / np.array(scale))
        return cls(layout["dictionary"], layout["marker_mm"], (w, h), corners, scale, span)

    def detector(self) -> cv2.aruco.ArucoDetector:
        params = cv2.aruco.DetectorParameters()
        # Must match the phone (agentcam/Packages/AgentCamVision ArucoBridge.cpp).
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        return cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(CV_DICTIONARIES[self.dictionary]), params)

    def object_points(self, ids) -> np.ndarray:
        """(4n, 3) mat-frame corners for `ids`, in detection order."""
        pts = np.concatenate([self.corners[i] for i in ids])
        return np.c_[pts, np.zeros(len(pts))]

    def describe(self) -> dict:
        allpts = np.concatenate(list(self.corners.values()))
        return {
            "dictionary": self.dictionary,
            "marker_mm": self.marker_mm,
            "mat_mm": list(self.mat_mm),
            "markers": len(self.corners),
            "print_scale": list(self.scale),
            "marker_ring_extent_mm": {"x": [float(allpts[:, 0].min()), float(allpts[:, 0].max())],
                                      "y": [float(allpts[:, 1].min()), float(allpts[:, 1].max())]},
            "outer_marker_span_nominal_mm": list(self.nominal_span_mm),
        }
