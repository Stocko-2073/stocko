"""Regenerate agentcam/protocol/examples from the real models and resolver.

    uv run python tests/make_examples.py

The pytest suite and the Swift tests both read these files, which is what keeps
the two sides of the protocol in step. Rerun after changing models.py or the
pose conventions, and review the diff.
"""

import json
from pathlib import Path

import numpy as np

from agentcam.board import Board
from agentcam.geometry import upright_rotation_cw_deg
from agentcam.models import PROTOCOL_VERSION, BoardInfo, PhotoRequest, PhotoRequestSpec, PoseSpec
from agentcam.resolve import resolve, resolve_pose

OUT = Path(__file__).resolve().parents[2] / "protocol" / "examples"

POSE_SPECS = {
    "front landscape": {"look_at": [0, 0, 20], "orbit": {"azimuth_deg": -90, "elevation_deg": 35, "distance_mm": 300}},
    "right side portrait": {"look_at": [0, 0, 20], "orbit": {"azimuth_deg": 0, "elevation_deg": 30, "distance_mm": 250},
                            "hold": "portrait"},
    "top down": {"look_at": [0, 0, 0], "orbit": {"azimuth_deg": 0, "elevation_deg": 90, "distance_mm": 400}},
    "top down portrait": {"look_at": [0, 0, 0], "orbit": {"azimuth_deg": 0, "elevation_deg": 90, "distance_mm": 400},
                          "hold": "portrait"},
    "back left rolled": {"look_at": [10, -5, 15], "orbit": {"azimuth_deg": 135, "elevation_deg": 50, "distance_mm": 280},
                         "roll_deg": 20},
    "eye form": {"look_at": [0, 0, 10], "eye": [150, -200, 180]},
    "up hint": {"look_at": [0, 0, 0], "orbit": {"azimuth_deg": -90, "elevation_deg": 60, "distance_mm": 300},
                "up_hint": [1, 0, 0]},
}


def pose_examples() -> list[dict]:
    out = []
    for name, spec in POSE_SPECS.items():
        t, eye, distance = resolve_pose(PoseSpec.model_validate(spec))
        out.append({"name": name, "spec": spec, "camera_to_page": np.round(t, 9).tolist(),
                    "eye": np.round(eye, 9).tolist(), "distance_mm": round(distance, 9),
                    "upright_rotation_cw_deg": upright_rotation_cw_deg(t)})
    return out


def requests_snapshot() -> dict:
    board = Board.load()
    specs = [
        PhotoRequestSpec.model_validate({"pose": POSE_SPECS["front landscape"], "note": "front of the latch"}),
        PhotoRequestSpec.model_validate({
            "pose": POSE_SPECS["right side portrait"],
            "options": {"lens": "telephoto", "raw": "bayer", "flash": "on", "focus": {"mode": "locked"},
                        "exposure": {"mode": "custom", "duration_s": 0.01, "iso": 100, "bias_ev": 0}},
            "tolerance": {"position_mm": 15, "pointing_deg": 2},
            "placement": {"label": "flipped", "instruction": "Turn the battery upside down, centred on the page."}}),
        PhotoRequestSpec.model_validate({"kind": "free", "options": {"torch": 0.5, "depth": "arkit"},
                                         "note": "anything that shows the vent depth"}),
        PhotoRequestSpec.model_validate({"kind": "freeform", "note": "first look at what's on the page"}),
    ]
    items = []
    for i, spec in enumerate(specs):
        target, warnings = resolve(spec, board)
        items.append(PhotoRequest(**spec.model_dump(), id=f"r{i + 1:04d}", seq=i + 1,
                                  created_at="2026-09-23T22:00:00.000+00:00", updated_at="2026-09-23T22:00:00.000+00:00",
                                  target=target, preflight=warnings).model_dump(mode="json"))
    return {"t": "requests", "v": PROTOCOL_VERSION, "rev": 7, "items": items}


HELLO = {
    "t": "hello", "v": PROTOCOL_VERSION, "app_state": "foreground",
    "device": {"model": "iPhone17,1", "ios": "26.6.2", "app": "0.1.0"},
    "lenses": [
        {"id": "wide", "fov_deg": [71.6, 57.0], "min_focus_mm": 150, "max_photo_dims": [[4032, 3024], [8064, 6048]],
         "raw": ["bayer", "proraw"], "flash": True},
        {"id": "ultrawide", "fov_deg": [106.0, 90.0], "min_focus_mm": 20, "max_photo_dims": [[4032, 3024], [8064, 6048]],
         "raw": ["bayer", "proraw"], "flash": True},
        {"id": "telephoto", "fov_deg": [16.4, 12.3], "min_focus_mm": 600, "max_photo_dims": [[4032, 3024]],
         "raw": ["bayer", "proraw"], "flash": True},
    ],
    "lidar": True,
}

STATUS = {
    "t": "status", "v": PROTOCOL_VERSION, "ts": 1790200000.25, "app": "foreground", "thermal": "nominal", "battery": 0.81,
    "tracking": {"arkit": "normal", "board": {"locked": True, "age_s": 0.3, "markers": 23, "rms_px": 0.6,
                                              "tilt_deg": 1.1, "jitter_mm": 0.3, "generation": 1}},
    "camera_to_page": [[1, 0, 0, 0], [0, -0.5736, 0.8192, -245.7], [0, -0.8192, -0.5736, 192.1], [0, 0, 0, 1]],
    "active": {"request_id": "r0001", "phase": "aligning",
               "err": {"right_mm": 12.0, "down_mm": -3.0, "forward_mm": 40.0, "pointing_deg": 4.1, "roll_deg": 2.0,
                       "steady": False}},
    "outbox": {"pending": 0, "bytes": 0},
}

CAPTURE_META = {
    "capture_id": "6f1c0a9e2b7d4c11", "request_id": "r0001", "captured_at": "2026-09-23T22:01:10.512+00:00",
    "path": "fast",
    "files": [{"name": "image.jpg", "sha256": "0" * 64, "bytes": 3145728},
              {"name": "depth.png", "sha256": "1" * 64, "bytes": 98304},
              {"name": "confidence.png", "sha256": "2" * 64, "bytes": 49152}],
    "image": {"file": "image.jpg", "w": 4032, "h": 3024, "grid": "sensor", "upright_rotation_cw_deg": 0},
    "intrinsics": {"K": [[2860.1, 0, 2015.2], [0, 2860.1, 1511.8], [0, 0, 1]], "source": "arkit",
                   "ref_dims": [4032, 3024], "distortion": {"model": "none"}},
    "pose": {"camera_to_page": [[1, 0, 0, 0], [0, -0.5736, 0.8192, -245.7], [0, -0.8192, -0.5736, 192.1], [0, 0, 0, 1]],
             "source": "arkit_live",
             "target_error": {"right_mm": 1.5, "down_mm": -0.4, "forward_mm": 3.2, "pointing_deg": 0.8, "roll_deg": 1.2}},
    "lens": {"id": "wide", "device_type": "AVCaptureDeviceTypeBuiltInWideAngleCamera", "lens_position": 0.62,
             "focus_mode": "auto", "distortion_correction": True},
    "exposure": {"duration_s": 0.008, "iso": 200, "bias_ev": 0, "wb_gains": [2.0, 1.0, 1.7], "flash_fired": False,
                 "torch": 0},
    "tracking": {"arkit": "normal", "board_age_s": 0.2, "board_generation": 1, "tilt_deg": 1.1, "speed_mm_s": 4,
                 "ang_speed_deg_s": 0.6},
    "depth": {"file": "depth.png", "format": "uint16_mm", "confidence": "confidence.png", "w": 256, "h": 192,
              "K": [[182.4, 0, 128.5], [0, 182.4, 96.4], [0, 0, 1]], "source": "arkit_scene_depth"},
    "placement": None,
    "warnings": [],
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "pose_specs.json": pose_examples(),
        "hello.json": HELLO,
        "welcome.json": {"t": "welcome", "v": PROTOCOL_VERSION, "server_id": "a1b2c3d4e5f6",
                         "board": BoardInfo().model_dump(mode="json")},
        "requests.json": requests_snapshot(),
        "status.json": STATUS,
        "request_update.json": {"t": "request_update", "v": PROTOCOL_VERSION, "id": "r0002", "state": "skipped",
                                "reason": "can't reach behind the monitor"},
        "capture_meta.json": CAPTURE_META,
    }
    for name, data in files.items():
        (OUT / name).write_text(json.dumps(data, indent=1) + "\n")
        print("wrote", OUT / name)


if __name__ == "__main__":
    main()
