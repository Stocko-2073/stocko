"""A8 — an MCP server over stdio, in the standard library and nothing else.

Why a hand-written server rather than the `mcp` package
-------------------------------------------------------
`mcp==2.1.1` installs cleanly here, and it pulls in 20 packages (pydantic,
starlette, uvicorn, cryptography, ...). A4, A5, A6 and A7 all shipped a lock
file whose first line says the shared `chunks/A3/.venv` is reused **unchanged**,
and A8 is a ~400-line tool surface over products that are already on disk. Six
hundred megabytes of transitive dependency to speak three JSON-RPC methods is a
bad trade for a research chunk whose whole point is auditability.

So: MCP is JSON-RPC 2.0 over newline-delimited JSON on stdio, and that is what
this file implements — `initialize`, `notifications/initialized`, `tools/list`,
`tools/call`, `ping`, and nothing else, because nothing else is needed.

**The choice is verified rather than asserted.** `mcp_sdk_client.py` drives
this server with the *official* `mcp` Python client from a throwaway
client-only venv (`.venv-client`, `mcp` and its dependencies, no numpy) and
performs a real `initialize` / `tools/list` / `tools/call` session against it.
If the wire format were wrong, that client would fail. `results/mcp_conformance.json`
records what it saw. That is a stronger check than using the SDK on both ends,
where a shared bug is invisible.

Errors are errors
-----------------
A tool refusal comes back as `isError: true` with the refusal text. It is never
converted into an empty-but-plausible result. A7 lost a whole run to a
transport failure being swallowed by a safe-looking default, and wrote the
lesson down: *"a safety default that swallows a transport error produces a
plausible, safe-looking, entirely fictitious result."* An empty target list is
a meaningful answer from this server and a failed call must not be able to
imitate one.

Run:  chunks/A3/.venv/bin/python chunks/A8/server.py
"""
from __future__ import annotations

import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import a8_tools as T  # noqa: E402

PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_INFO = {"name": "weeding-perception", "version": "0.1.0",
               "title": "Garden weeding perception (Phase A)"}
INSTRUCTIONS = (
    "Two tools, in this order. `segment_garden` returns plant instances with "
    "geometry and NO crop/weed opinion. Label the instances it returns by "
    "their integer `instance_id` — never by coordinates — then pass those "
    "labels to `plan_removals`, which applies the safety gate in code and "
    "returns an ordered target list plus a rejection report. Supply each "
    "instance's label more than once, from independent looks, or the gate "
    "refuses it: one look is not evidence. Every length is in relative depth "
    "units (rdu); this image has no absolute scale and a metric tool profile "
    "is refused rather than converted. The heights are measured against the "
    "straw mulch surface, not bare soil.")


def _err(code, message, data=None):
    e = {"code": code, "message": message}
    if data is not None:
        e["data"] = data
    return e


def handle(req: dict):
    """One JSON-RPC request in, one response dict out (or None for a notify)."""
    method = req.get("method")
    rid = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        want = params.get("protocolVersion")
        version = want if want in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": INSTRUCTIONS}}

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "tools": [{"name": n, "description": t["description"],
                       "inputSchema": t["inputSchema"]}
                      for n, t in sorted(T.TOOLS.items())]}}

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            result = T.call_tool(name, args)
        except T.ToolRefusal as e:
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": f"REFUSED: {e}"}],
                "isError": True}}
        except TypeError as e:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": _err(-32602, f"invalid arguments for {name!r}: {e}")}
        except Exception as e:                                  # pragma: no cover
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text",
                             "text": f"{type(e).__name__}: {e}\n"
                                     f"{traceback.format_exc()}"}],
                "isError": True}}
        text = json.dumps(result, indent=1)
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text", "text": text}],
            "structuredContent": result,
            "isError": False}}

    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid,
            "error": _err(-32601, f"method not found: {method!r}")}


def serve(stdin=None, stdout=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                     "error": _err(-32700, f"parse error: {e}")})
                         + "\n")
            stdout.flush()
            continue
        batch = isinstance(req, list)
        reqs = req if batch else [req]
        out = [r for r in (handle(x) for x in reqs) if r is not None]
        if not out:
            continue
        stdout.write(json.dumps(out if batch else out[0]) + "\n")
        stdout.flush()


if __name__ == "__main__":
    serve()
