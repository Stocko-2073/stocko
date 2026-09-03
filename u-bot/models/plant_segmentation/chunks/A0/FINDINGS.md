# Chunk A0 — Ground truth for one image

**Sessions:** 2026-09-01 · **Status:** done

## What was built

Ground truth for `plants.jpeg` on a **768 × 1024** grid (a uniform 3.90625×
downsample of the native 3000 × 4000; identical scale in x and y), plus the
scoring function every later chunk reports against.

Committed contract — `groundtruth/`:

| File | Contents |
|---|---|
| `SCHEMA.md` | **the contract.** Grid, class table, instance rules, contact-point fields, scoring rules |
| `plants_material.png` | 8-bit palette PNG, per-pixel material class |
| `plants_instances.png` | 8-bit PNG, per-pixel plant instance id (255 = unresolved grass) |
| `plants_contacts.json` | one stem-soil contact point per instance, with status |
| `plants_regions.png` | 16-bit PNG of the 688-region partition the labels were painted on |
| `plants_gt.json` | manifest: grid, palette, pixel counts, provenance |

Tooling — `chunks/A0/`, all run from `ZeroPlantSeg/` with the patched venv:

| Script | Role |
|---|---|
| `sam_propose.py` | SAM ViT-H automatic masks at 768×1024 → 512 proposals (~9 min on MPS) |
| `build_partition.py` | overlapping proposals → a 688-region non-overlapping cover |
| `propose_classes.py` | a crude first guess per region, so the review overlay starts from something |
| `render_review.py`, `zoom.py`, `grid_view.py` | the review renders: plain image \| class overlay + region ids, at 4–10× |
| `corrections.json` | **the labelling record** — every hand call, by region id, with the reasoning per pass |
| `instances.json` | instance grouping and contact points |
| `apply_assign.py`, `build_groundtruth.py` | assemble and emit `groundtruth/` |
| `eval.py` | `load_gt` / `load_prediction` / `score` / `print_report` + CLI |
| `test_eval.py` | 14 assertions on the scoring behaviour; all pass |
| `score_baseline.py` | scores the ZeroPlantSeg output; writes `baseline/zps_baseline_scores.json` |
| `render_gt_figures.py` | `figs/gt_material.png`, `figs/gt_instances.png` |

```bash
cd ZeroPlantSeg && export PYTORCH_ENABLE_MPS_FALLBACK=1 PYTHONPATH=.
.venv/bin/python ../chunks/A0/eval.py --zps
.venv/bin/python ../chunks/A0/test_eval.py
```

### How the labels were actually made

SAM was used **only to draw boundaries**. Every class was assigned by looking at
the region: the whole frame was swept as sixteen 4× tiles (plain image beside the
current class overlay with region ids drawn), then ~15 further windows at 6–10×
on anything I could not call, and seven native-resolution crops
(`work/n_*.jpg`) where even 10× on the label grid was not enough — that is where
grass blade vs. squash petiole and the mid-frame ovate weed were settled. Each
pass of calls was applied, re-rendered and re-inspected; `corrections.json` is
the record and carries the reasoning per pass. No classifier assigned a class.

The boundary-drawing step is honest about its limits: the label boundary is
SAM's, so it is crisp but not mine, and at this grid a grass blade is 3–6 px
wide.

## What was measured

Ground-truth composition (786 432 px):

| Class | px | % of frame |
|---|---:|---:|
| `squash_leaf` | 360 852 | 45.88 |
| `straw` | 216 116 | 27.48 |
| `grass` | 106 099 | 13.49 |
| `squash_petiole` | 55 560 | 7.06 |
| `broadleaf_weed` | 18 655 | 2.37 |
| `fruit` | 16 692 | 2.12 |
| **`unlabelled`** | **11 904** | **1.51** |
| `other` | 554 | 0.07 |
| `soil` | 0 | 0.00 |

All squash material together is **55.06 %** of the frame, against ZeroPlantSeg's
descriptive 52.2 % — close, and it should be, since both are measuring the same
canopy.

**Unlabelled fraction: 1.51 %**, three regions: a deep-shadow tangle behind the
crown where grass, straw and stem interleave below the resolution of this grid
(two regions), and a dark band under a leaf edge that is either the leaf's own
shaded underside or material behind it.

10 instances: the squash (1) and nine broadleaf weeds (2–10). Grass carries
instance id 255, unresolved.

### Recorded baseline — ZeroPlantSeg as published

`configs/squash.yaml`, `eps=100`, `min_samples=2`, output at 768×1024, so
**nothing is resampled** to score it. Full numbers in
`chunks/A0/baseline/zps_baseline_scores.json`; the RESULTS.md block is in
`BOOKKEEPING.md`.

| Metric | Value |
|---|---|
| Instance precision / recall / **F1** (IoU ≥ 0.5) | 0.000 / 0.000 / **0.000** |
| GT instances / predicted instances | 10 / 5 |
| Best IoU against the squash | **0.425** — below the 0.5 match threshold |
| Squash split across | **3** predicted instances (185 681 / 98 841 / 59 916 px) |
| **Grass absorbed into the crop instance** | **53.0 %** of GT grass (56 193 / 106 099 px) |
| Best IoU against any weed instance | 0.246 (the clover patch it did isolate) |
| Plant vs. background IoU (config-free) | **0.7574** |
| Mean IoU, charitable material mapping | 0.2534 |
| — `squash_leaf` | 0.6760 |
| — `broadleaf_weed` | 0.4903 |
| — `straw` | 0.6076 |
| — `grass`, `squash_petiole`, `fruit` | 0.0000 (no such output) |
| Contact-point error | n/a — the pipeline produces no contact points |

The material row needs its mapping stated, because ZeroPlantSeg emits instances,
not classes: the three squash instances were called `squash_leaf`, the clover
instance `broadleaf_weed`, background `straw`. That is the most favourable
reading of its output and it still scores 0.253 mean IoU, because grass, petiole
and fruit have no representation at all.

## What was decided

1. **The label grid is 768 × 1024, not native.** Boundaries at native resolution
   would be finer but the baseline runs at 768 × 1024, and inventing a resample
   between the two would make the recorded baseline unfalsifiable.
   `eval.to_gt_grid` nearest-resamples anything else and prints that it did.
2. **`squash_petiole` means all non-blade, non-fruit squash structure** —
   petioles, vines, peduncles, tendrils. Splitting them further is not
   supportable by eye, and petioles are what tie the plant together (A3, A4).
3. **`straw` means dry dead plant material anywhere**, including dried leaves and
   spent flower sheaths still attached to the plant. A separate
   "dead-but-attached" class would be a class I could not label consistently.
4. **Grass instances are declared unresolved, not guessed.** Grass is clonal and
   the blades interleave; id 255, excluded from instance matching the way
   `unlabelled` is excluded from IoU. The failure that matters is measured
   directly instead, as `grass_absorbed_into_crop`.
5. **The instance match rule is greedy one-to-one by descending IoU, accepted at
   IoU ≥ 0.5**, and the threshold is a keyword argument. Documented and
   swappable, as the roadmap requires.
6. **Contact points carry two extra fields** the roadmap's three-value status
   cannot express: `occluded_by` (`straw` | `foliage` | `frame`) and
   `localisation` (`observed` | `estimated`). Hidden-by-straw and
   hidden-by-leaves are different problems for a robot, and a point I estimated
   must not be silently scored as if I had seen it.
7. **`soil` is left empty rather than approximated.** Bare mineral soil is
   visible only in a few shadowed gaps under leaf edges, none of which the
   partition isolates. Labelling those gaps `soil` would have been a guess about
   what shadow contains.

## Constants introduced

| Name | Value | Cat | Justification | Sweep |
|---|---|---|---|---|
| instance match IoU | 0.5 | (c) | Stated convention; keyword argument in `eval.py`, swappable per chunk | n/a |
| GT label grid | 768 × 1024 | (a) | The resolution the recorded baseline runs at; a uniform 3.90625× downsample of the native image, identical in x and y | n/a |
| min reviewable region | 25 px | (a) | Below this a fragment cannot be judged by eye on this grid, so it is merged into a neighbour rather than labelled | n/a |
| fragmentation min part | 200 px | (a) | Reporting threshold only — a predicted piece smaller than this is speckle, not a fragment. Affects no score | n/a |

None encodes a belief about how gardens are arranged.

## What surprised us

- **Nothing in this image shows a stem meeting the ground.** All ten contact
  points are `under_straw` and `estimated`; **zero are `visible`**. The metric
  the roadmap specifies for A5 — contact-point error over `visible` points — is
  *empty* for `plants.jpeg`. This is not a labelling shortfall, it is what
  mulched beds look like, and it settles Open Question 1 harder than expected:
  "enters soil" is not merely hard to observe here, it is unobservable, in every
  instance, from this view. `lowest_visible_stem_point` is not a fallback, it is
  the only measurable target.
- **The squash's own base is not visible either.** The petioles converge on a
  crown node around (352, 516) and the stem bundle then goes behind straw and a
  leaf. Even the crop plant, the largest thing in the frame, cannot have its root
  position observed.
- **ZeroPlantSeg's grass failure is worse than "grass is absorbed": it is 53 %.**
  Just over half of all grass pixels end up inside the crop instance. The other
  half is not correctly rejected either — it simply falls outside every instance.
- **Its best IoU against the squash is 0.425**, so at the conventional 0.5
  threshold it scores an instance F1 of exactly zero on this image despite
  visibly finding the plant. The "5 instances, squash in 3" summary in
  `RESULTS.md` was, if anything, generous.
- **Bare soil is absent from a garden photograph.** I expected a small `soil`
  class; there is none. A2 already treats straw as the datum, which now looks
  less like a simplification and more like the only option.
- **`squash_petiole` is 7.06 % of the frame** — larger than every weed class put
  together. The A3 note that the prompt variant "drops the petioles" is therefore
  a bigger loss than it sounds.
- Colour alone separates dry from living material almost perfectly, but is
  useless for grass vs. squash: both sit in the same chromaticity band. The
  separation that actually worked by eye was texture and cross-section —
  petioles are ribbed, hairy and round-sectioned; blades are flat, keeled and
  taper to a point — and neither survives to 768 × 1024. That is a direct warning
  for A3: a shape prior computed on this grid is working with less evidence than
  I had at native resolution.

## Not done / deferred

- **Boundary precision is SAM's, not mine.** Where SAM drew a boundary badly, the
  ground truth inherits it. I did not hand-correct polygons; at 768 × 1024 the
  worst cases are a pixel or two.
- **Instance 3 (`weed_clover_patch_lower_left`) may be more than one plant.** I
  could not separate the individuals and recorded it as one, flagged in
  `instances.json`.
- **Instances 9 and 10 have guessed contact points** (`occluded_by: foliage`).
  They are marked `localisation: estimated` and must not be scored.
- **`soil` has zero pixels**, so its IoU is undefined and `eval.py` prints `n/a`
  rather than 0. Any later per-class mean IoU excludes it.
- **One image only**, as scoped. Generalisation is B1.

## Implications for the roadmap

- **A5 needs rewriting, or at least re-reading.** Its done-criterion
  "contact-point error in pixels for `visible` ground-truth points" cannot be met
  on `plants.jpeg`, because there are none. A5 should report against
  `lowest_visible_stem_point` and treat the `under_straw` points as diagnostic.
  `eval.py` already prints this warning rather than a misleading zero.
- **Open Question 1 is effectively resolved for mulched beds**: "enters soil" is
  unobservable. Confirm against B1's image set before hardening it.
- **A3 gets a hard target.** Beat mean IoU 0.2534 and, specifically, `grass` IoU
  0.0000 and `squash_petiole` IoU 0.0000 — the two classes the baseline cannot
  express at all. Any A3 winner must be scored on the full eight-class table, not
  on plant-vs-background, where the baseline already reaches 0.7574 and looks
  deceptively good.
- **A4 gets its number**: the squash must come out as **one** component with IoU
  ≥ 0.5 against instance 1 (baseline: 3 components, best IoU 0.425), the clover
  must stay separate, and `grass_absorbed_into_crop` must fall well below 53 %.
- **A7 has ground truth for `crop`**: instance 1 is the only `crop: true` entry,
  and instances 9/10 (a dark ovate weed growing up through the squash vines) are
  exactly the hard case that chunk wants — visually entangled with the crop
  rather than sitting alone on mulch.
