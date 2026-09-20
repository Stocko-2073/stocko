"""Shared paths for the plants2 probe.

The probe is a SHADOW ROOT: `probes/plants2/chunks/<id>/...` mirrors the layout
of the real `chunks/<id>/products` so that each Phase A stage's loader can be
pointed here (the way A1b's `run_stage.py` did) without forking any chunk's
code and without writing into any Phase A product directory.

`probes/plants2/plants.jpeg` is a symlink to `plants2.jpeg`, for the loaders
that build the image path inline from their ROOT (A3's `sam_regions`).
"""
import os
from pathlib import Path

PROBE = Path(__file__).resolve().parent
REPO = PROBE.parent.parent
IMAGE = REPO / "plants2.jpeg"
REF_IMAGE = REPO / "plants.jpeg"

CH = {k: REPO / "chunks" / k for k in ("A0", "A1", "A1b", "A2", "A3", "A4", "A5", "A6", "A7", "A8")}
P = {k: PROBE / "chunks" / k for k in ("A1", "A2", "A3", "A4", "A5")}
FIGS = PROBE / "figs"
RESULTS = PROBE / "results"

for d in list(P.values()) + [FIGS, RESULTS]:
    d.mkdir(parents=True, exist_ok=True)

PRIMARY_GEOMETRY = "da3nested-giant-large_res504"
PRIMARY_RASTER = "da3nested-giant-large_res1344"

# A1b's adopted camera for plants.jpeg, for comparison only.
F_PLANTS_ASSUMED_PX = 4453.214615110367


def on_path(*keys):
    import sys
    for k in keys:
        s = str(CH[k])
        if s not in sys.path:
            sys.path.insert(0, s)
