"""Advertise the server as _agentcam._tcp so the phone finds it without an address.

Uses macOS's own mDNSResponder through `dns-sd -R` rather than a Python mDNS
stack (no second responder fighting for port 5353). The child's stdout goes to
DEVNULL: an MCP stdio server's stdout is the protocol stream.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import subprocess

log = logging.getLogger(__name__)

SERVICE_TYPE = "_agentcam._tcp"


def local_host_name() -> str:
    """The Mac's Bonjour name (e.g. Honeypot.local), which the phone resolves itself."""
    try:
        name = subprocess.run(["scutil", "--get", "LocalHostName"], capture_output=True, text=True,
                              timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        name = ""
    return f"{name or socket.gethostname().split('.')[0]}.local"


class Advertisement:
    def __init__(self, port: int, server_id: str):
        self.port, self.server_id = port, server_id
        self.host = local_host_name()
        self._proc: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        name = f"AgentCam on {self.host.removesuffix('.local')}"
        try:
            self._proc = await asyncio.create_subprocess_exec(
                "dns-sd", "-R", name, SERVICE_TYPE, "local", str(self.port),
                f"host={self.host}", f"port={self.port}", f"server_id={self.server_id}", "v=1",
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL)
            log.info("advertising %r as %s on port %d", name, SERVICE_TYPE, self.port)
        except OSError as e:
            log.warning("Bonjour advertisement unavailable (%s); the phone will need the address", e)

    async def stop(self) -> None:
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), 3)
            except TimeoutError:
                self._proc.kill()
