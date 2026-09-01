# Chunk A3 — Plant material segmentation

**Session:** 2026-09-01 · **Status:** done · **Depends on:** A0 (done), A2 (done)
**Ground truth:** `groundtruth/`, A0's 768×1024 label grid, scored with
`chunks/A0/eval.py`. Nothing is resampled — every prediction is produced on that
grid natively.
**Baseline to beat:** ZeroPlantSeg, mean IoU **0.2534**, with **0.0000** on
`grass` and `squash_petiole`, and **53.0 %** of ground-truth grass absorbed into
the crop instance.

> **Read this before any number below.** A0's ground truth was painted
> region-by-region onto A0's **own** SAM partition. Classifying those same
> regions has a ceiling of **exactly 1.0** and zero boundary error —
> `test_a3.py::test_a0_partition_ceiling_is_one` asserts it, and it is not an
> approximation. Reusing that partition would have handed every region-based A3
> approach the hard half of the problem for free. A3 therefore ran SAM again
> with different generator settings and scored everything on that
> **independent** partition, whose ceiling is **0.9246**.

## What was built

Everything under `chunks/A3/`; rebuild instructions in `README.md`.

| File | Role |
|---|---|
| `a3_api.py` | **the shipped default** — frozen DINOv2 + a 42-patch logistic probe |
| `seed_patches.json` | the 42 fitted patches, with their provenance stated in the artifact |
| `a3_common.py` | partition construction, region features in five named groups, spatially blocked CV, scoring wrappers |
| `sam_regions.py` | the independent SAM run, and the argument for it |
| `shape_prior.py` | approaches 1 and 2, plus an 11-variant feature-group ablation |
| `dino_probe.py` | approach 3, plus the height ablation *inside the winner* |
| `dino_region.py` | approach 3b — the same features on the SAM substrate, as a control |
| `open_vocab.py` | approach 4 — 3 models × 3 crop variants × 2 vocabularies × 2 prompt modes |
| `alpha_clip_check.py` | the Alpha-CLIP feasibility probe, so the fallback is recorded rather than asserted |
| `height_report.py` | A2's height channel scored against A0 labels for the first time |
| `compare.py` | the one comparison table, plus the probe-`C` and patch-count sweeps |
| `figures.py`, `test_a3.py` | five figures, all checked by eye; 18 tests, all passing |

New venv `chunks/A3/.venv` (Python 3.11, torch 2.13.0 + MPS, transformers
5.16.1, scikit-learn 1.9.0); lock in `requirements.lock.txt`. SAM still runs
from `ZeroPlantSeg/.venv`, untouched.

### Method notes that change how the numbers should be read

* **Approaches 1, 2 and 4 classify SAM regions; approach 3 classifies a
  3.5-label-px patch grid.** The two substrates have almost the same ceiling —
  **0.9246** for the 728-region partition, **0.9201** for the patch grid — so
  the comparison is about features, not about who got the better boundaries.
* **Approaches 1 and 2 are scored strictly out-of-fold.** The frame is cut into
  a 4×4 grid of spatial blocks and whole blocks are dealt to 4 folds, because
  regions are contiguous and a random split would leave a region's own
  neighbours (same leaf, same tussock, same light) in the training set.
  `test_cv_is_actually_blind` builds a dataset whose label is a function of the
  block alone and asserts the CV cannot learn it. Every headline is the **mean
  over five block-to-fold deals**, with the in-sample score printed beside it so
  the overfitting gap is visible rather than implied. Seed 0 alone reads 0.248
  for approach 2 against a five-deal mean of 0.285 — publishing one deal would
  have been publishing a lucky draw.
* **Approach 3 is fitted on 42 patches sampled from the ground truth** (6 per
  class × 7 classes; a patch is eligible only if its label-grid footprint is
  100 % one class). Those patches' own pixels are **0.07 %** of the frame, and
  every score is reported twice: whole-frame, and with the fitted pixels removed
  from the ground truth the way A0 removes `unlabelled`. Five independent draws;
  the headline is their mean ± sd. The gap between the two readings is 0.0053 —
  real, small, and stated.
* **Approach 4 is zero-shot, so the whole frame is legitimately test data.** The
  only thing that can be over-fitted is the configuration, so the headline cell
  (`crop_fill` = OVSeg's own protocol, descriptive prompts, 12-template
  ensemble) was fixed before scoring, and the full 12-cell grid is reported
  underneath with the best cell flagged as chosen after the fact.
* **`soil` is never predicted.** A0 has zero soil pixels, so it can be neither
  learnt nor scored; predicting it could only steal pixels from classes that
  exist. `eval.py` prints `n/a` and the mean excludes it.

### Roadmap classes → A0 classes

The roadmap names six classes; A0 labels eight and is finer. A3 predicts
**A0's** classes and reports on A0's table, as the brief requires.

| roadmap | A0 |
|---|---|
| `broadleaf` | `squash_leaf` **+** `broadleaf_weed` — A0 separates crop leaf from weed leaf, and the split is kept, because it is the distinction A7 exists to make |
| `stem_petiole` | `squash_petiole` (all non-blade, non-fruit squash structure) |
| `grass` | `grass` |
| `straw` | `straw` |
| `fruit` | `fruit` |
| `soil` | `soil` — **0 px in this image**, unscoreable |
| — | `other` (554 px, one feather) has no roadmap class; scored anyway |

## What was measured

### The four approaches, one table

Per-class IoU on A0's eight-class table. `soil` omitted (0 GT px, `n/a`).
Approaches 1–3 are means over 5 CV deals / patch draws (± sd); approach 4 is
deterministic.

| approach | squash_leaf | squash_petiole | grass | broadleaf_weed | straw | fruit | other | **mean IoU** | grass→squash | compute |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| ZeroPlantSeg baseline (charitable mapping) | 0.6760 | 0.0000 | 0.0000 | 0.4903 | 0.6076 | 0.0000 | 0.0000 | **0.2534** | 53.0 %\* | ~8 min |
| 1. shape prior over SAM regions | 0.6502 | 0.1444 | 0.4152 | 0.0000 | 0.5113 | 0.0000 | 0.0000 | **0.2459** ±0.0180 | 22.5 % | SAM 776 s + 1.5 s features + <1 s fit |
| 2. shape prior + A2 `height_above_soil` | 0.6609 | 0.1707 | 0.4397 | 0.0629 | 0.6577 | 0.0001 | 0.0000 | **0.2846** ±0.0336 | 34.5 % | as above (A2 rasters already on disk) |
| **3. frozen DINOv2 + logistic probe, 42 patches** | **0.7634** | **0.3598** | 0.4084 | **0.3327** | **0.7292** | 0.8170 | **0.4656** | **0.5537** ±0.0197 | 25.3 % | **4.7 s features + 0.04 s fit/predict, no SAM** |
| 4. open-vocabulary, SigLIP 2 so400m | 0.7027 | 0.1940 | 0.1025 | 0.1830 | 0.5846 | **0.9362** | 0.0809 | **0.3977** | 84.9 % | SAM 776 s + 6 s crops + 103 s encode |

\* the baseline's 53.0 % is grass absorbed into the crop *instance*; it emits no
grass class at all, so a class-level figure is undefined for it. Every other row
is the class-level number: the fraction of GT grass pixels predicted as
`squash_leaf`, `squash_petiole` or `fruit`.

**Every approach beats 0.0000 on `grass` and `squash_petiole`** — the two
classes the baseline cannot express. Three of the four beat mean IoU 0.2534;
approach 1, the pure shape prior, does not.

Figures: `figs/fig_comparison.png` (all four maps beside the ground truth),
`figs/fig_confusion.png` (row-normalised confusion), `figs/fig_grass_zoom.png`
(three crops where grass and squash interleave), `figs/fig_height.png`,
`figs/fig_seed_patches.png`.

### The winner, and by how much

Approach 3 at **0.5537 ± 0.0197** is **2.19×** the baseline and **1.39×** the
runner-up. It is also the cheapest by two orders of magnitude: 4.7 s of DINOv2
features on MPS and 40 ms to fit and predict, against 13 minutes of SAM ViT-H
for every region-based approach and 8 minutes for the baseline. It uses no SAM
at all.

The shipped default (`a3_api.py`, the frozen 42-patch set in
`seed_patches.json`) scores **0.5425**, grass→squash **17.8 %** — inside the
±0.0197 band, and reported separately from the approach mean because a shipped
artifact should advertise what it actually produces rather than what its family
averages.

### Grass vs. squash — the failure this chunk exists to fix

Row-normalised GT `grass` row, from the saved map of one deal / draw each
(`figs/fig_confusion.png`); the multi-deal means are in the table above.

| | → grass | → squash_leaf | → squash_petiole | → straw | GT squash → grass |
|---|---:|---:|---:|---:|---:|
| baseline | — (no grass class) | 53.0 % into the crop **instance** | — | — | — |
| 1. shape prior | 65.7 % | 21.2 % | 0.7 % | 12.4 % | 8.5 % |
| 2. + height | 61.8 % | 22.4 % | 8.5 % | 6.3 % | 7.4 % |
| **3. DINOv2 probe (the default)** | **76.3 %** | **9.4 %** | 8.2 % | 4.0 % | 15.2 % |
| 4. SigLIP 2 so400m | 14.2 % | 56.6 % | 28.3 % | 0.4 % | 7.3 % |

**Verdict: fixed, not solved.** The winner cuts grass-into-squash from the
baseline's 53 % to **17.8 %** (25.3 % as an approach mean over five draws) and
recovers **76 %** of grass as grass, against a baseline with no grass class at
all. But `grass` IoU is 0.41, the weakest of the winner's plant classes, it
over-predicts grass (170 955 predicted px against 106 099 GT), and it pays for
its grass recall with 15.2 % of squash material called grass — the highest
squash→grass rate of the four. The residual confusion is exactly where A0
predicted: blades passing behind petioles at the crown, where a blade is 3–6 px
wide on this grid (`figs/fig_grass_zoom.png`, row 3).

**Approach 4 makes the failure worse than the baseline.** 84.9 % of grass goes
to squash material. The mechanism is visible in the grid: it is the *descriptive
prompts* that do it. With plain class names and OVSeg's own crop protocol,
SigLIP 2 so400m puts 38 % of grass into squash; swapping in "long narrow blades
of green grass" against "a large lobed green squash leaf blade" moves that to
85 % while mean IoU only moves 0.4213 → 0.3977. A prompt that reads better to a
human moved the decision boundary the wrong way, and the aggregate score barely
flinched.

### The height ablation — what `height_above_soil` contributed on its own

Three measurements, because "on its own" has three readings.

**(a) Inside approach 2, where the brief asks for it.** Same regions, same tree,
same folds; only the feature group changes.

| features | mean IoU | Δ |
|---|---:|---:|
| SHAPE + SIZE (approach 1) | 0.2459 | — |
| **SHAPE + SIZE + HEIGHT (approach 2)** | **0.2846** | **+0.0387** |
| HEIGHT alone | 0.2148 | — |
| COLOUR alone | 0.1986 | — |
| COLOUR + HEIGHT | 0.2093 | +0.0107 over colour |
| SHAPE + SIZE + COLOUR | 0.2817 | — |
| SHAPE + SIZE + COLOUR + HEIGHT | 0.2978 | +0.0161 over shape+colour |
| all hand-crafted (+ native-resolution TEXTURE) | 0.3001 | +0.0023 over the above |

Height is the most valuable single hand-crafted group: **+0.0387** on top of
shape, and 0.2148 entirely on its own, which is within noise of the whole shape
prior. It is what lifts approach 2 over the baseline when approach 1 sits under
it. But its contribution **shrinks as other features are added** (+0.039 over
shape, +0.016 over shape+colour) — the signature of information that is also
carried elsewhere.

**(b) Inside the winner, which is the reading that decides the default.**

| features | mean IoU |
|---|---:|
| DINOv2 (standardised) | 0.5267 |
| DINOv2 + height + datum reliability | 0.5263 |
| height + datum reliability alone | 0.1536 |

**Height adds −0.0004 — nothing.** DINOv2 already knows everything the height
channel was contributing. The shipped default therefore does not use A2's height
raster, and says so in its provenance dict.

**(c) Against the labels, for the first time.** A2 checked its height field
against five hand-placed boxes; A0 did not exist yet. Over every labelled pixel
(`results/height_report.json`, `figs/fig_height.png`), in datum σ, weighted by
`height_sigma` reliability as A2's FINDINGS asked:

| class | A2's hand-placed box | A3 median over all labelled px | p25 … p75 |
|---|---:|---:|---:|
| `straw` (the datum) | 0 | **−0.0** | −0.7 … 1.0 |
| `broadleaf_weed` | 7 | **4.7** | 2.5 … 10.7 |
| `fruit` | 22 | **20.0** | 16.6 … 23.4 |
| `grass` | 52 | **33.1** | 13.6 … 61.0 |
| `squash_petiole` | — | **43.2** | 25.5 … 57.6 |
| `squash_leaf` | 93 | **62.9** | 53.6 … 95.8 |

The **ordering** A2 published survives. The **margins** do not: A2's boxes sit
near each class's p75, systematically optimistic, and once the whole class is
included grass and squash overlap heavily. Separability of a height-only
threshold, `max(AUC, 1−AUC)`:

| pair | separability |
|---|---:|
| `squash_leaf` vs `straw` | **0.974** |
| `grass` vs `straw` | **0.959** |
| `broadleaf_weed` vs `straw` | 0.885 |
| `grass` vs `broadleaf_weed` | 0.833 |
| `grass` vs `squash_leaf` | **0.736** |
| `grass` vs `squash_petiole` | **0.548** |

**Height is excellent at plant-versus-ground and nearly useless at
grass-versus-squash-stem** — 0.548 is 0.048 above a coin toss. That is the
honest answer to the brief's ablation: A2's channel is a strong plant/background
separator, it is not the grass/squash discriminator A2's FINDINGS hoped for, and
the thing it is good at is the thing colour was already good at. (Per-pixel AUCs
over hundreds of thousands of correlated pixels carry no confidence interval;
they describe this image.)

### Approach 4 in detail: model, region marking, prompt ensembling

Headline cell = `crop_fill` | descriptive | 12-template ensemble.

| model | headline mean IoU | best cell (chosen after seeing scores) | encode time / variant |
|---|---:|---|---:|
| SigLIP 2 so400m/14 @384 | **0.3977** | 0.4213 (`crop_fill`\|plain\|ensemble) | 103 s |
| SigLIP 2 base/16 @384 | 0.2443 | 0.2558 (`crop_fill`\|descriptive\|single) | 18 s |
| CLIP ViT-L/14 (the "before") | 0.3895 | 0.4382 (`crop_fill`\|descriptive\|single) | 20 s |

**The model upgrade did not deliver.** A 2022-era CLIP ViT-L/14, on identical
crops and identical prompts, scores 0.3895 against SigLIP 2 so400m's 0.3977 — a
0.008 difference, far inside the spread across configurations, at a fifth of the
compute. SigLIP 2 *base* is clearly worse than either. Whatever limits approach
4, it is not the vision-language model's vintage. (The so400m size was named as
the approach-4 headline *after* base under-performed; that selection is
disclosed rather than hidden, and both are in the table.)

**Prompt ensembling is worth approximately nothing here.** Mean Δ mean-IoU over
the six (crop variant, vocabulary) cells: **+0.0091** for SigLIP 2 so400m,
**+0.0070** for SigLIP 2 base, **−0.0045** for CLIP-L. Per cell it ranges from
−0.049 to +0.045 and the sign is not stable. The roadmap called it "a known
few-point gain and a two-line change". It is a two-line change; on this task it
is noise.

**Crop-and-fill won, which was not expected.** OVSeg's destroy-the-surround
protocol beat both context-preserving variants for all three models (so400m:
0.398 `crop_fill` vs 0.288 `crop_context` vs 0.218 `blend`). The `blend` variant
is Alpha-CLIP's actual idea — mark the region, keep the surround at reduced
contrast — implemented without new weights, and it came **last every time**. On
a scene where every crop's surround is more leaves, the surround is a
distractor, not context.

**Alpha-CLIP itself could not be run, and the check is recorded rather than
asserted** (`alpha_clip_check.py`, `results/alpha_clip_check.txt`). The *code*
installs cleanly: `uv pip install --dry-run git+https://github.com/SunzeY/AlphaCLIP`
resolves at commit `ef9262bc`, adding only ftfy and wcwidth. The *weights* are
not obtainable from any attributable source: no PyPI package (`alpha-clip`,
`alpha_clip` → 404), no official Hugging Face repo (`SunzeY/AlphaCLIP` → 404),
model-zoo Google Drive links behind an interactive consent page, and
`download.openxlab.org.cn` does not resolve from here at all. The only HF hits
for "alphaclip" are an unversioned third-party fine-tune with no model card and
a repo containing nothing but `.gitattributes`. Loading unattributed weights to
make a claim about a published method would be worse than not running it, so
approach 4 ships SigLIP 2, as the brief permits.

### Sweeps, so the winner's constants are not hidden

`results/comparison.json → probe_sweeps`, each over the same 5 draws.

| probe `C` | 0.01 | 0.1 | **1.0** | 10 | 100 |
|---|---:|---:|---:|---:|---:|
| mean IoU | 0.4863 | 0.5083 | **0.5537** | 0.5499 | 0.5411 |

sklearn's untouched default is also the optimum and the curve is flat over two
decades above it, so `C = 1.0` is a read-off rather than a tuning.

| labelled patches | 14 | 28 | **42** | 84 | 168 |
|---|---:|---:|---:|---:|---:|
| mean IoU | 0.4219 ±0.0700 | 0.4910 ±0.0298 | **0.5537 ±0.0197** | 0.5834 ±0.0152 | 0.6095 ±0.0069 |
| grass→squash | 36.8 % | 35.0 % | 25.3 % | 23.1 % | 28.0 % |

Fourteen patches — two clicks per class — already beat the baseline by 1.7×.
Returns are still positive at 168 but flattening; "a few dozen" sits just past
the knee.

Tree depth for approaches 1–2 was fixed at 4 *a priori* (a shape prior is meant
to be readable) and swept 2–8 as sensitivity: approach 1 runs 0.153 → 0.272,
approach 2 0.268 → 0.296. Both stay far below approach 3 at every depth.

### Extensions, kept separate because the brief asked for four

| variant | mean IoU | note |
|---|---:|---|
| 3b. DINOv2 features pooled over SAM regions, logreg, blocked CV | 0.5203 ±0.0925 | in-sample 0.9246 — *exactly* the partition ceiling: it fits its training regions perfectly |
| 3b. same, random forest | 0.3892 ±0.0327 | |
| 3b. same, depth-4 tree | 0.3159 ±0.0231 | |
| 1. shape prior, random forest instead of a tree | 0.2753 | +0.029 over the tree |
| 2. shape + height, random forest | 0.3264 | +0.042 over the tree |
| all hand-crafted features, random forest | 0.3413 | the ceiling of the hand-crafted route |

Snapping the winner's features to SAM boundaries (3b) scores **worse** than the
raw patch grid, and with four times the variance, because the partition's own
errors are then inherited whole.

## What was decided

1. **The winner is approach 3, wired up as `a3_api.segment_material()`.** Frozen
   DINOv2-base at two scales (a tiled 3.5-label-px fine grid plus one
   whole-frame coarse pass), L2-normalised and concatenated, with a multinomial
   logistic probe over 42 frozen patches. It is the most accurate, the cheapest,
   the only one needing no SAM, and the only one above 0.33 on every plant
   class.
2. **The default does not use `height_above_soil`,** because it was measured to
   add −0.0004. This is a decision about A3 only. A4 still wants the channel —
   for grouping, not for classification.
3. **A3 ran its own SAM.** Scoring on A0's partition would have been scoring a
   segmentation problem the ground-truth construction had already solved. The
   independent ceiling (0.9246) is published beside every region-based score so
   the headroom is visible.
4. **`soil` is dropped from the predicted label space** rather than predicted
   and scored at zero. A class with no ground truth cannot be learnt, and
   predicting it can only take pixels from classes that can.
5. **Approach 4 ships SigLIP 2, and Alpha-CLIP is recorded as unobtainable
   rather than quietly skipped.** The `blend` crop variant tests Alpha-CLIP's
   idea without its weights, and the idea lost.
6. **Every headline is an average over five splits or draws.** Single-split
   numbers moved by up to 0.09 between deals.
7. **Colour and native-resolution texture are ablations, not approach 1.** The
   brief's approach 1 is shape only, and shape only is the headline row — but a
   shape-only classifier cannot tell a leaf from straw at all, so the colour and
   texture columns are there to say how much of approach 1's weakness is the
   *feature set* rather than the *idea*.

## Constants introduced

| Name | Value | Cat | Justification | Sweep |
|---|---|---|---|---|
| A3 SAM generator settings | pps 64, pred_iou 0.82, stability 0.90, min area 25 | (a) | Chosen to differ from A0's (48 / 0.80 / 0.88 / 60) so the partition is independent of the one the ground truth was painted on. Finer is better for a region classifier's ceiling — a principle, not a fit to score. | two settings run: 282 masks → 369 regions (ceiling 0.8202) and 572 → 728 (ceiling 0.9246) |
| min reviewable region | 25 px | (a) | **A0's registered constant, reused unchanged**, so the two partitions are comparable. | inherited from A0 |
| CV block grid | 4 × 4 blocks, 4 folds | (c) | Spatial blocking, because regions are contiguous and a random split leaks a region's own neighbourhood. A statement about the leak, not about the scene. | 5 block-to-fold deals; spread ±0.018–0.034 mean IoU |
| CV deals averaged | 5 | (c) | How many block-to-fold deals a headline averages; chosen so an sd is reportable. | the spread itself is the sweep |
| shape-prior tree depth | 4 | (c) | A shape prior should be a handful of readable thresholds. Fixed a priori, not selected on score. | 2/3/4/6/8 → 0.153–0.272 (a1), 0.268–0.296 (a2) |
| shape-prior min leaf weight | 1 % of training weight | (c) | So no threshold is fitted to a single region. | n/a |
| DINOv2 fine scale | 3066 × 4088; 14 px patch = **3.5 label px** | (a) | A uniform 3.992× of A0's label grid, tiled at DINOv2's own 518 px training size with a 6-patch overlap, averaged. Set by the model's patch size and the label grid, not by the scene. | patch-grid ceiling 0.9201 vs the 0.9246 region ceiling |
| DINOv2 coarse scale | 546 × 728 | (a) | The whole frame in one pass, so every patch also carries plant-level context. | n/a |
| probe regularisation `C` | 1.0 | (c) | sklearn's untouched default, and the optimum of the sweep. | 0.01/0.1/1/10/100 → 0.486/0.508/**0.554**/0.550/0.541 |
| labelled patches | 42 (6 per class × 7) | (c) | The brief's "few dozen". | 14/28/42/84/168 → 0.422/0.491/**0.554**/0.583/0.609 |
| open-vocab crop pad | 30 % of the bbox | (c) | Context margin for the two non-OVSeg crop variants; both lost to the zero-margin variant, so the value never decided anything. | `crop_fill` (no pad) beat both padded variants for all three models |
| open-vocab min crop | 96 native px | (a) | Below this a crop carries no texture at the encoder's 384 px input. A property of the encoder. | n/a |
| prompt ensemble size | 12 templates | (c) | The roadmap's "a dozen". | single vs ensemble, 6 cells × 3 models: −0.045 … +0.045; means +0.009 / +0.007 / −0.004 |

**Nothing here encodes a belief about how gardens are arranged** — no plant
spacing, no expected crop size, no assumed camera height. Two constants come
close enough to say out loud, and both are inside **approach 1, the loser**: the
fitted tree splits on `mean_width ≤ 15.86 px` and `log_area ≤ 3.72`, which are
*pixel sizes*, and a pixel size is a statement about how far the camera was from
the bed. They are category (c) — measured in this scene — and they will not
survive a different camera height, which is what B1 is for. The
`abl_shape_scalefree` row (dimensionless ratios only, no SIZE group) scores
0.2176 against 0.2459 with them, so those scale-dependent features are worth
+0.028 and are load-bearing for that approach. **The shipped winner has no such
constant**: its only numbers are a regularisation strength and a patch count.

## What surprised us

1. **A0's own partition has a ceiling of exactly 1.0, and it took writing a test
   to notice.** The ground truth was painted on it, so a region classifier
   scored there has zero boundary error by construction, and the first A3 run
   was about to use it. Two SAM runs and thirteen minutes later the honest
   ceiling is 0.9246 — and the difference between 1.0 and 0.9246 is exactly the
   part of the problem a region-classification framing hides from itself.
2. **The best approach is also the cheapest, by two orders of magnitude.**
   DINOv2 features take 4.7 s and the probe 40 ms. Every region-based approach
   pays 13 minutes for SAM ViT-H first; the baseline pays 8. The expectation
   going in was the opposite trade.
3. **A0's warning was right, and the way past it was to stop labelling at
   768 × 1024, not to give up.** A0 wrote: "the separation that actually worked
   by eye was texture and cross-section, and neither survives to 768 × 1024.
   A3's shape prior will have less evidence than I did." It did — approach 1 is
   the only approach that fails to beat the baseline. But the label grid caps
   the *labels*, not the *features*. Running DINOv2 at 3.5 label px per patch
   puts the features back where the evidence lives, and that one change is most
   of the gap between 0.246 and 0.554.
4. **Height's contribution to the winner is exactly zero.** A2 measured straw
   0 σ, clover 7, grass 52, squash leaf 93, and wrote that "the A3 ablation …
   has a real chance of being large". Against the labels the ordering holds but
   the margins collapse: A2's hand-placed boxes sit near each class's p75, and
   grass-vs-petiole separability is 0.548, a coin toss. Height is worth +0.039
   to a shape prior that has nothing else and −0.0004 to a probe on frozen
   features.
5. **The 2022 CLIP was not the problem.** The roadmap framed approach 4 as
   "upgrade the 2022-era mask-tuned CLIP". CLIP ViT-L/14 scores 0.3895 and
   SigLIP 2 so400m 0.3977 on identical crops and prompts — a smaller difference
   than between two prompt vocabularies for the same model.
6. **Prompt ensembling did nothing, and it was supposed to be free points.**
   Mean +0.009 / +0.007 / −0.005 across three models, sign unstable per cell.
7. **Better prose in the prompt made the grass failure five times worse.**
   Swapping plain class names for careful descriptions moved SigLIP 2's
   grass→squash from 38 % to 85 % while barely moving mean IoU. A single
   aggregate would have called that change harmless.
8. **Crop-and-fill beat every context-preserving variant, for all three
   models.** The Alpha-CLIP motivation — don't destroy the surround — is the one
   thing this scene punishes, because every crop's surround is more leaves.
9. **Approach 2's grass→squash is *worse* than approach 1's** (34.5 % vs
   22.5 %) while its mean IoU is better (0.285 vs 0.246). Height buys back straw
   and petiole and pays in exactly the confusion this chunk exists to fix. Two
   numbers, opposite directions, one feature — and only one of them is in the
   headline.
10. **Two clicks per class already beat the baseline.** Fourteen labelled
    patches score 0.422 against 0.2534. Most of what an eight-minute pipeline
    produces on this image is available from fourteen points and five seconds of
    frozen features.

## Not done / deferred

* **One image.** Everything here is `plants.jpeg`. Whether a 42-patch probe
  transfers to another bed, crop, or light is B1's question; the honest guess is
  that the probe needs re-fitting per scene while the *approach* transfers.
* **The 42 patches came from the A0 ground truth**, not from an independent
  human pass. `make_seed_patches.py` records that in the artifact's own
  provenance field. It is a fair stand-in for a user's clicks and it is not the
  same thing.
* **DINOv3 was not tested.** `facebook/dinov3-vitb16-pretrain-lvd1689m` is a
  gated Hugging Face repo and returned 403. The brief allows v2 or v3;
  DINOv2-base is what ran.
* **The winner's output is blocky at 3.5 label px.** Its `grass` IoU of 0.41 is
  partly a boundary artefact on 3–6 px blades, not only a class error. Snapping
  probe labels to SAM boundaries was tested as 3b and scored *worse* (0.520
  ±0.092). A per-pixel CRF, or a finer patch grid, is the untried route.
* **`confidence` is uncalibrated.** It is a 42-point logistic probability. Under
  R2 it can order attention; it must not gate a removal.
* **No instance reasoning, grouping, or contact points.** Out of scope, as the
  roadmap says.
* **Compute figures are single runs on one machine** (Apple Silicon, MPS), not
  benchmarks. They are right to a factor of two, which is all the comparison
  needs.
* **The open-vocab grid was not re-run per CV seed** because it is zero-shot and
  deterministic; its one degree of freedom, configuration choice, is handled by
  fixing the headline cell in advance.

## Implications for the roadmap

* **A4 gets a material map that costs 5 seconds and contains no SAM.** That
  changes A4's shape: connectivity can be built over the winner's patch grid
  plus A4's own SAM run, rather than inheriting A3's regions. Note that the
  winner's `squash_petiole` IoU is **0.3598** — the best of any approach and
  still its weakest plant class. Petioles are what tie the plant together, so
  A4's grouping will be limited by that number more than by anything in its own
  graph.
* **A4 should still take A2's height channel.** A3 found height adds nothing to
  *classification*, which says nothing about *grouping*. A2's advice to subtract
  `soil_surface_depth` before testing depth continuity stands untouched.
* **A2's material-ordering claim needs a footnote now that A0 exists.** The
  ordering (straw < clover < fruit < grass < squash) holds against the full
  labels; the margins are roughly half what the hand-placed boxes suggested, and
  grass/petiole is not separable by height at all (0.548). `height_report.py` is
  the labelled version of `material_check.py` that A2's own FINDINGS asked for.
* **A7 should be told that prose prompts are not free.** The measurement here
  that bears most directly on a VLM stage is that rewriting class descriptions
  moved one specific confusion by 5× while leaving the aggregate flat. A7
  compares two prompt framings; it must report the confusion that matters, not
  only the aggregate.
* **B1's first job is the transfer question this chunk could not ask.** Two
  things to measure per new image: how many patches the probe needs, and whether
  approach 1's `mean_width ≤ 15.86 px` split — the one genuinely
  scale-dependent constant A3 produced — moves with camera height as predicted.
* **Open question 4 ("where does ZeroPlantSeg end up?") moves closer to an
  answer.** Its material output is beaten 2.2× by five seconds of frozen
  features and 42 clicks. Whatever case remains for it is about instances, and
  A4 decides that.
