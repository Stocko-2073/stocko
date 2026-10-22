# Chunk A4 — Grouping by connectivity, not distance

Replaces ZeroPlantSeg's DBSCAN-over-leaf-root-points with a graph over plant
material whose edges assert **physical contiguity in 3-D**. Results and the
honest account of what did not work: `FINDINGS.md`. Bookkeeping to be merged
into the repo-level files: `BOOKKEEPING.md`.

**There is no spacing constant anywhere in the code path**, and `test_a4.py`
enforces it by parsing the source.

## Environment

Runs in `chunks/A3/.venv` (Python 3.11, numpy 2.4.6, scipy 1.17.1,
scikit-learn 1.9.0, matplotlib, PIL, torch 2.13 on MPS). **A4 added `pytest`
9.1.1 to that venv and changed nothing else**; `requirements.lock.txt` here is
that venv's freeze after the addition. No new venv, no new model weights.

```bash
cd chunks/A4
../A3/.venv/bin/python -m pytest test_a4.py -q      # 16 assertions
```

## Inputs

| what | where | note |
|---|---|---|
| float depth | `chunks/A1/products/MANIFEST.json` → `primary_raster` (1344×1008) | **never resampled**; the 8-bit preview is forbidden here (A1: it flattens 75 % of adjacent-pixel differences) |
| datum | `chunks/A2/products/soil_surface_depth.npy` | subtracted before any continuity test, as A2 instructed |
| material | `chunks/A3/a3_api.segment_material()` | cached to `work/a3_material.npz` on first run |
| partition | `chunks/A3/work/regions_a3f.npy` | A3's independent SAM run (ceiling 0.9246). **A0's own partition is not used** — its ceiling is exactly 1.0 |
| ground truth | `groundtruth/` via `chunks/A0/eval.py` | the scorer of record |

If `chunks/A3/work/` has been cleaned, rebuild it first per `chunks/A3/README.md`
(SAM ~13 min, DINOv2 ~5 s).

## Rebuild, in order

```bash
cd chunks/A4
V=../A3/.venv/bin/python

$V diagnostics.py            # ~15 s  ceilings, statistic comparison, oracle-edge bound
$V run_a4.py                 # ~20 s  the shipped run  -> products/, results/a4_scores_default.json
$V run_a4.py --unresolved-policy merge --tag merge     # the R2 variant
$V run_a4.py --oracle-material                         # diagnostic: A0 material instead of A3
$V sweeps.py                 # ~90 s  tolerance / quantile / statistic / node / min-size
$V report.py                 # ~40 s  the three verdicts + Open Question 2
$V figures.py                # ~20 s  figs/
$V -m pytest test_a4.py -q
```

Total ~3.5 minutes with A3's cache warm. Everything is deterministic except the
figure colour jitter (seeded).

## Files

| file | role |
|---|---|
| `a4_api.py` | **the loader A5 / A6 / A7 should import.** Components, unresolved edges, `unresolved_for(component)` |
| `a4_common.py` | grids, inputs, and every registered constant in one place |
| `a4_graph.py` | the chunk: fragments, surface fits, boundary residuals, the three-way verdict, union-find |
| `unresolved.py` | the three kinds of unresolved edge; nothing here decides anything |
| `run_a4.py` | build + score + write products |
| `report.py` | the three roadmap verdicts and Open Question 2 |
| `diagnostics.py` | the measurements that decided the design (ceilings, statistic AUCs, oracle bound) |
| `sweeps.py` | every knob, moved over decades |
| `fast_eval.py` | vectorised twin of `eval.py`'s instance metrics, for the sweeps only; `test_a4.py` asserts they agree exactly |
| `figures.py` | the four figures |
| `test_a4.py` | 16 assertions, including the no-spacing-constant scan |

## Products

| file | what |
|---|---|
| `products/components_gt_grid_default.npy` / `.png` | component label map on A0's 768×1024 grid, 0 = not plant (uint16 PNG) |
| `products/components_depth_grid_default.npy` | same on the 1344×1008 depth grid |
| `products/unresolved_edges_default.json` | 11 409 edges: `ambiguous_boundary`, `occluded_by`, `leaves_frame` |
| `*_merge.*` | the same under the R2 unresolved-edge policy |
| `results/a4_scores_*.json` | full score dicts incl. provenance |
| `results/{diagnostics,sweeps,report}.json` | the tables in FINDINGS |
| `figs/fig_{components,unresolved,operating,zooms}.png` | verified by eye |

**Every product carries `scale_confidence = "scale_free"` and the A2 datum
caveat: the datum is the STRAW surface, not soil.**

## The headline, so it is not only in FINDINGS

Instance F1 **0.0088** (baseline **0.0000**); squash best IoU **0.462**
(baseline 0.425) and **not** one component; clover **stays separate**; grass
absorbed into the crop **11.8 %** (baseline **53.0 %**). The `merge` variant puts
the squash out as one component at IoU 0.885 and absorbs 83 % of the grass.
Neither meets all three roadmap targets at once. Read `FINDINGS.md` before
quoting any of these.
