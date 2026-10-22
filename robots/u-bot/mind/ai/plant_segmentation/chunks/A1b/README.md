# A1b — assumed intrinsics, bounded rather than hidden

`plants.jpeg` has no EXIF and the camera belongs to someone else, so the
intrinsics are assumed. This chunk makes the assumption explicit, tries to
refine it from the scene, **finds that it cannot be refined**, and bounds what
it costs by re-running A2 → A4 → A5 across nine focal lengths.

Deliverable: **`calib/plants_assumed.json`**. Findings: **`FINDINGS.md`**.
Bookkeeping to merge into the repo-level files: **`BOOKKEEPING.md`**.

> Everything here is `scale_free` and in **rdu** (1 rdu = median scene depth).
> The datum in every A2/A4/A5 number is the **STRAW mulch surface**, not soil.
> **Absolute scale is UNRESOLVED and this chunk does not resolve it.**

## The one-line result

Changing `f` while holding the depth raster fixed maps the point cloud by the
linear map `diag(f0/f1, f0/f1, 1)`. Linear maps take planes to planes, so
**planarity cannot see `f` at all** — and the whole Phase A stack turns out to
be either exactly invariant under that map or invariant up to a units factor.
A1b adopts **f = 4453 px at 3000×4000** (DA3's own res-504 estimate — the camera
every shipped Phase A product already used), because the scene cannot adjudicate
between that and the 26 mm-equivalent prior of 3005 px.

## Environment

No new dependencies and no new venv. Two existing ones are used, each for the
chunk it belongs to:

| stage | venv | why |
|---|---|---|
| refinement, normals, principal point, A2 re-fits, figures, tests | `chunks/A1/.venv` | A2 shipped and ran here |
| A4 + A5 re-runs | `chunks/A3/.venv` | A4's README: A4 and A5 both run here |

## Rebuild, in order

```bash
cd <repo>/models/plant_segmentation
V1=chunks/A1/.venv/bin/python
V3=chunks/A3/.venv/bin/python

$V1 chunks/A1b/refine_focal.py            # ~10 s  -> results/focal_refinement.json
$V1 chunks/A1b/normal_reconciliation.py   # ~6 min -> results/normal_reconciliation.json
$V1 chunks/A1b/principal_point.py         # ~2 min -> results/principal_point_sweep.json
$V1 chunks/A1b/make_calib.py              #        -> calib/plants_assumed.json

# the reference row: A1's own camera. Must reproduce RESULTS.md exactly.
$V1 chunks/A1b/run_stage.py --aspect manifest --stage a2     # ~6 min
$V3 chunks/A1b/run_stage.py --aspect manifest --stage a45    # ~1 min

# the sweep. SEED= transports A2's RANSAC seed plane from the reference row --
# see FINDINGS "the RANSAC seed lottery"; without it four of the nine rows
# diverge for a reason that has nothing to do with the focal length.
SEED="--seed-plane-from chunks/A1b/work/manifest/results/fit_report_primary_raster.json \
      --seed-plane-fx 4453.214615110367 --seed-plane-fy 4492.415170820932"
for f in 1502 2774 3005 3236 4159 4453 4489 4695 6009; do
  $V1 chunks/A1b/run_stage.py --f $f --stage a2 $SEED &     # ~6-15 min each
done; wait
for f in 1502 2774 3005 3236 4159 4453 4489 4695 6009; do
  $V3 chunks/A1b/run_stage.py --f $f --stage a45
done

# the free-seed sweep, kept as the evidence for the RANSAC-seed finding
for f in 1502 2774 3005 3236 4159 4453 4489 4695 6009; do
  $V1 chunks/A1b/run_stage.py --f $f --stage a2 --tag-suffix _freeseed &
done; wait

$V1 chunks/A1b/aggregate.py               # -> results/sensitivity.json + .md
$V1 chunks/A1b/figures.py                 # -> figs/
$V1 -m pytest chunks/A1b/test_a1b.py -q
```

`work/` holds one full set of A2/A4 products per focal length (~900 MB) and is
gitignored; everything needed to rebuild it is above.

## Files

| file | role |
|---|---|
| `a1b_common.py` | the assumed camera, the candidate set, and the algebra the whole chunk rests on. Read the module docstring first. |
| `refine_focal.py` | the refinement the roadmap asked for, on both A1 depth products, in three normalisations — plus the synthetic control with a **known** `f` that proves the estimator has no power |
| `normal_reconciliation.py` | A2's 7.6° plane-normal disagreement as a function of `f`, three ways (closed form / least squares / RANSAC) |
| `principal_point.py` | the other two (d) constants: the principal-point sweep, and why distortion cannot be bounded from this image |
| `run_stage.py` | re-runs A2 (and then A4 + A5) at one assumed focal length. Drives the shipped chunks; forks nothing |
| `aggregate.py` | the sensitivity table and the invariance verdict, both computed rather than asserted |
| `make_calib.py` | writes `calib/plants_assumed.json` |
| `figures.py` | four figures, all checked by eye |
| `test_a1b.py` | 15 tests. The load-bearing ones assert the algebra, the degeneracy, and that nothing here can present an assumed camera as measured |

## Products

| file | what |
|---|---|
| `../../calib/plants_assumed.json` | **the deliverable.** Camera, provenance, the refinement curve, the sweep set, the scale statement |
| `results/focal_refinement.json` | the full curve, 72 focal lengths × 2 products × 3 normalisations, with a bootstrap band and both controls |
| `results/normal_reconciliation.json` | the 7.6° disagreement vs `f` |
| `results/principal_point_sweep.json` | principal-point sensitivity; the distortion statement |
| `results/stage_<row>.json` | one row of the sweep: A2 fit quality, A4 both policies with the three verdicts, A5 both policies with statuses and the GT-consistency diagnostic |
| `results/sensitivity.json`, `results/sensitivity_table.md` | the table and the verdicts |
| `figs/fig_{refinement,shape,normals,sensitivity}.png` | |

## What NOT to read this chunk as saying

* Not a calibration. `provenance` is `assumed+refined`, and "refined" records
  that a refinement was **run**, not that it succeeded. It did not.
* Not a scale. Nothing in `calib/plants_assumed.json` makes a metric claim, and
  `depth_to_cloud` flags anything built with it `assumed_scale`.
* Not a reason to re-score Phase A. The reference row reproduces every shipped
  number exactly, because A1b's chosen `f` **is** the camera Phase A used.
