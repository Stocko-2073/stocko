# Chunk A4 — Grouping by connectivity, not distance

**Date:** 2026-09-01 · **Scale confidence:** `scale_free`, every distance in
**rdu** (1 rdu = median scene depth). **Datum: the STRAW mulch surface**, not
soil (A2).
**Inputs:** A1 `primary_raster` float depth (1344×1008, no resampling anywhere in
the graph), A2 `soil_surface_depth` / `height_sigma`, A3 `segment_material()`,
A3's independent SAM partition (`regions_a3f.npy`, oracle ceiling 0.9246).
**Scorer:** `chunks/A0/eval.py`, unmodified, greedy 1-1 at IoU ≥ 0.5.

---

## Headline

| | A4 (shipped, `unresolved → split`) | A4 (`unresolved → merge`) | ZeroPlantSeg baseline |
|---|---:|---:|---:|
| **Instance F1** | **0.0088** | 0.0198 | **0.0000** |
| precision / recall | 0.0045 / 0.300 | 0.0104 / 0.200 | 0.000 / 0.000 |
| TP / FP / FN | 3 / 671 / 7 | 2 / 190 / 8 | 0 / 5 / 10 |
| **squash best IoU** | **0.462** | **0.885** | 0.425 |
| **squash one component?** | **no** (69 parts ≥ 200 px) | **yes** (largest covers 95.6 %) | no (3 parts) |
| **clover separate?** | **yes** (0.0 % of it inside the crop component) | **yes** (0.0 %) | yes |
| **grass absorbed into the crop** | **11.8 %** | 83.3 % | **53.0 %** |
| predicted components | 674 | 192 | 5 |

**The three verdicts the roadmap asks for, plainly.**

* **Does the squash come out as one component?** *Not in the shipped
  configuration.* Its largest component covers 46.9 % of it, IoU 0.462 — above
  the baseline's 0.425 but still below the 0.5 match threshold, so it still
  scores as a miss. Under the `merge` policy it **does**: IoU 0.885, one
  component covering 95.6 %.
* **Does the clover stay separate?** **Yes, under every configuration tested.**
  Zero percent of GT instance 3 lands in the crop component, against the
  baseline's zero percent at `eps=100` and total absorption at `eps=130`. Unlike
  the baseline this does not depend on a threshold: no tolerance, however large,
  can bridge the straw between the clover and the squash, because A4 has no
  distance in it at all (`test_synthetic_disconnected_patches_stay_apart_at_any_tolerance`
  asserts this at tolerances up to 1e6 rdu).
* **How much grass is absorbed?** **11.8 %**, against the baseline's 53.0 % —
  a 4.5× reduction, and the clearest win in the chunk. Under `merge` it is
  83.3 %, worse than the baseline.

**Neither policy meets all three targets at once.** That is the chunk's central
result and it is not hidden anywhere below.

---

## What was built

`fragments → boundary-wise depth-continuity test → connected components`, on the
A1 float depth at its native 1344×1008, with A2's datum subtracted first.

1. **Nodes.** A fragment is an 8-connected piece that is uniform in *both* the
   SAM partition and the A3 material class. Two independent hypotheses are being
   crossed and neither is trusted: SAM says where the boundaries are, A3 says
   what each piece is made of, and **the depth then adjudicates every boundary
   between them, including every grass/squash boundary A3 drew**. A fragment's
   class is never used to decide whether an edge exists — only to decide where a
   candidate boundary is placed. 1 776 fragments, median 93 px.
2. **Relief.** `relief = A2 soil_surface_depth − A1 depth`, both rdu, as A2
   instructed. `test_tilt_invariance` asserts that adding an arbitrary plane to
   the scene and the datum together changes no edge decision — a sloping bed
   cannot split a plant.
3. **Edges.** For each 8-adjacent pixel pair across a fragment boundary, a
   directional second difference of the relief, computed from inside each
   fragment and extrapolated one pixel across, taking the smaller of the two
   sides (a leaf and its petiole meet at a curvature the leaf's own surface
   cannot follow; the petiole's can).
4. **The verdict, per boundary, by quartiles** — never by a single pixel, so a
   handful of leaking pixels cannot merge two plants and a handful of noisy ones
   cannot split one:

   | | |
   |---|---|
   | `p75(residual) ≤ tol` | **connected** — 1 375 boundaries |
   | `p25(residual) > tol` | **separated** — 1 392 boundaries |
   | otherwise | **unresolved** — 1 237 boundaries, recorded, not decided |

5. **Components** = union-find over the accepted edges.

### There is no spacing constant, and a test enforces it

`test_a4.py::test_no_spacing_constant_in_the_code_path` parses every A4 module,
strips comments and docstrings, and fails on any occurrence of `eps`, radius,
`max_gap`, `search_radius`, `spacing`, `cm`, … in executable code.
`test_every_module_level_constant_is_registered` fails on any module-level
numeric constant not in an explicit allow-list carrying its R1 category. The
structural guarantee behind both: **fragments that do not touch are never
linked, at any tolerance.** Raising the threshold can only reach across
*material*, never across empty space. That is the property `eps` did not have.

---

## What was measured

### 1. The ceilings, before any method was scored

| bound | instance F1 | reading |
|---|---:|---|
| perfect grouping on **A3's** plant mask | **1.0000** | A3's plant/not-plant mask is **not** the binding constraint. It covers 80–100 % of every GT instance (IoU 0.886 against the GT plant mask) and a perfect grouping on it scores a perfect 1.0. Everything below is the graph's own doing. |
| perfect grouping on the **GT** plant mask | 1.0000 | sanity |
| **oracle edges** — every adjacent fragment pair that really is one GT plant linked, and no other | **0.0315** | recall **1.0**, precision **0.016**, squash IoU 0.876, grass absorbed 5.0 %. This is the best *any* method whose nodes are these fragments and whose edges are these adjacencies could reach. |

**The oracle bound is the most important number in the chunk.** Even with the
true answer for every edge, F1 caps at 0.031, because grass shatters into ~400
components and `eval.py` counts each one that touches a single non-grass
labelled pixel as a false instance. A0 excludes GT grass instances from the
ground-truth side; it has no symmetric exclusion on the prediction side, so
*correctly refusing to absorb the grass is punished*. Reported symmetrically as
a clearly-labelled diagnostic (predicted components that are themselves majority
GT-grass excluded, exactly as GT grass instances are): **F1 0.0112** for the
shipped run, 0.0223 for `merge`. The headline table above does **not** use this.

### 2. A1's registered tolerance shatters the scene — the roadmap's literal reading fails

The brief says the tolerance comes from A1's `local_planarity_p10` at win3–win9.
Measured against material *known* to be continuous, that constant is far too
tight:

| | rdu |
|---|---:|
| A1 `local_planarity_p10`, win 3 / 5 / 9 | 2.95e-5 / 6.67e-5 / **1.29e-4** |
| A4's **within-fragment** continuity residual, p10 / p25 / **p50** / p75 / p90 / p95 | 2.5e-5 / 7.1e-5 / **2.16e-4** / 8.7e-4 / **4.24e-3** / 1.25e-2 |

A1's win9 value sits at the **median** of the residuals over pixel pairs that
lie inside one fragment and are therefore continuous by construction. Used as an
acceptance threshold it rejects half of them. The result, from the sweep: at
1.29e-4 rdu the scene comes out in **1 751 components**, the squash in 161
pieces at IoU 0.193, and every value A1 registered (2.9e-5 … 5.7e-4) lands in
the same shattered regime. **`local_planarity_p10` is a *tenth* percentile — the
smoothness of the flattest tenth of the scene — and A1 never claimed it was the
smoothness of a typical continuous surface.** Reading it as one is the mistake
this chunk found.

**The shipped tolerance instead re-measures the same quantity where it is
needed:** the p90 of the continuity residual over within-fragment pixel pairs,
**4.238e-3 rdu** on this image. Category **(c) observation** — measured in this
scene, from this scene's own material — not (a). It contains no belief about how
gardens are arranged, and it is re-derived per image rather than hard-coded per
dataset-and-capture-date the way `eps` was.

### 3. The operating curve — five decades of tolerance

`figs/fig_operating.png`, `results/sweeps.json`. Shipped policy (`split`):

| tol (rdu) | components | TP | squash parts | F1 | squash IoU | grass |
|---:|---:|---:|---:|---:|---:|---:|
| 1e-5 … 5.7e-4 *(A1's registered band)* | 1776 → 1569 | 2 | 163 → 139 | 0.0025 | 0.193–0.219 | 0.2 % |
| 1e-3 | 1380 | 2 | 120 | 0.0032 | 0.231 | 0.3 % |
| 3e-3 | 901 | **6** | 81 | 0.0146 | 0.245 | 3.3 % |
| **4.24e-3 (shipped)** | **742** | **3** | **69** | **0.0088** | **0.462** | **11.8 %** |
| 6e-3 | 607 | 4 | 49 | 0.0143 | **0.557** | 20.1 % |
| 1e-2 | 439 | 2 | 35 | 0.0098 | 0.819 | 52.6 % |
| 3e-2 | 204 | 2 | 9 | 0.0198 | 0.889 | 81.7 % |
| 1.0 | 111 | 1 | 1 | 0.0168 | 0.894 | 92.7 % |

**Two windows, and they are not the same width.**

* **squash IoU ≥ 0.5 alone:** tol ∈ [6e-3, 1.0] — a factor of **167**, against
  the `eps` window's 1.3×.
* **squash IoU ≥ 0.5 *and* grass below the baseline's 53 %:** tol ∈ [6e-3, 1e-2]
  — a factor of **1.7**.

So the honest statement is: **removing `eps` did not remove the narrow window.**
It moved it from a hand-set, dataset-and-date-specific length to a quantity the
method measures off the image itself, which is a real advance in *provenance*
and only a 1.3× → 1.7× advance in *stability*. B1 is where that claim gets
tested, because the self-measurement is the part that has to transfer.

### 4. The convention that sets the tolerance is the sensitive knob

| within-fragment quantile | 50 | 75 | 85 | 88 | **90** | 92 | 95 | 99 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| tol (rdu) | 2.2e-4 | 8.7e-4 | 2.2e-3 | 3.2e-3 | **4.24e-3** | 6.0e-3 | 1.25e-2 | 1.0e-1 |
| squash IoU | 0.196 | 0.230 | 0.234 | 0.245 | **0.462** | **0.557** | 0.869 | 0.894 |
| grass absorbed | 0.2 % | 0.3 % | 0.6 % | 3.3 % | **11.8 %** | 20.1 % | 64.9 % | 91.5 % |

**q = 90 was fixed in `run_a4.py` before any score was computed and has not been
moved.** q = 92 would have met both roadmap targets simultaneously (squash 0.557,
grass 20.1 %) and q = 90 does not. Two percentile points on a stated convention
flip the headline verdict. That is disclosed rather than harvested, and it is
the strongest argument in this chunk for B1 deciding the quantile from data
across images rather than by convention on one.

### 5. Which continuity statistic — it barely matters

Three candidates, each with its tolerance re-measured at its own p90:

| statistic | tol (rdu) | squash IoU | grass | AUC (same GT plant vs. different, per boundary) |
|---|---:|---:|---:|---:|
| raw depth step | 6.80e-3 | 0.468 | 11.4 % | 0.661 |
| **directional 2nd difference (shipped)** | **4.24e-3** | **0.462** | **11.8 %** | **0.664** |
| 5×5 in-fragment plane extrapolation | 4.18e-3 | 0.314 | 9.2 % | 0.660 |

All three separate "same ground-truth plant" from "different plant" at
**AUC ≈ 0.66**, and normalising the residual by each fragment's own roughness
(geometric / max / min of the two sides) did not improve it either (0.55–0.66).
This is not a statistics problem; see "what surprised us".

### 6. Node granularity and the one size constant

| nodes | fragments | squash IoU | grass |
|---|---:|---:|---:|
| SAM region only | 603 | 0.355 | 12.5 % |
| **SAM region × A3 class (shipped)** | **1776** | **0.462** | **11.8 %** |

| `MIN_FRAGMENT_PX` | 1 | 9 | **25** | 49 | 100 |
|---|---:|---:|---:|---:|---:|
| fragments | 3863 | 2770 | **1776** | 1306 | 948 |
| squash IoU | 0.322 | 0.303 | **0.462** | 0.418 | 0.429 |
| grass | 8.3 % | 6.2 % | **11.8 %** | 9.5 % | 9.3 % |

25 px is A0's and A3's registered minimum region, reused unchanged; it is also
exactly the 5×5 plane fit's support, which is the reason a smaller fragment has
no surface to test continuity against.

### 7. How much of the failure is A3's material map?

Re-run with A0's **ground-truth** material map in place of A3's (diagnostic
only, `--oracle-material`):

| | A3 material (shipped) | A0 material (oracle) |
|---|---:|---:|
| instance F1 | 0.0088 | **0.0402** |
| TP / recall | 3 / 0.300 | **7 / 0.700** |
| grass absorbed | 11.8 % | **2.4 %** |
| squash best IoU | 0.462 | **0.302** |
| squash parts | 69 | 95 |

**The two failures have different causes and they separate cleanly.** A clean
material map more than doubles weed recall (3 → 7 of 10) and cuts grass
absorption to 2.4 %, so *finding the weeds* is limited by A3. It does **not**
fix the squash, which fragments *more* — so *holding the crop together* is a
geometry-and-occlusion problem that no classifier will solve.

### 8. Unresolved edges

`products/unresolved_edges_default.json`, `figs/fig_unresolved.png`.

| kind | count | what it is |
|---|---:|---|
| `ambiguous_boundary` | **1 237** | the two fragments touch and the shared boundary is continuous along part of its length and a step along the rest (`p25 ≤ tol < p75`) |
| `occluded_by` | **10 059** | two plant fragments that do not touch, both touching a third fragment that stands **in front of both** along their shared boundaries |
| `leaves_frame` | **113** | fragments touching the image border — the ZeroPlantSeg failure ("corner leaves attach off-frame so their roots never reach the crown"), counted rather than inherited silently |
| **total** | **11 409** | of which **8 185** join two *distinct* components; the rest are already connected by another path and change nothing |

Under **R4** not one of them is resolved by extrapolation. The occlusion list is
built **with no distance whatsoever** — a pair qualifies by sharing an occluder,
never by being "close enough" — and the gap is *reported*, never thresholded.
By eye (`fig_unresolved.png`) the ambiguous boundaries trace exactly the petiole
edges and the leaf-over-leaf overlaps, and the frame fragments are exactly the
four corner leaves. This list is what C1 (multi-view re-observation) exists to
consume.

### 9. Open Question 2 — does instance segmentation earn its place?

> *"Semantic classes plus a soil surface plus connected components may be enough
> for targeting. A4 should be evaluated against that simpler alternative, not
> assumed superior."*

Four policies, same ground truth, same frame. The R2 question is **how much crop
would a tool be sent at**:

| policy | crop px targeted (**fraction of all crop**) | weed px targeted (fraction of all weed) | instance F1 | squash IoU | grass absorbed |
|---|---:|---:|---:|---:|---:|
| **S0** semantic class only, per pixel | **16.71 %** | 79.5 % | n/a (no instances) | n/a | n/a |
| **S1** + A2 soil surface (`confident_above(3σ)`) | **13.96 %** | 65.5 % | n/a | n/a | n/a |
| **S2** + 2-D connected components (no depth at all) | **0.009 %** | 3.8 % | **0.0597** | **0.892** (one part) | 84.5 % |
| **A4** 3-D connectivity, `split` | 9.48 % | 67.9 % | 0.0088 | 0.462 | 11.8 % |
| **A4** 3-D connectivity, `merge` | **1.65 %** | 20.4 % | 0.0198 | 0.885 | 83.3 % |

**The answer has three parts and only the first is the one the question
expected.**

1. **Grouping earns its place decisively, on R2 grounds.** Deciding crop-vs-weed
   per *pixel* from A3's class puts **16.7 %** of the crop under the tool.
   Deciding it per *component* by majority puts **1.65 %** there — a **10×**
   reduction in the catastrophic direction — because a component votes, and a
   speckled classifier loses the vote. Adding the soil surface to a per-pixel
   policy buys only 16.7 % → 14.0 %; it is a plant-vs-ground separator, not a
   plant-vs-plant one, exactly as A3 measured.
2. **But the *simple* grouping wins the metric.** Plain 2-D connected components
   — no depth consulted at all — score instance F1 **0.0597**, seven times A4's
   0.0088, put the squash out as one component at IoU 0.892, and are the safest
   policy in the table (0.009 % of crop at risk). On this image, on this metric,
   **the simpler alternative beats A4.**
3. **It wins by giving up.** It absorbs 84.5 % of the grass and targets **3.8 %**
   of the weed pixels: everything touching the crop becomes crop, so almost
   nothing is a target and almost nothing can go wrong. A4's `split` targets
   67.9 % of the weed. The right reading is that **F1 on this metric rewards
   under-segmentation**, and that the honest comparison for v1 is the pair
   (crop at risk, weed reached) — where A4 `split` reaches 18× more weed than the
   2-D baseline at 9.5 % crop-at-risk, and A4 `merge` reaches 5× more at 1.65 %.

**Recommendation for v1:** ship grouping, ship 3-D connectivity for the grass
rejection (11.8 % vs 84.5 %), and do **not** claim the instance F1 as the reason.

---

## What was decided

1. **The tolerance is (c), not (a).** A1's `local_planarity_p10` is registered
   and correct for what A1 measured; it is the wrong percentile for this
   question, and the chunk says so rather than quietly scaling it. A4 re-measures
   the same estimator on within-fragment pairs and takes p90.
2. **The quartile rule is three-way, and the third outcome is a first-class
   output.** `p75 ≤ tol` connected, `p25 > tol` separated, otherwise recorded and
   not decided. 31 % of adjacent boundaries land in the third bucket.
3. **Both unresolved-edge policies ship, because R2 and R4 disagree.** R4 says an
   undecided link is not a link (`split`). R2 says splitting the crop is the
   failure this chunk exists to fix and that A6 will build the keep-out volume
   out of a crop component that would then under-cover the plant (`merge`).
   `split` is the default because the brief's own wording is R4's; `merge` is one
   argument away and `a4_api.load_a4(tag="merge")` returns it.
4. **The graph is built on the depth grid, and the depth is never resampled.**
   The material map and the SAM partition are lifted up to 1344×1008 by nearest
   neighbour; the components come back down to 768×1024 by nearest neighbour for
   scoring. A1 measured what touching the depth costs; nothing here touches it.
5. **A3's partition, not A0's.** A0's labels were painted on A0's own SAM
   regions (ceiling exactly 1.0). A4 reuses A3's independent partition, and
   `results/diagnostics.json` records both ceilings.
6. **Grass components are not suppressed.** The prediction-side symmetric
   exclusion is reported as a diagnostic and never as the headline, because
   hiding false positives by class is exactly the move R3 forbids.

---

## What surprised us

1. **A1's registered depth-noise constant is off by more than an order of
   magnitude for this job, and in a direction nobody would guess.** The roadmap
   said "within the depth noise established in A1" and A1 handed over
   `local_planarity_p10`. It is a *tenth percentile*: it describes the flattest
   tenth of the scene. Material that is continuous by construction has a median
   continuity residual of 2.16e-4 rdu, and the p90 that actually separates a
   crease from a step is 4.24e-3 — **33× the win9 constant**. Every value A1
   registered lies inside the shattered regime. A2 had the same conversation
   with itself about window size; A4's version is about *percentile*, and it is
   the more dangerous of the two because the number looks like it transfers.
2. **The pieces of one squash plant mostly are not contiguous in the image.** Of
   1 524 adjacent fragment pairs that both belong to the squash, the median
   across-boundary depth step is 5.03e-3 rdu — a real 3-D discontinuity, 0.92
   datum-σ. Those are leaf-over-leaf overlaps. **A squash is not a connected
   surface; it is a set of surfaces that touch at edges and connect only through
   its petioles.** The roadmap guessed this ("petiole tracing is the likely
   mechanism"); what was not expected is that the petiole junctions are a *tiny
   minority* of the plant's internal adjacencies, so the whole plant hangs on a
   handful of links that a second difference reads as high curvature.
3. **Every continuity statistic scores AUC ≈ 0.66, and so it should.** "Depth
   continuity" and "same plant" are genuinely different questions in this scene:
   one plant's leaves overlap with a real step, and a grass blade lying on a
   squash leaf is in real contact. A statistic that predicted "same plant" from
   contiguity would have to be *wrong about the geometry*. The low AUC is not a
   measurement failure; it is the honest ceiling on the idea.
4. **A perfect edge oracle scores F1 0.031.** Knowing the true answer for every
   edge gives recall 1.0 and precision 0.016, because ~400 correctly-separated
   grass components each count as a false instance. **The metric penalises the
   behaviour A0 declared unresolvable.** A0 excludes grass on the ground-truth
   side and has no symmetric exclusion on the prediction side; this is a real gap
   in the scoring contract and A5–A8 will hit it too.
5. **The simple alternative beats the complicated one on the metric, and it does
   it by refusing to segment.** 2-D connected components with no depth: F1
   0.0597, squash in one piece, 0.009 % of crop at risk — and 3.8 % of the weed
   reached. Open Question 2 came within an inch of answering "no", and only the
   R2 targeting table rescues the case for grouping.
6. **A3's material map is not the constraint people expected, and is the
   constraint they did not.** A3's FINDINGS predicted A4 would be limited by
   `squash_petiole` IoU 0.36. The measurement says otherwise: A3's *plant mask*
   supports a perfect 1.0 (ceiling), so the mask is fine. What A3 costs is
   *weed recall* — a clean material map takes TP from 3 to 7 — and what it does
   not cost is the squash, which fragments **worse** with perfect labels. The
   petiole class was the wrong thing to worry about; the class map's **speckle**
   was the right thing (it is what makes 769 fragments out of one plant).
7. **Removing `eps` did not remove the narrow window.** The usable band for
   "squash together *and* grass out" is 1.7× wide, against `eps`'s 1.3×. What
   changed is not the width but the *provenance*: the number is now measured off
   each image rather than published per dataset and capture date. That is a
   smaller victory than the roadmap's framing implies, and it should be said out
   loud before B1 rather than after.
8. **The relief raster is beautiful and the graph still fails.** A1's promise
   holds completely — `figs/fig_zooms.png` shows every petiole, tendril and the
   fruit resolved as continuous 3-D structure radiating from the crown. The
   depth is not the weak link. Turning that structure into one component needs a
   *skeleton rooted at the crown*, not a pairwise contiguity test.

---

## Not done / deferred

* **One image**, as with every Phase A chunk.
* **No skeleton / tree model.** The finding in (2) and (8) points at tracing
  petioles as 1-D structures rooted at a crown, rather than at pairwise
  contiguity. That is a different algorithm and it was not in the brief.
* **Occlusion-mediated links are recorded, never resolved.** R4. Resolving them
  would mean asserting material behind an occluder from one view. C1's job.
* **The occlusion list is capped** at 200 pairs per occluder (16 occluders hit
  the cap); the cap is a reporting limit on list length, applied after the pairs
  are found, and it is not a threshold on any geometric quantity.
* **`height_sigma` is loaded and not used in the edge test.** A2's datum
  uncertainty should probably weight a boundary's evidence where the datum under
  it is interpolated; the shipped test does not, and the ablation was not run.
* **No sensitivity to A1b's focal length.** A1b has not landed. A1b's own
  done-criteria ask for "A4 instance count and F1" across five `f` values;
  `run_a4.py` takes its camera from the A1 manifest and will produce that table
  unchanged when A1b runs.
* **Compute** is ~20 s for the whole graph on Apple Silicon (plus A3's 5 s of
  DINOv2 features, cached), against ZeroPlantSeg's ~8 min. No SAM is run: A3's
  cached partition is reused.

---

## Constants introduced

See `BOOKKEEPING.md` for the exact `CONSTANTS.md` rows. In summary: one (c)
observation (the continuity tolerance and the quantile that defines it), and
four (a) instrument values reused unchanged from A0/A1/A3. **No (d) constants,
and no constant with a unit of length in the image plane.**

---

## Implications for the roadmap

* **A5** — take `a4_api.load_a4()`, and read `unresolved_for(component)` before
  trusting a component's extent. The shipped `split` components are *surfaces*,
  not plants: a "component" may be one leaf. A5's `lowest_visible_stem_point`
  should be computed per component *and* per `merge`-policy component, because
  the two disagree about what a plant is by a factor of 3.5 in component count.
  A0's finding stands: no stem in this image is seen meeting the ground.
* **A6** — build the keep-out volume from the **`merge`** components, not the
  `split` ones. A6's whole purpose is to over-cover the crop, and a crop split
  into 69 pieces produces a volume with 68 holes in it. Treat every
  `unresolved_for(crop_component)` edge as volume the camera could not see, not
  as empty space.
* **A7** — label the `merge` components (192 of them, not 674) and expect the
  crop component to contain 83 % of the grass. The VLM will be asked "is this a
  weed?" about a component that is mostly squash and partly grass; A3's finding
  that prose moves one confusion 5× while the aggregate stays flat applies
  directly.
* **A0 / A8 — the scoring contract has a symmetric gap.** GT grass instances are
  excluded from `n_gt`; predicted components lying on grass are not excluded
  from `n_pred`. A method that correctly refuses to absorb the grass is punished
  for it, and the oracle bound of F1 0.031 is the proof. A0 should decide
  whether to add the symmetric exclusion (it is a breaking change to the
  contract, so it needs a version note and a re-score of every recorded result).
* **A1b** — nothing in A4 is focal-length-sensitive by construction *except*
  through the relief raster, which is A2's product. A1b's expectation that "A4
  should be nearly invariant, since it is ratio-based" is testable directly by
  re-running `run_a4.py` against A2 fits at each `f`.
* **B1** — two questions, both sharper than they were. (i) Does the
  within-fragment p90 tolerance transfer, or does the right quantile move per
  scene? The q-sweep says 2 percentile points flip the verdict, so this is the
  single most important transfer question A4 produced. (ii) Does the
  crop-at-risk gap between per-pixel and per-component decisions (16.7 % vs
  1.65 %) hold on other beds?
* **Open Question 2 is answered**: grouping earns its place on R2 grounds
  (10× less crop at risk), not on instance F1, where the simplest possible
  grouping wins by under-segmenting.
* **Open Question 4 — the ZeroPlantSeg kill decision.** See below.

---

## The ZeroPlantSeg kill decision

**Kill it from the runtime path. Keep it as a candidate auto-labeller for B2,
and keep the port.**

The evidence is now complete on all three axes the roadmap cared about:

| | ZeroPlantSeg | replacement | ratio |
|---|---:|---:|---|
| material, mean IoU (A3) | 0.2534 | 0.5537 | **2.2×** |
| grass absorbed into the crop (A4) | 53.0 % | **11.8 %** | **4.5×** |
| squash best IoU (A4) | 0.425 | 0.462 (`split`) / 0.885 (`merge`) | 1.1× / 2.1× |
| instance F1 | 0.0000 | 0.0088 / 0.0198 | — |
| runtime | ~8 min | ~5 s (A3) + ~20 s (A4) | **~20×** |
| the grouping constant | `eps`, hand-set per dataset **and capture date** | measured off the image, no length in the code path | — |

Nothing in the runtime case survives: it is 20× slower, 2.2× worse on material,
4.5× worse on the failure that matters, and its one remaining advantage —
compact output, 5 components — is an artifact of a distance threshold that its
own authors re-tune per capture. **A4's honest F1 of 0.0088 is not a strong
number, but it is against a recorded 0.0000, and the 2-D-connected-components
control (0.0597) shows that beating it does not require ZeroPlantSeg either.**

What is *not* killed: (a) the working Apple-Silicon port and `recluster.py`,
which cost real effort and are the reproduction path for the recorded baseline —
every number in `RESULTS.md` depends on them; (b) its use as an **offline**
auto-labeller in B2, where 8 minutes an image is irrelevant and its leaf-mask
stage is still a reasonable proposal generator. That decision should itself be
re-taken in B2 against SAM-plus-A3, which is cheaper and already scores better.
