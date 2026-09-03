# A2 — bookkeeping for the manager to apply

Three blocks, to be appended verbatim to `RESULTS.md`, `CONSTANTS.md` and
`PROGRESS.md`. A2 did **not** edit those files.

Two notes that are not any of the three:

- **`.gitignore`** may want a line for `chunks/A2/products*/` (40 MB of float32
  rasters across the two product directories) and `chunks/A2/results/*.png`
  (14 MB of figures). Both rebuild in about 10 minutes from
  `chunks/A2/README.md`. A2 did not edit `.gitignore` — if A0 or A1b also
  touched it, merge the hunks.
- **No dependency changes.** A2 runs entirely inside `chunks/A1/.venv`
  (numpy 2.4.6, scipy 1.17.1, matplotlib, pillow — all already present). No new
  packages, no new model weights, no torch.

---

## (1) Append to `RESULTS.md`

```markdown
## A2 — Soil surface and height above soil

**Input:** A1 `primary_raster` (DA3 nested-giant @ res 1344, 1344×1008) via
`chunks/A1/products/MANIFEST.json`, back-projected with the res-504 camera
rescaled, as that manifest requires. Cross-checked on A1 `primary_geometry`.
**Date:** 2026-09-01 · **Scale confidence:** `scale_free` — all distances in
**rdu**. No metric claim.
**Datum:** the **straw mulch surface**, not bare soil. Every height is offset
from height-above-soil by the straw depth, which one photograph cannot measure.

### Fit quality

| Quantity | Value |
|---|---|
| Ground inlier fraction | **29.1 %** (394 340 / 1 354 752 px) |
| Inlier residual RMS | **6.85e-3 rdu** (MAD 6.21e-3, p95 abs 1.43e-2) |
| Same inliers against a single RANSAC plane | 1.41e-2 rdu |
| **Smooth field vs. plane** | **51 % lower residual** |
| Datum roughness σ (below-surface estimator) | **5.47e-3 rdu** |
| Fitted datum − plane | RMS 1.89e-2 rdu; peak-to-peak 0.143 rdu = **26 σ** |
| Datum tilt away from the plane | median 5.9°, p90 14.3°, max 60.9° |
| Effective d.o.f. / fit scale | 63 / **147 px** |
| Cross-validated `lam` | **316** (canopy-hole hold-out); 31.6 with block CV |

### Coverage — observed vs. interpolated

| Class | Fraction |
|---|---|
| observed (a ground inlier) | **29.1 %** |
| interpolated (within the measured trust distance) | **69.8 %** |
| extrapolated (beyond it) | **1.1 %** |
| valid | 98.9 % |

Support distance to the nearest ground observation: p50 16 px, p90 125 px,
p99 245 px, max 349 px. Occlusion is one connected sheet — 69.2 % of the frame
is a single component with no ground inside it — so it is reported by depth:
47.2 % of the frame is more than 20 px from any ground observation, 19.1 % more
than 80 px, 1.1 % beyond the trust distance in two regions, both touching the
frame edge.

### The cost of interpolating under canopy — measured, not assumed

Ground blanked inside disks of radius 20/40/80/160 px, surface refitted, error
scored on the hidden pixels:

| support distance (px) | 0–5 | 10–20 | 40–60 | 80–120 | 160–240 |
|---|---|---|---|---|---|
| gap-fill RMS (rdu) | 7.0e-3 | 7.5e-3 | 8.2e-3 | 8.9e-3 | 1.33e-2 |
| in datum σ | 1.3 | 1.4 | 1.5 | 1.6 | 2.4 |

It never reached the 3σ ground band inside the radii tested, so the trust
distance is published as **≥ 240 px — a lower bound set by the largest disk
measured**, not a resolved value. Shipped per-pixel as `height_sigma.npy`.

### Sensitivity

| Swept | Range | Effect |
|---|---|---|
| RANSAC threshold | 1×–30× (5.4e-4 → 1.6e-2 rdu) | plane normal moves **< 1°** |
| RANSAC threshold | 100×–300× | normal jumps **36°** — RANSAC finds canopy, not ground |
| Ground band | 2σ–5σ | inlier fraction 22.8–32.4 %; surface moves ≤ 1.0e-2 rdu (1.8σ) |
| Spline basis | 24×32 → 16×21 | surface moves 2.0e-3 rdu (0.36σ) — `lam`, not the basis, decides |
| A1 depth product | res 1344 vs res 504 | heights r = **0.975**, raw-rdu gain 1.048, ground-mask IoU 0.80, but **plane normals differ by 7.6°** |

### By-eye check, quantified (hand-placed boxes, not ground truth)

| material | median height | in datum σ |
|---|---|---|
| straw (the datum) | +0.0001 rdu | **0** |
| low broadleaf weed ("clover") | +0.040 rdu | **7** |
| squash fruit | +0.119 rdu | 22 |
| grass blade | +0.286 rdu | **52** |
| squash leaf | +0.511 rdu | **93** |

The roadmap's acceptance test — clover just above the datum, grass mid-band,
squash canopy high — **passes**, by 7× and 1.8× margins with the straw pinned at
zero. Figures: `chunks/A2/results/fig_height_overlay_primary_raster.png`,
`fig_zooms_primary_raster.png`, `fig_material_boxes.png`.

### Not scored against ground truth

**A0 does not exist yet**, so there is no per-class IoU, no instance F1 and no
contact-point error in this block, and the material table above is a hand-placed
sample checked by eye — not a labelled set. Every number here is internal:
hold-out against hidden ground, sweep against sweep, depth product against depth
product. Nothing in A2 was compared against the ZeroPlantSeg baseline, which
produces no soil surface to compare with.
```

---

## (2) Append to `CONSTANTS.md` → Active table

```markdown
| A2 | RANSAC inlier threshold | 5.446e-4 rdu | (a) | A1's local-planarity p10 at win33, re-measured on `primary_raster` under the manifest camera (A1's registered 5.674e-4 was computed under that product's own, physically-impossible camera). Seeds the plane only. | 1×/3×/10×/30×/100×/300× — normal stable to <1° over 30×, jumps 36° at 100× where RANSAC latches onto canopy. `results/fit_report_primary_raster.json` → `ransac.threshold_sweep` | C0 |
| A2 | local-planarity σ, win 49 / 65 / 97 / 129 | 8.77e-4 / 1.558e-3 / 4.72e-3 / 6.01e-3 rdu | (a) | A1's win-3…33 curve extended to the windows A2 actually fits over (fit scale 147 px). Same estimator, same raster, new windows. | the curve itself is the sweep | C0 |
| A2 | datum roughness σ | 5.47e-3 rdu | (c) | Robust scale of the ground residual, estimated from the **below-surface half only** — nothing in a scene lies under the ground, so that half cannot contain canopy. Agrees to 10 % with the (a) local-planarity p10 read at the same 147 px scale. **This is the natural unit for every height question downstream.** | band sweep 2–5σ | — |
| A2 | spline smoothing `lam` | 316 | (c) | 5-fold cross-validation on the inliers, holding out compact disks sized to this scene's measured canopy holes. A block design on the same data picks 31.6, ten times rougher; both curves recorded. | `cross_validation.curve_lam_rmse_gap` / `_block` | — |
| A2 | residual autocorrelation range | 40 px | (c) | Exponential variogram model fitted to the ground residual raster over lags ≤ 60 px. Sets the block-CV block size. | n/a | — |
| A2 | CV hold-out disk radii | 38.6 / 85.2 / 148.8 px | (c) | p50/p75/p90 of the distance from a non-ground pixel to the nearest ground observation, i.e. the hole sizes this image actually contains. Chooses a smoothing parameter; never used as a threshold. | n/a | B1 re-measures per scene |
| A2 | trust distance for the interpolated datum | ≥ 240 px | (c) | Support distance at which the **measured** gap-fill error would exceed the ground band. Never reached inside the radii tested, so this is a lower bound, and it is reported as one. | radii 20/40/80/160 px, `holdout_error_vs_support` | C1 (re-observation) |
| A2 | ground band multiplier | 3 σ | (c) convention | Ground = within 3 datum-σ of the current surface. Documented and swappable. | 2/3/4/5σ: inlier fraction 22.8–32.4 %, surface moves ≤1.0e-2 rdu (1.8σ) | — |
| A2 | bisquare tuning constant | 4.685 | (c) convention | The standard 95 %-efficiency constant of Tukey's bisquare, multiplying a MAD re-measured each IRLS iteration. Not tuned here. | n/a | — |
| A2 | spline basis size | 24 × 32 segments | (c) resolution ceiling | An upper bound on resolution, not a tuning: the penalty sets the effective smoothness. | halved to 16×21 → surface moves 2.0e-3 rdu (0.36σ) | — |
```

---

## (3) Append to `PROGRESS.md`

Status table: set the A2 row to

```markdown
| A2 | Soil surface and height above soil | A1 | done | `chunks/A2/FINDINGS.md` |
```

Log entry (append at the bottom):

```markdown
### 003 — 2026-09-01 · A2: soil surface and height above soil

**Chunk:** A2

**Done**
- Fitted the datum as a **robust smooth height field**, not a plane: RANSAC
  plane for the initial estimate, then a penalised tensor-product cubic B-spline
  (2nd-difference penalty, Tukey-bisquare IRLS) over ground inliers, iterated
  with the ground band re-derived each round.
- Shipped nine rasters on the A1 depth grid plus `products/A2_MANIFEST.json`:
  `height_above_soil` (along the **local** surface normal), the plane-normal
  variant, `validity_mask`, `coverage_class`, `support_distance_px`,
  `height_sigma`, `ground_inliers`, `soil_surface_depth`,
  `soil_surface_plane_offset`. `a2_api.py` is the loader A3/A4/A5 should import;
  it carries the datum caveat and the `scale_free` flag on every field.
- Extended A1's local-planarity curve from win33 to win129, because A2's fit
  scale is 147 px and reading an (a) constant off the end of someone else's
  table is not reading it at the scale you fit over.
- 18 tests. The load-bearing ones are a synthetic curved garden with known
  heights under a canopy covering most of the frame, and an explicit check that
  a single-plane answer would have failed that same scene.

**Measured** — see `RESULTS.md`.
- Inlier fraction **29.1 %**, inlier residual RMS **6.85e-3 rdu**, against
  1.41e-2 rdu for a single plane over the same inliers — the smooth field halves
  the residual. Datum roughness σ = **5.47e-3 rdu**.
- Coverage: **29.1 % observed, 69.8 % interpolated, 1.1 % extrapolated.**
- The cost of interpolating under canopy, measured by blanking disks: gap-fill
  RMS 1.3σ at zero support rising only to 2.4σ at 240 px. Shipped per-pixel as
  `height_sigma`.
- By-eye check, quantified: straw 0σ, clover 7σ, grass 52σ, squash leaf 93σ —
  the roadmap's ordering, passing by wide margins.
- Fitted on both A1 depth products: heights agree at r = 0.975 and 5 % in raw
  rdu, but the two plane normals differ by **7.6°**.

**Decided**
- **The datum is the straw, and it is stated in the manifest, the loader and
  every figure title** — height above straw, offset from height above soil by an
  unmeasurable straw depth.
- Ground is the **lower envelope**: the datum roughness is estimated from the
  below-surface half of the residual distribution only, which cannot contain
  canopy.
- The plane normal is oriented **toward the camera**, never toward gravity.
  Nothing in A2 knows which way is down or how high the camera is.
- `lam` is cross-validated on hold-outs **shaped like the job** — canopy-sized
  disks. Small-block CV would have picked a surface ten times rougher.
- Validity comes from the measured gap-fill curve, not a chosen number, and is
  published as a lower bound because the curve never crossed the line.

**Surprised us**
- The straw's roughness (5.47e-3 rdu, from the residual distribution) and A1's
  instrument-floor curve read at A2's own fit scale (6.0e-3 rdu at win129) are
  the **same number to 10 %**. Two unrelated estimators, one measurement. At
  this scale "how flat is a flat thing" and "how rough is the straw" stop being
  different questions.
- The RANSAC threshold is safe across a **30× band** and then falls off a cliff:
  at 100× the recovered normal jumps 36° because RANSAC finds the canopy.
- Interpolating the datum under the squash is nearly free — 1.3σ → 2.4σ across
  the whole frame — because this bed has no structure at the scale of its holes.
  That is a property of this bed, not of gardens; B1 tests it.
- 71 % of the frame is canopy and the fit still lands within 1.3σ of held-out
  truth.
- The two A1 depth products agree on heights to 5 % but disagree about which way
  the ground tilts by 7.6°. Ratios survive the product choice; directions do not.
- The fitted datum is **26σ from being a plane**. Assuming level ground would
  have injected a 13σ systematic — larger than the entire "clover just above the
  datum" signal this chunk exists to produce.

**Dependencies changed**
- None. A2 runs entirely inside `chunks/A1/.venv`.

**Next**
- A3 is unblocked on the A2 side (still needs A0). It should reason in
  `height_in_sigma()` and take `height_sigma` as a weight.
- A4 must **not** reuse A2's tolerance: its continuity threshold is
  `local_planarity_p10` at win3–win9, and it should subtract
  `soil_surface_depth` first so a sloping bed does not split fragments.
- A5 should note that a `lowest_visible_stem_point` here is a point on the
  **straw**; "enters soil" is not observable in this scene at all. That is most
  of an answer to roadmap open question 1.
- A1b gains a second reconciliation target: the 7.6° normal disagreement between
  depth products, measured on the surface its planarity refinement uses.
```
