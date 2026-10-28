"""Recordings on disk: one compressed .npz of arrays per run, plus a .json of
its metadata next to it so a directory of runs can be read without numpy.

Raw sample arrays are kept as the board sent them; conversion to physical units
happens on load (see units.py), so a wiring correction never means re-running.
"""

import datetime
import json
import subprocess
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[3] / "data"


def git_describe():
    try:
        return subprocess.run(["git", "describe", "--always", "--dirty"], capture_output=True,
                              text=True, check=True, cwd=Path(__file__).parent).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def save(recording, unit, name, meta, schedule=None, directory=DATA):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = Path(directory) / unit / f"{stamp}_{name}.npz"
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = dict(meta, unit=unit, experiment=name, saved=stamp, host_git=git_describe(),
                markers=[[t_us, label] for t_us, label in recording.markers])
    arrays = recording.arrays()
    if schedule is not None:
        arrays["schedule"] = np.asarray(schedule, np.uint16)
    np.savez_compressed(path, meta=np.array(json.dumps(meta)), **arrays)
    path.with_suffix(".json").write_text(json.dumps(meta, indent=2, default=str) + "\n")
    return path


def load(path):
    """A recording as (arrays, meta)."""
    with np.load(path) as f:
        arrays = {k: f[k] for k in f.files if k != "meta"}
        meta = json.loads(str(f["meta"]))
    return arrays, meta


def unwrap_us(t_us):
    """Board timestamps (u32 microseconds) to a monotonic int64."""
    t = np.asarray(t_us, np.int64)
    if t.size == 0:
        return t
    jumps = np.diff(t) < -(1 << 31)
    return t + np.concatenate([[0], np.cumsum(jumps)]) * (1 << 32)
