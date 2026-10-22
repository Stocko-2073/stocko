# Chunk A5 — Stem-soil contact points

The output the arm needs: for every component A4 produced, where its material
meets the datum, with a status that is `observed`, `extrapolated` or
`occluded` — and **no point at all** when none of those can be defended.

> **The datum is the STRAW mulch surface, not soil** (A2). Every point here is a
> point on the mulch. And in `plants.jpeg` **no stem is seen meeting the soil at
> all**: A0 found zero `visible` contact points, so the roadmap's done-criterion
> "contact-point error over `visible` GT points" is *empty* for this image. See
> `FINDINGS.md` § "enters soil vs lowest visible stem" for the decision taken.

Results and the honest account of what did not work: `FINDINGS.md`.
Bookkeeping to merge into the repo-level files: `BOOKKEEPING.md`.

## Environment

Runs in `chunks/A3/.venv` (Python 3.11, numpy 2.4.6, scipy 1.17.1, matplotlib,
PIL, pytest 9.1.1). **A5 added nothing to it** — no new dependency, no new model
weights, no new venv.

```bash
cd chunks/A5
V=../A3/.venv/bin/python
$V run_a5.py          # ~4 s   -> products/contacts_{split,merge,gt_instances}.json
$V diagnostics.py     # ~15 s  -> results/diagnostics.json + the RESULTS.md tables
$V sweeps.py          # ~60 s  -> results/sweeps.json (incl. the (b) constant's sweep)
$V figures.py         # ~30 s  -> figs/
$V -m pytest test_a5.py -q     # 25 assertions
```

## Inputs

| what | where | note |
|---|---|---|
| components | `chunks/A4/a4_api.load_a4(tag=…)` | **both** policies: `default` (`split`, 742 components on the depth grid) and `merge` (207). `unresolved_for()` is read before any component's extent is trusted |
| datum + heights | `chunks/A2/a2_api.load_a2()` | `height_above_soil`, `height_sigma`, `coverage_class`, `ground_inliers`, `soil_surface_depth`; native 1344×1008, never resampled |
| float depth | `chunks/A1/products/MANIFEST.json` → `primary_raster` | back-projected with the manifest camera in `scale_free` mode |
| material | `chunks/A3` via A4's cache `chunks/A4/work/a3_material.npz` | lifted to the depth grid by nearest neighbour, exactly as A4 does |
| ground truth | `groundtruth/` via `chunks/A0/eval.py` | used **only** as a labelled diagnostic — A0's ten points are `estimated` |

## Files

| File | Role |
|---|---|
| `a5_common.py` | `load_scene()` — depth, datum, normals and the 3-D material/surface rasters on one grid; grid conversions; A2's two geometry helpers reused verbatim so A5's height field *is* A2's (agrees to 5.3e-5 rdu = 0.01 σ) |
| `contact_points.py` | the algorithm and the whole status decision. Every constant is module-level with its R1 category |
| `run_a5.py` | runs both A4 policies plus the GT-instance-mask oracle, writes the products |
| `diagnostics.py` | counts, the circularity check, the GT-consistency diagnostic, policy disagreement, and A0's `eval.py` fed A5's points |
| `sweeps.py` | the (b) placeholder's sweep, four convention sweeps, and the extrapolation-distance CDF C3 should read its budget off |
| `figures.py` | six figures, every one carrying the datum caveat in its title |
| `a5_api.py` | **the loader A8 should import.** `load_a5(policy=…)`, `admissible()` |
| `test_a5.py` | 25 tests, mostly on a synthetic scene with known geometry, because the property under test is a refusal |

## The decision rule, in one place

Let `σ_c = sqrt(σ_datum² + height_sigma²)` at the pixel, and `h` be the height
of the component's lowest distinguishable material above A2's datum.

| condition | status |
|---|---|
| `h < −3·σ_c` | **occluded** — material below the ground is the *surface* being wrong |
| `\|h\| ≤ 3·σ_c` | **observed** — the material is inside the datum's own ground band |
| axis measurable, reaches the datum within the tool budget | **extrapolated**, with distance, lateral wander and confidence |
| anything else | **occluded**, with the reason in words, and `point: null` |

`lowest_visible_point` is emitted regardless, because it is an observation.
