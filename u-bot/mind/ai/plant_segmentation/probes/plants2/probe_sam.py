"""Probe stage A3 step 1 — A3's independent SAM partition, same generator
settings as the shipped `a3f_` run (pps 64 / iou 0.82 / stab 0.90 / mmra 25),
on plants2.jpeg. Runs in ZeroPlantSeg/.venv from inside ZeroPlantSeg/ exactly
as chunks/A3/README.md prescribes.

`sam_regions` builds its image path inline from its ROOT, so ROOT is pointed
at the probe shadow root, where `plants.jpeg` is a symlink to plants2.jpeg.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from probe_common import CH, P, PROBE  # noqa: E402

sys.path.insert(0, str(CH["A3"]))
import sam_regions as S  # noqa: E402

assert os.path.realpath(str(PROBE / "plants.jpeg")).endswith("plants2.jpeg")
S.ROOT = str(PROBE)
S.OUT = str(P["A3"] / "work")
S.main(prefix="a3f_", pps=64, iou=0.82, stab=0.90, mmra=25)
