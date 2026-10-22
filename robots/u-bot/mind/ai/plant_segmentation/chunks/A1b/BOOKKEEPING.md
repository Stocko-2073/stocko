# A1b — bookkeeping to merge into the repo-level files

A1b did **not** edit `PROGRESS.md`, `RESULTS.md` or `CONSTANTS.md`: chunk A8 was
running in parallel. Everything below is ready to paste. Chunk A1b's status
becomes **done**.

---

## 1. `RESULTS.md` — block to append (after the A1 block, or at the end)

```markdown
## A1b — Assumed intrinsics, bounded rather than hidden

**Input:** A1 both depth products via `chunks/A1/products/MANIFEST.json`; A2
`ground_inliers` as the soil band; the shipped A2 / A4 / A5 code driven at nine
assumed focal lengths. **Date:** 2026-09-01 · **Scale confidence:**
`scale_free`, all distances in **rdu**. **Absolute scale UNRESOLVED.**
**Datum:** the straw mulch surface, not soil.

### The camera A1b ships

| | |
|---|---|
| chosen `f` | **4453 px at 3000×4000** (38.5 mm-equivalent) = fx = fy 1496.28 px on the 1008×1344 depth grid |
| principal point / distortion / pixel aspect | image centre / zero / 1.0 — all category (d) |
| provenance | `assumed+refined` (the refinement was **run**; it did not succeed) |
| vs. DA3's own head (A1) | identical to its res-504 value; A1's usable band is 4159–4695 px, mean 4489 |
| vs. the roadmap's 26 mm prior (3005 px) | **1.48× larger**; the scene cannot adjudicate |
| absolute scale | **UNRESOLVED** |

File: `calib/plants_assumed.json`.

### The refinement failed, and here is the proof

| control | result |
|---|---|
| exactly planar depth map, planarity residual at f = 500 / 1502 / 3005 / 4453 / 20000 px | **1e-16 rdu at every one** — a change of `f` is the linear map diag(s, s, 1), and linear maps preserve planes |
| real soil band, planarity RMS 1502 → 6009 px | 5.27e-3 → 2.91e-3 rdu, **monotone**; minimum at the grid edge |
| real soil band, both scale-invariant normalisations | interior **maximum** (4506 px on res-1344, 5326 px on res-504), minima at both grid edges |
| **synthetic rough locally-planar surface with KNOWN f** = 1502 / 3005 / 6009 px | argmin at the grid edge (60 000 px) **every time — the estimator recovers nothing** |
| peak-location "estimator", ratio to true `f` across synthetic surfaces | **1.08–12.10** (3.3× spread, driven by surface tilt) → implied `f` ∈ [373, 4185] px, i.e. no constraint |

### What `f` actually changes

| assumed `f` | 1502 | 3005 | 4453 | 6009 |
|---|---|---|---|---|
| ground rake across the frame | 13° | 24° | — | 42° |
| A2 ground tilt from the optical axis | 16.3° | 30.2° | 40.8° | 49.4° |
| A2 two-product plane-normal disagreement (closed form) | 3.3° | 5.95° | **7.64°** | 8.79° |

A2's recorded 7.6° is reproduced exactly at f = 4453 px, which is the `f` A2's
own fits used. The disagreement is monotone in `f` and → 0 only as `f` → 0, so
it cannot select `f` either.

### Sensitivity across the sweep (9 focal lengths + A1's own camera as reference)

Roadmap set `{1502, 2774, 3005, 3236, 6009}` **widened per A1's FINDINGS** with
`{4159, 4453, 4489, 4695}` to cover DA3's own band. 10 A2 fits, 20 A4 builds,
20 A5 runs. Reference row reproduces every shipped Phase A number to **0.35 %**.

| metric | 1502 | 3005 | 4453 | 6009 | spread | verdict |
|---|---:|---:|---:|---:|---:|---|
| A2 inlier fraction | 0.2911 | 0.2911 | 0.2911 | 0.2911 | 0.0 % | **exactly invariant** |
| A2 `lam` / fit scale / trust distance / coverage fractions | 316 / 147 px / 240 px | same | same | same | 0.0 % | **exactly invariant** |
| A2 inlier residual RMS (rdu) | 8.73e-3 | 7.85e-3 | 6.88e-3 | 5.92e-3 | 39.7 % | moves — **units only** |
| A2 datum σ (rdu) | 6.97e-3 | 6.27e-3 | 5.49e-3 | 4.72e-3 | 39.7 % | moves — **units only** |
| **A2 residual / datum σ** | 1.2525 | 1.2525 | 1.2525 | 1.2525 | **0.0 %** | **invariant** |
| **A2 ground tilt (deg)** | 16.3 | 30.2 | 40.8 | 49.4 | **85.2 %** | **MOVES** |
| A4 continuity tolerance (rdu) | 4.238e-3 | 4.238e-3 | 4.238e-3 | 4.238e-3 | 0.0 % | **exactly invariant** |
| A4 split components / F1 | 742 / 0.008772 | same | same | same | 0.0 % | **exactly invariant** |
| A4 squash best IoU (split / merge) | 0.462 / 0.885 | same | same | same | 0.0 % | **exactly invariant** |
| A4 clover separate (split & merge) | yes | yes | yes | yes | 0.0 % | **exactly invariant** |
| A4 grass absorbed (split / merge) | 11.8 % / 83.3 % | same | same | same | 0.0 % | **exactly invariant** |
| A4 unresolved boundaries | 1237 | 1237 | 1237 | 1237 | 0.0 % | **exactly invariant** |
| A5 split observed | 475 | 475 | 476 | 475 | 0.4 % | invariant <1 % |
| A5 split arm-admissible | 376 | 376 | 379 | 381 | 1.3 % | invariant <5 % |
| A5 split extrapolated / occluded | 58 / 209 | 64 / 203 | 61 / 205 | 53 / 214 | 21 % / 6 % | ≤13 components move |
| A5 split GT-consistency median (px) | 54.4 | 61.4 | 61.4 | 61.4 | 11.3 % | one row moves |
| A5 merge arm-admissible | 137 | 137 | 137 | 137 | 0.0 % | **exactly invariant** |

**24 of 39 reported quantities are bit-identical across a 4× range of `f`.**
Of the 8 that move, 5 move only because their unit moves. **All three A4
verdicts — squash not one component (split) / one component (merge), clover
separate, 11.8 % grass absorbed — are identical at every focal length.**
**A3 was not re-run: its winning approach consults no geometry, so it is
focal-invariant by inspection.**

### Focal-invariance verdict for Phase A

| conclusion | verdict |
|---|---|
| A2's fit quality, coverage, trust distance, smoothing | **focal-invariant** (exactly) |
| A2's residual, datum σ, RANSAC threshold **in rdu** | scale with `f`; their **ratios are invariant** |
| A2's *orientation* of the ground | **NOT invariant** — 16°–49° over the sweep |
| A3's material classification | focal-invariant (uses no geometry) |
| A4's grouping, tolerance, components, F1 and all three verdicts | **focal-invariant** (exactly — `relief` is a difference of z-depths) |
| A5's statuses, admissibility, confidence ordering | focal-invariant to <1.3 % |
| A5/A6 absolute distances | never emitted; everything is rdu, `scale_free` |
| absolute scale | **UNRESOLVED**, deliberately, everywhere |

### The other two (d) constants

| assumption | swept | effect |
|---|---|---|
| principal point at the image centre | ±1 / 2 / 5 % of image width, both candidate `f` | ground normal moves ≤ **0.23°** at 1 %, ≤ **1.11°** at 5 %; planarity residual ≤ 2.1 % |
| zero distortion | **not sweepable from this image** | no straight edge in frame; the longest linear features are grass and straw, neither straight nor known to be. Registered unbounded, retired by C0 |

### Discovered, not sought: A2's RANSAC seed is unstable

A2 seeds its outer loop at 1.2 % inliers. Re-drawing that seed per `f` (the
shipped code path) makes it jump to a different plane above f = 4159 px, and
the outer loop does not recover:

| | good seed | bad seed |
|---|---:|---:|
| A2 inlier fraction / edf / fit scale | 29.3 % / 63 / 147 px | 45.2 % / 936 / 38 px |
| A4 squash best IoU | 0.462 | **0.314** |
| A5 split observed / arm-admissible | 483 / 381 | **311 / 94** |

**A2's seed instability costs A5 four times more than the entire focal-length
sweep does.** A1b's primary sweep therefore transports the seed plane from the
reference row by the exact closed form; the free-seed sweep ships as the
evidence (`chunks/A1b/results/sensitivity.json → free_seed_control`).

### Not scored against ground truth

A1b introduces no new prediction and is scored against nothing. Every number
above is either an internal sensitivity, a control with a known answer, or a
re-run of an already-scored Phase A stage under a different assumed camera.
The A5 GT-consistency row remains what A5 declared it: a **diagnostic, not an
accuracy** — all ten A0 contact points are `estimated` / `under_straw`.
```

---

## 2. `CONSTANTS.md` — changes

### 2a. REPLACE the three existing A1b (d) rows (their sweeps are now done)

Find these three rows in the **Active** table:

```
| A1b | `f` initial | 3005 px | (d) | 26 mm-equiv phone main camera at 3000×4000, via `f_px = f_eq × diag_px / 43.27 mm`. Camera unavailable, EXIF stripped. | **required** — `f ∈ {1502, 2774, 3005, 3236, 6009}` | C0 |
| A1b | principal point | image centre (1500, 2000) | (d) | No calibration available. | **required** — with `f` sweep | C0 |
| A1b | distortion | zero | (d) | Phone ISPs pre-correct most lens distortion. | **required** — bound the residual | C0 |
```

and replace them with these four:

```
| A1b | `f` initial | 3005 px | (d) | 26 mm-equiv phone main camera at 3000×4000, via `f_px = f_eq × diag_px / 43.27 mm`. Camera unavailable, EXIF stripped. **Not the shipped value** — kept as the recorded prior against which the chosen `f` is 1.48× larger; the scene cannot adjudicate between them. | **done** — `f ∈ {1502, 2774, 3005, 3236, 4159, 4453, 4489, 4695, 6009}` px, widened per A1's FINDINGS to cover DA3's own 4159–4695 band. A2 + A4 + A5 fully re-run at every value: 24 of 39 reported quantities **bit-identical**, all three A4 verdicts identical, A5 admissible-target count within 1.3 %. `chunks/A1b/results/sensitivity.json` | C0 |
| A1b | `f` **chosen** (shipped) | **4453 px @ 3000×4000** (fx = fy = 1496.28 px on the 1008×1344 depth grid; 38.5 mm-equivalent) | (d) | The planarity refinement the roadmap specified is **degenerate**: changing `f` maps the cloud by the linear map diag(s, s, 1), which preserves planes exactly, so planarity residual has no interior optimum — proved on an exactly planar depth map (1e-16 rdu at every `f`) and on a synthetic surface with a *known* `f` that the estimator fails to recover. The value is therefore **adopted, not measured**: it is DA3's own res-504 camera estimate, which the depth field being back-projected is conditioned on, and which every shipped Phase A product already used. Provenance in `calib/plants_assumed.json` is `assumed+refined`, where "refined" records that the refinement was run and reports that it failed. | **done** — same sweep as the row above; the full 72-point refinement curve in three normalisations is in `chunks/A1b/results/focal_refinement.json` and in `calib/plants_assumed.json` | C0 |
| A1b | principal point | image centre — (1499.5, 1999.5) at 3000×4000 | (d) | No calibration available. DA3 pins its own principal point to the image centre too, so this matches the geometry the depth was produced under. | **done, partial** — offsets of ±1 / 2 / 5 % of image width in x, y and diagonally, at both candidate `f`: the fitted ground normal moves ≤ **0.23°** at 1 % and ≤ **1.11°** at 5 %; planarity residual moves ≤ 2.1 %. Covers the soil-band geometry every later stage is built on; the downstream stack was **not** re-run per principal point, and a shear is not absorbed by the focal sweep's linear map. `chunks/A1b/results/principal_point_sweep.json` | C0 |
| A1b | distortion | zero (all coefficients) | (d) | Phone ISPs pre-correct most lens distortion — a statement about phones in general, not a measurement of this camera. | **NOT BOUNDED — declared, with the reason measured.** Bounding a distortion model needs something known to be straight; `plants.jpeg` contains none. Its longest linear features are grass blades and straw stalks, which are neither straight nor known to be, so any bound computed here would be a bound on the straightness of straw. This is the one A1b assumption that stays unbounded, and it is recorded as such rather than given a fake sweep. `chunks/A1b/results/principal_point_sweep.json → distortion` | C0 |
```

The `absolute scale` row is unchanged and stays exactly as it is.

### 2b. APPEND these new A1b rows to the Active table

```
| A1b | pixel aspect fx/fy | 1.0 (square pixels) | (d) | A1b's pinhole model assumes square pixels. DA3's own head reports fx/fy = 0.991 at res 504 — inside A1's registered 5 % tolerance — so the assumption is consistent with the only camera estimate available. | **done** — the sweep's `manifest` row uses A1's actual anisotropic camera (fx 4453, fy 4492 px @ 3000×4000) and the `f4453` row the square-pixel one. Every A4 verdict identical; A2 residual differs by 0.4 %; A5 observed 472 vs 476 of 742 components. | C0 |
| A1b | `f` sweep set | {1502, 2774, 3005, 3236, 4159, 4453, 4489, 4695, 6009} px @ 3000×4000 (13–52 mm-eq) | (c) convention | The roadmap's five values plus the four A1's FINDINGS asked for, so DA3's physically-consistent band (4159–4695 px) is covered rather than stepped over. Bounds, not candidates: 13 mm and 52 mm are there to bracket. | the sweep is itself the sweep | C0 re-runs it with true intrinsics |
| A1b | focal-refinement search grid | 400–60 000 px, 72 log-spaced values | compute budget | Wide enough that an interior optimum could not be missed. Not a threshold: it decides how long the scan takes, not what counts as a minimum. | the argmin lands on the grid edge at both ends, which is the finding | — |
| A1b | planarity patch window | 33 px (res-1344 raster) / 17 px (res-504) | (a) instrument | The window A2's own local-planarity curve is defined at, matched to each raster's sampling so the two products are compared at the same physical scale. Only sets where the residual is read; the invariance result does not depend on it. | three normalisations of the same patch statistic, all reported | — |
| A1b | A2 seed-plane transport (sweep control) | closed form `n(f) ∝ (n_x·f/fx₀, n_y·f/fy₀, n_z)` from the reference row | (a) instrument / exact algebra | Not a tuned value: the exact transformation of a plane normal under the change of camera. Used so the sweep measures `f` and not A2's 1.2 %-inlier RANSAC draw, which jumps to a different plane above f = 4159 px and takes A5's admissible count from 381 to 94. Both sweeps ship. | free-seed control sweep, all nine `f`: `chunks/A1b/results/sensitivity.json → free_seed_control` | A2 fixes the seed |
```

### 2c. One correction to an existing A1 row (optional, factual)

`A1 | DA3 model-estimated f` says "A1b reconciles; C0 retires". A1b did **not**
reconcile it — it proved the reconciliation is impossible from this image. If
the register's **Retired by** column is meant to stay accurate, change that
cell to:

```
| A1b showed the reconciliation is impossible from one image (planarity is exactly focal-invariant); C0 retires
```

---

## 3. `PROGRESS.md`

### 3a. Status table — change one row

```
| A1b | Assumed intrinsics, bounded rather than hidden | A1 | done | `chunks/A1b/FINDINGS.md` |
```

and update the **Next up** line to whatever A8's state is when this lands (A1b
is no longer in progress).

### 3b. Log entry to append at the bottom (`NNN` = next number)

```markdown
### NNN — 2026-09-01 · A1b: assumed intrinsics, bounded rather than hidden

**Chunk:** A1b → done

**Done**
- Ran the roadmap's planarity refinement of `f` as specified — 72 focal lengths
  from 400 to 60 000 px, both A1 depth products (`process_res` fixed per curve
  as A1 required), A2's `ground_inliers` as the soil band, three normalisations,
  bootstrap band — and **found it degenerate**.
- Shipped `calib/plants_assumed.json`: pinhole, no distortion, principal point
  at the image centre, square pixels, **f = 4453 px at 3000×4000**
  (38.5 mm-equivalent), provenance `assumed+refined`, carrying the full
  refinement curve and the sentence `refinement_outcome: DEGENERATE`.
- Re-ran the whole downstream stack at nine focal lengths — the roadmap's five
  widened with `{4159, 4453, 4489, 4695}` per A1's FINDINGS so DA3's own band is
  covered — plus a reference row on A1's actual camera. **10 complete A2 fits,
  20 A4 builds, 20 A5 runs.** Nothing was frozen: A2's RANSAC threshold and
  `lam` and A4's continuity tolerance were re-measured off the image at each `f`,
  as those chunks do per image.
- Answered A2's second question: the 7.6° plane-normal disagreement between A1's
  two depth products, as a function of `f`, three ways (closed form,
  least-squares refit, RANSAC refit).
- Swept the principal point; declared distortion unbounded with the reason
  measured rather than asserted.
- 15 tests. The load-bearing ones assert the algebra, the degeneracy (including
  a test that fails if the refinement ever starts working), and that nothing
  here can present an assumed camera as measured.
- **No new dependency, no new venv.** A2's re-fits ran in `chunks/A1/.venv`,
  A4/A5's in `chunks/A3/.venv`, each in the venv its own chunk shipped with.

**Measured** — see `RESULTS.md`.
- The refinement has **no interior optimum, and cannot have one**: changing `f`
  maps the cloud by the linear map `diag(s, s, 1)`, which preserves planes
  exactly. An exactly planar depth map has residual 1e-16 rdu at *every* focal
  length; a synthetic rough locally-planar surface with a **known** `f` of 1502 /
  3005 / 6009 px returns the grid edge every time.
- **24 of 39 reported quantities are bit-identical across a 4× range of `f`.**
  All three A4 verdicts — squash not one component under `split` and one
  component under `merge`, clover separate, 11.8 % grass absorbed — are identical
  at every focal length, as are 742 components, F1 0.008772, squash IoU 0.4619
  and 1237 unresolved edges. A5 moves by ≤1.3 % on admissibility.
- What *does* move: the **absolute orientation of the ground**, 16.3° → 49.4°
  from the optical axis over the sweep (spread 85 %). A2's residual, datum σ and
  RANSAC threshold move 39.7 % — and their **ratios are flat to four decimals**,
  so that is a change of unit, not of conclusion.
- Reference row reproduces every shipped Phase A number to **0.35 %**.
- Principal point: ±5 % of image width moves the ground normal ≤1.11°.

**Decided**
- **`f` = 4453 px, adopted rather than measured**, because the depth field is
  conditioned on DA3's own estimate and the scene cannot adjudicate between that
  and the roadmap's 26 mm prior (3005 px, 1.48× smaller). It stays category (d);
  `assumed` mode still refuses `model_estimated` intrinsics, and A1b supplies its
  own object rather than laundering DA3's.
- **Report the refinement as failed**, ship the whole curve and both controls,
  and put the failure in the calib file next to the value so they cannot be read
  apart.
- **Hold A2's RANSAC seed fixed across the sweep** (transported by the exact
  closed form), because otherwise the sweep measures A2's seed lottery. Ship the
  free-seed sweep too, as the evidence.
- **No Phase A result needs re-scoring**: A1b's chosen `f` *is* the camera Phase
  A used.
- **Absolute scale stays unresolved.** Nothing in `calib/plants_assumed.json`
  implies otherwise, and a test enforces it.
- A3 declared focal-invariant by inspection — its winner uses no geometry —
  rather than by nine identical rows.

**Surprised us**
- The refinement is degenerate **regardless of DA3**. The roadmap expected to
  recover DA3's assumption instead of truth; in fact there is nothing to
  recover, and the synthetic control proves it with DA3 out of the room.
- A4 is not "nearly" invariant, it is **bit-identical** — because its input,
  `relief = A2 soil depth − A1 depth`, is a difference of two z-depths, and z is
  the one coordinate a focal length does not touch. That can be derived, not
  just observed.
- The biggest thing `f` decides is **how steeply the bed is believed to rake
  away**: 13° at 1502 px, 42° at 6009 px. Not size, not flatness — rake.
- **A2's RANSAC seed is less stable than the entire focal-length assumption.**
  Seeded at 1.2 % inliers, the winning plane jumps ~40° somewhere between
  f = 4159 and 4453 px and the outer loop diverges: squash IoU 0.462 → 0.314,
  A5 admissible targets 381 → 94. A1b went looking for the cost of an unknown
  camera and the most actionable finding is about a different chunk.
- A quantity can move 40 % and mean nothing: A2's residual and its own σ move
  together, and the ratio is flat.

**Next**
- A6 is the one Phase A stage A1b did not re-run and the only one that consumes
  an absolute orientation; it should either be re-run against `work/f3005` and
  `work/f6009` or state that its clearance dominates the 16°–49° tilt spread.
- A2 should fix its seed — cheapest robustness win in the stack.
- Ask whoever took `plants.jpeg` for the unstripped original. It is the only
  thing that would close the 3005-vs-4453 question, and C0 will not.
```

---

## 4. `.gitignore` — suggested additions

`chunks/A1b/work/` is **~900 MB**: ten full sets of A2 rasters plus A4 component
maps, twice over (seeded and free-seed). Everything in it is rebuildable with
`chunks/A1b/sweep_all.sh`, and nothing downstream reads it.

Append:

```gitignore
# A1b: one complete set of A2 + A4 products per assumed focal length, twice
# over (seeded and free-seed sweeps) — ~900 MB. Rebuild in ~90 min with
# chunks/A1b/sweep_all.sh; every number derived from it is in
# chunks/A1b/results/*.json, which ARE committed.
chunks/A1b/work/
chunks/A1b/figs/*.png
```

**Keep committed** (small, and the chunk's actual output): `calib/`,
`chunks/A1b/results/*.json`, `chunks/A1b/results/sensitivity_table.md`, and
every `.py` / `.sh` / `.md` in `chunks/A1b/`. Note the existing
`chunks/**/*.npy` rule already covers the rasters inside `work/`, but not the
per-row JSON or the `.png`s, hence the explicit directory rule above.
