"""Runtime state shared by the MCP tools and the phone's HTTP/WebSocket API."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path

import numpy as np
from aiohttp import web
from pydantic import ValidationError

from .analysis import analyze, write_preview
from .mat import MatLayout
from .models import (PROTOCOL_VERSION, MatInfo, CaptureMetadata, Hello, PhotoRequest, PhotoRequestSpec,
                     RequestUpdate)
from .resolve import resolve
from .store import Store, now, write_json

log = logging.getLogger(__name__)

PING_INTERVAL_S = 2.0


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Hub:
    def __init__(self, store: Store, server_id: str):
        self.store = store
        self.server_id = server_id
        self.mat = MatLayout.load(store.mat.dictionary, tuple(store.mat.print_scale))
        self.phone: web.WebSocketResponse | None = None
        self.hello: Hello | None = None
        self.status: dict | None = None
        self.last_seen: float | None = None          # wall clock
        self.connected_since: float | None = None
        self.app_state = "closed"
        self.rev = 0
        self.analyzing: set[str] = set()              # capture ids still being analyzed
        self.changed = asyncio.Condition()
        self._tasks: set[asyncio.Task] = set()

    # ---- agent side ---------------------------------------------------------

    def lens_models(self) -> dict:
        return {l.id: l.model_dump() for l in self.hello.lenses} if self.hello else {}

    async def add_requests(self, specs: list[PhotoRequestSpec]) -> list[PhotoRequest]:
        """All or nothing: a bad spec rejects the whole batch (ValueError)."""
        resolved = []
        for i, spec in enumerate(specs):
            try:
                resolved.append(resolve(spec, self.mat, self.lens_models()))
            except ValueError as e:
                raise ValueError(f"request {i}: {e}") from None
        seq, stamp, out = self.store.next_seq(), now(), []
        for i, (spec, (target, warnings)) in enumerate(zip(specs, resolved)):
            r = PhotoRequest(**spec.model_dump(), id=f"r{seq + i:04d}", seq=seq + i, created_at=stamp,
                             updated_at=stamp, target=target, preflight=warnings)
            self.store.save(r)
            out.append(r)
        await self.requests_changed()
        return out

    async def cancel(self, ids: list[str] | None) -> list[str]:
        canceled = []
        for r in self.store.queued():
            if ids is None or r.id in ids:
                r.state = "canceled"
                self.store.save(r)
                canceled.append(r.id)
        if canceled:
            await self.requests_changed()
        return canceled

    async def set_mat(self, mat: MatInfo) -> None:
        self.mat = MatLayout.load(mat.dictionary, tuple(mat.print_scale))
        self.store.save_mat(mat)
        if self.phone is not None:
            await self._send(self.phone, self.welcome())

    def is_done(self, r: PhotoRequest) -> bool:
        return r.state != "queued" and not any(c in self.analyzing for c in r.capture_ids)

    async def wait_changed(self, timeout: float) -> None:
        async with self.changed:
            try:
                await asyncio.wait_for(self.changed.wait(), timeout)
            except TimeoutError:
                pass

    async def notify(self) -> None:
        async with self.changed:
            self.changed.notify_all()

    async def requests_changed(self) -> None:
        self.rev += 1
        if self.phone is not None:
            await self._send(self.phone, self.snapshot())
        await self.notify()

    # ---- phone side ---------------------------------------------------------

    def welcome(self) -> dict:
        return {"t": "welcome", "v": PROTOCOL_VERSION, "server_id": self.server_id,
                "mat": self.store.mat.model_dump(mode="json")}

    def snapshot(self) -> dict:
        return {"t": "requests", "v": PROTOCOL_VERSION, "rev": self.rev,
                "items": [r.model_dump(mode="json") for r in self.store.queued()]}

    async def _send(self, ws: web.WebSocketResponse, msg: dict) -> None:
        try:
            await ws.send_str(json.dumps(msg))
        except (ConnectionResetError, RuntimeError) as e:     # closing or closed
            log.info("send to phone failed: %s", e)

    async def serve_phone(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=10.0, max_msg_size=4 << 20)
        await ws.prepare(request)
        pinger = asyncio.create_task(self._ping(ws))
        try:
            async for msg in ws:
                if msg.type != web.WSMsgType.TEXT:
                    continue
                try:
                    await self._on_message(ws, json.loads(msg.data))
                except (ValueError, ValidationError) as e:
                    log.warning("bad message from phone: %s", e)
                    await self._send(ws, {"t": "error", "v": PROTOCOL_VERSION, "message": str(e)[:500]})
        finally:
            pinger.cancel()
            if self.phone is ws:
                self.phone = None
                # A "bye" said where it went; otherwise the connection just dropped.
                self.app_state = "disconnected" if self.app_state == "foreground" else self.app_state
                log.info("phone disconnected")
                await self.notify()
        return ws

    async def _ping(self, ws: web.WebSocketResponse) -> None:
        """App-level pings: URLSessionWebSocketTask doesn't surface WebSocket
        control frames, so the phone's watchdog listens for these."""
        while not ws.closed:
            await self._send(ws, {"t": "ping", "v": PROTOCOL_VERSION})
            await asyncio.sleep(PING_INTERVAL_S)

    async def _on_message(self, ws: web.WebSocketResponse, msg: dict) -> None:
        self.last_seen = time.time()
        t = msg.get("t")
        if t == "hello":
            hello = Hello.model_validate(msg)
            if self.phone is not None and self.phone is not ws:
                old = self.phone
                self.phone = None
                await old.close(code=4001, message=b"replaced by a newer connection")
            self.phone, self.hello, self.connected_since = ws, hello, time.time()
            self.app_state = hello.app_state
            log.info("phone connected: %s", hello.device)
            await self._send(ws, self.welcome())
            await self._send(ws, self.snapshot())
            await self.notify()
        elif ws is not self.phone:
            await self._send(ws, {"t": "error", "v": PROTOCOL_VERSION, "message": "send hello first"})
        elif t == "status":
            self.status = msg
            self.app_state = msg.get("app", self.app_state)
        elif t == "request_update":
            u = RequestUpdate.model_validate(msg)
            r = self.store.requests.get(u.id)
            if r is not None and r.state == "queued":
                r.state, r.skip_reason = "skipped", u.reason or "skipped by the user"
                self.store.save(r)
                await self.requests_changed()
        elif t == "bye":
            self.app_state = msg.get("reason", "background")
            await self.notify()
        elif t == "pong":
            pass
        else:
            raise ValueError(f"unknown message type {t!r}")

    async def commit(self, request_id: str, capture_id: str, body: dict) -> dict:
        r = self.store.requests.get(request_id)
        if r is None:
            raise web.HTTPNotFound(text=f"no request {request_id}")
        try:
            meta = CaptureMetadata.model_validate(body)
        except ValidationError as e:
            raise web.HTTPBadRequest(text=str(e)[:2000]) from None
        if meta.request_id != request_id or meta.capture_id != capture_id:
            raise web.HTTPBadRequest(text="capture_id/request_id do not match the URL")
        folder = self.store.capture_dir(request_id, capture_id)
        if (folder / "meta.json").exists():
            return {"ok": True, "duplicate": True, "request_state": r.state}
        names = {f.name for f in meta.files}
        if meta.image.file not in names:
            raise web.HTTPBadRequest(text=f"image file {meta.image.file} is not among files")
        for f in meta.files:
            path = folder / f.name
            if not path.exists():
                raise web.HTTPConflict(text=f"{f.name} has not been uploaded")
            if await asyncio.to_thread(sha256_file, path) != f.sha256:
                raise web.HTTPConflict(text=f"{f.name} does not match its sha256")
        stored = body | {"received_at": now()}
        write_json(folder / "meta.json", stored)
        if capture_id not in r.capture_ids:
            r.capture_ids.append(capture_id)
        if r.state == "queued":
            r.state = "captured"
        self.store.save(r)
        self.analyzing.add(capture_id)
        task = asyncio.create_task(self._run_analysis(request_id, capture_id, stored))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        await self.requests_changed()
        return {"ok": True, "duplicate": False, "request_state": r.state}

    async def _run_analysis(self, request_id: str, capture_id: str, meta: dict) -> None:
        folder = self.store.capture_dir(request_id, capture_id)
        try:
            analysis = await asyncio.to_thread(self._analyze, folder, meta)
        except Exception as e:                                  # never lose the capture over analysis
            log.exception("analysis of %s/%s failed", request_id, capture_id)
            analysis = {"error": f"{type(e).__name__}: {e}"}
        write_json(folder / "analysis.json", analysis)
        self.analyzing.discard(capture_id)
        await self.notify()

    def _analyze(self, folder: Path, meta: dict) -> dict:
        image = folder / meta["image"]["file"]
        k = np.array(meta["intrinsics"]["K"], float)
        phone = meta["pose"].get("camera_to_mat")
        out = analyze(image, self.mat, k, None if phone is None else np.array(phone, float))
        try:
            out["preview"] = write_preview(image, folder / "preview.jpg",
                                           meta["image"].get("upright_rotation_cw_deg", 0))
        except OSError as e:                                    # PIL can't decode it either
            out["preview_error"] = str(e)
        return out

    async def close(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        if self.phone is not None:
            await self.phone.close(code=1001, message=b"server shutting down")
