"""The agent-facing MCP tools."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import Context, Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import enrich
from .models import BoardInfo, PhotoRequest, PhotoRequestSpec

MAX_WAIT_S = 600
PROGRESS_EVERY_S = 15

CONVENTIONS = """\
Frames and units (millimetres, degrees):
- Page frame: origin at the page centre, +x toward the right edge, +y toward the top edge
  (the marker row holding id 0), +z up out of the paper. The object sits inside the marker ring.
- Pose spec: {"look_at": [x,y,z], "orbit": {"azimuth_deg", "elevation_deg", "distance_mm"}} or
  {"look_at", "eye": [x,y,z]}. Orbit: eye = look_at + d*(cos e*cos a, cos e*sin a, sin e); azimuth runs
  counter-clockwise from +x seen from above; elevation 90 looks straight down.
  "hold": "landscape" (phone top to the left; the stored image is upright) or "portrait" (phone upright).
  "roll_deg" turns the camera about its viewing axis, clockwise as seen from behind it.
  "up_hint" picks the world direction that is image-up (default +z; +y when looking straight down).
- Camera frame: OpenCV (x right, y down, z forward) on the stored pixel grid, which is the sensor's
  native landscape grid; pixel (0,0) is the centre of the top-left pixel. Stored files have EXIF
  Orientation 1, so cv2.imread gives exactly that grid. meta.json "image.upright_rotation_cw_deg" says how
  to turn the image upright for viewing. camera_to_page maps camera-frame points to the page frame.
- The user may turn the page, with the object on it, to reach a view (say the desk is against a wall).
  Poses are relative to the page, so that's fine as long as the object doesn't shift on the paper; each move
  bumps meta.json "tracking.board_generation". Photos in the same generation share an unmoved page.
- Two poses per photo: meta.json "pose" is the phone's (ARKit tracking relative to the page); analysis.json
  "pnp" is solved from the markers visible in the still itself, with its reprojection rms. Prefer "pnp"
  when it exists and its rms is small.
"""

INSTRUCTIONS = """\
AgentCam guides the user's iPhone to camera poses you choose around an object sitting on a printed
ArUco-bordered US Letter page, captures automatically when the phone is aligned and steady, and returns
the photo with its intrinsics and pose.

Workflow: queue requests with request_photos (they wait on this Mac even while the app is closed),
ask the user to open AgentCam on their iPhone, then call wait_for_photos. Full-resolution files stay on
disk at the paths given; tool results carry downscaled upright previews. Call get_board for the frame
conventions before choosing poses. For a first look at what's on the page, request {"kind": "freeform"}:
no pose, taken as soon as the whole page is in view with the phone steady.
""" + "\n" + CONVENTIONS


def register(mcp: MCPServer, runtime) -> None:
    def hub():
        if runtime.error:
            raise ToolError(runtime.error)
        return runtime.hub

    def phone_hint() -> str:
        h = hub()
        if h.phone is not None and h.app_state == "foreground":
            return "The phone is connected with AgentCam open."
        if h.last_seen is None:
            return (f"No phone has connected yet. Ask the user to open AgentCam on their iPhone (it finds this "
                    f"Mac over Bonjour; manual address {runtime.address}). If it never connects, the macOS firewall "
                    f"may be blocking incoming connections to this server's Python.")
        return (f"The phone is not in the foreground (last seen {time.time() - h.last_seen:.0f} s ago). "
                "Ask the user to open AgentCam on their iPhone.")

    @mcp.tool()
    async def request_photos(requests: list[PhotoRequestSpec]) -> str:
        """Queue one or more photo requests. Returns their ids, the resolved camera targets and any preflight
        warnings. Requests wait here until the phone takes them, so queue a whole set, then ask the user to
        open AgentCam and call wait_for_photos. Lens/flash/48mp/RAW/lidar_photo options briefly leave AR on
        the phone; the photo's pose then comes from the markers in the still. See get_board for frames."""
        try:
            made = await hub().add_requests(requests)
        except ValueError as e:
            return f"Nothing queued: {e}"
        lines = [f"Queued {len(made)} request(s). {phone_hint()}"]
        for r in made:
            lines.append(_describe(r))
        return "\n".join(lines)

    @mcp.tool()
    async def list_requests(include_done: bool = True, limit: int = 50) -> str:
        """The request queue: state (queued, captured, skipped, cancelled), target and capture ids."""
        h = hub()
        rs = h.store.ordered() if include_done else h.store.queued()
        rs = rs[-limit:]
        if not rs:
            return f"No requests. {phone_hint()}"
        return "\n".join([phone_hint()] + [_describe(r) for r in rs])

    @mcp.tool()
    async def wait_for_photos(ctx: Context, ids: list[str] | None = None, mode: Literal["all", "any"] = "all",
                              timeout_s: float = 300, max_previews: int = 4,
                              preview_px: int = 1024) -> list[str | Image]:
        """Block until the given requests (default: every queued one) are captured or skipped, or until
        timeout_s (max 600). Returns a summary with file paths and upright preview images of the newest
        captures. Cancelling this call does not cancel the requests; call it again to keep waiting."""
        h = hub()
        ids = ids if ids is not None else [r.id for r in h.store.queued()]
        missing = [i for i in ids if i not in h.store.requests]
        if missing:
            return [f"Unknown request ids: {', '.join(missing)}"]
        if not ids:
            return [f"Nothing is queued. {phone_hint()}"]
        deadline = time.monotonic() + min(max(timeout_s, 0), MAX_WAIT_S)
        while True:
            reqs = [h.store.requests[i] for i in ids]
            done = [r for r in reqs if h.is_done(r)]
            finished = len(done) == len(reqs) if mode == "all" else bool(done)
            remaining = deadline - time.monotonic()
            if finished or remaining <= 0:
                break
            await ctx.report_progress(len(done), len(reqs), f"{len(done)}/{len(reqs)} done. {phone_hint()}")
            await h.wait_changed(min(PROGRESS_EVERY_S, remaining))
        head = f"{len(done)}/{len(reqs)} done." + ("" if finished else f" Timed out waiting. {phone_hint()}")
        out: list[str | Image] = [head + "\n" + "\n".join(_describe(r, h.store) for r in reqs)]
        shown = 0
        for r in sorted(done, key=lambda r: r.updated_at, reverse=True):
            if shown >= max_previews or not r.capture_ids:
                continue
            folder = h.store.capture_dir(r.id, r.capture_ids[-1])
            if (folder / "preview.jpg").exists():
                out.append(f"{r.id} preview (upright):")
                out.append(Image(data=enrich.jpeg_bytes(folder / "preview.jpg", preview_px), format="jpeg"))
                shown += 1
        return out

    @mcp.tool()
    async def get_photo(request_id: str, capture: int = -1, crop: list[int] | None = None,
                        preview_px: int = 1568, upright: bool = True) -> list[str | Image]:
        """One capture's metadata and analysis, with an image: the upright preview, or with crop=[x, y, w, h]
        a region of the full-resolution image in stored-grid pixels (to inspect detail)."""
        h = hub()
        r = h.store.requests.get(request_id)
        if r is None or not r.capture_ids:
            return [f"No capture for {request_id}."]
        cid = r.capture_ids[capture]
        folder = h.store.capture_dir(r.id, cid)
        meta = h.store.capture_meta(r.id, cid) or {}
        analysis = h.store.capture_analysis(r.id, cid)
        text = json.dumps({"folder": str(folder), "meta": meta, "analysis": analysis}, indent=1)
        rot = meta.get("image", {}).get("upright_rotation_cw_deg", 0) if upright else 0
        if crop:
            if len(crop) != 4:
                return ["crop must be [x, y, w, h]"]
            data = enrich.jpeg_bytes(folder / meta["image"]["file"], preview_px, tuple(crop), rot)
        elif (folder / "preview.jpg").exists():
            data = enrich.jpeg_bytes(folder / "preview.jpg", preview_px)
        else:
            data = enrich.jpeg_bytes(folder / meta["image"]["file"], preview_px, None, rot)
        return [text, Image(data=data, format="jpeg")]

    @mcp.tool()
    async def cancel_requests(ids: list[str] | None = None) -> str:
        """Cancel queued requests (default: all of them). The phone drops them from its list."""
        cancelled = await hub().cancel(ids)
        return f"Cancelled {', '.join(cancelled)}." if cancelled else "Nothing to cancel."

    @mcp.tool()
    async def phone_status() -> str:
        """Whether the phone is connected and in the foreground, its lenses, whether it has the page locked,
        its live camera pose, and what it is doing now."""
        h = hub()
        info = {
            "summary": phone_hint(),
            "server_address": runtime.address,
            "connected": h.phone is not None,
            "app_state": h.app_state,
            "last_seen_s_ago": None if h.last_seen is None else round(time.time() - h.last_seen, 1),
            "device": h.hello.device if h.hello else None,
            "lenses": [l.model_dump() for l in h.hello.lenses] if h.hello else None,
            "lidar": h.hello.lidar if h.hello else None,
            "live": h.status,
            "queued": [r.id for r in h.store.queued()],
        }
        return json.dumps(info, indent=1)

    @mcp.tool()
    async def get_board() -> str:
        """The printed page, its frame conventions, and where its marker layout (page-frame mm) is on disk."""
        h = hub()
        return CONVENTIONS + "\nBoard:\n" + json.dumps(
            h.board.describe() | {"layout_page_frame_file": str(runtime.write_board_file())}, indent=1)

    @mcp.tool()
    async def set_print_scale(measured_x_mm: float, measured_y_mm: float) -> str:
        """Correct for the printer's scaling. Ask the user to measure, with calipers, the page's marker ring
        from the outer edge of the leftmost marker to the outer edge of the rightmost (x) and from the top
        row's outer edge to the bottom row's (y); get_board lists the nominal spans."""
        h = hub()
        nx, ny = h.board.nominal_span_mm
        if not (0.9 < measured_x_mm / nx < 1.1 and 0.9 < measured_y_mm / ny < 1.1):
            return f"Those differ from the nominal {nx:.1f} x {ny:.1f} mm by more than 10%; not applied."
        scale = (round(measured_x_mm / nx, 6), round(measured_y_mm / ny, 6))
        await h.set_board(BoardInfo(dictionary=h.store.board.dictionary, print_scale=scale))
        runtime.write_board_file()
        return f"Print scale set to x {scale[0]:.5f}, y {scale[1]:.5f}; the phone and later analyses use it."


def _describe(r: PhotoRequest, store=None) -> str:
    parts = [f"{r.id} [{r.state}]"]
    if r.target:
        e = r.target.eye
        parts.append(f"eye ({e[0]:.0f}, {e[1]:.0f}, {e[2]:.0f}) -> look_at {tuple(r.target.look_at)}, "
                     f"{r.target.distance_mm:.0f} mm, lens {r.options.lens}")
    elif r.kind == "freeform":
        parts.append(f"freeform (whole page in view), lens {r.options.lens}")
    else:
        parts.append(f"free framing, lens {r.options.lens}")
    if r.note:
        parts.append(f'note "{r.note}"')
    if r.placement:
        parts.append(f"placement {r.placement.label}")
    line = " ".join(parts)
    for w in r.preflight:
        line += f"\n    warning: {w}"
    if r.skip_reason:
        line += f"\n    skipped: {r.skip_reason}"
    if store is not None:
        for cid in r.capture_ids:
            line += "\n    " + _capture_line(store, r.id, cid)
    return line


def _capture_line(store, rid: str, cid: str) -> str:
    folder = store.capture_dir(rid, cid)
    meta = store.capture_meta(rid, cid) or {}
    a = store.capture_analysis(rid, cid)
    img = meta.get("image", {})
    s = (f"capture {cid}: {folder / img.get('file', '?')} ({img.get('w')}x{img.get('h')}, "
         f"rotate {img.get('upright_rotation_cw_deg', 0)} cw to view), path {meta.get('path')}, "
         f"pose {meta.get('pose', {}).get('source')}")
    if a is None:
        s += ", analysis pending"
    elif a.get("error"):
        s += f", analysis failed: {a['error']}"
    elif a.get("pnp"):
        p = a["pnp"]
        s += f", still PnP {a['markers_used']} markers rms {p['rms_px']} px"
        if "phone_vs_pnp" in a:
            s += f", phone vs PnP {a['phone_vs_pnp']['dt_mm']} mm / {a['phone_vs_pnp']['dr_deg']} deg"
    else:
        s += f", no page pose in the still ({a.get('markers_detected', 0)} markers seen)"
    return s + f"; meta {Path(folder) / 'meta.json'}"
