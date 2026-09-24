"""agentcam-mcp: a stdio MCP server that also serves the phone over the LAN.

Claude Code starts it per session (see 3d-scan/.mcp.json). stdout is the MCP
protocol stream, so everything else logs to stderr and <data>/agentcam.log.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import aiohttp
from aiohttp import web
from mcp.server.mcpserver import MCPServer

from .bonjour import Advertisement
from .hub import Hub
from .phone_api import make_app
from .store import AlreadyRunning, Store, write_json
from .tools import INSTRUCTIONS, register

log = logging.getLogger("agentcam")

# 3d-scan/captures, next to the checkout.
DEFAULT_DATA = Path(__file__).resolve().parents[4] / "captures"
DEFAULT_PORT = 47815


class Runtime:
    def __init__(self, data: Path, port: int, advertise: bool = True):
        self.data, self.port, self.advertise = data, port, advertise
        self.hub: Hub | None = None
        self.error: str | None = None
        self.address = f"<this Mac>:{port}"

    def write_board_file(self) -> Path:
        b = self.hub.board
        path = self.data / "board_page_frame.json"
        write_json(path, {"frame": "page: mm, origin page centre, +x right, +y toward marker 0's edge, +z up; "
                                   "corners TL, TR, BR, BL as printed",
                          **b.describe(),
                          "markers": [{"id": i, "corners": c.round(4).tolist()} for i, c in sorted(b.corners.items())]})
        return path

    @asynccontextmanager
    async def lifespan(self, _server: MCPServer):
        self.data.mkdir(parents=True, exist_ok=True)
        try:
            store = Store(self.data)
        except AlreadyRunning as e:
            # Stay up so the agent gets a clear message from every tool.
            self.error = f"{e}. Only one Claude Code session can run AgentCam at a time."
            log.error(self.error)
            yield self
            return
        self.hub = Hub(store, server_id=uuid.uuid4().hex[:12])
        runner = web.AppRunner(make_app(self.hub), access_log=None, handle_signals=False)
        await runner.setup()
        try:
            await web.TCPSite(runner, host=None, port=self.port).start()   # IPv4 and IPv6
        except OSError as e:
            self.error = f"could not listen on port {self.port}: {e}"
            log.error(self.error)
            await runner.cleanup()
            store.close()
            yield self
            return
        if not await self._answers_as_us():
            # aiohttp binds with SO_REUSEADDR, so a program already on 127.0.0.1:<port>
            # doesn't stop the bind, it just takes local connections.
            self.error = f"another program is already using port {self.port}; set AGENTCAM_PORT in .mcp.json"
            log.error(self.error)
            await runner.cleanup()
            store.close()
            yield self
            return
        ad = Advertisement(self.port, self.hub.server_id)
        self.address = f"{ad.host}:{self.port}"
        if self.advertise:
            await ad.start()
        self.write_board_file()
        log.info("serving the phone on %s; data in %s", self.address, self.data)
        try:
            yield self
        finally:
            await ad.stop()
            await self.hub.close()
            await runner.cleanup()
            store.close()


    async def _answers_as_us(self) -> bool:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as s, \
                    s.get(f"http://127.0.0.1:{self.port}/v1/health") as r:
                return (await r.json()).get("server_id") == self.hub.server_id
        except (aiohttp.ClientError, TimeoutError, ValueError):
            return False


def build(data: Path, port: int, advertise: bool = True) -> MCPServer:
    runtime = Runtime(data, port, advertise)
    mcp = MCPServer("agentcam", instructions=INSTRUCTIONS, lifespan=runtime.lifespan)
    register(mcp, runtime)
    return mcp


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=Path(os.environ.get("AGENTCAM_DATA") or DEFAULT_DATA))
    p.add_argument("--port", type=int, default=int(os.environ.get("AGENTCAM_PORT") or DEFAULT_PORT))
    p.add_argument("--no-bonjour", action="store_true", help="don't advertise over Bonjour (tests)")
    args = p.parse_args(argv)
    data = args.data.resolve()
    data.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stderr), logging.FileHandler(data / "agentcam.log")])
    build(data, args.port, advertise=not args.no_bonjour).run("stdio")


if __name__ == "__main__":
    main()
