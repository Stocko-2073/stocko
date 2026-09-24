import socket
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import Client

from agentcam.server import build

PROTOCOL = Path(__file__).resolve().parents[2] / "protocol"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@asynccontextmanager
async def running_server(data: Path, port: int | None = None):
    """An in-process server (MCP client + the phone's HTTP API on a real port)."""
    port = port or free_port()
    async with Client(build(data, port, advertise=False)) as client:
        yield client, f"http://127.0.0.1:{port}"


def text_of(result) -> str:
    return "\n".join(c.text for c in result.content if c.type == "text")


def images_of(result) -> list:
    return [c for c in result.content if c.type == "image"]


def orbit(az: float, el: float, d: float, **kw) -> dict:
    return {"pose": {"look_at": [0, 0, 0], "orbit": {"azimuth_deg": az, "elevation_deg": el, "distance_mm": d}, **kw}}
