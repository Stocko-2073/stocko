"""On-disk state, so a server restart loses nothing.

    <root>/requests/<id>.json                 one file per request
    <root>/<request_id>/<capture_id>/...      delivered files, meta.json, analysis.json, preview.jpg
    <root>/mat.json                           marker dictionary and print scale
    <root>/.lock                              held by the running server
"""

from __future__ import annotations

import fcntl
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .models import MatInfo, PhotoRequest

SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class AlreadyRunning(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def write_json(path: Path, data) -> None:
    """Atomic: a reader never sees half a file, a crash never leaves one."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    os.replace(tmp, path)


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.requests_dir = root / "requests"
        self.requests_dir.mkdir(parents=True, exist_ok=True)
        self._lock_file = open(root / ".lock", "a+")
        try:
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._lock_file.seek(0)
            holder = self._lock_file.read().strip() or "another process"
            self._lock_file.close()
            raise AlreadyRunning(f"another AgentCam server ({holder}) is using {root}") from None
        self._lock_file.seek(0)
        self._lock_file.truncate()
        self._lock_file.write(f"pid {os.getpid()}")
        self._lock_file.flush()
        self.requests: dict[str, PhotoRequest] = {}
        for p in sorted(self.requests_dir.glob("*.json")):
            r = PhotoRequest.model_validate_json(p.read_text())
            self.requests[r.id] = r
        mat = root / "mat.json"
        self.mat = MatInfo.model_validate_json(mat.read_text()) if mat.exists() else MatInfo()

    def close(self) -> None:
        if not self._lock_file.closed:
            fcntl.flock(self._lock_file, fcntl.LOCK_UN)
            self._lock_file.close()

    def next_seq(self) -> int:
        return max((r.seq for r in self.requests.values()), default=0) + 1

    def save(self, r: PhotoRequest) -> None:
        r.updated_at = now()
        self.requests[r.id] = r
        write_json(self.requests_dir / f"{r.id}.json", r.model_dump(mode="json"))

    def save_mat(self, mat: MatInfo) -> None:
        self.mat = mat
        write_json(self.root / "mat.json", mat.model_dump(mode="json"))

    def ordered(self) -> list[PhotoRequest]:
        return sorted(self.requests.values(), key=lambda r: r.seq)

    def queued(self) -> list[PhotoRequest]:
        return [r for r in self.ordered() if r.state == "queued"]

    def capture_dir(self, request_id: str, capture_id: str) -> Path:
        if not (SAFE_NAME.match(request_id) and SAFE_NAME.match(capture_id)):
            raise ValueError("bad id")
        return self.root / request_id / capture_id

    def capture_meta(self, request_id: str, capture_id: str) -> dict | None:
        p = self.capture_dir(request_id, capture_id) / "meta.json"
        return json.loads(p.read_text()) if p.exists() else None

    def capture_analysis(self, request_id: str, capture_id: str) -> dict | None:
        p = self.capture_dir(request_id, capture_id) / "analysis.json"
        return json.loads(p.read_text()) if p.exists() else None
