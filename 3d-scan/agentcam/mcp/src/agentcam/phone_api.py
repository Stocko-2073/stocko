"""The phone's side of the server: WebSocket control plus HTTP uploads.

    GET  /v1/ws                                          control channel (see hub.py)
    PUT  /v1/requests/{rid}/captures/{cid}/files/{name}  one file; header X-AgentCam-SHA256
                                                         201 stored, 200 already stored, 409 hash mismatch
    POST /v1/requests/{rid}/captures/{cid}/commit        CaptureMetadata JSON; idempotent
    GET  /v1/requests                                    queue snapshot (polling fallback)
    GET  /v1/mat, GET /v1/health
"""

from __future__ import annotations

import hashlib
import os

from aiohttp import web

from .hub import Hub, sha256_file
from .models import PROTOCOL_VERSION
from .store import SAFE_NAME

HUB = web.AppKey("hub", Hub)


def make_app(hub: Hub) -> web.Application:
    app = web.Application(client_max_size=4 << 20)
    app[HUB] = hub
    app.add_routes([
        web.get("/v1/ws", ws),
        web.put("/v1/requests/{rid}/captures/{cid}/files/{name}", put_file),
        web.post("/v1/requests/{rid}/captures/{cid}/commit", commit),
        web.get("/v1/requests", requests),
        web.get("/v1/mat", mat),
        web.get("/v1/health", health),
    ])
    return app


async def ws(request: web.Request) -> web.WebSocketResponse:
    return await request.app[HUB].serve_phone(request)


async def put_file(request: web.Request) -> web.Response:
    hub = request.app[HUB]
    rid, cid, name = (request.match_info[k] for k in ("rid", "cid", "name"))
    if not all(SAFE_NAME.match(v) for v in (rid, cid, name)) or name.endswith((".part", ".tmp")) \
            or name in ("meta.json", "analysis.json", "preview.jpg"):
        raise web.HTTPBadRequest(text="bad request, capture or file name")
    if rid not in hub.store.requests:
        raise web.HTTPNotFound(text=f"no request {rid}")
    expected = request.headers.get("X-AgentCam-SHA256", "").lower()
    if len(expected) != 64:
        raise web.HTTPBadRequest(text="X-AgentCam-SHA256 header required")
    folder = hub.store.capture_dir(rid, cid)
    folder.mkdir(parents=True, exist_ok=True)
    final = folder / name
    if final.exists():
        if sha256_file(final) == expected:
            return web.json_response({"stored": False, "reason": "already stored"}, status=200)
        raise web.HTTPConflict(text=f"{name} already stored with different content")
    part = folder / (name + ".part")
    digest, size = hashlib.sha256(), 0
    with open(part, "wb") as f:
        async for chunk in request.content.iter_chunked(1 << 20):
            digest.update(chunk)
            f.write(chunk)
            size += len(chunk)
    if digest.hexdigest() != expected:
        part.unlink(missing_ok=True)
        raise web.HTTPConflict(text=f"{name}: sha256 mismatch after {size} bytes")
    os.replace(part, final)
    return web.json_response({"stored": True, "bytes": size}, status=201)


async def commit(request: web.Request) -> web.Response:
    hub = request.app[HUB]
    try:
        body = await request.json()
    except ValueError:
        raise web.HTTPBadRequest(text="body must be JSON") from None
    return web.json_response(await hub.commit(request.match_info["rid"], request.match_info["cid"], body))


async def requests(request: web.Request) -> web.Response:
    return web.json_response(request.app[HUB].snapshot())


async def mat(request: web.Request) -> web.Response:
    hub = request.app[HUB]
    return web.json_response(hub.store.mat.model_dump(mode="json") | hub.mat.describe())


async def health(request: web.Request) -> web.Response:
    hub = request.app[HUB]
    return web.json_response({"ok": True, "v": PROTOCOL_VERSION, "server_id": hub.server_id,
                              "phone_connected": hub.phone is not None})
