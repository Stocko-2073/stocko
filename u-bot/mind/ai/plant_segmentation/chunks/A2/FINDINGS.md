# Chunk A2 — Soil surface and height above soil

**Session:** 2026-09-01 · **Status:** done · **Depends on:** A1 (done)
**Scale confidence:** `scale_free` — every distance below is in **rdu**
(1 rdu = median scene depth). No metric claim anywhere in this chunk.

> **The datum is the straw mulch surface, not bare soil.** Bare soil is barely
> visible in `plants.jpeg`. What the depth observes, and what this surface is
> fitted to, is the top of the mulch. Every height in every A2 product is a
> height above *straw*, offset from height above *soil* by the straw depth —
> which is unmeasured, and unobservable from one overhead photograph. An arm
> that wants the soil must add that offset. This is stated in
> `products/A2_MANIFEST.json`, in `a2_api.A2Product.datum`, and in the title of
> every figure, because it is the single most dangerous way to misread this
> product.

## What was built

Everything under `chunks/A2/`; rebuild instructions in `README.md`. No new
dependencies — A1's venv already had numpy 2.4.6, scipy 1.17.1, matplotlib,
pillow.

| File | Role |
|---|---|
| `soil_fit.py` | RANSAC plane whose normal orientation is fixed by geometry alone; `PSpline2D`, a penalised tensor-product cubic B-spline with a 2nd-difference roughness penalty and bisquare IRLS; empirical variogram with an exponential-model practical range; the two cross-validation fold designs. Scene-agnostic — every constant is passed in by the caller. |
| `fit_soil_surface.py` | The pipeline. Reads A1's manifest, back-projects with A1's `depth_to_cloud` in `scale_free`, re-measures and **extends** A1's local-planarity curve to the window A2 fits over, runs the outer loop, measures the gap-fill error curve by disk hold-out, sweeps both conventions, writes nine rasters plus `A2_MANIFEST.json`. |
| `figures.py`, `material_check.py`, `occlusion_report.py`, `compare_products.py` | The four checks: banded overlay + zooms, the hand-sampled material ordering, occlusion behaviour, and the same fit on both A1 depth products. |
| `a2_api.py` | The loader A3/A4/A5 should import. Carries the datum caveat and the scale flag; `height_in_sigma()` and `confident_above(k)` are the scale-free ways to use the raster. |
| `test_soil_fit.py` | 18 tests, all passing. The load-bearing ones: a synthetic curved garden with known heights and a canopy covering most of the frame, and an explicit check that a single-plane ("the ground is level enough") answer would have failed that same scene. |

### The pipeline, and where each number comes from

1. **Back-project** `primary_raster` (1344x1008) with the res-504 camera
   rescaled, exactly as A1's manifest instructs, in `scale_free` mode.
2. **Extend A1's local-planarity curve.** A1 measured it to a 33 px window; A2
   fits over ~147 px, so the curve is re-measured here at
   9/17/33/49/65/97/129 px. This is what makes the RANSAC threshold a read-off
   rather than a pick.
3. **RANSAC plane** at that threshold — the initial estimate only. Its normal is
   oriented toward the camera origin, never toward gravity.
4. **Outer loop.** Robust P-spline over ground candidates; re-estimate the datum
   roughness from the **below-surface half** of the residual distribution;
   re-select candidates within 3 sigma; repeat.
5. **`lam` by cross-validation on the inliers**, holding out compact disks the
   size of the canopy holes this scene actually has.
6. **Heights measured along the local surface normal** of the fitted field, not
   along the global plane normal.

## What was measured

Full numbers in `results/fit_report_primary_raster.json`; scores in `RESULTS.md`.

### Fit quality

| Quantity | Value |
|---|---|
| Ground inlier fraction | **29.1 %** (394 340 px of 1 354 752) |
| Inlier residual RMS | **6.85e-3 rdu** (MAD 6.21e-3, p95 abs 1.43e-2) |
| Same inliers, single RANSAC plane instead | 1.41e-2 rdu |
| **Improvement of the smooth field over a plane** | **51 %** |
| Datum roughness sigma (below-surface estimator) | **5.47e-3 rdu** |
| Fitted datum minus the plane | RMS 1.89e-2 rdu, peak-to-peak **0.143 rdu = 26 sigma** |
| Local tilt of the datum away from the plane | median 5.9 deg, p90 14.3 deg, max 60.9 deg |
| Height along local normal vs. plane normal | differ by 2.69e-2 rdu RMS, about 4.9 sigma |
| Effective d.o.f. / fit scale | 63 / **147 px** |
| Cross-validated `lam` | **316** (gap design); 31.6 if blocks are used instead |

### Coverage

| Class | Fraction |
|---|---|
| observed (a ground inlier) | **29.1 %** |
| interpolated (surface inferred, within the measured trust distance) | **69.8 %** |
| extrapolated (beyond it) | **1.1 %** |
| valid | 98.9 % |

Support distance to the nearest ground observation: p50 16 px, p90 125 px,
p95 170 px, p99 245 px, max 349 px.

### What interpolating under a canopy actually costs — measured

Ground observations were blanked inside disks of radius 20/40/80/160 px and the
surface refitted; error against the pixels that were hidden:

| support distance (px) | 0–5 | 10–20 | 40–60 | 80–120 | 160–240 |
|---|---|---|---|---|---|
| gap-fill RMS (rdu) | 7.0e-3 | 7.5e-3 | 8.2e-3 | 8.9e-3 | 1.33e-2 |
| in units of the datum roughness | 1.3σ | 1.4σ | 1.5σ | 1.6σ | 2.4σ |

It never exceeded the 3-sigma ground band inside the radii tested, so the trust
distance is reported as **at least 240 px, a lower bound set by the largest disk
measured**, not as a value the data resolved. `height_sigma.npy` is this curve,
evaluated at each pixel's own support distance.

### The by-eye check, written down (`results/material_ordering.json`)

Hand-placed boxes on five materials, verified against the RGB (see
`results/fig_material_boxes.png`):

| material | median height | in sigma | ground-inlier fraction |
|---|---|---|---|
| straw (the datum) | +0.0001 rdu | **0 sigma** | 85 % |
| low broadleaf weed ("clover") | +0.040 rdu | **7 sigma** | 54 % |
| squash fruit | +0.119 rdu | 22 sigma | 0.3 % |
| grass blade | +0.286 rdu | **52 sigma** | 28 % |
| squash leaf | +0.511 rdu | **93 sigma** | 0 % |

The roadmap's acceptance test — "clover just above the datum, grass mid-band,
squash canopy high" — **passes**, and passes by a wide margin: the three are
separated by 7x and 1.8x in height with the straw pinned at zero. The fruit is
reported but excluded from the ordering test; nobody ever asserted where a fruit
resting on the ground should rank.

### Both A1 depth products, fitted independently (`results/product_comparison.json`)

| | `primary_raster` (res 1344) | `primary_geometry` (res 504) |
|---|---|---|
| inlier fraction | 29.1 % | 29.5 % |
| inlier RMS | 6.85e-3 rdu (1.25 sigma) | 6.93e-3 rdu (1.15 sigma) |
| datum sigma | 5.47e-3 rdu | 6.01e-3 rdu |
| fit scale | 147 px (10.9 % of frame height) | 82 px (16.3 %) |
| rdu normaliser | 1.3997 | 1.4000 |

Agreement: Pearson r = **0.975**, raw-rdu gain **1.048**, ground-mask IoU
**0.80**. The disagreement is concentrated on the tall canopy, not on the datum
(`results/fig_product_comparison.png`). But the two fitted **plane normals
differ by 7.6 deg** — the two inference resolutions genuinely disagree about
which way the ground tilts, and nothing in this image can adjudicate.

## What was decided

1. **The datum is the straw, and it is said out loud everywhere.** Not a
   footnote: it is in the manifest, the loader, and every figure title.
2. **Ground is defined as "the lower envelope", not "the flat part".** The datum
   roughness is estimated from the below-surface half of the residual
   distribution only, because nothing in a scene lies under the ground, so that
   half is roughness and depth noise and can never be canopy. Two tests pin this
   down: the estimator is unchanged when half the residuals are replaced by
   arbitrarily tall plants.
3. **The plane normal is oriented toward the camera, never toward gravity.**
   "Above the soil" means "on the camera side of the surface". Nothing in A2
   knows which way is down, what the camera height is, or that the bed is level
   — and there is a test asserting a steeply banked surface is handled the same
   way as a level one.
4. **`lam` is cross-validated on a hold-out shaped like the job.** Scattered- or
   small-block CV scores a task the surface never faces: every held-out point
   has a neighbour one pixel away. The real task is a canopy hole. Holding out
   disks sized to the measured hole scale selects `lam = 316`; the textbook
   block design selects **31.6, a factor of ten rougher**. Both curves are in
   the report; the gap design decides, and the reason is written down.
5. **Heights are measured along the local surface normal.** The datum tilts away
   from the global plane by 5.9 deg median and 61 deg at worst, which moves
   heights by 4.9 sigma RMS. The plane-normal version ships alongside as a
   reference.
6. **Validity comes from a measured curve, not a chosen number.** A pixel is
   valid while the measured gap-fill error at its support distance stays inside
   the ground band. Because the curve never crossed that line inside the radii
   tested, the limit is honestly published as a lower bound, and the two regions
   that exceed it are reported rather than quietly filled.
7. **`primary_raster` is the shipped product**, with `primary_geometry` kept as
   the independent check. A2 never touches the camera A1 flagged unusable: the
   rescaled res-504 camera does the back-projection, as the manifest requires.

## Behaviour where the canopy hides the ground completely

`results/occlusion.json`, `results/fig_occlusion.png`.

The canopy is one connected sheet: 69.2 % of the frame is a single component
with no ground observation inside it, so "how many holes are there" is the wrong
question. Sliced by how deep inside the occluded set a pixel sits:

| support distance greater than | area | components | largest |
|---|---|---|---|
| 0 px | 70.9 % | 201 | 69.2 % |
| 20 px | 47.2 % | 19 | 32.1 % |
| 80 px | 19.1 % | 4 | 10.5 % |
| 160 px | 6.0 % | 2 | 5.0 % |
| 240 px (the trust distance) | 1.1 % | 2 | 1.0 % |

What the code does there: the surface is continued by the spline's roughness
penalty alone — no ground pixel inside the hole contributes anything. That is a
smooth continuation of the surrounding datum, not a measurement, and it is
labelled as such in `coverage_class` and priced in `height_sigma`. Nothing is
silently filled. Both regions that exceed the trust distance **touch the frame
edge** (the top-left leaf and the bottom-right leaf) — exactly the case where
the surface is constrained from one side only and has nothing on the far side to
bracket it. Under R2 and R4 no removal decision may rest on a height there.

## What surprised us

1. **The straw roughness and the "instrument floor" turn out to be the same
   number.** A1 predicted the straw would dominate the sensor by two orders of
   magnitude, and it does — but the specific coincidence was not predictable:
   the datum roughness measured from the residual distribution (5.47e-3 rdu) and
   A1's local-planarity p10 read at A2's own fit scale (6.0e-3 rdu at win129)
   agree to 10 %. Two completely different estimators — one a percentile over
   windows of a plane fit, one a one-sided robust scale of a spline residual —
   land on the same value. At the scale A2 works, "how flat is a flat thing" and
   "how rough is the straw" are one measurement.
2. **The RANSAC threshold barely matters, and then it matters enormously.** The
   plane normal moves by less than 1 deg as the threshold sweeps 30x, from
   5.4e-4 to 1.6e-2 rdu. At 100x it jumps 36 deg — RANSAC stops finding the
   ground and finds the canopy instead. So the A1-derived (a) constant is not a
   delicate choice, it is a safe one inside a wide basin with a cliff on the far
   side, and the sweep is what shows the cliff exists.
3. **Interpolating the datum under a canopy is nearly free in this scene.**
   Expectation going in was that the surface would go badly wrong under the
   squash. Measured, the gap-fill error grows only from 1.3 sigma at zero
   support to 2.4 sigma at 240 px — less than a factor of two across the whole
   frame. The reason appears to be that this ground has no structure at the
   scale of the holes: the datum is smooth over 147 px, so a 100 px hole removes
   almost no information. **That is a property of this bed, not of gardens**, and
   B1 is where it gets tested.
4. **Ground is 29 % of the frame and that was enough.** With 71 % of the image
   canopy, the surface is observation-free over more than two-thirds of its
   domain and still lands within 1.3 sigma of held-out truth.
5. **The two A1 depth products disagree about which way the ground tilts by
   7.6 deg, while agreeing about heights to 5 %.** Ratios survive the choice of
   product; the absolute orientation does not. This is the A2-level echo of A1's
   finding that DA3's camera head is resolution-dependent, and it is a warning
   for anything downstream that wants a *direction* rather than a *height*.
6. **The fitted datum is 26 sigma away from being a plane.** A single plane is
   not a rounding error here: fitting one leaves twice the residual, and the
   departure has smooth mound structure across the frame. Whether that is real
   bed topography or monocular depth bending cannot be separated from one image
   — but either way, treating the ground as flat would have put a systematic
   0.07 rdu error into every height, which is 13 sigma, larger than the entire
   "clover just above the datum" signal.

## Constants introduced

| Name | Value | Cat | Justification |
|---|---|---|---|
| RANSAC inlier threshold | 5.446e-4 rdu | (a) | A1's local-planarity p10 at win33, re-measured on this product under the manifest camera. Swept 1x-300x: the normal is stable to under 1 deg over 30x. |
| local-planarity p10, win 49/65/97/129 | 8.77e-4 / 1.558e-3 / 4.72e-3 / 6.01e-3 rdu | (a) | A1's estimator, extended to the windows A2 fits over. |
| datum roughness sigma | 5.47e-3 rdu | (c) | Robust scale from the below-surface half of the residual distribution, measured on this scene. |
| spline smoothing `lam` | 316 | (c) | 5-fold CV on the inliers with canopy-hole-shaped hold-outs. |
| residual autocorrelation range | 40 px | (c) | Exponential variogram model on the residual raster. |
| CV hold-out disk radii | 38.6 / 85.2 / 148.8 px | (c) | p50/p75/p90 of the support distance over non-ground pixels. |
| trust distance | at least 240 px | (c) | Where the measured gap-fill error would exceed the ground band — a lower bound, never reached. |
| ground band multiplier | 3 sigma | convention, swept | Swept 2-5 sigma; inlier fraction 22.8-32.4 %, surface moves at most 1.0e-2 rdu (1.8 sigma). |
| bisquare tuning constant | 4.685 | convention | The standard 95 %-efficiency constant of Tukey's bisquare. Multiplies a MAD measured every iteration. |
| spline basis | 24 x 32 segments | resolution ceiling, swept | Halved to 16 x 21: surface moves 2.0e-3 rdu (0.36 sigma). `lam`, not the basis, decides the smoothness. |

**Nothing in A2 encodes a belief about how gardens are arranged.** There is no
plant spacing, no crop size, no expected height, no assumed camera height and no
assumption that the ground is level. The one place a scene property enters — the
hold-out disk radii — is measured from this image's own occlusion geometry and
is used only to choose a smoothing parameter, never as a threshold.

## Not done / deferred

- **No ground truth.** A0 does not exist yet, so there is no IoU or
  contact-point number here and the material ordering is a hand-placed sample,
  not a labelled set. Everything measured in A2 is internal (hold-out, sweep,
  product-vs-product). When A0 lands, `material_check.py` should be re-pointed
  at those labels.
- **The straw depth is not measured and cannot be.** Height above *soil* is
  unavailable from this photograph; it is available only where bare soil is
  visible, which here is essentially nowhere. C1's second viewpoint or a probe
  is the honest route.
- **The gap-fill curve measures holes over ground that is observable.** Whether
  the ground under a squash canopy behaves like the ground between straw stalks
  cannot be checked from one image. R4's answer is to look again (C1), not to
  widen the claim.
- **The outer loop does not fully converge**: it oscillates between adjacent
  `lam` grid points (100 and 316) with 0.4 % candidate churn, which moves the
  datum sigma by 8 %. Tightened by a finer `lam` grid or an inner-loop `lam`
  freeze; not worth it before B1.
- **The 7.6 deg plane-normal disagreement between depth products is quantified,
  not resolved.** A1b's `f` refinement is the chunk that can speak to it.
- **Only `plants.jpeg`.** Whether 29 % ground coverage, a 147 px fit scale and a
  nearly-free interpolation are properties of this bed or of gardens is a B1
  question, and the honest guess is: this bed.

## Implications for the roadmap

- **A3** should use `a2_api.load_a2()` and reason in `height_in_sigma()`, not in
  rdu. The height channel separates the four materials by 0 / 7 / 52 / 93 sigma
  before any appearance feature is looked at, so the A3 ablation "what did
  `height_above_soil` contribute on its own" has a real chance of being large.
  Feed it `height_sigma` too: a leaf over a 200 px canopy hole has a 2.4 sigma
  datum under it and its height should count for less.
- **A4** wants the *depth-continuity* tolerance, not this one. A2's numbers are
  at the 147 px patch scale; A4 links across a few pixels and must read
  `local_planarity_p10` at win3-win9 (2.9e-5 to 1.3e-4 rdu), as A1 said.
  `soil_surface_depth.npy` is the right thing to subtract before testing
  continuity, so that two fragments on a sloping bed are not split by the slope.
- **A5** gets three things it needs: `coverage_class` (an `observed` contact
  point is one where the *material* reaches a datum that was itself observed —
  both conditions, not one), `height_sigma` for the confidence, and the honest
  fact that a `lowest_visible_stem_point` on this scene is a point on the
  **straw**, not on the soil. Open question 1 in the roadmap can be answered
  from this: "enters soil" is not observable here at all, and A5 should target
  the straw datum with the straw depth carried as an explicit unknown offset.
- **A6** should build the keep-out volume in the datum's frame — heights above
  the fitted surface, not distances in camera space — or a sprawling vine on a
  26-sigma-curved bed will get a keep-out volume that follows the camera rather
  than the ground.
- **A1b** now has a second thing to reconcile besides `f`: the two depth products
  disagree about the ground normal by 7.6 deg, and the planarity refinement is
  measured on exactly this surface.
