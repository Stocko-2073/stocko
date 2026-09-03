# A0 bookkeeping — blocks for the manager to apply

Three sections, each a verbatim block. A0 did **not** edit `RESULTS.md`,
`CONSTANTS.md` or `PROGRESS.md`.

---

## 1. Append to `RESULTS.md`

Also: in the existing "Baseline — ZeroPlantSeg, as published" block, the two rows
`| Per-class IoU | pending A0 |` and `| Instance F1 | pending A0 |` are now
answered — replace them with `see "Baseline re-scored against A0" below` or leave
them and rely on the new block; the new block is self-contained either way.

```markdown
## Baseline re-scored against A0 ground truth

**Config:** `ZeroPlantSeg/configs/squash.yaml`, `eps=100`, `min_samples=2`
**Ground truth:** `groundtruth/`, chunk A0, 768×1024 label grid
**Scored with:** `chunks/A0/eval.py --zps` (and `score_baseline.py`)
**Date:** 2026-09-01

ZeroPlantSeg already runs at 768×1024, the A0 label grid, so **nothing is
resampled** — this is a native-grid comparison. 1.51 % of the frame is
`unlabelled` and excluded from every number below.

### Instances

| Quantity | Value |
|---|---|
| GT instances / predicted instances | 10 / 5 |
| Match rule | greedy 1-1, highest IoU first, accepted at IoU ≥ 0.5 |
| TP / FP / FN | 0 / 5 / 10 |
| Precision / Recall / **F1** | 0.0000 / 0.0000 / **0.0000** |
| Best IoU vs. the squash (GT instance 1) | **0.425** — below threshold, so no match |
| Squash split across | **3** predicted instances: 185 681 / 98 841 / 59 916 px |
| Best IoU vs. any weed | 0.246 (the clover patch, GT instance 3) |
| **Grass absorbed into the crop instance** | **53.0 %** of GT grass (56 193 / 106 099 px) |

Grass carries GT instance id 255 (unresolved — clonal, interleaved blades) and is
excluded from matching; absorption is reported separately instead.

### Material classes

ZeroPlantSeg emits instances, not classes, so the material row needs a stated
mapping. **Charitable mapping:** squash instances (2, 4, 5) → `squash_leaf`,
clover instance (3) → `broadleaf_weed`, background → `straw`. This is the most
favourable reading of its output.

| Class | IoU | GT px | Pred px |
|---|---:|---:|---:|
| `squash_leaf` | 0.6760 | 360 852 | 408 128 |
| `squash_petiole` | 0.0000 | 55 560 | 0 |
| `grass` | 0.0000 | 106 099 | 0 |
| `broadleaf_weed` | 0.4903 | 18 655 | 19 387 |
| `straw` | 0.6076 | 216 116 | 347 013 |
| `soil` | n/a | 0 | 0 |
| `fruit` | 0.0000 | 16 692 | 0 |
| `other` | 0.0000 | 554 | 0 |
| **mean IoU** (classes present in GT) | **0.2534** | | |

| Config-free check | Value |
|---|---|
| Plant vs. background IoU | **0.7574** (GT plant 557 858 px, pred 428 313 px) |

Plant-vs-background flatters it badly: 0.757 there, 0.253 on the real class
table. Any A3 result must be reported on the eight-class table.

### Contact points

n/a — ZeroPlantSeg produces no contact points. Nothing to score.

**Targets this sets.** A3: beat mean IoU 0.2534, and beat 0.0000 on `grass` and
`squash_petiole`, which the baseline cannot express at all. A4: one component for
the squash at IoU ≥ 0.5 (baseline: 3 components, best 0.425), clover still
separate, grass absorption well below 53 %.

---

## A0 — Ground truth for one image

**Ground truth:** `groundtruth/` · **Scorer:** `chunks/A0/eval.py`
**Date:** 2026-09-01 · **Findings:** `chunks/A0/FINDINGS.md`

Label grid 768×1024, a uniform 3.90625× downsample of the native 3000×4000.

| Class | px | % of frame |
|---|---:|---:|
| `squash_leaf` | 360 852 | 45.88 |
| `straw` | 216 116 | 27.48 |
| `grass` | 106 099 | 13.49 |
| `squash_petiole` | 55 560 | 7.06 |
| `broadleaf_weed` | 18 655 | 2.37 |
| `fruit` | 16 692 | 2.12 |
| **`unlabelled` (excluded from scoring)** | **11 904** | **1.51** |
| `other` | 554 | 0.07 |
| `soil` | 0 | 0.00 |

| Layer | Value |
|---|---|
| Plant instances | 10 — the squash (1, `crop: true`) and 9 broadleaf weeds |
| Grass instances | **unresolved**, id 255, excluded from instance matching |
| Contact points | 10, one per instance |
| — tagged `visible` | **0** |
| — tagged `under_straw` | **10** (all `localisation: estimated`) |
| — tagged `out_of_frame` | 0 |
| Bare soil visible | **none isolable** |

`eval.py` self-check: the ground truth scores IoU 1.0 per class and instance F1
1.0 against itself; `chunks/A0/test_eval.py` — 14 assertions, all pass.
```

---

## 2. Append to `CONSTANTS.md` → Active table

The existing A0 row for `instance match IoU` is already correct; add these three:

```markdown
| A0 | GT label grid | 768 × 1024 | (a) | Uniform 3.90625× downsample of native 3000×4000, identical scale in x and y. Chosen because it is the resolution the recorded ZeroPlantSeg baseline runs at, so the baseline is scored with no resampling. `eval.to_gt_grid` nearest-resamples anything else and reports that it did. | n/a | — |
| A0 | min reviewable region | 25 px | (a) | Below 25 px on the GT grid a partition fragment cannot be judged by eye, so it is merged into its nearest labelled neighbour rather than given a guessed class. Grid-resolution property, not a scene property. | n/a | — |
| A0 | fragmentation min part | 200 px | (a) | Reporting threshold in `eval.fragmentation` only: a predicted piece smaller than this is speckle, not a fragment. Affects no score. | n/a | — |
```

---

## 3. Append to `PROGRESS.md`

Status table change: the `A0` row becomes

```markdown
| A0 | Ground truth for one image | — | done | `chunks/A0/FINDINGS.md` |
```

and **Next up:** should read `A1` (A0 is done; A3 is now unblocked once A2 lands).

Log entry to append at the bottom:

```markdown
### 002 — 2026-09-01 · A0 ground truth and the scoring contract

**Chunk:** A0 — Ground truth for one image

**Done**
- Labelled `plants.jpeg` once, carefully, on a 768×1024 grid (a uniform 3.90625×
  downsample of the native 3000×4000). SAM ViT-H drew the boundaries — 512
  proposals collapsed to a 688-region non-overlapping cover — and every class was
  then assigned by eye: sixteen 4× review tiles over the whole frame, ~15 further
  windows at 6–10× on the calls I could not make, and seven native-resolution
  crops where 10× on the label grid still was not enough. No classifier assigned
  a class. The decisions are recorded region-by-region in
  `chunks/A0/corrections.json` with the reasoning per pass.
- Shipped `groundtruth/`: material label map, instance map, contact-point JSON,
  the region partition for provenance, a manifest, and `SCHEMA.md` — which is the
  contract, and says so.
- Shipped `chunks/A0/eval.py`: per-class IoU over labelled pixels only, instance
  precision/recall/F1 under a documented and swappable match rule (greedy 1-1 by
  descending IoU, accepted at IoU ≥ 0.5), contact-point error in grid px split by
  status, plus two diagnostics — squash fragmentation and grass-absorbed-into-crop.
  `chunks/A0/test_eval.py` asserts the properties that make those numbers mean
  what they say; 14 assertions, all pass.
- Re-scored the ZeroPlantSeg baseline against it. See `RESULTS.md`.

**Measured** — see `RESULTS.md`. Headline: instance F1 **0.000**; best IoU
against the squash **0.425** (below the 0.5 match threshold, so zero matches);
the squash split across **3** predicted instances; **53.0 %** of ground-truth
grass absorbed into the crop instance; mean IoU **0.2534** on the eight-class
table under a charitable mapping, against **0.7574** for plant-vs-background.
Ground truth is **1.51 % `unlabelled`**.

**Decided**
- The label grid is the baseline's grid, not native, so the recorded baseline is
  scored with no resampling at all. Anything else is nearest-resampled and the
  report says so.
- Grass instances are declared **unresolved** (id 255) and excluded from instance
  matching, because grass is clonal and its blades interleave below this
  resolution — guessing tussock membership would be a fabricated label. The
  failure that actually matters is measured directly instead, as
  `grass_absorbed_into_crop`.
- Contact points carry `occluded_by` (`straw`/`foliage`/`frame`) and
  `localisation` (`observed`/`estimated`) beyond the roadmap's three-value
  status. Hidden-by-straw and hidden-by-leaves are different problems for a
  robot, and an estimated point must not be scored as if it had been seen.
- `soil` is left at zero pixels rather than approximated. `squash_petiole` covers
  all non-blade, non-fruit squash structure; `straw` covers dry dead plant
  material wherever it lies.

**Surprised us**
- **Not one stem in this image is seen meeting the ground.** All ten contact
  points are `under_straw` and estimated; zero are `visible` — including the
  squash's own, whose petioles converge on a visible crown node and then vanish
  behind straw. A5's specified metric, contact-point error over `visible` points,
  is therefore *empty* for this image. That is not a labelling shortfall, it is
  what a mulched bed looks like, and it settles Open Question 1 much harder than
  expected: `lowest_visible_stem_point` is not a fallback, it is the only
  measurable target.
- There is **no bare soil** to label. A2's choice of straw as the datum is not a
  simplification, it is the only option.
- ZeroPlantSeg scores an instance F1 of exactly **zero** while visibly finding the
  plant — its best squash IoU, 0.425, sits just under the conventional threshold.
  The old "5 instances, squash in 3" summary was generous.
- **53 %** of grass ends up inside the crop instance; the rest is not correctly
  rejected either, it simply lands in no instance at all.
- `squash_petiole` is **7.06 %** of the frame, more than every weed class
  combined — so A3's "the strict prompt drops the petioles" is a bigger loss than
  it sounded.
- Colour separates living from dead material almost perfectly and is useless for
  grass vs. squash. What separated them by eye was cross-section and texture
  (ribbed, hairy, round petioles vs. flat, keeled, tapering blades) — and neither
  survives the downsample to 768×1024. A3's shape prior will have less evidence
  than I did.

**Next**
- A1: real float depth for `plants.jpeg`.
- A5's done-criteria need re-reading against the finding that no contact point in
  this image is observable.
```
