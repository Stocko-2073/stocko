"""A8 — conformance: drive `server.py` with the OFFICIAL `mcp` client.

`server.py` implements MCP by hand, so "it is a real MCP server" needs to be
checked by something that is not also A8's code. This script is that check. It
runs in its own throwaway venv containing `mcp` and nothing else — no numpy,
no access to the products — and speaks to the server as any MCP host would:
spawn it over stdio, `initialize`, `tools/list`, `tools/call`.

    chunks/A8/.venv-client/bin/python chunks/A8/mcp_sdk_client.py

Setup (once; recorded in README.md and PROGRESS):

    uv venv chunks/A8/.venv-client --python 3.11
    uv pip install --python chunks/A8/.venv-client/bin/python mcp

The compute venv (`chunks/A3/.venv`, shared by A3-A7) is deliberately **not**
touched: this client venv exists only so the conformance check has an
independent implementation to run.

Writes `results/mcp_conformance.json`.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SERVER_PYTHON = os.path.join(ROOT, "chunks", "A3", ".venv", "bin", "python")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402


async def main():
    params = StdioServerParameters(command=SERVER_PYTHON,
                                   args=[os.path.join(HERE, "server.py")])
    out = {"client": "official mcp python SDK",
           "mcp_version": _version(),
           "server_command": [SERVER_PYTHON, "server.py"]}
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            out["initialize"] = {
                "protocolVersion": str(init.protocol_version),
                "serverInfo": {"name": init.server_info.name,
                               "version": init.server_info.version},
                "capabilities_tools": init.capabilities.tools is not None,
                "instructions_chars": len(init.instructions or "")}
            tools = (await session.list_tools()).tools
            out["tools"] = [{"name": t.name,
                             "description_chars": len(t.description or ""),
                             "schema_properties":
                                 sorted((t.input_schema or {})
                                        .get("properties", {})),
                             "required": (t.input_schema or {}).get("required")}
                            for t in tools]

            r = await session.call_tool("segment_garden", {
                "image": os.path.join(ROOT, "plants.jpeg"),
                "include_contact_candidates": False})
            doc = json.loads(r.content[0].text)
            out["segment_garden"] = {
                "isError": bool(r.is_error),
                "n_instances": doc["n_instances"],
                "scale_confidence": doc["scale_confidence"],
                "crop_fields_all_null": all(i["crop"] is None
                                            for i in doc["instances"])}

            labels = json.load(open(os.path.join(
                HERE, "results", "labels_for_conformance.json")))
            r = await session.call_tool("plan_removals", {
                "labels": labels,
                "tool_profile": {"name": "placeholder_awaiting_C3",
                                 "clearance": 1.0e-2, "clearance_units": "rdu"}})
            doc = json.loads(r.content[0].text)
            out["plan_removals"] = {
                "isError": bool(r.is_error),
                "n_targets": len(doc["targets"]),
                "n_rejections": len(doc["rejections"]),
                "rejections_by_reason": doc["summary"]["rejections_by_reason"]}

            r = await session.call_tool("segment_garden",
                                        {"image": "/does/not/exist.jpeg"})
            out["refusal_is_an_error"] = {
                "isError": bool(r.is_error),
                "text_starts": r.content[0].text[:60]}

            r = await session.call_tool("plan_removals", {
                "labels": labels,
                "tool_profile": {"name": "tine", "clearance": 15.0,
                                 "clearance_units": "mm"}})
            doc = json.loads(r.content[0].text)
            out["metric_tool_profile"] = {
                "n_targets": len(doc["targets"]),
                "refusal": doc["summary"]["refusal"]["reason"]}

    out["verdict"] = (
        "PASS" if (out["initialize"]["serverInfo"]["name"] == "weeding-perception"
                   and len(out["tools"]) == 2
                   and out["refusal_is_an_error"]["isError"]
                   and out["metric_tool_profile"]["refusal"]
                   == "metric_tool_profile_refused") else "FAIL")
    path = os.path.join(HERE, "results", "mcp_conformance.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))
    return 0 if out["verdict"] == "PASS" else 1


def _version():
    try:
        from importlib.metadata import version
        return version("mcp")
    except Exception:                                          # pragma: no cover
        return "unknown"


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
