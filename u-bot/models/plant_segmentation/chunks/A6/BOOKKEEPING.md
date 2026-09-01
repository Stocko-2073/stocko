# A6 — bookkeeping to merge into the repo-level files

I did not edit `RESULTS.md`, `CONSTANTS.md` or `PROGRESS.md` — A5 and A7 were
running in parallel. Below is the exact text to append to each, plus
`.gitignore` suggestions. The PROGRESS log entry uses `NNN` as the entry-number
placeholder; the manager assigns it.

---

## 1. Append to `RESULTS.md`

```markdown
## A6 — Keep-out volumes

**Ground truth:** `groundtruth/` (A0), 768×1024 · **Scorer:** A6's own coverage
and shielding measures — `chunks/A0/eval.py` scores *instances*, and a keep-out
volume is not an instance, so there is **no `eval.py` number for this chunk** and
no baseline to beat. The recorded ZeroPlantSeg baseline produces no keep-out
volume at all; the honest comparison is the **`merge` vs `split` policy pair**
below, and a **disk around the crown**, which is what A6 replaces.
**Inputs:** A4 `load_a4(tag="merge")` component 1 (A4's explicit instruction),
A2 straw datum + plane normal, A1 `primary_raster` (1344×1008 float, **never
resampled**)
**Date:** 2026-09-01 · **Scale confidence:** `scale_free`, all lengths in
**rdu**, also reported in **A2 datum-σ** (1 σ = 5.4696e-3 rdu) · **Datum: the
STRAW surface**, not soil
**Findings:** `chunks/A6/FINDINGS.md` · **Loader:** `chunks/A6/a6_api.py`

**Crop identity is A0 ground truth (instance 1, `crop: true`), an explicit
stand-in for A7**, which ran in parallel and was not available. A8 wires the
real path; nothing else in A6 knows which component is the crop (R3).

### The clearance sweep — the one constant, and what it can change

`clearance` is category **(b) tool geometry** and is a **PLACEHOLDER**: the tool
does not exist. Shipped value **1.0e-2 rdu = 1.83 datum-σ**. Retired by C3.

| clearance (rdu) | 0 | 1e-3 | 2e-3 | 5e-3 | **1e-2** | 2e-2 | 5e-2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| in datum-σ | 0 | 0.18 | 0.37 | 0.91 | **1.83** | 3.66 | 9.14 |
| volume (rdu³) | 0.1323 | 0.1323 | 0.1323 | 0.2048 | **0.2395** | 0.2956 | 0.4418 |
| datum footprint (rdu²) | 0.584 | 0.584 | 0.584 | 0.772 | **0.841** | 0.942 | 1.172 |
| **GT squash covered** | **99.44 %** | 99.69 % | 99.80 % | 99.96 % | **100.00 %** | 100 % | 100 % |
| GT squash missed (px of 433 104) | 2 426 | 1 345 | 846 | 152 | **8** | 0 | 0 |
| **GT weed material shielded** | **85.1 %** | 85.4 % | 85.7 % | 86.3 % | **87.2 %** | 89.6 % | 99.0 % |
| · grass | 95.1 % | 95.5 % | 95.7 % | 96.3 % | **97.1 %** | 98.4 % | 100 % |
| · broadleaf weed | 28.3 % | 28.5 % | 28.7 % | 29.2 % | **30.8 %** | 39.6 % | 93.0 % |
| GT straw/soil inside | 37.4 % | 40.8 % | 43.6 % | 50.3 % | **58.9 %** | 71.2 % | 92.5 % |
| whole labelled frame inside | 79.7 % | 80.9 % | 81.8 % | 83.8 % | **86.4 %** | 90.3 % | 97.7 % |
| silhouette (of the photograph) | 83.4 % | — | — | 85.4 % | **87.3 %** | — | 98.5 % |

**Over two decades of clearance, crop coverage moves 0.56 points and weed
shielding moves 14.** The clearance buys almost nothing in the direction R2
cares about and costs everything in the other one. Whatever C3 measures, the
crop is already protected; the real number only decides how much of the bed the
robot refuses to touch.

Below one voxel edge (3.5e-3 rdu) the volume and footprint rows are
resolution-limited and flat; `is_inside` is not (it uses an exact k-d tree
distance), which is why the coverage rows still move at 1e-3 and 2e-3.

### Weed material shielded — where it comes from

| | fraction of all GT weed material |
|---|---:|
| inside the keep-out @ 1e-2 rdu | **87.2 %** |
| …because **A4's `merge` component already contained it** | **74.6 pts** |
| …added by A6 (occupancy assumption + clearance) | **12.5 pts** |
| A4 inheritance, for reference: GT grass in the crop component | 83.5 % |
| A4 inheritance: GT broadleaf weed in the crop component | 24.0 % |

**Three quarters of the shielding is A4's, not A6's.** A4 recorded 83.3 % grass
absorption as a score; A6 turns it into a physical consequence.

### Gate rehearsal — GT weed contact points inside the crop's keep-out

All A0 contact points are `under_straw` / `estimated` (this image has **zero**
`visible` stems), so these are gate rehearsals, not accuracy scores.

| clearance | 0 | 1e-2 (shipped) | 5e-2 |
|---|---:|---:|---:|
| **GT weeds whose contact point is inside** | **4 of 9** | **6 of 9** | **9 of 9** |
| ids inside | 7, 8, 9, 10 | + 4, 5 | + 2, 3, 6 |

Distances from each weed's contact point to the crop material (rdu): id 10 =
0.0000, id 8 = 0.0020, id 7 = 0.0021, id 9 = 0.0022, id 4 = 0.0092, id 5 =
0.0101, id 3 = 0.0195, id 2 = 0.0214, id 6 = 0.0258.

### A radius around the crown is wrong in both directions — measured

Footprint on the datum plane @ 1e-2 rdu vs the best disk centred on A0's crown:

| | value |
|---|---:|
| keep-out footprint area | 0.841 rdu² |
| crown→footprint distance, p50 / p90 / max | 0.394 / 0.598 / 0.903 rdu |
| **equal-area disk** (r = 0.517): covers | **76.6 %** of the sprawl |
| …and 23.4 % of that disk is not plant | |
| **smallest covering disk** (r = 0.903): area | **2.10×** the footprint |
| …and 52.4 % of that disk is not plant | |

### A4 policy — `merge` (A4's instruction) vs the largest `split` component

| | `merge`, id 1 | `split`, id 37 |
|---|---:|---:|
| component size | 938 112 px (69 % of frame) | 383 426 px |
| material volume | 0.1323 rdu³ | 0.0636 rdu³ |
| **GT squash covered @ clearance 0** | **99.4 %** | **60.0 %** |
| **GT squash covered @ 5e-2 rdu (9.1 σ)** | **100 %** | **70.8 %** |
| GT weed shielded @ 1e-2 rdu | 87.2 % | 45.1 % |

**A4's instruction is vindicated, and more strongly than A4 put it.** The
largest `split` component cannot be rescued by *any* clearance in the swept
range: at nine times the placeholder it still misses 29 % of the crop. A
clearance grows a boundary; it cannot attach a leaf the grouping never found.

### Ablations

| ablation | material volume | vol @ 1e-2 | GT squash covered | GT weed shielded |
|---|---:|---:|---:|---:|
| occupancy `column` (shipped) | 0.1323 | 0.2395 | 100.00 % | 87.2 % |
| occupancy `shell` (diagnostic) | 0.0593 | 0.1717 | 99.97 % | 87.0 % |
| `include_unseen=True` (shipped) | 0.1323 | 0.2395 | 100.00 % | 87.2 % |
| `include_unseen=False` | 0.1272 | 0.2337 | 99.76 % | 85.6 % |
| voxel cell 7.0e-3 / 5.0e-3 / **3.5e-3** | 0.1792 / 0.1562 / **0.1323** | 0.2534 / 0.2441 / **0.2395** | 100 / 100 / **100 %** | 88.0 / 87.4 / **87.2 %** |

The occupancy assumption **doubles the volume (2.23×) and moves crop coverage by
0.03 points**: the ground truth is a label map, so it can only probe *observed
surfaces*, which are in both variants. **The most consequential decision in the
chunk is structurally unscorable on this evaluation substrate**, and was
therefore made on R2/R4 grounds, stated, tiered and left switchable.

### Unresolved edges (A4) → unseen volume

| kind, on the crop component | count | treatment |
|---|---:|---|
| `occluded_by` | **1 204** | the 170 fragments behind them (36 058 px, 3.8 % of the crop) enter the volume as `TIER_UNSEEN` |
| `leaves_frame` | **83** (363 380 px, 39 % of the component) | cannot become voxels — the volume is flagged `frame_open` and `classify()` returns **UNKNOWN**, never OUTSIDE, off-frame |

Nothing is extrapolated; no link is resolved (R4).

### Honesty numbers that belong next to the score

* The **floor** of this volume is A2's datum, which under the crop is **5.8 %
  observed, 92.6 % interpolated, 1.6 % extrapolated**, median per-pixel datum σ
  **8.14e-3 rdu = 1.49 datum-σ** — the *same size as the 1.83-σ placeholder
  clearance*. The tool number is not currently the dominant error term.
* `is_inside` is conservative by default (the voxel bracket, ±3.03e-3 rdu,
  resolves toward *inside*; `UNKNOWN` resolves toward *inside*). Exact-bracket
  crop coverage at clearance 0 is 99.10 % against the conservative 99.44 %.

### Runtime

~5 s to build the volume (3.5 GB peak, 351×425×279 = 41.6 M voxels), ~10 µs per
`is_inside` query, ~1 min per ray-marched silhouette. 21 tests in 4 s.

### Contact points

n/a — A6 consumes contact points, it does not produce them. That is A5.
```

---

## 2. Append to `CONSTANTS.md` → Active

```markdown
| A6 | tool clearance | 1.0e-2 rdu (1.83 datum-σ) | (b) | **PLACEHOLDER — the tool does not exist.** The only parameter of the keep-out shape, and the only length in A6's code path besides the reporting resolution. Deliberately kept in rdu: converting to millimetres needs an absolute scale this image cannot supply, so A8 must refuse the conversion rather than invent it. The shipped value is a round number in the middle of the swept range and **nothing is tuned to it** — the sweep below is what bounds the eventual real number. | 0 / 1e-3 / 2e-3 / 5e-3 / 1e-2 / 2e-2 / 5e-2 rdu (0–9.14 datum-σ) — `chunks/A6/results/a6_report.json`. Across the whole range **GT crop coverage moves 0.56 pts (99.44 → 100.00 %)** and **GT weed shielding moves 14 pts (85.1 → 99.0 %)**; volume 0.132 → 0.442 rdu³; GT weed contact points inside 4/9 → 9/9. | **C3** (actuator selection and precision budget) |
| A6 | keep-out voxel edge | 3.5e-3 rdu (0.64 datum-σ) | (a) resolution ceiling / compute budget | **Not a threshold.** Same category as A2's spline basis size: an upper bound on reported resolution, chosen so the padded grid stays inside a stated 120 M-voxel budget (41.6 M at this value). It brackets every distance by `voxel_bracket = cell·√3/2 = 3.03e-3 rdu`, and the bracket is always resolved toward *inside* (R2) and always reported. `is_inside` itself is **not** quantised by it — the distance comes from a k-d tree over boundary voxel centres. | 7.0e-3 / 5.0e-3 / 3.5e-3 rdu — `chunks/A6/results/sweeps.json` → `voxel_resolution`. Dilated volume at the placeholder moves 5.5 % over a 2× change; GT crop coverage and weed shielding move < 1 pt. | — |
```

Note for whoever merges this: A6 introduces **one (b) constant and one (a)
resolution ceiling. No (c) and no (d) constants**, and no constant that encodes
how gardens are arranged, how far apart plants grow or how large a crop gets.
`chunks/A6/test_a6.py::ALLOWED_CONSTANTS` is the machine-readable twin of the
rows above; `test_no_spacing_constant_anywhere_in_the_code_path` and
`test_the_only_length_the_shape_depends_on_is_the_clearance` enforce both
properties by parsing the source and the `build_keepout` signature.

---

## 3. Append to `PROGRESS.md` → Log (and set A6 → `done` in the status table)

```markdown
### NNN — 2026-09-01 · A6: keep-out volumes

**Chunk:** A6 — Keep-out volumes

**Done**
- Built the keep-out volume the roadmap asked for, from the crop's **own
  observed 3-D geometry**: A4's `merge` component 1 → 3-D material → vertical
  extrusion to the A2 straw datum → voxel solid → Euclidean dilation by one
  named clearance. Shipped `products/keepout_squash_merge.npz` (7.9 MB) and
  `a6_api.load_a6()`.
- **`is_inside(point)` with 21 tests**, including the ones the roadmap named:
  points on the vines and petioles rather than only the crown (> 99 % inside),
  and the safety-critical half of the "a radius is wrong" claim — crop material
  lying *outside* an equal-area disk round the crown is > 99 % inside the
  keep-out. Distance comes from a k-d tree over boundary voxel centres, so it is
  exact up to the voxel bracket; the bracket always resolves toward *inside*.
- **Everything happens in a datum-aligned rigid frame** (a rotation of the A1
  camera frame onto A2's plane normal), so no distance is ever rescaled. The
  extrusion is **vertical, never along the camera ray**: this view is 41°
  oblique and ray extrusion builds the plant's occlusion shadow, not the plant.
- **Treated A4's unresolved edges as unseen volume, not empty space**, as A4
  instructed, and split them by what they actually are: the 1 204 `occluded_by`
  links put 170 fragments (36 058 px) into the volume as a separate
  `TIER_UNSEEN`; the 83 `leaves_frame` links cannot become voxels, so the volume
  is flagged `frame_open` and `classify()` returns **UNKNOWN**, never OUTSIDE,
  for a point that projects off the photograph. Nothing is extrapolated (R4).
- Swept the placeholder clearance over two decades (0 … 5e-2 rdu = 0 … 9.14
  datum-σ), plus the occupancy assumption, the unseen halo, the voxel resolution
  and the A4 policy. Five figures, all checked by eye at full size.
- Crop identity taken from **A0 ground truth as an explicit stand-in for A7**
  (which ran in parallel), recorded in the product's own provenance string and
  asserted by a test. Nothing else in A6 knows which component is the crop (R3).

**Measured** — see `RESULTS.md`. Headline: **GT squash covered 99.44 % at zero
clearance and 100.00 % at the placeholder**; **GT weed material shielded 85.1 %
→ 87.2 %**, of which **74.6 points were already inside A4's `merge` component**;
**4 of 9 GT weed contact points are inside the keep-out before any clearance
exists**, 6 of 9 at the placeholder. An equal-area disk round the crown covers
only **76.6 %** of the sprawl and is 23 % empty; the smallest covering disk costs
**2.10×** the area and is 52 % empty. The largest `split` component tops out at
**70.8 %** crop coverage at nine times the placeholder clearance.

**Decided**
- **Build on `merge`, as A4 instructed — and report loudly what it costs.** The
  instruction is vindicated (`split` cannot be rescued by any clearance) and the
  price is that the keep-out shields 85 % of the weed material.
- **The unobserved column between a leaf and the ground is occupied.** R4
  forbids asserting unseen space is empty; R2 makes over-covering the cheap
  error. Shipped as `occupancy="column"`, with `shell` as a diagnostic.
- **`is_inside` is conservative by default and says so**: the voxel bracket and
  `UNKNOWN` both resolve toward *inside*, both switchable so A8 can measure the
  cost of the defaults.
- **The clearance is the only parameter of the shape**, enforced by a test that
  parses every A6 module for spacing-like identifiers and asserts
  `build_keepout` takes exactly three float defaults.
- **The clearance stays in rdu.** A8 must refuse a millimetre `tool_profile`
  rather than convert one.

**Surprised us**
- **The one constant the chunk is built around barely matters, and it is not the
  largest error term.** Two decades of clearance move crop coverage 0.56 points.
  Meanwhile the volume's *floor* is A2's datum, which under this crop is **92.6 %
  interpolated** with a median uncertainty of **1.49 datum-σ against a 1.83-σ
  clearance**. The number C3 was going to supply is the same size as the
  uncertainty already underneath the volume.
- **A keep-out built the way A4 asked for shields 85 % of the weeds at zero
  clearance**, and puts 4 of 9 weed stem points off-limits before any tool
  parameter exists. A4's 83.3 % grass absorption was a score; here it is a robot
  that does not weed. The safety product and the segmentation failure turn out
  to be the same object.
- **The `split` component cannot be rescued by clearance at all.** A4 warned of
  "a volume with 68 holes"; the truth is worse — at 9.1 σ the largest piece still
  misses 29 % of the crop, because a clearance grows a boundary and cannot attach
  a leaf the grouping never found. The strongest argument yet for A4's untried
  skeleton-rooted-at-the-crown.
- **The occupancy assumption doubles the volume and is invisible to every metric
  on this image.** `column` vs `shell`: 2.23× the volume, 0.03 points of crop
  coverage. A0's ground truth is a label map, so it can only probe observed
  surfaces, and observed surfaces are in both. **The most consequential decision
  in the chunk is one this evaluation substrate structurally cannot score.**
- **Ray extrusion instead of vertical extrusion is a factor-of-secant error and
  is the obvious thing to write.** "Walk from the surface to the datum along the
  same ray" was the first implementation; on a 41° oblique view it gives a median
  column of 0.364 rdu against a true height of 0.327 rdu, aimed away from the
  plant, and everything downstream still runs.
- **Rendering the keep-out silhouette by projecting voxel centres was wrong and
  looked right.** One voxel subtends 3–10 px at this camera, so the scatter left
  a lattice of holes: it reported 63.1 % of the frame occluded where ray marching
  says 83.4 %, and the holes read by eye as real gaps over the corner leaves.
  Caught only by opening the figure at full size — a 20-point error in a headline
  number, invisible in the code.

**Dependencies changed**
- **None.** A6 reuses `chunks/A3/.venv` unchanged; `chunks/A6/requirements.lock.txt`
  is a byte-identical package set to `chunks/A4/requirements.lock.txt`. No new
  package, no new weights, no model run of any kind.
- `.gitignore`: see `chunks/A6/BOOKKEEPING.md` §4.

**Next**
- **A8** gets the gate it needs: `classify()` returns OUTSIDE / INSIDE /
  **UNKNOWN** and never a coordinate-bearing opinion from a model, so R2's third
  condition is enforceable in code. Four things it must not get wrong: keep both
  conservative defaults; refuse to print or accept a metre; expect to reject 6 of
  9 GT weeds at the placeholder and report *why*; take the union over keep-plants
  as a `min` over `distance_to_material` rather than rebuilding volumes.
- **A5** should record `distance_to_crop_material_rdu` beside each contact point
  — one call, and it makes A8's rejection report explain itself.
- **A7** should know that the component it will be asked to label contains 83 %
  of the grass and 24 % of the broadleaf weed.
- **A4** — the `merge`/`split` question is now decidable on physical grounds
  rather than on instance F1, and **neither policy is acceptable**: `split`
  cannot be rescued by any clearance, `merge` shields the garden. The gap between
  them is where the skeleton-rooted-at-the-crown idea has to live.
- **A2** — the datum uncertainty under a canopy (1.49 σ, 92.6 % interpolated) is
  now load-bearing, not a diagnostic.
- **A0 / B1** — a label map can only probe observed surfaces, so the occupancy
  assumption is unscorable here. One scene captured from two viewpoints would
  turn the argument into a measurement.
- **C3** — bring a tool clearance *and* a positioning repeatability, *and* C0's
  scale, or the number cannot be used against this volume.
```

---

## 4. `.gitignore` suggestions

Append:

```gitignore
# A6: the voxel keep-out product (7.9 MB) and figures (9.3 MB).
# Rebuild in ~5 min with chunks/A6/README.md.
chunks/A6/products/*.npz
chunks/A6/figs/*.png
```

`chunks/**/*.npy` already covers `chunks/A6/products/silhouette_default_clearance.npy`.
**Keep** `chunks/A6/results/*.json` (32 KB — the sweeps and the report are the
evidence for every table in FINDINGS), the code, and `requirements.lock.txt`.

One judgement call worth flagging, the mirror of A4's: `keepout_squash_merge.npz`
is a **product**, not working data — `a6_api.load_a6()` is the interface A8 is
meant to use, and ignoring it means A8 cannot run without a 5-minute rebuild. It
is listed here only for size and it rebuilds deterministically. If the repo would
rather keep one committed product than a rebuildable one, drop that line; 7.9 MB
is the price of A8 working out of the box.
