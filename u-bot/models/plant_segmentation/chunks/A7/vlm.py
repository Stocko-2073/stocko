"""A7 — the VLM call.

Path used: the real `claude` CLI, non-interactively, with images on disk. It is
recorded here rather than in prose because the isolation matters more than the
call does.

**Isolation.** Every call runs with its working directory inside a scratch
*arena* that contains nothing but the render PNGs. That is deliberate: this
repository's own `CLAUDE.md` states the crop, names the weeds, spells out R2 and
R3 and points at the ground truth. A model invoked with its cwd inside the
project would read all of that as context and the experiment would be measuring
a leak. `test_a7.py::test_arena_is_isolated` asserts no `CLAUDE.md` is
reachable from the arena. Settings are pinned with `--strict-mcp-config` and the
tool surface to `Read` only.

**Reproducibility.** The exact model id, the CLI version, the full prompt text
and the raw reply are written for every call into `results/raw/`. Nothing is
re-derived later from a summary.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ARENA = os.environ.get(
    "A7_ARENA",
    "/private/tmp/claude-503/-Users-samw3-prj-Make-stocko-u-bot-models-plant-"
    "segmentation/f88ad29d-e131-4494-b946-e12ecfa37434/scratchpad/a7_arena")
MODEL = "claude-opus-5"
RAW = os.path.join(HERE, "results", "raw")


def cli_version():
    return subprocess.run(["claude", "--version"], capture_output=True,
                          text=True).stdout.strip()


def stage(paths):
    """Copy renders into the isolated arena; return their arena paths."""
    os.makedirs(ARENA, exist_ok=True)
    out = []
    for p in paths:
        d = os.path.join(ARENA, os.path.basename(p))
        if not os.path.exists(d) or os.path.getmtime(d) < os.path.getmtime(p):
            shutil.copy2(p, d)
        out.append(d)
    return out


class TransportError(RuntimeError):
    """The CLI did not answer: usage limit, timeout, crash.

    Distinct from "the model answered badly", which is `schema.py`'s business.
    A transport error is **never cached** — see `call()`.
    """


# Substrings that mark a CLI reply as a transport failure rather than an answer.
# The first is the one that actually bit: a session limit returns rc=1 with the
# limit notice sitting in the `result` field, which the first version of this
# module happily cached as if it were the model's opinion about a plant. 90 such
# records were purged; this list and the `is_error` check are why it cannot
# recur silently.
TRANSPORT_MARKERS = (
    "hit your session limit", "usage limit", "rate limit", "Please run /login",
    "Credit balance is too low", "API Error", "overloaded_error",
)


def is_transport_failure(rec):
    if rec.get("returncode") not in (0, None):
        return f"returncode {rec['returncode']}"
    if rec.get("is_error"):
        return f"is_error: {str(rec.get('result'))[:120]}"
    if rec.get("result") is None:
        return "no result field in CLI output"
    for m in TRANSPORT_MARKERS:
        if m.lower() in str(rec["result"]).lower():
            return f"transport marker {m!r}"
    return None


def call(prompt: str, key: str, timeout=600):
    """One CLI call. Returns (reply_text, meta). Cached on `key`.

    Raises `TransportError` — and writes nothing — when the CLI did not answer.
    Caching a non-answer is what corrupted the first attempt at this chunk: the
    run "completed" with 90 regions holding a usage-limit notice in place of a
    label, and `unsure` counts that were a billing artifact. A transport error
    now aborts loudly and the cache stays clean, so a re-run after the limit
    resets resumes exactly where it stopped.
    """
    os.makedirs(RAW, exist_ok=True)
    h = hashlib.sha256(prompt.encode()).hexdigest()[:12]
    cache = os.path.join(RAW, f"{key}.json")
    if os.path.exists(cache):
        rec = json.load(open(cache))
        if rec.get("prompt_sha") == h:
            why = is_transport_failure(rec)
            if why:                      # a poisoned record from an old run
                os.remove(cache)
            else:
                return rec["result"], rec
    t0 = time.time()
    proc = subprocess.run(
        ["claude", "-p", "--model", MODEL, "--output-format", "json",
         "--allowedTools", "Read", "--permission-mode", "acceptEdits",
         "--strict-mcp-config", "--mcp-config", "{\"mcpServers\": {}}"],
        input=prompt, capture_output=True, text=True, cwd=ARENA,
        timeout=timeout)
    dt = time.time() - t0
    rec = {"key": key, "model": MODEL, "cli_version": cli_version(),
           "prompt_sha": h, "prompt": prompt, "wall_s": round(dt, 2),
           "returncode": proc.returncode}
    try:
        j = json.loads(proc.stdout)
        rec["result"] = j.get("result")
        rec["cost_usd"] = j.get("total_cost_usd")
        rec["model_usage"] = j.get("modelUsage")
        rec["is_error"] = j.get("is_error")
        rec["permission_denials"] = j.get("permission_denials")
    except json.JSONDecodeError:
        rec["result"] = None
        rec["stdout"] = proc.stdout[-4000:]
        rec["stderr"] = proc.stderr[-4000:]
    why = is_transport_failure(rec)
    if why:
        raise TransportError(f"{key}: {why}")
    with open(cache, "w") as f:
        json.dump(rec, f, indent=1)
    return rec["result"], rec


if __name__ == "__main__":
    print("arena:", ARENA)
    print("cli:", cli_version(), "model:", MODEL)
    for root, dirs, files in os.walk(ARENA):
        if "CLAUDE.md" in files:
            sys.exit(f"LEAK: CLAUDE.md inside arena at {root}")
    p = os.path.abspath(ARENA)
    while p != "/":
        if os.path.exists(os.path.join(p, "CLAUDE.md")):
            sys.exit(f"LEAK: CLAUDE.md above arena at {p}")
        p = os.path.dirname(p)
    print("isolation OK: no CLAUDE.md at or above the arena")
