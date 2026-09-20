# Probe: `plants2.jpeg` through the Phase A stack

**Not a chunk.** B1 stays `blocked` (it needs 20–50 photos to the capture
protocol). This is a one-evening, n = 1 look at what the Phase A stack does on
a second photograph, done because the photo turned up before the image set did.
Nothing here is scored — there is no ground truth for `plants2.jpeg` — and
nothing here changes a Phase A product or a Phase A number.

Read `FINDINGS.md` for what came out. This file is how it was run.

## The photo

`../../plants2.jpeg`, 3000×4000, no EXIF, same third-party source as
`plants.jpeg`. A pumpkin vine sprawling through a lawn against a white lattice
fence: three orange fruit, large lobed leaves, tall grass, ground ivy, dead
leaves, **no bare soil and no mulch anywhere**. Oblique, not overhead.

JPEG fingerprint (quantisation tables, subsampling, ICC, JFIF structure,
dimensions) is identical to `plants.jpeg`'s — consistent with the same phone,
though a messenger's re-encode would look the same, so "same delivery path" is
what is actually established.

## How it was run — a shadow root, not a fork

`probes/plants2/chunks/<id>/` mirrors the layout of `chunks/<id>/products` so
each stage's *shipped* loader can be pointed here the way `chunks/A1b/run_stage.py`
points A2/A4/A5 at `work/f<N>/`. Every stage runs the chunk's own code, imported
from `chunks/<id>/`, with exactly these substitutions:

| stage | driver | venv | substitution |
|---|---|---|---|
| A1 | `run_da3.sh`, `probe_a1.py` | `chunks/A1/.venv` | `--image plants2.jpeg --outdir …`; manifest rebuilt here with instrument constants **re-measured on this raster** |
| A2 | `probe_a2.py` | `chunks/A1/.venv` | `fit_soil_surface.A1` and `.HERE` |
| A3 | `probe_a3.py` | `chunks/A3/.venv` | `segment_material(image_path=…)`, feature cache redirected |
| A3 SAM | `probe_sam.py`, `probe_partition.py` | `ZeroPlantSeg/.venv`, then `chunks/A3/.venv` | `sam_regions.ROOT/OUT`, `a3_common.WORK` (`plants.jpeg` here is a symlink to `plants2.jpeg`) |
| A4 + A5 | `probe_a45.py` | `chunks/A3/.venv` | `a2_api.load_a2`, `a4_common.ROOT/WORK/PRODUCTS/RESULTS`, `DEPTH_RESOLUTION_FLOOR_RDU`, A3 cache pre-filled |

Not run: **A6, A7, A8.** They need a crop identity. On `plants.jpeg` that came
from the A0 ground truth (A6) and from ~$40 of VLM calls (A7). Neither exists
for this photo and a probe is not the place to invent a stand-in.

```bash
cd probes/plants2
bash run_da3.sh                                              # ~2 min, 5 DA3 runs
../../chunks/A1/.venv/bin/python probe_a1.py                 # manifest + camera comparison
../../chunks/A1/.venv/bin/python probe_a2.py                 # datum fit (slow on this scene)
../../chunks/A3/.venv/bin/python probe_a3.py                 # material probe, ~10 s
(cd ../../ZeroPlantSeg && PYTORCH_ENABLE_MPS_FALLBACK=1 PYTHONPATH=. \
   .venv/bin/python ../probes/plants2/probe_sam.py)          # SAM partition (slow)
../../chunks/A3/.venv/bin/python probe_partition.py
../../chunks/A3/.venv/bin/python probe_a45.py                # A4 both policies + A5
../../chunks/A3/.venv/bin/python spot_check.py               # by-eye boxes on the A3 map
../../chunks/A3/.venv/bin/python fig_a3.py; ../../chunks/A1/.venv/bin/python fig_a1.py
../../chunks/A3/.venv/bin/python fig_a245.py
```

## What is where

| path | what |
|---|---|
| `results/a1_camera.json` | DA3 camera-head focal estimates, per run, beside the same runs on `plants.jpeg` |
| `chunks/A1/products/MANIFEST.json` | A1-schema manifest; instrument constants re-measured, `plants.jpeg` values carried alongside for comparison |
| `results/a3_material.json`, `chunks/A3/material.npy` | the material map and its class fractions |
| `results/a3_spot_check.json`, `spot_check.py` | 15 author-placed boxes and what the probe called them. **Not ground truth.** |
| `chunks/A2/products/`, `chunks/A2/results/fit_report_primary_raster.json` | the datum fit |
| `results/a3_partition.json` | SAM region count |
| `results/a45.json`, `chunks/A4/products/`, `chunks/A5/products/` | A4 components (both policies), A5 contact points |
| `figs/` | one figure per stage |

Bulk arrays are gitignored (`.gitignore` here); everything above rebuilds from
the commands in ~40 minutes.
