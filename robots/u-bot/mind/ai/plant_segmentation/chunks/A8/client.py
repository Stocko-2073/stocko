"""A8 — a minimal MCP stdio client, used by the end-to-end run and the tests.

It speaks the wire protocol, in a subprocess, over pipes: nothing in here
imports the server's Python. That is the point — if `run_a8.py` produced its
artifacts by calling `a8_tools.plan_removals` directly, "callable as an MCP
tool" would be an untested claim.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "server.py")


class MCPError(RuntimeError):
    pass


class StdioClient:
    """One MCP session over one subprocess."""

    def __init__(self, python: str | None = None, server: str = SERVER,
                 env: dict | None = None):
        self.python = python or sys.executable
        self.server = server
        self._env = env
        self.proc = None
        self._id = 0
        self.server_info = None
        self.instructions = None

    # ----------------------------------------------------------- lifecycle
    def __enter__(self):
        self.proc = subprocess.Popen(
            [self.python, self.server], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            bufsize=1, env=self._env)
        init = self.request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "a8-test-client", "version": "0.1.0"}})
        self.server_info = init["serverInfo"]
        self.instructions = init.get("instructions")
        self.notify("notifications/initialized")
        return self

    def __exit__(self, *exc):
        if self.proc:
            try:
                self.proc.stdin.close()
            except Exception:
                pass
            self.proc.wait(timeout=30)

    # ------------------------------------------------------------- protocol
    def _send(self, obj):
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def notify(self, method, params=None):
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def request(self, method, params=None):
        self._id += 1
        self._send({"jsonrpc": "2.0", "id": self._id, "method": method,
                    "params": params or {}})
        line = self.proc.stdout.readline()
        if not line:
            err = self.proc.stderr.read()
            raise MCPError(f"server closed the pipe during {method!r}: {err}")
        rsp = json.loads(line)
        if "error" in rsp:
            raise MCPError(f"{method}: {rsp['error']}")
        return rsp["result"]

    # ---------------------------------------------------------------- tools
    def list_tools(self):
        return self.request("tools/list")["tools"]

    def call(self, name, arguments):
        """Returns (structured_result, is_error, text)."""
        r = self.request("tools/call", {"name": name, "arguments": arguments})
        text = "".join(c.get("text", "") for c in r.get("content", []))
        return r.get("structuredContent"), bool(r.get("isError")), text

    def call_ok(self, name, arguments):
        res, is_err, text = self.call(name, arguments)
        if is_err:
            raise MCPError(f"{name} returned isError: {text[:400]}")
        return res
