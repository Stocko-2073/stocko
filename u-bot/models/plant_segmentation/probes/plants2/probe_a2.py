"""Probe stage A2 — A2's soil-surface fit, unmodified, on the plants2 depth
product. Runs in chunks/A1/.venv (A2's venv). Exactly the substitution A1b's
run_stage.py makes: the A1 directory it reads and the directory it writes.

Every constant A2 measures off the image (RANSAC threshold from the local
planarity curve, lam by cross-validation, datum sigma) is re-measured here,
because that is what the chunk does per image.
"""
import sys
import time

from probe_common import P, on_path

on_path("A2", "A1")
import fit_soil_surface as FS  # noqa: E402

FS.A1 = P["A1"]          # read the probe's manifest + depth
FS.HERE = P["A2"]        # write products/ and results/ under the probe
(P["A2"] / "products").mkdir(exist_ok=True)
(P["A2"] / "results").mkdir(exist_ok=True)
t0 = time.time()
sys.argv = ["fit_soil_surface.py", "--product", "primary_raster", "--out", "primary_raster"]
FS.main()
print(f"A2 probe done in {time.time()-t0:.0f}s")
