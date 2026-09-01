# Chunk A1b — Assumed intrinsics, bounded rather than hidden

**Date:** 2026-09-01 · **Status:** done · **Depends on:** A1 (done)
**Scale confidence:** `scale_free` throughout — every distance below is in **rdu**
(1 rdu = median scene depth). **Absolute scale is UNRESOLVED and this chunk does
not resolve it.** Datum in every A2/A4/A5 number: the **STRAW mulch surface**.
**Inputs:** A1 `products/MANIFEST.json` (both depth products), A2
`ground_inliers` + `fit_report`, and the shipped A2/A4/A5 code, driven — not
forked — at nine assumed focal lengths.

---

## Headline

| | |
|---|---|
| **Chosen `f`** | **4453 px at 3000x4000** (38.5 mm-equivalent; fx = fy = 1496.28 px on A1's 1008x1344 depth grid) |
| Provenance | `assumed+refined` — where "refined" records that a refinement was **run**, not that it succeeded |
| How it compares to DA3's head | It **is** DA3's head: A1 measured 4159–4695 px (mean 4489) in the resolutions where DA3's camera is physically consistent, and 4453 is its res-504 value — the camera every shipped Phase A product already used. **1.48x the roadmap's 26 mm-equivalent prior of 3005 px.** |
| Refinement outcome | **DEGENERATE.** No interior optimum exists, for a reason deeper than the roadmap's caveat |
| Phase A conclusions that move with `f` | **none of A4's, none of A2's fit-quality conclusions, none of A5's verdicts.** What moves is one absolute angle and a set of units |
| Absolute scale | **UNRESOLVED**, deliberately |

**The one sentence that explains every number in this chunk.** Changing `f`
while holding the depth raster fixed maps the point cloud by

    P -> S P,   S = diag(f0/f1, f0/f1, 1)

which is a **linear, invertible** map. Linear maps take planes to planes, so
planarity cannot see `f` at all; and every Phase A quantity that is invariant
under an axial scaling — incidence, connectivity, z-depth, ratios of things
carrying the same unit — is *exactly* focal-invariant. The exceptions are
angles, and ratios between an in-plane length and a depth length. That is the
whole result, and the rest of this document is the evidence for it.
`test_changing_f_is_exactly_an_axial_scaling_of_the_cloud` asserts the identity
to 1e-12 on `depth_to_cloud` itself; `linear_map_check` in
`results/focal_refinement.json` confirms it on the real raster at a relative
error of 6e-17.

---

## 1. The planarity refinement, and why it cannot work

The roadmap's instruction was to back-project the A1 float depth across
candidate `f` and **choose the value minimising planarity residual over the soil
band**, with the caveat that "the refinement is degenerate if DA-V3 internally
assumed an FOV: you would recover *their* assumption rather than ground truth."

It was run as specified: 72 focal lengths from 400 to 60 000 px, on **both** A1
depth products (so `process_res` is fixed within each curve, as A1 required),
using A2's own `ground_inliers` as the soil band, in three normalisations, with
a bootstrap band over patches. `results/focal_refinement.json`,
`figs/fig_refinement.png`.

### What the curves do

| normalisation | primary_raster (res 1344) | primary_geometry (res 504) |
|---|---|---|
| planarity residual RMS (rdu) — the literal instruction | **monotone decreasing**; 5.27e-3 at 1502 px -> 2.91e-3 at 6009 px. Minimum wherever the grid ends | monotone decreasing |
| surface variation lambda3/sum(lambda) (scale-invariant) | interior **MAXIMUM** at 4506 px; minima at both grid edges | interior maximum at 5326 px |
| roughness slope sqrt(lambda3/(lambda1+lambda2)) (scale-invariant) | same shape, maximum at 4506 px | maximum at 5326 px |

The bootstrap band over patches at f = 3005 px is +/-3 %, so the monotone trend
is real and not sampling noise. **It is real and useless:** a criterion whose
optimum is at the boundary of the search range has not chosen anything.

### The caveat is true, and the real reason is stronger

Two controls settle it without reference to Depth Anything 3 at all.

**(a) An exactly planar depth map.** Rendered through a known camera, its
planarity residual is **1e-16 rdu at f = 500, at 1502, at 3005, at 4453 and at
20 000** — zero at every focal length, because `S` maps planes to planes.
`test_a_plane_stays_a_plane_at_every_focal_length` asserts it.

**(b) A synthetic locally-planar rough surface with a KNOWN focal length.** A
tilted plane plus three octaves of undulation plus correlated roughness, exact
depth, no model in the loop. Handed to the same estimator:

| true `f` (px) | argmin planarity RMS | recovered? |
|---|---|---|
| 1502 | 60 000 (grid edge) | no |
| 3005 | 60 000 (grid edge) | no |
| 6009 | 60 000 (grid edge) | no |

**The estimator cannot recover a focal length it was handed.** So the
degeneracy is a property of the parametrisation, not of DA3 having assumed an
FOV. `test_the_planarity_refinement_cannot_recover_a_focal_length_it_was_given`
is written to fail if this ever stops being true, which would mean the chunk's
central finding is wrong and the refinement should be reinstated.

### The one feature of the curve that is not flat — and why it still is not an estimator

The scale-invariant normalisations have an interior *maximum*, and on the
synthetic control that maximum sits at a fixed multiple of the true focal
length. That looks like an estimator. It is not: measured across synthetic
surfaces that differ in tilt, undulation and roughness, the multiple ranges from
**1.08 to 12.10** — a 3.3x spread — and it is dominated by the surface's own
tilt, which is exactly the unknown. Applying the observed peak of 4506 px with
that range of constants gives `f` in [373, 4185] px, i.e. no constraint at all.
Reading a focal length off the peak would be assuming a roughness and a tilt for
the straw and calling the result a measurement, which is the move R1 exists to
forbid.

### So the choice is argued, not measured

Since the scene cannot adjudicate, the two candidates are:

| | value | case for it | case against |
|---|---|---|---|
| the roadmap's prior | 3005 px (26 mm-eq) | a phone main camera at 3000x4000; `f ~ image width`, the roadmap's own sanity check | a prior about phones in general, not about this camera |
| DA3's own head | **4453 px (38.5 mm-eq)** | **the depth field being back-projected is conditioned on it**, so the reconstruction is self-consistent; and it is the camera every shipped Phase A product already used | it is a monocular model's guess, and it drifts 50 % with processing resolution (A1) |

**A1b adopts 4453 px.** A1 had already ruled that geometry should be
self-consistent with the depth being fed in, and the sweep below shows that
being wrong by the full 1.48x costs nothing that matters. This is registered as
a category **(d)** assumption, not upgraded to a measurement. A1's rule that
`assumed` mode refuses `model_estimated` intrinsics stands and is tested;
`calib/plants_assumed.json` supplies its own object with provenance
`assumed+refined`, and says in as many words that the value coincides with DA3's
res-504 estimate.

---

## 2. What `f` actually changes

`figs/fig_shape.png` — the same depth raster, the same soil band, three assumed
focal lengths, one common frame with equal aspect:

| assumed `f` | 1502 px | 3005 px | 6009 px |
|---|---|---|---|
| the bed rakes away from the camera by | **13 deg** | **24 deg** | **42 deg** |
| median tilt of the local soil patches | 18.0 deg | 39.3 deg | 64.1 deg |

The focal-length assumption is a statement about **how steeply the ground is
believed to fall away**, and about nothing else. It is not a statement about
size (that is scale, and it stays unresolved) and it is not a statement about
flatness (planarity is invariant). This is the sharp version of the roadmap's
Known-gaps #4, and it is the sentence to carry into C0.

---

## 3. The sensitivity table

Nine focal lengths — the roadmap's `{1502, 2774, 3005, 3236, 6009}` **widened
per A1's FINDINGS** with `{4159, 4453, 4489, 4695}` so DA3's own band is
covered instead of stepped over — plus a **reference row** using A1's own
anisotropic camera. A2's full fit, A4 under both policies with the three
roadmap verdicts, and A5 under both policies with the GT-consistency diagnostic
were re-run at every row: **10 complete A2 fits, 20 A4 builds, 20 A5 runs.**
Nothing was frozen — where a chunk measures a constant off the image (A2's
RANSAC threshold and `lam`, A4's continuity tolerance) it re-measured it at each
`f`. Full table: `results/sensitivity_table.md`; raw: `results/sensitivity.json`.

### The reference row reproduces shipped Phase A exactly

The harness is validated before anything is concluded from it. A1b's `manifest`
row uses A1's own camera, so it must land on the numbers already in
`RESULTS.md`:

| | RESULTS.md | A1b `manifest` row |
|---|---|---|
| A2 inlier fraction | 29.1 % | 29.108 % |
| A2 inlier residual RMS | 6.85e-3 rdu | 6.8496e-3 rdu |
| A2 datum sigma | 5.47e-3 rdu | 5.4696e-3 rdu |
| A4 split components / F1 / squash IoU / grass | 742 / 0.0088 / 0.462 / 11.8 % | 742 / 0.008772 / 0.4619 / 11.76 % |
| A5 split observed / extrapolated / occluded | 472 / 59 / 211 | 472 / 59 / 211 |
| A5 split arm-admissible / median confidence | 378 / 0.71 | 378 / 0.7146 |

Largest relative difference: **0.35 %**, all of it rounding in `RESULTS.md`.
`test_the_reference_row_reproduces_shipped_phase_A` enforces < 2 %.

### The table, abridged

| metric | 1502 | 3005 | 4453 | 6009 | spread | log-log slope | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| A2 inlier fraction | 0.2911 | 0.2911 | 0.2911 | 0.2911 | 0.0 % | 0.00 | **EXACTLY invariant** |
| A2 `lam` | 316 | 316 | 316 | 316 | 0.0 % | 0.00 | **EXACTLY invariant** |
| A2 fit scale (px) | 146.7 | 146.7 | 146.7 | 146.7 | 0.0 % | 0.00 | **EXACTLY invariant** |
| A2 observed / interpolated / extrapolated fractions | — | — | — | — | 0.0 % | 0.00 | **EXACTLY invariant** |
| A2 trust distance (px) | 240 | 240 | 240 | 240 | 0.0 % | 0.00 | **EXACTLY invariant** |
| A2 inlier residual RMS (rdu) | 8.73e-3 | 7.85e-3 | 6.88e-3 | 5.92e-3 | 39.7 % | -0.27 | moves |
| A2 datum sigma (rdu) | 6.97e-3 | 6.27e-3 | 5.49e-3 | 4.72e-3 | 39.7 % | -0.27 | moves |
| A2 RANSAC threshold (rdu) | 6.97e-4 | 6.25e-4 | 5.47e-4 | 4.75e-4 | 39.6 % | -0.27 | moves |
| **A2 residual / datum sigma** | **1.2525** | **1.2525** | **1.2525** | **1.2525** | **0.0 %** | 0.00 | **invariant** |
| **A2 residual / RANSAC threshold** | 12.53 | 12.55 | 12.57 | 12.47 | 1.5 % | 0.00 | **invariant to <5 %** |
| **A2 ground tilt from optical axis (deg)** | **16.3** | **30.2** | **40.8** | **49.4** | **85.2 %** | **+0.81** | **MOVES** |
| A4 continuity tolerance (rdu) | 4.238e-3 | 4.238e-3 | 4.238e-3 | 4.238e-3 | 0.0 % | 0.00 | **EXACTLY invariant** |
| A4 fragments / components (split) | 1776 / 742 | 1776 / 742 | 1776 / 742 | 1776 / 742 | 0.0 % | 0.00 | **EXACTLY invariant** |
| A4 instance F1 (split) | 0.008772 | 0.008772 | 0.008772 | 0.008772 | 0.0 % | 0.00 | **EXACTLY invariant** |
| A4 squash best IoU (split) | 0.4619 | 0.4619 | 0.4619 | 0.4619 | 0.0 % | 0.00 | **EXACTLY invariant** |
| A4 grass absorbed (split) | 11.76 % | 11.76 % | 11.76 % | 11.76 % | 0.0 % | 0.00 | **EXACTLY invariant** |
| A4 clover inside crop (split) | 0.0 % | 0.0 % | 0.0 % | 0.0 % | 0.0 % | — | **EXACTLY invariant** |
| A4 unresolved boundaries | 1237 | 1237 | 1237 | 1237 | 0.0 % | 0.00 | **EXACTLY invariant** |
| A4 merge: components / F1 / squash IoU / grass | 207 / 0.0198 / 0.885 / 83.3 % | identical | identical | identical | 0.0 % | 0.00 | **EXACTLY invariant** |
| A5 split observed | 475 | 475 | 476 | 475 | 0.4 % | 0.00 | invariant to <1 % |
| A5 split arm-admissible | 376 | 376 | 379 | 381 | 1.3 % | +0.01 | invariant to <5 % |
| A5 split median confidence | 0.7233 | 0.7231 | 0.7217 | 0.7245 | 0.8 % | 0.00 | invariant to <1 % |
| A5 split extrapolated | 58 | 64 | 61 | 53 | 21.3 % | -0.07 | moves (13 components) |
| A5 split occluded | 209 | 203 | 205 | 214 | 6.3 % | +0.02 | moves (13 components) |
| A5 split GT-consistency median (px) | 54.4 | 61.4 | 61.4 | 61.4 | 11.3 % | +0.08 | moves at one row only |
| A5 merge observed / arm-admissible | 166 / 137 | 166 / 137 | 165 / 137 | 164 / 137 | 1.2 % / 0.0 % | — | invariant / **EXACT** |

Counted: **24 of 39 reported quantities are bit-identical across a 4x range of
focal length**, 7 more move by under 5 %, and of the 8 that "move", 5 move only
because their *unit* moves — the ratios above are flat.

### The three A4 verdicts the roadmap asks for, at every `f`

| | 1502 | 2774 | 3005 | 3236 | 4159 | 4453 | 4489 | 4695 | 6009 |
|---|---|---|---|---|---|---|---|---|---|
| squash one component? (split) | no | no | no | no | no | no | no | no | no |
| squash best IoU | 0.462 | 0.462 | 0.462 | 0.462 | 0.462 | 0.462 | 0.462 | 0.462 | 0.462 |
| clover separate? | yes | yes | yes | yes | yes | yes | yes | yes | yes |
| grass absorbed | 11.8 % | 11.8 % | 11.8 % | 11.8 % | 11.8 % | 11.8 % | 11.8 % | 11.8 % | 11.8 % |
| squash one component? (merge) | yes | yes | yes | yes | yes | yes | yes | yes | yes |

**Not "nearly invariant" — identical.** The roadmap expected A4 to be "nearly
invariant, since it is ratio-based". It is better than that, and for a reason
the roadmap did not have: A4 consumes `relief = A2 soil_surface_depth - A1
depth`, and both terms are **z-depths**, the one coordinate `S` leaves alone.
The result can be derived as well as measured — A2's fitted datum surface obeys
`P_soil -> S P_soil`, so its z-component is exactly unchanged, so the relief
raster, the within-fragment tolerance measured off it, every boundary residual
and every component is unchanged.

### A3 was not re-run, and does not need to be

A3's winning approach is a probe on frozen DINOv2 patch features over RGB. It
consults **no geometry at all**, so it is trivially focal-invariant — there is
no focal length anywhere in its code path to move. The `height_above_soil`
channel that A3 ablated does depend on `f` (it is a projection onto the datum
normal), but the winner does not use it. Stated rather than measured,
deliberately: re-running it would have produced nine identical rows proving
something already true by inspection.

---

## 4. The plane-normal disagreement A2 left behind

A2 asked A1b to reconcile the **7.6 deg** disagreement between the ground
normals fitted on A1's two depth products.
`results/normal_reconciliation.json`, `figs/fig_normals.png`.

A normal is exactly the kind of quantity `S` does not preserve, and its focal
dependence has a closed form: `n(f) ~ (n_x*f/f0, n_y*f/f0, n_z)`. Measured three
ways — the closed form from A2's own two normals, a least-squares refit, and a
RANSAC refit — the three agree in shape:

| assumed `f` | 1502 | 3005 | 4453 | 6009 | as f -> 0 |
|---|---:|---:|---:|---:|---:|
| disagreement, closed form | 3.3 | **5.95** | **7.64** | 8.79 | -> 0 |
| disagreement, least-squares refit | 2.4 | 4.24 | 5.51 | 6.40 | -> 0 |
| disagreement, RANSAC refit | 2.8 | 6.35 | 9.43 | 10.9 | -> 0 |

(all in degrees)

**Validation:** both A2 fits used A1's res-504 camera, i.e. `f = 4453 px`, so the
closed form at that `f` must reproduce A2's recorded number. It gives
**7.6415 deg** against A2's 7.6. The algebra is right.

**The answer to A2's question, in three parts.**

1. **`f` does not reconcile it.** The disagreement is monotone increasing in `f`
   and goes to zero only as `f -> 0`, where every normal collapses onto the
   optical axis. Its minimum is at the edge of the grid, exactly like the
   planarity criterion. "Choose `f` so the two products agree" is degenerate.
2. **`f` does price it.** At the 26 mm prior the disagreement is 5.95 deg; at
   A1b's chosen 4453 px it is 7.64; across the whole sweep it spans 3.3–8.8. So
   the focal-length assumption is worth **about +/-2 deg of ground-normal
   disagreement** on top of whichever value is right.
3. **The disagreement is not the number that matters — the tilt is.** Both
   products agree with each other to within 8 deg while the *absolute* ground
   tilt they report moves from 16 to 49 deg across the sweep. Anything
   downstream that wants a **direction** rather than a **height** is being told
   something with an 85 % uncertainty band, and A6's keep-out geometry and any
   future gravity-referenced consumer are where that bites.

---

## 5. The other two (d) constants

`results/principal_point_sweep.json`.

**Principal point** — swept over offsets of 1, 2 and 5 % of the image width in
+/-x, +/-y and diagonally, at both candidate focal lengths:

| offset | ground normal moves by | planarity residual changes by |
|---|---|---|
| 1 % of width (30 px at 3000x4000) | <= **0.23 deg** | < 0.5 % |
| 5 % of width (150 px) | <= **1.11 deg** | <= 2.1 % |

A phone's principal point is not 5 % off centre, so this assumption is worth
well under a degree — an order of magnitude less than the focal-length
assumption's +/-2 deg, and two orders less than its 85 % effect on absolute
tilt. The sweep covers the **soil band's own geometry**, the quantity every
later stage is built on; the downstream stack was re-run per focal length only,
and that limitation is stated in the JSON rather than implied. A principal-point
offset is a shear-like perturbation, not a scaling, so it is **not** absorbed by
the linear map that makes the focal sweep so well behaved.

**Distortion** — assumed zero, and **not bounded by this chunk**, with the
reason recorded as a measurement rather than an assertion: bounding a distortion
model needs something known to be straight, and `plants.jpeg` is a garden bed
under straw. The longest linear features in it are grass blades and straw
stalks, which are neither straight nor known to be. Any "bound" computed here
would be a bound on the straightness of straw. It stays a (d) constant with an
explicitly unbounded residual, retired by C0.

---

## 6. What A1b found that nobody was looking for: A2's RANSAC seed is a lottery

The sweep was run twice.

A2 seeds its outer loop with a RANSAC plane found at a threshold that admits
**1.2 % of pixels**. At that inlier fraction the winning plane is a draw, not a
fit — and rescaling the cloud changes which ticket wins. Run with the shipped
code and a fresh draw per row (`*_freeseed`), the seed normal moves smoothly
through one family from 1502 to 4159 px and then **jumps to a completely
different plane at 4453 px**, about 40 deg away. The outer loop does not recover:

| | `f` <= 4159 (good seed) | `f` >= 4453 (bad seed) |
|---|---:|---:|
| A2 inlier fraction | 29.3 % | **45.2 %** |
| A2 effective d.o.f. / fit scale | 63 / 147 px | **936 / 38 px** |
| A2 inlier residual RMS | 6.9–8.3e-3 rdu | 1.3–1.6e-3 rdu *(smaller, and meaningless — it is interpolating)* |
| A4 split components | 742 | 749 |
| A4 instance F1 | 0.0088 | 0.0087 |
| **A4 squash best IoU** | **0.462** | **0.314** |
| A4 grass absorbed | 11.8 % | 8.1 % |
| **A5 split observed** | 483–484 | **311** |
| **A5 split arm-admissible** | 379–381 | **87–94** |

**A2's seed instability costs A5 four times more than the entire focal-length
sweep does** — 381 admissible targets against 94, versus a 1.3 % spread across
4x in `f`. It also almost exactly halves the squash IoU. This is not a
focal-length effect and it would have contaminated the sweep, so the **primary
sweep transports A2's seed plane from the reference row by the exact closed
form** (`--seed-plane-from`), leaving `f` as the only thing that differs between
rows. The free-seed sweep is kept in full as the evidence, in
`results/sensitivity.json -> free_seed_control` and `work/*_freeseed/`.

The fix for A2 is small and is not A1b's to make: seed the outer loop with a
plane found at a threshold that admits a *usable* fraction of the scene, or
seed it from the previous scale, or re-seed from the converged surface and check
the loop is a fixed point.

---

## 7. What was decided

1. **`f` = 4453 px at 3000x4000, square pixels, principal point at the image
   centre, zero distortion.** Category (d), sweep attached, retired by C0.
   Written to `calib/plants_assumed.json` with provenance `assumed+refined`, and
   with `refinement_outcome: "DEGENERATE — no interior optimum exists"` in the
   same file so the two cannot be read apart.
2. **The refinement is reported as failed, not quietly replaced by the argument
   that follows it.** The full curve ships, in three normalisations, with both
   controls. A future reader who wants to re-litigate the choice has everything
   needed to do so.
3. **The sweep's primary rows hold A2's RANSAC seed fixed**, because otherwise
   it measures A2's seed lottery instead of `f`. Both sweeps ship.
4. **No Phase A result needs re-scoring.** A1b's chosen `f` is the camera Phase A
   already used, and the reference row reproduces `RESULTS.md` to 0.35 %.
5. **Absolute scale stays unresolved** and nothing in this chunk implies it. The
   calib file says so in its own `absolute_scale` block, and
   `test_calib_file_is_complete_and_honest` fails if a unit of length appears in
   it without the word "unresolved" nearby.
6. **A3 is declared invariant by inspection, not by nine identical rows.**

---

## 8. What surprised us

1. **The refinement is not degenerate because of DA3 — it is degenerate,
   period.** The roadmap anticipated recovering DA3's assumption instead of
   truth. The real situation is worse and cleaner: there is nothing to recover.
   Planarity is *exactly* preserved by a change of focal length, so a planarity
   criterion has no optimum at all, and the synthetic control with a known `f`
   proves it without DA3 in the room. A whole planned comparison ("compare your
   planarity-refined f to DA3's head") turned into a two-line proof that the
   comparison cannot be made.
2. **A4 is not "nearly" invariant — it is bit-identical.** 742 components,
   F1 0.008772, squash IoU 0.4619, grass 11.76 %, 1237 unresolved boundaries, at
   1502 px and at 6009 px alike. The reason is that A4's input is a difference of
   two **z-depths**, and z is the one coordinate the focal length does not touch.
   Nobody predicted the invariance would be exact rather than approximate, and it
   is a much stronger statement about A4's design than "ratio-based" was.
3. **The largest thing `f` decides is how steeply the bed is believed to rake
   away — 13 to 42 degrees.** Not size, not flatness: rake. And no Phase A
   conclusion currently depends on it, which is why the sweep is so quiet. That
   is luck about *what Phase A happens to compute*, not robustness, and A6 is
   where it stops being lucky.
4. **A2's RANSAC seed turned out to be less stable than the whole focal-length
   assumption.** A1b went looking for the cost of an unknown camera and found a
   4x swing in A5's admissible-target count caused by a 1.2 %-inlier plane draw.
   The chunk's most actionable finding is about a different chunk.
5. **A quantity can move 40 % and mean nothing.** A2's residual, datum sigma and
   RANSAC threshold all move by 39.7 % across the sweep with a log-log slope of
   -0.27 — and their ratios are flat to the fourth decimal. Reporting the spread
   without the ratio would have manufactured a sensitivity that does not exist,
   which is the mirror image of the mistake R1 usually guards against.
6. **The one genuinely informative feature of the refinement curve is an
   interior maximum, and calibrating it needs the thing we do not know.** The
   peak sits at 1.08–12.10 x the true focal length depending on the surface's
   tilt. A beautifully shaped dead end.

---

## 9. Not done / deferred

* **No calibration, and none is possible.** The camera belongs to someone else.
  C0 retires all three (d) constants.
* **Absolute scale**, deliberately. No fiducial, no known dimension. A1 showed
  DA3's metres are `depth x f/300`, i.e. proportional to the very number this
  chunk has just declared assumed.
* **Distortion is registered as an unbounded (d) assumption.** The sweep that
  would bound it needs a straight edge this image does not contain.
* **The principal-point sweep stops at the soil band.** A4/A5 were re-run per
  focal length, not per principal point. A shear is not absorbed by the linear
  map, so that sweep is not free the way the focal one is; it is a real,
  bounded piece of work and it belongs with C0's real intrinsics.
* **A6 and A7 were not re-run.** A7 uses no geometry (R3: the VLM never sees
  coordinates). A6 does — its keep-out volume is built in the datum's frame, so
  it inherits the 16–49 deg tilt spread rather than the invariant part. Flagged
  below; it is the one Phase A stage whose focal sensitivity A1b has **not**
  measured.
* **One image.** Whether A4's exact invariance survives a scene where the datum
  is fitted differently is a B1 question; the derivation says it should, because
  it depends only on z-depths.
* **`f` and `process_res` were fixed but not jointly swept.** A1's finding that
  DA3's internal camera drifts 50 % with processing resolution means "the depth
  raster" and "the camera" are not independent. A1b fixed `process_res` per
  curve, as instructed, and did not explore the joint space.
* **Compute:** ~10 s for the refinement, ~6 min for the normal reconciliation,
  ~2 min for the principal point, ~7 min per A2 fit (10 of them, run in
  parallel, twice) and ~80 s per A4+A5 row. About 90 minutes of wall clock.

---

## 10. Implications for the roadmap

* **A6 — you are the exposed one.** Every stage A1b measured came out invariant,
  and A6 is the stage it did not measure. A6 builds its keep-out volume in the
  datum's frame, and the datum's *orientation* is the single quantity that moves
  most with `f` (16–49 deg, spread 85 %). Before A8 ships, A6 should either
  re-run `run_a6.py` against two A1b rows (`chunks/A1b/work/f3005` and
  `work/f6009` are on disk and loadable through
  `a2_api.load_a2(products=...)`), or state that its clearance dominates the
  tilt error. The second is probably true and should be written down rather than
  assumed.
* **A8 — nothing to change, and one line to add.** Every gate A8 depends on
  (`observed` status, coverage class, keep-out membership) sits on the invariant
  side of the ledger. The line to add is that `calib/plants_assumed.json` exists,
  carries provenance `assumed+refined`, and that any coordinate formed with it is
  `assumed_scale` — never `measured_scale`, which stays unreachable in Phase A.
* **A2 — fix the seed; it is your cheapest available robustness win.** See § 6.
  It is worth more than anything A1b changed. Note also that A2's `RESULTS.md`
  sensitivity row ("A1 depth product: plane normals differ by 7.6 deg") is now
  explained: 7.6 is the value *at f = 4453 px*, and it is 5.95 at 3005 px.
* **A1 — the "largest unquantified error in the whole stack" has been
  quantified, and it is small.** A1 wrote that DA3's internally-assumed FOV was
  that error. Measured end-to-end, a 4x swing in `f` changes no Phase A
  conclusion. The largest unquantified error is now A1's *other* number: the
  0.079–0.143 rdu cross-model depth disagreement, which is 14–26 datum sigma and
  is priced nowhere in the stack (A5 said the same thing from its own direction).
* **C0 — three things, in this order.** (i) Calibrate, and retire the three (d)
  rows. (ii) **Re-run this exact table** with the true intrinsics; it is a
  scripted rebuild (`sweep_all.sh`) and the reference row is the regression test.
  (iii) Note that C0 will *not* settle the 3005-vs-4453 question for
  `plants.jpeg` — a calibrated robot camera is a different camera. That question
  closes only with the original unstripped file. **The roadmap's own note
  stands: it is worth one message to ask whoever took the photo.**
* **B1 — one transfer question, sharper than before.** A1b's invariance results
  are *derivations*, not observations: they follow from `S = diag(s, s, 1)` and
  hold for any scene. What does not transfer is the *conclusion* that the focal
  assumption is harmless, because that depends on Phase A continuing to compute
  only invariant quantities. The moment anything downstream needs a direction —
  a gravity vector, a slope constraint, an approach angle for a tool — the 85 %
  tilt spread arrives all at once. B1 should treat "does any stage consume an
  absolute angle?" as a standing audit question.
* **Open question 3 (the scale story) gains one more piece of evidence.** Focal
  length turned out to be cheap to bound and, on this stack, free. Scale is
  neither, and the asymmetry the roadmap drew between them in Known gaps #4 is
  now measured rather than argued.
