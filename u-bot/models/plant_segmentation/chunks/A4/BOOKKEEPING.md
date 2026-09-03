# A4 — bookkeeping to merge into the repo-level files

I did not edit `RESULTS.md`, `CONSTANTS.md` or `PROGRESS.md`. Below is the exact
text to append to each, plus `.gitignore` suggestions.

---

## 1. Append to `RESULTS.md`

```markdown
## A4 — Grouping by connectivity, not distance

**Ground truth:** `groundtruth/` (A0), 768×1024 · **Scorer:** `chunks/A0/eval.py`,
unmodified, greedy 1-1 at IoU ≥ 0.5
**Inputs:** A1 `primary_raster` (1344×1008 float, **never resampled**), A2
`soil_surface_depth`, A3 `segment_material()`, A3's independent SAM partition
**Date:** 2026-09-01 · **Scale confidence:** `scale_free`, all distances in
**rdu** · **Datum: the STRAW surface**, not soil
**Findings:** `chunks/A4/FINDINGS.md` · **Default:** `chunks/A4/a4_api.py`

The graph is built on the depth grid and the component map is brought down to
768×1024 by nearest neighbour for scoring; the report says so.

### Instances

| Quantity | A4 `split` (shipped) | A4 `merge` | Baseline |
|---|---:|---:|---:|
| GT instances / predicted | 10 / 674 | 10 / 192 | 10 / 5 |
| TP / FP / FN | 3 / 671 / 7 | 2 / 190 / 8 | 0 / 5 / 10 |
| Precision / Recall / **F1** | 0.0045 / 0.300 / **0.0088** | 0.0104 / 0.200 / **0.0198** | 0 / 0 / **0.0000** |
| **Squash best IoU** | **0.4619** | **0.8850** | 0.4248 |
| **Squash as one component?** | **no** — 69 parts ≥ 200 px, largest covers 46.9 % | **yes** — largest covers 95.6 % | no — 3 parts |
| **Clover (GT id 3) separate?** | **yes** — 0.0 % of it in the crop component | **yes** — 0.0 % | yes |
| **Grass absorbed into the crop** | **11.8 %** (12 476 / 106 099 px) | 83.3 % | **53.0 %** |
| Matched GT ids | 2, 7, 8 | 1, 7 | none |

**Against the targets the baseline set.** Grass absorption **53.0 % → 11.8 %**,
a 4.5× reduction — met, and the clearest win. Squash as one component at
IoU ≥ 0.5 — **not met** by the shipped configuration (0.462, up from 0.425), met
by the `merge` variant (0.885) which costs 83 % grass absorption. Clover stays
separate under every configuration, and unlike the baseline it does so
*structurally*: A4 contains no distance, so no tolerance can bridge the straw
between two plants (asserted in `test_a4.py` up to 1e6 rdu).

### Ceilings, measured before the method was scored

| bound | instance F1 |
|---|---:|
| perfect grouping on A3's plant mask (mask IoU 0.886 vs GT plant) | **1.0000** |
| **oracle edges** — every adjacent fragment pair that is truly one plant linked, no other | **0.0315** (recall 1.000, precision 0.016, squash IoU 0.876) |

The oracle bound is 0.031 because ~400 correctly-separated grass components each
count as a false instance: A0 excludes GT grass instances from `n_gt` but has no
symmetric exclusion on the prediction side. Reported symmetrically as a labelled
diagnostic (predicted majority-GT-grass components excluded): F1 **0.0112**
(`split`) / **0.0223** (`merge`). **Not the headline.**

### The tolerance, and what the sweeps say

The roadmap's literal reading — A1's `local_planarity_p10` at win3–win9 — **fails
here**: at 1.29e-4 rdu the scene comes out in 1 751 components, squash IoU 0.193.
That constant is a *tenth* percentile, and it sits at the **median** of the
continuity residual over pixel pairs that are inside one fragment and therefore
continuous by construction. The shipped tolerance re-measures the same estimator
on those pairs and takes p90: **4.238e-3 rdu**, category (c).

| tol (rdu) | 1.3e-4 | 1e-3 | 3e-3 | **4.24e-3** | 6e-3 | 1e-2 | 3e-2 | 1.0 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| squash IoU | 0.193 | 0.231 | 0.245 | **0.462** | 0.557 | 0.819 | 0.889 | 0.894 |
| grass absorbed | 0.2 % | 0.3 % | 3.3 % | **11.8 %** | 20.1 % | 52.6 % | 81.7 % | 92.7 % |
| components | 1751 | 1380 | 901 | **742** | 607 | 439 | 204 | 111 |

Usable window for squash IoU ≥ 0.5: tol ∈ [6e-3, 1.0], a factor of **167**,
against `eps`'s 1.3×. Usable window for squash ≥ 0.5 **and** grass < 53 %:
tol ∈ [6e-3, 1e-2], a factor of **1.7**. **Removing `eps` did not remove the
narrow window; it changed the constant's provenance from hand-set-per-capture to
measured-off-the-image.**

The within-fragment quantile that sets the tolerance is the sensitive knob:
q = 90 (fixed a priori, unmoved) gives squash 0.462 / grass 11.8 %; q = 92 gives
0.557 / 20.1 % and would have met both targets. Disclosed, not harvested.

Other sweeps (`chunks/A4/results/sweeps.json`): the continuity statistic barely
matters (raw step 0.468, second difference 0.462, plane extrapolation 0.314; all
three separate same-plant from different-plant boundaries at AUC ≈ 0.66);
`MIN_FRAGMENT_PX` 1→100 moves squash IoU 0.322–0.462; SAM-region-only nodes score
0.355 against 0.462 for region × class.

### Unresolved edges

| kind | count |
|---|---:|
| `ambiguous_boundary` (`p25 ≤ tol < p75` — part continuous, part step) | **1 237** |
| `occluded_by` (two fragments sharing an occluder that is in front of both) | **10 059** |
| `leaves_frame` | **113** |
| **total** (8 185 join two *distinct* components) | **11 409** |

None is resolved by extrapolation (R4). The occlusion list is built with **no
distance term at all** — pairs qualify by sharing an occluder, never by being
close. `chunks/A4/products/unresolved_edges_default.json`,
`chunks/A4/figs/fig_unresolved.png`.

### Where the error comes from (A3 material vs. A0 material)

| | A3 material (shipped) | A0 material (oracle, diagnostic) |
|---|---:|---:|
| instance F1 / TP | 0.0088 / 3 | **0.0402 / 7** |
| grass absorbed | 11.8 % | **2.4 %** |
| squash best IoU | 0.462 | 0.302 |

Weed recall is limited by A3; squash fragmentation is not — it gets *worse* with
perfect labels, so it is a geometry-and-occlusion problem.

### Open Question 2 — "does instance segmentation earn its place in v1?"

Per-pixel vs per-component crop/weed decisions, same frame, same ground truth:

| policy | **crop px targeted** (of all crop) | weed px targeted (of all weed) | instance F1 | squash IoU | grass absorbed |
|---|---:|---:|---:|---:|---:|
| semantic class only, per pixel | **16.71 %** | 79.5 % | n/a | n/a | n/a |
| + A2 soil surface (`confident_above(3σ)`) | **13.96 %** | 65.5 % | n/a | n/a | n/a |
| + 2-D connected components (no depth) | **0.009 %** | 3.8 % | **0.0597** | **0.892** | 84.5 % |
| A4 3-D connectivity, `split` | 9.48 % | 67.9 % | 0.0088 | 0.462 | 11.8 % |
| A4 3-D connectivity, `merge` | **1.65 %** | 20.4 % | 0.0198 | 0.885 | 83.3 % |

**Answer: grouping earns its place on R2 grounds, not on F1.** Deciding
crop-vs-weed per pixel puts 16.7 % of the crop under the tool; deciding it per
component puts 1.65 % there — a 10× reduction in the catastrophic direction.
But the *simplest* grouping (2-D connected components, no depth at all) beats A4
on instance F1 by 7× and puts the squash out in one piece — **by
under-segmenting**: it absorbs 84.5 % of the grass and reaches only 3.8 % of the
weed pixels, against A4's 67.9 %. Instance F1 on this metric rewards
under-segmentation; the honest v1 comparison is the pair (crop at risk, weed
reached).

### Runtime

~20 s for the graph (Apple Silicon), on top of A3's cached 5 s of DINOv2
features. No SAM is run. Against ZeroPlantSeg's ~8 min.

### Contact points

n/a — A4 produces no contact points. That is A5.
```

---

## 2. Append to `CONSTANTS.md` → Active

```markdown
| A4 | depth-continuity tolerance | 4.238e-3 rdu | (c) | The p90 of the continuity residual measured over pixel pairs **inside one fragment**, which are continuous by construction — "a boundary is a discontinuity when it is rougher than 90 % of material already known to be continuous". Re-measured per image; nothing is hard-coded. **A1's registered `local_planarity_p10` was tried first and fails**: it is a *tenth* percentile and sits at the *median* of the within-fragment residual, so it rejects half of all continuous adjacencies and shatters the scene (1 751 components, squash IoU 0.193). | tol 1e-5…1 rdu (5 decades) and quantile 50…99, both policies — `chunks/A4/results/sweeps.json`; squash IoU ≥ 0.5 over tol ∈ [6e-3, 1.0] (167×), squash ≥ 0.5 **and** grass < 53 % over [6e-3, 1e-2] (1.7×) | B1 decides whether the quantile transfers |
| A4 | within-fragment quantile | 90 | (c) convention | Defines the tolerance above. Fixed in `run_a4.py` before any score was computed and not moved. **q = 92 would have met both roadmap targets and q = 90 does not** — a two-percentile move flips the squash verdict, and that is the method's real fragility. | 50/60/70/75/80/85/88/90/92/95/97/99 — `sweeps.json` → `quantile_sweep` | B1 |
| A4 | boundary link quantiles | p25 / p75 | (c) convention | A shared boundary is judged by its quartiles, never by one pixel: `p75 ≤ tol` connected, `p25 > tol` separated, otherwise **unresolved and recorded**. Stops a handful of leaking pixels merging two plants and a handful of noisy ones splitting one. | the p25 / p50 / p75 link rules are all run in `sweeps.json`; the third outcome takes 1 237 of 4 004 boundaries | — |
| A4 | plane-fit / stencil support | 5 × 5 px | (a) | Smallest odd window that overdetermines a 3-parameter plane. Sets the link stencil, hence which A1 window was read first. Only the `plane5` statistic uses it; the shipped `secdiff` statistic uses a 3-point directional stencil. | statistic sweep: step / secdiff / plane5 → squash IoU 0.468 / 0.462 / 0.314 | — |
| A4 | pixel adjacency | 8-connected | (a) | The roadmap's registered adjacency, used unchanged. | n/a | — |
| A4 | minimum fragment | 25 px | (a) | A fragment smaller than the plane fit's own 5×5 support carries no surface to test continuity against, so it is merged into the neighbour it shares the longest boundary with — purely geometric, no class and no depth. Numerically identical to A0's "min reviewable region" and A3's `MIN_REGION`, reused deliberately. 2 122 fragments (20 149 px, 2.0 % of plant material) merged this way. | 1 / 9 / 25 / 49 / 100 px → squash IoU 0.322 / 0.303 / 0.462 / 0.418 / 0.429, grass 8.3 / 6.2 / 11.8 / 9.5 / 9.3 % | — |
| A4 | occluder pair-list cap | 200 pairs per occluder | reporting limit, not a threshold | Bounds the length of the written unresolved-edge list only; applied after the pairs are found, and it thresholds no geometric quantity. 16 of the scene's occluders hit it. | n/a | — |
```

Note for whoever merges this: A4 introduces **no (d) constants** and **no
constant with a unit of length in the image plane**. `chunks/A4/test_a4.py`
asserts both properties by parsing the source, and `ALLOWED_CONSTANTS` in that
file is the machine-readable twin of the rows above.

---

## 3. Append to `PROGRESS.md` → Log (and set A4 → `done` in the status table)

```markdown
### 006 — 2026-09-01 · A4: grouping by connectivity, not distance

**Chunk:** A4 — Grouping by connectivity, not distance

**Done**
- Built the graph the roadmap asked for: nodes are mask fragments (A3's SAM
  partition crossed with the A3 material class), edges assert 3-D contiguity
  (8-adjacent **and** continuous in depth after subtracting A2's datum), and
  connected components are plants. Built on the A1 float raster at its native
  1344×1008 with **the depth never resampled**; the component map comes down to
  A0's 768×1024 by nearest neighbour for scoring.
- **No spacing constant exists in the code path, and `test_a4.py` enforces it**
  by parsing every A4 module (comments and docstrings stripped) for `eps`,
  radius, `max_gap`, `spacing`, `cm`, … and by failing on any module-level
  numeric constant not in an allow-list carrying its R1 category. The structural
  guarantee behind it: fragments that do not touch are never linked at any
  tolerance — asserted synthetically up to 1e6 rdu.
- Made the third outcome first-class: a boundary is `connected` (p75 ≤ tol),
  `separated` (p25 > tol), or **`unresolved`** — recorded, not decided. Shipped
  11 409 unresolved edges in three kinds (`ambiguous_boundary` 1 237,
  `occluded_by` 10 059, `leaves_frame` 113) plus the visualisation. The
  occlusion list is built with **no distance term at all**: a pair qualifies by
  sharing an occluder that stands in front of both, never by being close.
- Shipped both unresolved-edge policies, because R2 and R4 point opposite ways:
  `split` (R4 — an undecided link is not a link) and `merge` (R2 — a split crop
  gives A6 a keep-out volume with holes in it).
- Shipped `a4_api.load_a4()` with `unresolved_for(component)`, 16 tests, four
  figures checked by eye, and `fast_eval.py` — a vectorised twin of `eval.py`'s
  instance metrics for the sweeps, asserted to agree with it exactly.

**Measured** — see `RESULTS.md`. Headline: instance F1 **0.0088** against the
baseline's **0.0000**; squash best IoU **0.462** against 0.425 but **not one
component** (69 parts); clover **stays separate**; grass absorbed into the crop
**11.8 %** against **53.0 %** — 4.5×, the clearest win. The `merge` variant puts
the squash out as one component (IoU **0.885**) and absorbs **83 %** of the
grass. **Neither policy meets all three roadmap targets at once.** Ceilings
measured first: perfect grouping on A3's plant mask scores **1.0**, and an
**oracle that knows the truth for every edge scores F1 0.031** (recall 1.0,
precision 0.016).

**Decided**
- **The continuity tolerance is (c), not (a).** A1's registered
  `local_planarity_p10` is a *tenth* percentile and lands at the *median* of the
  residual over pairs inside one fragment; used as an acceptance threshold it
  rejects half of all continuous adjacencies. A4 re-measures the same estimator
  where it is needed and takes the p90: 4.238e-3 rdu, 33× A1's win9 value.
- The quantile (90) was fixed before scoring and has **not** been moved, even
  though q = 92 would have met both targets. Recorded as the method's fragility
  rather than harvested as a result.
- Grass components are never suppressed to flatter the score. The symmetric
  prediction-side exclusion is reported only as a labelled diagnostic.
- **ZeroPlantSeg is killed from the runtime path** and kept as a candidate
  offline auto-labeller for B2 (open question 4 — see below).

**Surprised us**
- **A1's registered depth-noise constant is the wrong percentile for this job by
  33×.** It describes the flattest tenth of the scene, not typical continuous
  material. Every value A1 registered lands in the shattered regime. A2 had this
  argument about *window size*; A4's version is about *percentile*, and it is
  worse because the number looks like it transfers.
- **A squash is not a connected surface.** Of 1 524 adjacent fragment pairs that
  both belong to the squash, the median across-boundary depth step is 5.03e-3
  rdu — 0.92 datum-σ, a real 3-D discontinuity. Those are leaf-over-leaf overlaps.
  The plant connects only through its petioles, and those junctions are a tiny
  minority of its internal adjacencies, so the whole plant hangs on a handful of
  links that a second difference reads as high curvature.
- **Every continuity statistic scores AUC ≈ 0.66** at separating "same plant"
  from "different plant", and normalising by each fragment's own roughness does
  not help. That is not a measurement failure: one plant's leaves overlap with a
  real step, and a grass blade lying on a leaf is in real contact. Contiguity and
  identity are genuinely different questions in this scene.
- **A perfect edge oracle scores F1 0.031.** ~400 correctly-separated grass
  components each count as a false instance. A0 excludes GT grass from `n_gt`
  and has no symmetric exclusion on the prediction side, so **the contract
  punishes the behaviour A0 itself declared unresolvable**. A5–A8 will hit this.
- **The simplest possible alternative beats A4 on the metric.** Plain 2-D
  connected components with no depth at all: F1 0.0597, squash in one piece, and
  the safest policy in the table — because it gives up, absorbing 84.5 % of the
  grass and reaching 3.8 % of the weed pixels against A4's 67.9 %.
- **A3's material map was not the constraint A3 predicted.** Its plant mask
  supports a ceiling of exactly 1.0, so the mask is fine; `squash_petiole` IoU
  0.36 was the wrong worry. What A3 costs is *weed recall* (oracle labels take
  TP from 3 to 7) — and with perfect labels the squash fragments **worse**.
- **Removing `eps` did not remove the narrow window.** Squash-together-and-grass-
  out survives a 1.7× band, against `eps`'s 1.3×. What changed is provenance, not
  width: the constant is now measured off each image instead of published per
  dataset and capture date. Worth saying before B1 rather than after.
- **The depth is not the weak link.** A1's promise holds completely — every
  petiole, tendril and the fruit resolve as continuous 3-D structure radiating
  from the crown (`chunks/A4/figs/fig_zooms.png`). Turning that into one
  component needs a skeleton rooted at the crown, not a pairwise contiguity test.

**Open question 2 answered.** Semantic classes + soil surface + connected
components is *not* enough, but not for the expected reason. Grouping earns its
place on **R2** grounds: per-pixel crop/weed decisions put **16.7 %** of the crop
under the tool, per-component decisions **1.65 %** — 10×. It does **not** earn it
on instance F1, where the 2-D control wins by under-segmenting. Adding A2's soil
surface to a per-pixel policy buys only 16.7 % → 14.0 %.

**Open question 4 answered — the ZeroPlantSeg kill decision.** Kill it from the
runtime path; keep the port and `recluster.py` (they are the reproduction path
for the recorded baseline, on which every number in `RESULTS.md` depends); keep
it as a *candidate* offline auto-labeller for B2, to be re-decided there against
SAM + A3. Runtime case: 20× slower, 2.2× worse on material IoU, 4.5× worse on
grass absorption, instance F1 0.0000, and its one advantage — a compact
five-component output — is an artifact of a distance threshold its own authors
re-tune per dataset *and capture date*.

**Dependencies changed**
- `pytest` 9.1.1 added to `chunks/A3/.venv`, which A4 otherwise reuses
  unchanged. No new venv, no new model weights, no SAM run (A3's cached
  partition is reused). Freeze in `chunks/A4/requirements.lock.txt`.
- `.gitignore`: see `chunks/A4/BOOKKEEPING.md` §4.

**Next**
- **A5** must read `unresolved_for(component)` before trusting a component's
  extent — the shipped `split` components are *surfaces*, and one may be a single
  leaf. A0's finding stands: no stem in this image is seen meeting the ground.
- **A6** should build the keep-out volume from the **`merge`** components; a crop
  split into 69 pieces gives a volume with 68 holes. Every unresolved edge on the
  crop component is volume the camera could not see, not empty space.
- **A7** should label the 192 `merge` components and expect the crop component to
  contain 83 % of the grass.
- **A0/A8** should decide whether `eval.py` gains the symmetric
  prediction-side grass exclusion. It is a breaking change to the contract and
  needs a version note plus a re-score of every recorded result.
- **B1** gets the sharpest transfer question A4 produced: does the
  within-fragment p90 tolerance transfer, or does the right quantile move per
  scene? Two percentile points flip the squash verdict on this image.
- A **skeleton rooted at the crown** is the untried route to holding the plant
  together, and it is a different algorithm from anything in the A4 brief.
```

---

## 4. `.gitignore` suggestions

Append:

```gitignore
# A4: fragment maps, cached graph, cached A3 material, and the unresolved-edge
# lists (3.3 MB each). Rebuild in ~3.5 min with chunks/A4/README.md.
chunks/A4/work/
chunks/A4/figs/*.png
chunks/A4/products/*.png
chunks/A4/products/unresolved_edges_*.json
```

`chunks/**/*.npy` already covers `chunks/A4/products/*.npy` (33 MB of component
maps). **Keep** `chunks/A4/results/*.json` (196 KB — the sweeps, the diagnostics
and the score dicts are the evidence for every table in FINDINGS), the code, and
`requirements.lock.txt`.

One judgement call worth flagging: `products/unresolved_edges_*.json` is a
*product*, not working data — A5/A6/A7 consume it through `a4_api`. It is
ignored here only for size, and it rebuilds deterministically in ~20 s. If the
repo would rather keep a product committed than rebuildable, drop that line and
keep the `default` one only.
