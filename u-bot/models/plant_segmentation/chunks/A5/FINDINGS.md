# Chunk A5 — Stem-soil contact points

**Date:** 2026-09-01 · **Scale confidence:** `scale_free`, every 3-D distance in
**rdu** (1 rdu = median scene depth), every image distance in px on the named
grid. **Datum: the STRAW mulch surface**, not soil (A2).
**Inputs:** A4 `load_a4()` under *both* policies, A2 `load_a2()` (native
1344x1008, never resampled), A1 `primary_raster`, A3 material via A4's cache.
**Scorer:** `chunks/A0/eval.py`, unmodified — and it reports the headline metric
as **empty**, which is the first thing this chunk has to say.

---

## Headline

| | A4 `split` (742 comps) | A4 `merge` (207 comps) | A0 GT masks (10, diagnostic) |
|---|---:|---:|---:|
| **observed** | **472** (63.6 %) | **164** (79.2 %) | 8 |
| **extrapolated** | **59** (8.0 %) | **11** (5.3 %) | 1 |
| **occluded** (no point at all) | **211** (28.4 %) | **32** (15.5 %) | 1 |
| components silently given a fabricated point | **0** | **0** | **0** |
| `lowest_visible_point` emitted | 741 / 742 | 207 / 207 | 10 / 10 |
| `lowest_visible_stem_point` emitted | 299 | 40 | 3 |
| R2-admissible for a removal | 378 | 137 | 7 |
| median confidence (of those with a point) | 0.71 | 0.81 | — |

**And the number that matters more than any of them: `observed` in this chunk
means "the material reaches the STRAW". Zero components in this image are
observed to reach the SOIL, because nothing in the frame shows a stem meeting
the ground.** A0 established that; A5 could not and did not overturn it.

---

## The two decisions the roadmap asked for

### 1. Open Question 1 — is the product target "enters soil" or "lowest visible stem"?

> *"Under straw mulch it is often unobservable. `lowest_visible_stem_point` may
> be both more honest and sufficient. Resolve in A5, revisit after C3."*

**Decision: the product target is the lowest visible point on the plant, and its
height above the straw datum. "Enters soil" is not a target this stack may
claim, on this image or any mulched bed, from one overhead view.**

The evidence is now complete and it comes from three independent directions:

1. **A0's labelling.** All ten stem-soil contacts are `under_straw` with
   `localisation: estimated`; **zero** are `visible`. The schema says in as many
   words that estimated points must not be used as a scoring target.
2. **A2's fit.** Bare soil is 0 px of the frame. The surface A2 fitted, and
   therefore the only surface A5 can measure a height against, is the *top of
   the mulch*. The straw depth is an unmeasured offset and is unmeasurable from
   one overhead photograph.
3. **A5's own measurement.** 45.2 % of all the material immediately surrounding
   the components' lowest visible material is `straw`, and **294 of 742 `split`
   components (39.6 %) — 140 of 207 `merge` components (67.6 %) — have straw as
   the majority material in that ring.** The plant disappears into mulch, not
   into soil.

So: A5 emits a datum contact and calls it a datum contact. The straw-depth
offset travels with every record, in `a5_api.A5Product.datum` and in
`product_target` inside every JSON. **The one thing A5 must never do is let a
downstream consumer read "observed contact" as "observed soil entry", and the
API is written so that reading it that way requires ignoring a field.**

The revisit is C3's, and it may well moot the question: a thermal or laser tool
wants the *growing point*, not the soil entry, and the growing point is above
the straw and therefore observable. A mechanical tine is the only option in C3's
list that needs the soil entry at all.

### 2. The `split` / `merge` disagreement

A4 shipped two policies because R2 and R4 point opposite ways, and told A5 to
compute contact points under both. They disagree far more than the 3.5x in
component count suggests:

| | `split` | `merge` | ratio |
|---|---:|---:|---:|
| components | 742 | 207 | 3.58x |
| components carrying an actionable point | **531** | **175** | 3.03x |
| observed | 472 | 164 | 2.88x |
| merge components holding more than one split point | — | 17 | — |

**The disagreement is not spread evenly; it is one component.** `merge`'s
component 1 is 938 112 px — 92 % of all plant material in the frame — and A5
statuses it **`occluded`**, because its lowest material sits 14.7 sigma *below*
A2's fitted datum (see below). Inside it sit **488 `split` components carrying
319 points, 274 of them `observed`.** So the single choice A4 could not settle
turns 319 candidate targets into zero.

**Recommendation for A8: take contact points from `split`.** A6 was told to
build keep-out volumes from `merge`, and that is still right — over-covering the
crop and under-committing to targets are the same instinct pointing at different
products. But `merge` gives A5 almost nothing to aim at, and a policy that
returns one `occluded` blob for 92 % of the scene cannot be the targeting input.

---

## What was built

`components -> lowest distinguishable material -> is it in the ground band? ->
if not, continue its own 3-D axis to the surface -> status, with a reason in
words`. All geometry on A1's native 1344x1008 depth grid; nothing resampled.

1. **Heights are read as a 3x3 median *inside the component*.** A component's
   boundary pixels straddle material and background and their depth is a
   mixture; `MIN_MEDIAN_SUPPORT = 3` is what a one-pixel-wide stem supplies, so
   thin structure is not eroded. Without the filter (`median_window = 1`) the
   count of `observed` moves 472 -> 498: the filter is doing real work and it is
   working in the conservative direction.
2. **The base is a band, not a pixel.** Heights differing by less than one
   combined datum sigma are not distinguishable, so the "lowest material" is
   every pixel within 1 sigma of the minimum, 8-connected to it. The reported
   point is the band pixel nearest the band's 3-D centroid — **a real material
   pixel, never the centroid itself**, which would be a point on nothing.
3. **`observed` is A2's own ground band, both conditions.** `|h| <= 3*sigma_c`
   where `sigma_c = sqrt(sigma_datum^2 + height_sigma^2)` — A2's registered
   datum roughness *and* A2's measured gap-fill uncertainty at that pixel's own
   support distance. A point over an interpolated datum is worth less, and it is
   priced twice: in `confidence` through `kappa_datum`, and absolutely in
   `arm_admissible`, which requires `coverage_class == observed`.
4. **The extrapolation window is set by the gap itself.** To cross a height gap
   `h`, the direction is measured from the material in `[h, 2h]` — "to
   extrapolate a distance d, use the last d of observed material". No length
   constant anywhere.
5. **The axis carries its own cone.** `theta = arctan(sigma2/sigma1)` of the
   basal scatter, with the PCA sampling error added in quadrature. A stem's cone
   is a few degrees; a leaf blob's is ~45 deg, so a blob refuses itself with no
   linearity threshold to pick. `test_a_blob_has_no_axis_and_is_refused` is the
   assertion.
6. **The march is to the surface, along the surface's own local normal.** The
   same field A2 published: A5's reconstruction agrees with
   `height_above_soil.npy` to 5.3e-5 rdu max, RMS 4.0e-6 — 0.01 sigma.
7. **Confidence is a product of three measured factors**, and it is an
   **ordering, not a probability** — the same caveat A3 attached to its own:

   ```
   confidence = kappa_datum * lambda_axis * rho_reach * rho_band
     kappa_datum = sigma_c,min / sigma_c(landing)   how well-observed the datum is
     lambda_axis = 1 - d*tan(theta) / d_max         how much the direction may wander
     rho_reach   = 1 - d / d_max                    how far we had to guess
     rho_band    = 1 - |h| / (3*sigma_c)            how firmly an observed point sits
   ```

   Nothing here is calibrated, because nothing in this image could calibrate it.

### Where the constants come from, and the one that is a placeholder

The chunk has **one (b) constant**: `MAX_EXTRAPOLATION_SIGMA = 20`, expressed in
datum roughnesses because Phase A is scale-free and sigma_datum is the only
length the scene supplies. It caps both the extrapolation length and the lateral
wander it may accumulate, so a single tool-precision number governs the whole
error budget rather than two unrelated ones.

**It is swept, and the sweep has a property worth stating on its own: raising it
cannot manufacture an `observed`.**

| `MAX_EXTRAPOLATION` (sigma) | 0 | 2 | 5 | 10 | **20** | 40 | 80 | 160 | inf |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| observed | 472 | 472 | 472 | 472 | **472** | 472 | 472 | 472 | 472 |
| extrapolated | 0 | 0 | 3 | 20 | **59** | 111 | 185 | 211 | 211 |
| occluded | 270 | 270 | 267 | 250 | **211** | 159 | 85 | 59 | 59 |

Since R2 admits a removal only on `observed`, **the placeholder cannot open the
gate**; it can only move a component between "guess with a number attached" and
"no answer". That is the structural property that makes shipping a placeholder
defensible, and `test_raising_the_tool_budget_never_creates_an_observed_point`
enforces it.

Better still, the distance is measured to a 1 rdu reporting ceiling *regardless*
of the budget, so `results/sweeps.json -> extrapolation_distance_cdf_split` is
exact: **C3 reads its own budget off that curve and gets the resulting counts
directly, instead of inheriting A5's number.** 211 components have an axis that
reaches the datum at all; the distances run 2.7 sigma (min) / 17.3 (p25) /
36.2 (median) / 86.2 (p90) / 143.9 (max).

---

## What was measured

### 1. Counts by status, and why the occluded ones were refused

`results/diagnostics.json`, `figs/fig_contacts_split.png`.

| reason a component got **no** point | `split` | `merge` |
|---|---:|---:|
| the axis reaches the datum, but beyond the tool budget | **152** | 20 |
| the basal material is under 9 px — a direction would be chosen, not measured | 34 | 4 |
| **the material sits more than 3 sigma BELOW the fitted datum** | **12** | **6** |
| the axis runs along the datum and never reaches it | 9 | 2 |
| the axis never reaches the datum inside the 1 rdu reporting ceiling | 3 | 0 |
| the axis lands where A2's datum is past its trust distance | 1 | 0 |
| **total occluded** | **211** | **32** |

### 2. The straw-occlusion rate, asked three ways

The roadmap asks for "the straw-occlusion rate called out". There are three
honest answers and they are different numbers, so all three are given:

| question | answer |
|---|---|
| what fraction of *stem-soil* contacts are hidden by straw? | **10 / 10 = 100 %**, from A0's labels. Not an A5 measurement — A5 cannot see the soil at all |
| what is the majority material immediately around a component's lowest visible material? | **straw for 294 / 742 `split` (39.6 %)** and **140 / 207 `merge` (67.6 %)** |
| of all that surrounding material, by pixel | **45.2 % straw**, 32.2 % grass, 10.6 % petiole, 6.2 % broadleaf, 4.6 % squash leaf |

Of the 270 `split` components that are *not* `observed`, A5 names the thing in
the way as foliage for 98, straw for 33, petiole for 40, and finds only the
component's own material for 97. **The last figure is the interesting one: for
more than a third of the non-observed components, nothing at all stands between
the lowest visible material and the datum — the material simply stops.** That is
what a leaf held above the ground on a petiole looks like, and no amount of
re-observation from another angle fixes it, because there is nothing to see.
C1's multi-view helps the 98 occluded-by-foliage cases; it does not help these.

### 3. `observed` is substantially circular, and that is the chunk's most uncomfortable finding

A2 selected its ground inliers as everything within 3 sigma of the fitted
surface — **plant material included**. So a low-lying grass blade base is both
"plant" to A3 and "ground" to A2, and it helped fit the very datum A5 then
measures it against.

| | `split` | `merge` | GT masks |
|---|---:|---:|---:|
| `observed` contacts whose base pixel is itself an A2 ground inlier | **410 / 472 (86.9 %)** | 150 / 164 (91.5 %) | 7 / 8 |
| median share of the local datum support (147 px, A2's fit scale) from **non-plant** material | 0.52 | 0.75 | 0.67 |

So for the large majority of `observed` contacts, "this plant reaches the
ground" is partly a restatement of A2's own inlier decision rather than an
independent observation. The mitigating measurement is the second row: the datum
under a typical base pixel is still about half pinned by material that is not
plant at all, so the statement is not *entirely* circular — but it is not clean,
and **calling this "observed" is generous.**

The fix is not an A5 fix. It is for A2 to publish a datum fitted with A3's plant
mask excluded, or for C1 to re-observe. Under R2, A8 should treat
`arm_admissible` as necessary and not sufficient, and the honest reading of the
472 is "472 components whose lowest material is indistinguishable from the
mulch", which is a weaker and more accurate sentence.

### 4. Consistency against A0's contact points — a labelled diagnostic, NOT an accuracy

A0's ten points are all `under_straw` with `localisation: estimated`, and A0's
schema says they must not be used as a scoring target. `eval.py` agrees: fed
A5's points it reports `visible n=0` and prints its warning rather than a number.
**The roadmap's A5 done-criterion is therefore empty for `plants.jpeg`, and this
chunk does not pretend otherwise.** What follows compares one estimate of an
unobservable thing to another.

Median distances in px on A0's 768x1024 grid, best-overlap assignment
(deliberately generous — the strict IoU >= 0.5 matching leaves 3 instances):

| | contact point | lowest visible point | centroid baseline | bottom-most-pixel baseline |
|---|---:|---:|---:|---:|
| **A0 GT masks** (A4 removed from the loop) | **26.4** (n=9) | 29.5 | 21.3 | **13.1** |
| `split` | 61.4 (n=9) | 54.4 | 60.1 | 51.3 |
| `merge` | 96.5 (n=6) | 126.4 | 95.1 | 191.4 |

**Two trivial image-space baselines beat A5 on the median, and the reason is
instructive rather than damning.** A0's points were placed by a human reading a
2-D photograph — "where the stem was last seen heading toward the datum" — so
they correlate with the bottom edge of the mask, which is exactly what the
baseline computes. The diagnostic is measuring agreement with a 2-D human
heuristic, not correctness in 3-D.

Where the baseline collapses is the case R2 cares about most:

| GT instance 1 (the squash) | error |
|---|---:|
| bottom-most pixel of the mask | **477.9 px** |
| A5 `lowest_visible_point` on the GT mask | 581.8 px |
| A5 `lowest_visible_point`, `split`'s largest squash component | **142.3 px** |
| A5 contact point, `split` | **142.3 px** (`observed`) |

Both A5 and the baseline are badly wrong about the crop, for the same underlying
reason (see below), and neither is usable. On the nine weeds A5's contact point
lands at a median 26.4 px against A0's estimate on the GT masks — about 3.4 % of
the frame width, and given that the target is itself a human's guess, about as
much agreement as the data supports.

### 5. The by-eye checks

`figs/fig_crown_zoom.png` — A0 noted that "the petioles converge on a crown node
near (352, 516)". Rendered and read: the white star lands exactly on the junction
where the thick petioles radiate, and A0's GT contact (330, 552) sits on the stem
bundle just below-left of it, where it descends into straw. **Two `split`
components put a `squash_petiole` point within ~21 px of that node** — component
726 (`extrapolated`) and component 582 (`occluded`) — so the crown region *is*
found, but only as small fragments, never as "the squash's contact point".

`figs/fig_contacts_split.png` — the green (`observed`) points sit over the straw
and along the low weeds; the tall upper leaves carry almost no points at all,
which is the correct behaviour and is visible at a glance.

`figs/fig_below_datum.png` — 0.5 % of plant pixels lie more than 3 sigma below
the datum, as a fine speckle concentrated on the big frame-edge leaves.

`figs/fig_gt_instances.png` — the nine weed points land beside their GT crosses;
the single long white line is the squash, and it is the failure this chunk found.

---

## What surprised us

1. **A minimum over a large component finds the tail of the height error, not
   the plant's base.** Only **0.5 %** of plant pixels lie more than 3 sigma
   *below* A2's fitted datum — a small, speckled residue of the depth-vs-surface
   disagreement. But `lowest_visible_point` is a *minimum*, and a minimum over
   750 000 pixels is drawn straight to that 0.5 %. So the GT squash mask's
   lowest point is a leaf edge at (754, 154) in the top-right corner sitting
   10.2 sigma below the datum, 582 px from the crown, and `merge`'s 938 k-px
   component fails the same way at 14.7 sigma. **The bigger and more sprawling
   the plant, the worse the estimator behaves — the exact opposite of the usual
   assumption that more pixels means a better estimate.** The 3x3 in-component
   median filter helps but cannot fix it, because the residue is spatially
   coherent, not per-pixel noise.
2. **"Lowest point of the component" is simply the wrong concept for a vine.**
   A squash's lowest material is a leaf tip lying on the mulch two-thirds of a
   frame away from its crown. The concept only means anything for a component
   that is both one plant *and* mostly base. Every weed in this image satisfies
   that; the crop does not. **The right object for a sprawling plant is a
   skeleton rooted at the crown** — which is exactly what A4 concluded from a
   completely different direction ("turning that structure into one component
   needs a skeleton rooted at the crown, not a pairwise contiguity test"). Two
   chunks arriving at the same missing algorithm from opposite ends is the
   strongest signal in this session about what to build next.
3. **`observed` was supposed to be the hard-won status and it is the easy one.**
   Going in, the expectation was that almost everything would be `extrapolated`
   or `occluded` under mulch. 63.6 % came out `observed` — because the *datum is
   the straw*, and plants do reach the straw. The status is honest for the
   question A5 can actually ask and completely misleading for the question the
   roadmap's prose asks. Renaming it was considered and rejected: `observed` is
   the roadmap's contract term, and the fix is the `product_target` field that
   travels with every record, not a private vocabulary.
4. **86.9 % of those `observed` contacts stand on a pixel A2 fitted its ground
   to.** The two products were built independently and their disagreement — A3
   says plant, A2 says ground — is where nearly every `observed` verdict lives.
   Nobody predicted the overlap would be that near-total.
5. **The (b) placeholder turned out to be structurally safe.**
   `MAX_EXTRAPOLATION` moves 152 components between `extrapolated` and
   `occluded` and moves **zero** into or out of `observed`. Since R2 gates on
   `observed`, the one constant A5 cannot justify is also the one constant that
   cannot cause a crop to be cut. That property is worth preserving deliberately
   in A8, and it is now a test.
6. **Two trivial baselines beat the 3-D method against ground truth, and the
   ground truth is the thing at fault.** A0's estimated points are 2-D human
   readings; a 2-D estimator reproduces them better than a 3-D one. This is a
   sharper version of A4's finding that "F1 on this metric rewards
   under-segmentation": on this image, *both* of the metrics the roadmap
   specified reward the simpler method for structural reasons that have nothing
   to do with which method is right.
7. **97 of 270 non-observed `split` components have nothing between them and the
   ground.** The material just stops in mid-air. That is not occlusion and C1
   cannot fix it; it is a leaf on a petiole, and the only correct answer is the
   one A5 gives — no contact point for that surface, look at the plant it
   belongs to instead. It is also a direct argument that `split` components are
   *surfaces*, exactly as A4 warned, and that A5's per-component output only
   becomes per-*plant* output after A4's grouping problem is solved.

---

## Sensitivity

`results/sweeps.json`, `figs/fig_sweeps.png`. Counts for `split`.

| knob | values | observed | extrapolated | occluded |
|---|---|---|---|---|
| `MAX_EXTRAPOLATION_SIGMA` **(b)** | 0 / 5 / 10 / **20** / 40 / 80 / inf | 472 (flat) | 0 / 3 / 20 / **59** / 111 / 185 / 211 | 270 / 267 / 250 / **211** / 159 / 85 / 59 |
| `GROUND_BAND_K` (c, A2's) | 2 / **3** / 4 / 5 | 402 / **472** / 501 / 513 | 91 / **59** / 43 / 36 | 249 / **211** / 198 / 193 |
| `BASAL_BAND_K` (c) | 0.5 / **1** / 2 / 3 | 475 / **472** / 462 / 451 | 58 / **59** / 66 / 76 | 209 / **211** / 214 / 215 |
| `MIN_AXIS_POINTS` (a) | 5 / **9** / 25 / 49 | 472 (flat) | 71 / **59** / 41 / 24 | 199 / **211** / 229 / 246 |
| `MEDIAN_WINDOW` (a) | 1 / **3** / 5 | 498 / **472** / 439 | 45 / **59** / 82 | 199 / **211** / 221 |

Three readings. **(i)** Only `GROUND_BAND_K` and `MEDIAN_WINDOW` move the
`observed` count, and both are inherited or instrument-scale, not free
parameters. **(ii)** The `observed` count varies by 13 % across the whole
`GROUND_BAND_K` sweep 2-5 sigma — the same sweep A2 ran, with a comparable
insensitivity. **(iii)** Nothing in the table changes the chunk's conclusions;
the counts move, the verdicts do not.

---

## Constants introduced

See `BOOKKEEPING.md` for the exact `CONSTANTS.md` rows. In summary: **one (b)
tool-geometry placeholder** (`MAX_EXTRAPOLATION_SIGMA`, swept, awaiting C3, and
structurally unable to create an `observed`), three **(a) instrument** values
(3x3 median window, its 3-pixel minimum support, the 9-point minimum for a 3-D
line), one **(c) convention** re-used unchanged from A2 (the 3 sigma ground
band), and one new **(c) convention** (the 1 sigma basal band, itself a
restatement of A2's roughness). **No (d) constants. No constant with a unit of
length in the image plane, and no constant encoding anything about how gardens
are arranged** — `test_there_is_no_spacing_or_agronomic_constant_in_the_code_path`
parses the modules and enforces it.

---

## Not done / deferred

* **One image**, as with every Phase A chunk. Whether 63.6 % `observed` is a
  property of this mulched bed or of gardens is B1's question, and the honest
  guess is: this bed, and specifically this depth of mulch.
* **No skeleton or crown model**, so no per-plant contact point for a sprawling
  plant. Surprise 2 says this is the thing to build; it was not in the brief and
  it is the same algorithm A4 asked for.
* **The circularity in `observed` is measured, not removed.** Removing it needs
  A2 to refit its datum with A3's plant mask held out. That is a small change to
  A2's candidate selection plus a re-run, and it should happen before B1.
* **`height_sigma` prices the datum but nothing prices the *depth*.** A1's
  cross-model disagreement is 0.079-0.143 rdu — 14-26 sigma, an order of
  magnitude larger than every distance A5 reports. A5's confidences are
  conditioned on DA3's depth being right, and that is not priced anywhere in the
  stack.
* **No A1b sensitivity.** A1b has not landed. A1b's done-criteria ask for "A5
  contact-point error" across five focal lengths; `run_a5.py` takes its camera
  from the A1 manifest through A2 and will produce that table unchanged.
* **The extrapolation is a straight line.** A real stem bends. The measured axis
  half-angle is reported per component so the assumption is visible, but no
  curved model was tried.
* **`occluded` is not split by whether re-observation would help.** The 98
  foliage-occluded components are C1's; the 97 nothing-in-the-way ones are not,
  and A8 could usefully carry that distinction. It is in the JSON (`occluder`,
  `occluder_profile`) but not in the status.
* **Compute** ~4 s for both policies plus the oracle, on Apple Silicon.

---

## Implications for the roadmap

* **A8 — take `a5_api.load_a5(policy="split")`, and gate on `admissible()`, not
  on `confidence`.** `admissible()` already enforces the geometric half of R2 in
  code: status `observed`, datum coverage `observed`, and no `leaves_frame`
  unresolved edge. 378 of 742 `split` components pass it. A8 must add the VLM
  label and A6's keep-out test; the test A8's brief asks for ("a high-confidence
  `remove` with `extrapolated` status is rejected") is already true by
  construction here — `test_no_extrapolated_point_is_arm_admissible` asserts it
  on the shipped products.
* **A8 — do not print an absolute distance anywhere.** Everything is rdu and
  A1b has not landed. The `product_target` string in every record exists to be
  surfaced, not stripped.
* **A8 — the `visible`-contact metric is empty and the report must say so.**
  `eval.py` already prints the warning. Any A8 scorecard showing a
  contact-point error for this image without the `estimated` / `under_straw`
  caveat is wrong.
* **A6 — `merge` is still right for keep-out volumes**, but note that A5
  statuses the 938 k-px `merge` crop component `occluded` because its lowest
  material is 14.7 sigma below the datum. A6 building a volume from that same
  component should expect the same disagreement at its lower boundary and should
  not clip the volume to the datum.
* **A2 — please publish a plant-excluded datum.** 86.9 % of A5's `observed`
  contacts stand on pixels A2 fitted its surface to. It is A2's cheapest
  available improvement and it is the difference between "observed" meaning
  something and meaning "A3 and A2 disagreed here".
* **A4 / A5 together — build the crown-rooted skeleton.** A4 could not hold the
  squash together with pairwise contiguity; A5 cannot find its base with a
  minimum over the component. Both failures are the same missing object.
* **A0 — the scoring contract's second gap.** A4 found the asymmetric grass
  exclusion. A5 finds that the contact-point metric has no *target* when every
  GT point is `estimated`: `eval.py` handles it gracefully, so A5's
  done-criterion is unmeetable rather than failed. B1's image set needs at least
  a few images with a visible stem base — an unmulched bed would do — or this
  metric never has data.
* **B1 — three transfer questions.** (i) Does the 63.6 % `observed` rate survive
  a different mulch depth, or is it this bed? (ii) Does the circularity in
  `observed` grow or shrink when the ground is more visible? (iii) Does the
  extrapolation-distance CDF keep its shape, since that curve is what C3 will
  read its tool budget off.
* **C3 — read the budget off `results/sweeps.json`, do not inherit 20 sigma.**
  The CDF is exact and the counts follow from it directly. And note that the
  *choice of tool changes the question*, not just the number: a thermal or laser
  tool wants the growing point, which is above the straw and observable, and
  would make Open Question 1 moot rather than answered.
