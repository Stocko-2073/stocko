"""The real entry point over real stdio: every tool answers, and nothing but
JSON-RPC ever reaches stdout (a stray print or access log would break it)."""

import sys

from mcp import Client, StdioServerParameters

from conftest import free_port, orbit, text_of


async def test_every_tool_over_stdio(tmp_path):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "agentcam.server", "--data", str(tmp_path), "--port", str(free_port()), "--no-bonjour"])
    async with Client(params) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        assert names == {"request_photos", "list_requests", "wait_for_photos", "get_photo", "cancel_requests",
                         "phone_status", "get_board", "set_print_scale"}
        assert "r0001" in text_of(await client.call_tool("request_photos", {"requests": [orbit(-90, 55, 380)]}))
        for name, args in [("list_requests", {}), ("phone_status", {}), ("get_board", {}),
                           ("wait_for_photos", {"timeout_s": 0.2}), ("get_photo", {"request_id": "r0001"}),
                           ("set_print_scale", {"measured_x_mm": 197.2, "measured_y_mm": 259.7}),
                           ("cancel_requests", {})]:
            r = await client.call_tool(name, args)
            assert not r.is_error, (name, text_of(r))
    assert (tmp_path / "agentcam.log").read_text()
