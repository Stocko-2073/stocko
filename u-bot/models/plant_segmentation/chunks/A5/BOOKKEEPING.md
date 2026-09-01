# A5 — bookkeeping to merge into the repo-level files

I did **not** edit `RESULTS.md`, `CONSTANTS.md` or `PROGRESS.md` — A6 and A7 ran
in parallel. Below is the exact text to append to each, plus `.gitignore`
suggestions. The log entry uses `NNN` as the entry-number placeholder; the
manager assigns the real number at merge time.

---

## 1. Append to `RESULTS.md`

````markdown
## A5 — Stem-soil contact points

**Ground truth:** `groundtruth/` (A0), 768×1024 · **Scorer:** `chunks/A0/eval.py`,
unmodified
**Inputs:** A4 `load_a4()` under **both** policies, A2 `load_a2()`
(1344×1008, never resampled), A1 `primary_raster`, A3 material
**Date:** 2026-09-01 · **Scale confidence:** `scale_free`, 3-D distances in
**rdu**, image distances in px · **Datum: the STRAW surface**, not soil
**Findings:** `chunks/A5/FINDINGS.md` · **Default:** `chunks/A5/a5_api.py`

> **The roadmap's A5 done-criterion is EMPTY for this image.** It asks for
> "contact-point error in pixels for `visible` ground-truth points". A0 found
> **zero** `visible` points in `plants.jpeg` — all ten are `under_straw` with
> `localisation: estimated`, which A0's schema says must not be scored against.
> `eval.py` prints that warning rather than a misleading number, and so does
> this section. Everything below labelled *consistency* compares one estimate of
> an unobservable quantity with another.

### Counts by status

| Quantity | A4 `split` (shipped for targeting) | A4 `merge` | A0 GT masks (diagnostic) |
|---|---:|---:|---:|
| components | 742 | 207 | 10 |
| **observed** | **472** (63.6 %) | **164** (79.2 %) | 8 |
| **extrapolated** | **59** (8.0 %) | **11** (5.3 %) | 1 |
| **occluded** — no point emitted | **211** (28.4 %) | **32** (15.5 %) | 1 |
| **components silently given a fabricated point** | **0** | **0** | **0** |
| `lowest_visible_point` emitted | 741 / 742 | 207 / 207 | 10 / 10 |
| `lowest_visible_stem_point` emitted | 299 | 40 | 3 |
| R2-admissible (observed + observed datum + not off-frame) | 378 | 137 | 7 |
| median confidence, of those with a point | 0.71 | 0.81 | — |

**`observed` here means the material reaches the STRAW.** Nothing in this image
is observed to reach the soil, and A5 does not claim otherwise.

Why the occluded ones were refused (`split` / `merge`): beyond the tool budget
152 / 20; basal support under 9 px 34 / 4; **material more than 3σ *below* the
fitted datum 12 / 6**; axis runs along the datum 9 / 2; never reaches the datum
inside the 1 rdu ceiling 3 / 0; lands past A2's trust distance 1 / 0.

### Straw occlusion, asked three ways

| question | answer |
|---|---|
| fraction of *stem-soil* contacts hidden by straw | **10 / 10 = 100 %** (A0's labels; not an A5 measurement) |
| components whose lowest visible material is surrounded mostly by straw | **294 / 742 `split` (39.6 %)**, **140 / 207 `merge` (67.6 %)** |
| that surrounding material by pixel | **45.2 % straw**, 32.2 % grass, 10.6 % petiole, 6.2 % broadleaf, 4.6 % squash leaf |

Of the 270 non-observed `split` components, the thing in the way is foliage for
98, petiole for 40, straw for 33 — and for **97 there is nothing in the way at
all**: the material simply stops above the ground. C1's re-observation helps the
first group and cannot help the last.

### Is `observed` circular? — measured, and the answer is "substantially"

A2 selected ground inliers as everything within 3σ of its surface, **plant
material included**, so a low blade base is both "plant" to A3 and "ground" to A2.

| | `split` | `merge` | GT masks |
|---|---:|---:|---:|
| `observed` contacts whose base pixel is itself an A2 ground inlier | **410 / 472 (86.9 %)** | 150 / 164 (91.5 %) | 7 / 8 |
| median share of the local datum support (147 px = A2's fit scale) from non-plant material | 0.52 | 0.75 | 0.67 |

Not entirely circular — the datum under a typical base pixel is still about half
pinned by non-plant material — but **"observed" is a generous word for it**, and
the fix belongs to A2 (refit with A3's plant mask held out) or C1.

### Consistency vs A0's estimated points — DIAGNOSTIC, NOT ACCURACY

Median px on the 768×1024 grid, best-overlap assignment (generous; strict
IoU ≥ 0.5 matching leaves 3 instances). `eval.py` on the same points reports
`visible n=0` for both policies.

| | contact point | lowest visible point | centroid baseline | bottom-most-pixel baseline |
|---|---:|---:|---:|---:|
| **A0 GT masks** (A4 removed from the loop) | **26.4** (n=9) | 29.5 | 21.3 | **13.1** |
| `split` | 61.4 (n=9) | 54.4 | 60.1 | 51.3 |
| `merge` | 96.5 (n=6) | 126.4 | 95.1 | 191.4 |

**Two trivial image-space baselines beat the 3-D method on the median**, because
A0's points are a human's 2-D reading of where a stem was last seen heading, and
a 2-D estimator reproduces a 2-D heuristic. The baseline collapses exactly where
R2 cares most — on the squash it is **477.9 px** wrong, against A5's 142.3 px
from `split`'s largest squash component. On the nine weeds, A5's contact point
sits a median **26.4 px** from A0's estimate.

By eye (`figs/fig_crown_zoom.png`): A0's noted crown node (352, 516) lands
exactly on the petiole junction, and two `split` components put a
`squash_petiole` point within **~21 px** of it — but as fragments, never as
"the squash's contact point".

### Policy disagreement — one component decides it

| | `split` | `merge` | ratio |
|---|---:|---:|---:|
| components | 742 | 207 | 3.58× |
| components carrying an actionable point | **531** | **175** | 3.03× |
| observed | 472 | 164 | 2.88× |

`merge`'s component 1 is 938 112 px — 92 % of all plant material — and A5
statuses it **`occluded`** (lowest material 14.7σ *below* the datum). It
contains **488 `split` components carrying 319 points, 274 of them `observed`**.
The choice A4 could not settle turns 319 candidate targets into zero.
**Recommendation: A8 takes contact points from `split`; A6 keeps `merge` for
keep-out volumes.**

### Sensitivity (`split`)

| knob | values | observed | extrapolated | occluded |
|---|---|---|---|---|
| `MAX_EXTRAPOLATION_SIGMA` **(b) placeholder** | 0 / 5 / 10 / **20** / 40 / 80 / ∞ | **472 at every value** | 0 / 3 / 20 / **59** / 111 / 185 / 211 | 270 / 267 / 250 / **211** / 159 / 85 / 59 |
| `GROUND_BAND_K` (c, A2's) | 2 / **3** / 4 / 5 | 402 / **472** / 501 / 513 | 91 / **59** / 43 / 36 | 249 / **211** / 198 / 193 |
| `BASAL_BAND_K` (c) | 0.5 / **1** / 2 / 3 | 475 / **472** / 462 / 451 | 58 / **59** / 66 / 76 | 209 / **211** / 214 / 215 |
| `MIN_AXIS_POINTS` (a) | 5 / **9** / 25 / 49 | 472 (flat) | 71 / **59** / 41 / 24 | 199 / **211** / 229 / 246 |
| `MEDIAN_WINDOW` (a) | 1 / **3** / 5 | 498 / **472** / 439 | 45 / **59** / 82 | 199 / **211** / 221 |

**The one (b) constant cannot manufacture an `observed`** — it only moves a
component between "guess with a number attached" and "no answer". Since R2
admits a removal only on `observed`, the constant A5 cannot justify is also the
one that cannot cause a crop to be cut. Asserted in `test_a5.py`.

**Extrapolation-distance CDF** (budget removed; the curve C3 should read its own
budget off, `results/sweeps.json`): 211 components have an axis that reaches the
datum; distances 2.7σ (min) / 17.3 (p25) / **36.2 (median)** / 86.2 (p90) /
143.9 (max). At A5's 20σ placeholder, 59 are admitted.

### Runtime

~4 s for both policies plus the GT-mask oracle (Apple Silicon), on top of A4's
cached components. No model is run.
````

---

## 2. Append to `CONSTANTS.md` (Active table)

```markdown
| A5 | max extrapolation distance | 20 datum-σ = 0.1094 rdu | (b) | **Tool geometry, PLACEHOLDER awaiting C3.** Expressed in datum roughnesses because Phase A is scale-free and σ_datum is the only length the scene supplies. Caps both the extrapolation length and the lateral wander it may accumulate, so one tool-precision number governs the whole error budget. **Structurally cannot create an `observed` status**, and R2 admits a removal only on `observed` — so the constant A5 cannot justify is also the one that cannot cause a crop to be cut (`test_raising_the_tool_budget_never_creates_an_observed_point`). | 0 / 2 / 5 / 10 / **20** / 40 / 80 / 160 / ∞ σ → extrapolated 0/0/3/20/**59**/111/185/211/211, occluded 270/270/267/250/**211**/159/85/59/59, observed **472 at every value**. Distances are measured to a 1 rdu ceiling regardless of the budget, so `chunks/A5/results/sweeps.json → extrapolation_distance_cdf_split` is exact and C3 reads its own value off it | C3 |
| A5 | ground band multiplier | 3 σ_combined | (c) convention | **A2's registered ground-band multiplier, reused unchanged.** σ_combined = sqrt(σ_datum² + `height_sigma`²), i.e. A2's datum roughness *and* A2's measured gap-fill uncertainty at that pixel's own support distance. Material inside the band is *at* the datum; material more than the band *below* it is the surface being wrong, not a contact, and is refused. | 2/3/4/5 σ → observed 402/**472**/501/513 of 742 (13 % across the whole range) — `chunks/A5/results/sweeps.json → ground_band_k` | — |
| A5 | basal band | 1 σ_combined | (c) convention | Two heights differing by less than one combined datum σ are not distinguishable, so "the lowest material" is a band 8-connected to the minimum, not a pixel. The reported point is the band pixel nearest the band's 3-D centroid — a real material pixel, never the centroid. A restatement of A2's roughness, not a new scale. | 0.5/1/2/3 → observed 475/**472**/462/451 | — |
| A5 | in-component height median window | 3 × 3 px, min support 3 | (a) | A component's boundary pixels straddle material and background, so their depth is a mixture; heights are read as the median over the 3×3 neighbourhood **inside the component**. 3 is the support a one-pixel-wide stem supplies, so thin structure is not eroded. Smallest odd window — the same argument as A4's 5×5, one scale down, because A5 reads a height rather than fitting a plane. | window 1/3/5 → observed 498/**472**/439; the filter moves the count in the conservative direction | — |
| A5 | minimum points for a 3-D axis | 9 | (a) | 3 × 3 = the smallest support that overdetermines a 3-D line. Below it a direction would be *chosen*, not measured, and the component is refused (R4). The axis's own cone half-angle is `arctan(σ₂/σ₁)` of the basal scatter, so an isotropic blob refuses itself with no linearity threshold to pick. | 5/9/25/49 → extrapolated 71/**59**/41/24; `observed` unmoved | — |
| A5 | march reporting ceiling | 1.0 rdu | reporting limit, not a threshold | Terminates a runaway ray at the median scene depth. It bounds the length of the measured distance, never a decision: any axis needing more than a whole scene depth is past every candidate tool budget by two orders of magnitude. | n/a | — |
```

---

## 3. Append to `PROGRESS.md` (Log) — and set A5 → `done` in the Status table

```markdown
### NNN — 2026-09-01 · A5: stem-soil contact points

**Chunk:** A5

**Done**
- Contact points for every A4 component under **both** policies, with an honest
  three-way status and a reason in words. `split`: 742 components, **472
  observed / 59 extrapolated / 211 occluded**. `merge`: 207 → **164 / 11 / 32**.
  The same code on A0's ten GT instance masks (diagnostic, A4 removed from the
  loop): **8 / 1 / 1**. **Zero components anywhere received a fabricated point.**
- `lowest_visible_point` for 741 of 742 components and
  `lowest_visible_stem_point` for 299 — `null`, never substituted, where a
  component has no `squash_petiole` material (A0/A3 have no other stem class).
- `chunks/A5/a5_api.py` for A8, with `admissible()` enforcing the geometric half
  of R2 in code: `observed` status **and** an observed (not interpolated) datum
  **and** no `leaves_frame` unresolved edge from A4. 378 of 742 pass.
- 25 tests, mostly on a synthetic scene with known geometry, because the
  property under test is a refusal. The load-bearing ones: an isotropic blob is
  refused rather than given an axis; material below the datum is refused;
  raising the (b) placeholder never creates an `observed`; a steeply banked bed
  is handled identically to a level one; no shipped `occluded` component carries
  a point.
- Six figures, all carrying the datum caveat in the title, all read back by eye.

**Measured** — see `RESULTS.md`.
- **Straw**: 45.2 % of the material immediately around the components' lowest
  visible material; the majority material for 39.6 % of `split` components and
  67.6 % of `merge` ones. For **97 of 270** non-observed `split` components
  there is *nothing* in the way — the material just stops.
- **Circularity**: **410 of 472** `observed` contacts (86.9 %) stand on a pixel
  A2 used as a ground inlier. Median non-plant share of the local datum support
  is 0.52.
- **Consistency vs A0's estimated points** (diagnostic, not accuracy — there are
  zero `visible` GT points): contact median **26.4 px** on the GT masks,
  61.4 px under `split`. Two trivial image-space baselines beat it, and collapse
  on the crop (477.9 px vs A5's 142.3 px).
- **Policy disagreement**: 531 vs 175 actionable points. `merge`'s single
  938 k-px component holds 488 `split` components carrying 319 points, and is
  itself `occluded`.
- Sweeps over all five knobs; the (b) placeholder moves 152 components between
  `extrapolated` and `occluded` and **zero** into or out of `observed`.

**Decided**
- **Open Question 1 is resolved: the product target is the lowest visible point
  and its height above the STRAW datum. "Enters soil" is not a claim this stack
  may make from one overhead view of a mulched bed** — A0 sees no stem meet the
  ground, A2 has no soil to fit, and A5 measures the plant disappearing into
  mulch. Revisit after C3, which may moot it: a thermal or laser tool wants the
  growing point, which is above the straw and observable.
- **A8 takes contact points from `split`; A6 keeps `merge` for keep-out
  volumes.** `merge` returns one `occluded` blob for 92 % of the scene.
- **Material more than 3σ below the fitted datum is `occluded`, not a contact.**
  Nothing lies under the ground, so that is the surface disagreeing with the
  material, and R4 says report it rather than snap a point to zero.
- **`confidence` is an ordering, not a probability** (A3's caveat, restated).
  The safety field is `status`, and `admissible()` is the gate.
- The status vocabulary stays the roadmap's. `observed` is misleading for the
  soil question and the fix is the `product_target` field that travels with
  every record, not a private renaming.

**Surprised us**
- **A minimum over a large component finds the tail of the height error, not the
  plant's base.** Only 0.5 % of plant pixels sit more than 3σ below the datum,
  but a minimum over 750 k pixels goes straight to them: the GT squash's lowest
  point is a frame-edge leaf 582 px from its crown. **The bigger the plant, the
  worse the estimator** — the opposite of the usual expectation.
- **"Lowest point of the component" is the wrong concept for a vine.** The right
  object is a skeleton rooted at the crown — the same missing algorithm A4
  arrived at from the opposite direction.
- **`observed` was expected to be the rare status and came out at 63.6 %**,
  because the datum is the straw and plants do reach the straw.
- **86.9 % of those `observed` verdicts stand where A2 and A3 disagree** — a
  pixel A3 calls plant and A2 fitted its ground to.
- **The one (b) constant is structurally unable to open the R2 gate.** That was
  not designed in; it fell out, and it is now a test.
- **Two trivial baselines beat the 3-D method against A0's points**, because
  those points are a 2-D human reading. Both roadmap metrics for this image
  reward the simpler method for reasons unrelated to correctness.

**Next**
- A8 (needs A6 and A7): `segment_garden` / `plan_removals`, gate on
  `a5_api.admissible()`.
- A2 should publish a plant-excluded datum before B1 — it is the difference
  between `observed` meaning something and meaning "A2 and A3 disagreed here".
```

---

## 4. `.gitignore` suggestions

Append:

```gitignore
# A5: figures (13 MB). Rebuild in ~30 s with chunks/A5/figures.py.
chunks/A5/figs/*.png
```

**Deliberately NOT ignored:** `chunks/A5/products/*.json` (2.5 MB total, of
which `contacts_split.json` is 1.5 MB). They are the chunk's product and A8's
input, they are text, and they diff meaningfully. `chunks/A5/results/*.json`
(56 KB) likewise. `chunks/A5/__pycache__/` is already covered by the existing
`chunks/**/__pycache__/` rule.

---

## 5. Files A5 added

```
chunks/A5/
  README.md  FINDINGS.md  BOOKKEEPING.md
  a5_common.py  contact_points.py  run_a5.py  diagnostics.py  sweeps.py
  figures.py  a5_api.py  test_a5.py
  products/contacts_{split,merge,gt_instances}.json
  results/{status_counts,diagnostics,sweeps}.json
  figs/fig_{contacts_split,contacts_merge,crown_zoom,gt_instances,below_datum,sweeps}.png
```

**No dependency change.** A5 runs in `chunks/A3/.venv` exactly as A4 left it —
no new package, no new model weights, no new venv.
