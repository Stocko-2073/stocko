"""agentcam-fakephone: a stand-in for the iPhone app, for tests and demos.

It speaks the real protocol: connects to /v1/ws, says hello, takes each queued
request, renders a synthetic photo of the marker page from (nearly) the
requested pose, uploads it and commits it, so the whole server path, including
the still-PnP analysis, runs without a phone.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import math
import sys
import uuid
from datetime import datetime, timezone

import aiohttp
import cv2
import numpy as np

from .board import BOARDS_DIR, LAYOUT_FILES, CV_DICTIONARIES
from .geometry import invert, look_at_pose, orbit_eye, upright_rotation_cw_deg
from .models import PROTOCOL_VERSION

log = logging.getLogger("agentcam.fakephone")

WIDTH, HEIGHT, FOCAL = 1920, 1440, 1450.0
K = np.array([[FOCAL, 0, (WIDTH - 1) / 2], [0, FOCAL, (HEIGHT - 1) / 2], [0, 0, 1]])
PX_PER_MM = 6


def page_raster(dictionary: str = "DICT_4X4_100") -> np.ndarray:
    """The printed page at PX_PER_MM, drawn from the layout JSON."""
    layout = json.loads((BOARDS_DIR / LAYOUT_FILES[dictionary]).read_text())
    w, h = layout["page_mm"]
    page = np.full((round(h * PX_PER_MM), round(w * PX_PER_MM)), 255, np.uint8)
    d = cv2.aruco.getPredefinedDictionary(CV_DICTIONARIES[dictionary])
    side = round(layout["marker_mm"] * PX_PER_MM)
    for m in layout["markers"]:
        x, y = (round(v * PX_PER_MM) for v in m["corners"][0])
        page[y:y + side, x:x + side] = d.generateImageMarker(m["id"], side, 1)
    return page


def render(camera_to_page: np.ndarray, page: np.ndarray, page_mm=(215.9, 279.4), noise: float = 2.0,
           rng: np.random.Generator | None = None) -> np.ndarray:
    """What an undistorted pinhole camera K at `camera_to_page` sees: the page on a grey table."""
    w, h = page_mm
    cam_from_page = invert(camera_to_page)
    r, t = cam_from_page[:3, :3], cam_from_page[:3, 3]
    s = 1 / PX_PER_MM
    raster_to_page = np.array([[s, 0, s / 2 - w / 2], [0, -s, h / 2 - s / 2], [0, 0, 1]])
    homography = K @ np.c_[r[:, 0], r[:, 1], t] @ raster_to_page
    img = cv2.warpPerspective(page, homography, (WIDTH, HEIGHT), flags=cv2.INTER_AREA, borderValue=90)
    img = cv2.GaussianBlur(img, (3, 3), 0.7)
    rng = rng or np.random.default_rng()
    return np.clip(img + rng.normal(0, noise, img.shape), 0, 255).astype(np.uint8)


def perturb(pose: np.ndarray, mm: float, deg: float, rng: np.random.Generator) -> np.ndarray:
    """A pose near `pose`, as a person holding a phone would land."""
    axis = rng.normal(size=3)
    rv = axis / np.linalg.norm(axis) * math.radians(deg)
    out = pose.copy()
    out[:3, :3] = pose[:3, :3] @ cv2.Rodrigues(rv)[0]
    out[:3, 3] += rng.normal(size=3) / math.sqrt(3) * mm
    return out


def hello() -> dict:
    return {"t": "hello", "v": PROTOCOL_VERSION, "app_state": "foreground",
            "device": {"model": "fakephone", "ios": "-", "app": "fakephone"},
            "lenses": [{"id": "wide", "fov_deg": [2 * math.degrees(math.atan(WIDTH / 2 / FOCAL)),
                                                  2 * math.degrees(math.atan(HEIGHT / 2 / FOCAL))],
                        "min_focus_mm": 150}],
            "lidar": False}


async def capture(session: aiohttp.ClientSession, base: str, req: dict, page: np.ndarray,
                  rng: np.random.Generator) -> dict:
    target = np.array(req["target"]["camera_to_page"]) if req.get("target") else _default_pose()
    true_pose = perturb(target, 3.0, 0.5, rng)
    reported = perturb(true_pose, 1.0, 0.1, rng)     # tracking is good, not perfect
    jpeg = cv2.imencode(".jpg", render(true_pose, page, rng=rng), [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()
    cid = uuid.uuid4().hex[:16]
    rid = req["id"]
    sha = hashlib.sha256(jpeg).hexdigest()
    url = f"{base}/v1/requests/{rid}/captures/{cid}"
    async with session.put(f"{url}/files/image.jpg", data=jpeg, headers={"X-AgentCam-SHA256": sha}) as resp:
        resp.raise_for_status()
    meta = {
        "capture_id": cid, "request_id": rid, "captured_at": datetime.now(timezone.utc).isoformat(),
        "path": "fast", "files": [{"name": "image.jpg", "sha256": sha, "bytes": len(jpeg)}],
        "image": {"file": "image.jpg", "w": WIDTH, "h": HEIGHT, "grid": "sensor",
                  "upright_rotation_cw_deg": upright_rotation_cw_deg(true_pose)},
        "intrinsics": {"K": K.tolist(), "source": "fakephone", "ref_dims": [WIDTH, HEIGHT]},
        "pose": {"camera_to_page": reported.tolist(), "source": "arkit_live"},
        "lens": {"id": "wide"},
        "fake_true_pose": true_pose.tolist(),
    }
    async with session.post(f"{url}/commit", json=meta) as resp:
        resp.raise_for_status()
        return await resp.json()


def _default_pose() -> np.ndarray:
    return look_at_pose(orbit_eye((0, 0, 0), -90, 50, 350), (0, 0, 0))


async def run(base: str, count: int | None, skip: set[str], seed: int | None, once: bool) -> int:
    rng = np.random.default_rng(seed)
    page = page_raster()
    done: set[str] = set()
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(f"{base}/v1/ws") as ws:
            await ws.send_json(hello())
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    break
                m = json.loads(msg.data)
                if m["t"] != "requests":
                    continue
                for req in m["items"]:
                    if req["id"] in done:
                        continue
                    done.add(req["id"])
                    if req["id"] in skip:
                        await ws.send_json({"t": "request_update", "v": PROTOCOL_VERSION, "id": req["id"],
                                            "state": "skipped", "reason": "fakephone was told to skip it"})
                        log.info("skipped %s", req["id"])
                    else:
                        log.info("captured %s: %s", req["id"], await capture(session, base, req, page, rng))
                    if count is not None and len(done) >= count:
                        return len(done)
                if once and not m["items"]:
                    return len(done)
    return len(done)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--server", default="http://127.0.0.1:8765")
    p.add_argument("--count", type=int, help="stop after this many requests")
    p.add_argument("--skip", nargs="*", default=[], help="request ids to skip instead of capture")
    p.add_argument("--seed", type=int)
    p.add_argument("--once", action="store_true", help="exit when the queue is empty")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(message)s")
    n = asyncio.run(run(args.server.rstrip("/"), args.count, set(args.skip), args.seed, args.once))
    print(f"handled {n} request(s)")


if __name__ == "__main__":
    main()
