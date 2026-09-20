# A3 — bookkeeping

Copy-paste blocks for the three tracking files. **A3 did not edit
`RESULTS.md`, `CONSTANTS.md` or `PROGRESS.md`.** Everything below is ready to
append, unchanged.

---

## 1. Append to `RESULTS.md`

```markdown
## A3 — Plant material segmentation

**Ground truth:** `groundtruth/` (A0), 768×1024 · **Scorer:** `chunks/A0/eval.py`
**Date:** 2026-09-01 · **Findings:** `chunks/A3/FINDINGS.md` ·
**Table:** `chunks/A3/results/comparison.md` · **Default:** `chunks/A3/a3_api.py`
Every prediction is produced natively on the 768×1024 label grid — nothing is
resampled. `soil` is omitted throughout: A0 has zero soil pixels.

### The substrate, before any score

A0's ground truth was painted region-by-region onto A0's **own** SAM partition,
so classifying those regions has a ceiling of **exactly 1.0** with zero boundary
error (asserted in `chunks/A3/test_a3.py`). A3 therefore ran SAM again with
different generator settings and scored everything on that independent
partition.

| substrate | regions / patches | oracle ceiling (majority GT class per region) |
|---|---:|---:|
| A0's own partition | 688 | **1.0000** — the leak |
| A3 coarse (pps 32) | 369 | 0.8202 |
| **A3 fine (pps 64) — used for approaches 1, 2, 4** | **728** | **0.9246** |
| DINOv2 patch grid (3.5 label px) — used for approach 3 | 63 948 | 0.9201 |

### The four approaches

Per-class IoU on A0's eight-class table. Approaches 1–3 are means over five
spatially-blocked CV deals / patch draws (± sd); approach 4 is zero-shot and
deterministic.

| approach | squash_leaf | squash_petiole | grass | broadleaf_weed | straw | fruit | other | **mean IoU** | grass→squash | compute (Apple Silicon, MPS) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| ZeroPlantSeg baseline (charitable mapping) | 0.6760 | 0.0000 | 0.0000 | 0.4903 | 0.6076 | 0.0000 | 0.0000 | **0.2534** | 53.0 %* | ~8 min/image |
| 1. shape prior over SAM regions (depth-4 tree, blocked CV) | 0.6502 | 0.1444 | 0.4152 | 0.0000 | 0.5113 | 0.0000 | 0.0000 | **0.2459** ±0.0180 | 22.5 % | SAM ViT-H 776 s + features 1.5 s + fit <1 s |
| 2. shape prior + A2 `height_above_soil` | 0.6609 | 0.1707 | 0.4397 | 0.0629 | 0.6577 | 0.0001 | 0.0000 | **0.2846** ±0.0336 | 34.5 % | as above; A2 rasters already on disk |
| **3. frozen DINOv2 + logistic probe, 42 patches** | **0.7634** | **0.3598** | 0.4084 | **0.3327** | **0.7292** | 0.8170 | **0.4656** | **0.5537** ±0.0197 | 25.3 % | **features 4.7 s + fit/predict 0.04 s; no SAM** |
| 4. open-vocabulary, SigLIP 2 so400m (crop_fill, descriptive, 12-template ensemble) | 0.7027 | 0.1940 | 0.1025 | 0.1830 | 0.5846 | **0.9362** | 0.0809 | **0.3977** | 84.9 % | SAM 776 s + crops 6 s + encode 103 s |

\* the baseline's 53.0 % is grass absorbed into the crop *instance*; it emits no
grass class, so a class-level figure is undefined for it. Every other row is the
fraction of GT grass pixels predicted as `squash_leaf`, `squash_petiole` or
`fruit`.

**vs. the recorded baseline.** Winner mean IoU **0.5537 vs 0.2534 = 2.19×**.
`grass` **0.4084 vs 0.0000** and `squash_petiole` **0.3598 vs 0.0000** — the two
classes the baseline cannot express at all. Three of four approaches beat 0.2534;
the pure shape prior (0.2459) does not.

**The shipped default** (`a3_api.py`, the frozen 42-patch set) scores mean IoU
**0.5425** with grass→squash **17.8 %** — inside the ±0.0197 band, recorded
separately because a shipped artifact should advertise what it produces, not
what its family averages.

### Grass vs. squash — the failure this chunk exists to fix

Row-normalised GT `grass` row, from one saved deal/draw each.

| | → grass | → squash_leaf | → squash_petiole | → straw | GT squash → grass |
|---|---:|---:|---:|---:|---:|
| baseline | — (no grass class) | 53.0 % into the crop **instance** | — | — | — |
| 1. shape prior | 65.7 % | 21.2 % | 0.7 % | 12.4 % | 8.5 % |
| 2. + height | 61.8 % | 22.4 % | 8.5 % | 6.3 % | 7.4 % |
| **3. DINOv2 probe (default)** | **76.3 %** | **9.4 %** | 8.2 % | 4.0 % | 15.2 % |
| 4. SigLIP 2 so400m | 14.2 % | 56.6 % | 28.3 % | 0.4 % | 7.3 % |

**Fixed, not solved.** 53 % → 17.8 %, and 76 % of grass recovered as grass. But
`grass` IoU 0.41 is the winner's weakest plant class, it over-predicts grass
(170 955 px against 106 099 GT), and it pays with 15.2 % of squash called grass.
Approach 4 makes the failure *worse* than the baseline, and the cause is
isolated: descriptive prompts rather than plain class names move SigLIP 2's
grass→squash from 38 % to 85 % while mean IoU only moves 0.4213 → 0.3977.

### Height ablation — what `height_above_soil` contributed on its own

**(a) In the shape prior (approach 2), the reading the brief asks for**

| features | mean IoU | Δ |
|---|---:|---:|
| SHAPE + SIZE (approach 1) | 0.2459 | — |
| **SHAPE + SIZE + HEIGHT (approach 2)** | **0.2846** | **+0.0387** |
| HEIGHT alone | 0.2148 | — |
| COLOUR alone | 0.1986 | — |
| COLOUR + HEIGHT | 0.2093 | +0.0107 over colour |
| SHAPE + SIZE + COLOUR | 0.2817 | — |
| SHAPE + SIZE + COLOUR + HEIGHT | 0.2978 | +0.0161 over shape+colour |
| all hand-crafted (+ native-resolution texture) | 0.3001 | +0.0023 |

**(b) In the winner, the reading that decided the default**

| features | mean IoU |
|---|---:|
| DINOv2 (standardised) | 0.5267 |
| DINOv2 + height + datum reliability | 0.5263 |
| height + datum reliability alone | 0.1536 |

**Height adds −0.0004 to the winner.** The shipped default does not use it.

**(c) A2's height channel scored against A0 labels — the first time it has been**
(A2 used five hand-placed boxes; A0 did not exist yet). Datum σ, straw datum:

| class | A2 hand-placed box | A3 median, all labelled px | p25 … p75 |
|---|---:|---:|---:|
| `straw` | 0 | −0.0 | −0.7 … 1.0 |
| `broadleaf_weed` | 7 | 4.7 | 2.5 … 10.7 |
| `fruit` | 22 | 20.0 | 16.6 … 23.4 |
| `grass` | 52 | 33.1 | 13.6 … 61.0 |
| `squash_petiole` | — | 43.2 | 25.5 … 57.6 |
| `squash_leaf` | 93 | 62.9 | 53.6 … 95.8 |

Height-only separability, `max(AUC, 1−AUC)`: `squash_leaf` vs `straw` **0.974**,
`grass` vs `straw` **0.959**, `broadleaf_weed` vs `straw` 0.885, `grass` vs
`broadleaf_weed` 0.833, **`grass` vs `squash_leaf` 0.736**, **`grass` vs
`squash_petiole` 0.548**.

A2's ordering survives; its margins do not. The hand-placed boxes sit near each
class's p75. Height is a plant-versus-ground separator, not a plant-versus-plant
one, and 0.548 on grass-vs-petiole is 0.048 above a coin toss.

### Approach 4 in detail

| model | headline cell | best cell (selected on GT, disclosed) | encode s/variant |
|---|---:|---|---:|
| SigLIP 2 so400m/14@384 | **0.3977** | 0.4213 (`crop_fill`\|plain\|ensemble) | 103 |
| SigLIP 2 base/16@384 | 0.2443 | 0.2558 (`crop_fill`\|descriptive\|single) | 18 |
| CLIP ViT-L/14 ("before") | 0.3895 | 0.4382 (`crop_fill`\|descriptive\|single) | 20 |

**The model upgrade did not deliver:** 2022-era CLIP-L/14 scores 0.3895 against
SigLIP 2 so400m's 0.3977 on identical crops and prompts, at a fifth of the
compute.

**Prompt ensembling (12 templates vs OVSeg's single `a photo of {name}`), mean
Δ mean-IoU over six (crop variant, vocabulary) cells:** so400m **+0.0091**,
base **+0.0070**, CLIP-L **−0.0045**; per cell −0.049 … +0.045, sign unstable.
The roadmap's expected "few-point gain" is not present.

**Crop-and-fill beat both context-preserving variants for all three models**
(so400m 0.398 / 0.288 / 0.218). The `blend` variant — Alpha-CLIP's idea without
its weights — came last every time.

**Alpha-CLIP could not be run** and the check is recorded
(`chunks/A3/alpha_clip_check.py`, `results/alpha_clip_check.txt`): the code
installs from GitHub, the weights exist on no attributable source (no PyPI, no
official HF repo, Google Drive behind interactive consent, openxlab does not
resolve). SigLIP 2 is the recorded fallback the brief permits.

### Winner sweeps

| probe `C` | 0.01 | 0.1 | **1.0** | 10 | 100 |
|---|---:|---:|---:|---:|---:|
| mean IoU | 0.4863 | 0.5083 | **0.5537** | 0.5499 | 0.5411 |

| labelled patches | 14 | 28 | **42** | 84 | 168 |
|---|---:|---:|---:|---:|---:|
| mean IoU | 0.4219 ±0.0700 | 0.4910 ±0.0298 | **0.5537 ±0.0197** | 0.5834 ±0.0152 | 0.6095 ±0.0069 |
| grass→squash | 36.8 % | 35.0 % | 25.3 % | 23.1 % | 28.0 % |

Fourteen patches — two clicks per class — already beat the baseline by 1.7×.

### Extensions (reported separately; the brief asked for four)

| variant | mean IoU |
|---|---:|
| 3b. DINOv2 features pooled over SAM regions, logreg, blocked CV | 0.5203 ±0.0925 (in-sample 0.9246 = the partition ceiling exactly) |
| 3b. same, random forest / depth-4 tree | 0.3892 ±0.0327 / 0.3159 ±0.0231 |
| 1. shape prior with a random forest | 0.2753 |
| 2. shape + height with a random forest | 0.3264 |
| all hand-crafted features, random forest | 0.3413 |

### Honesty of the splits

* Approaches 1–2: out-of-fold only, 4×4 spatial blocks dealt to 4 folds, mean
  over 5 deals. In-sample for comparison: 0.2940 (a1) and 0.4641 (a2) — the
  overfitting gap is 0.05 and 0.18 respectively.
* Approach 3: 42 patches sampled from GT; their own pixels are 0.07 % of the
  frame. Whole-frame 0.5537, with those pixels excluded from the GT
  **0.5484**. Both reported; 5 independent draws.
* Approach 4: zero-shot, no fit. Headline configuration fixed before scoring;
  best-of-grid disclosed as selected on GT.
* `test_a3.py` — 18 assertions, all pass, including a test that the blocked CV
  cannot learn a block-determined label and a test that A0's partition has a
  ceiling of exactly 1.0.
```

---

## 2. Append to `CONSTANTS.md` → Active

```markdown
| A3 | SAM generator settings (A3 partition) | pps 64, pred_iou 0.82, stability 0.90, min area 25 | (a) | Deliberately different from A0's (48 / 0.80 / 0.88 / 60) so the partition is independent of the one A0's labels were painted on — classifying A0's own regions has a ceiling of exactly 1.0. Finer is better for a region classifier's ceiling: a principle, not a fit to score. | two settings run: 282 masks → 369 regions (ceiling 0.8202); 572 masks → 728 regions (ceiling 0.9246) | B1 re-measures per scene |
| A3 | CV block grid | 4 × 4 blocks dealt to 4 folds | (c) | Regions are spatially contiguous, so a random split leaves a region's own neighbourhood in the training set. Whole blocks are held out. A statement about the leak, not about the scene. | 5 block-to-fold deals; headline spread ±0.018–0.034 mean IoU | — |
| A3 | CV deals / patch draws averaged | 5 | (c) | Every A3 headline is a mean over this many splits, because a single deal moved mean IoU by up to 0.09. | the spread itself is the sweep | — |
| A3 | shape-prior tree depth | 4 | (c) | The roadmap's "shape-prior thresholds, fitted on ground truth, reported with margins". Fixed a priori — a shape prior should be a handful of readable thresholds — not selected on score. | 2/3/4/6/8 → 0.153–0.272 (approach 1), 0.268–0.296 (approach 2) | — |
| A3 | shape-prior min leaf weight | 1 % of training weight | (c) | So no threshold is fitted to a single region. | n/a | — |
| A3 | shape-prior fitted split, `mean_width` | 15.86 px | (c) | A fitted threshold in approach 1 (the losing approach), reported for transparency: **it is a pixel size, so it encodes the camera's distance from the bed** and will not survive a different camera height. Not used by the shipped default. | scale-free feature set (no SIZE group) scores 0.2176 vs 0.2459 with it — worth +0.028 | B1 |
| A3 | shape-prior fitted split, `log_area` | 3.72 (≈ 5 250 px) | (c) | As above — a pixel area, camera-distance dependent. Reported so it is visible rather than buried. Not used by the shipped default. | same sweep as `mean_width` | B1 |
| A3 | DINOv2 fine scale | 3066 × 4088; 14 px patch = 3.5 label px | (a) | A uniform 3.992× of A0's 768×1024 label grid, tiled at DINOv2's own 518 px training size with a 6-patch overlap, averaged. Set by the model's patch size and the label grid — nothing about the scene. A0 found the discriminating evidence (texture, cross-section) does not survive to 768×1024; the label grid caps the labels, not the features. | patch-grid ceiling 0.9201 against the 0.9246 region ceiling | — |
| A3 | DINOv2 coarse scale | 546 × 728 | (a) | The whole frame in one pass, so each patch carries plant-level context alongside the fine feature. | n/a | — |
| A3 | probe regularisation `C` | 1.0 | (c) | scikit-learn's untouched default, which is also the optimum of the sweep, on a curve flat over two decades above it. A read-off, not a tuning. | 0.01 / 0.1 / 1 / 10 / 100 → 0.486 / 0.508 / **0.554** / 0.550 / 0.541 | — |
| A3 | labelled patches for the probe | 42 (6 per class × 7 classes) | (c) | The brief's "a few dozen hand-labelled patches". Sampled from the A0 ground truth as a stand-in for a user's clicks; provenance recorded inside `chunks/A3/seed_patches.json`. Their own pixels are 0.07 % of the frame and every score is also reported with them excluded. | 14 / 28 / 42 / 84 / 168 → 0.422 / 0.491 / **0.554** / 0.583 / 0.609 | B1 re-measures per scene |
| A3 | open-vocab crop pad | 30 % of the bounding box | (c) | Context margin for the two non-OVSeg crop variants. Both lost to the zero-margin `crop_fill` variant for all three models, so the value never decided anything. | `crop_fill` (no pad) beat `crop_context` and `blend` for every model | — |
| A3 | open-vocab min crop | 96 native px | (a) | Below this a crop carries no texture at the encoder's 384 px input. A property of the encoder, not of the garden. | n/a | — |
| A3 | prompt ensemble size | 12 templates | (c) | The roadmap's "averaging over a dozen templates". | single vs ensemble across 6 (crop, vocabulary) cells × 3 models: −0.045 … +0.045; means +0.0091 / +0.0070 / −0.0045 | — |
```

Also worth a one-line edit in the `A2 | datum roughness σ` row's Sweep column, or
a note beside it, though A3 has **not** made it: A3 measured that A2's
hand-placed material ordering holds but its margins are roughly halved against
the full A0 labels (`chunks/A3/results/height_report.json`).

---

## 3. Append to `PROGRESS.md`

Status table: set **A3 → `done`**, Findings → `chunks/A3/FINDINGS.md`, and update
**Next up:** to `A4`.

```markdown
### 005 — 2026-09-01 · A3: plant material segmentation

**Chunk:** A3 — Plant material segmentation

**Done**
- Scored all four briefed approaches against the A0 ground truth on one table
  (`chunks/A3/results/comparison.md`, block in `RESULTS.md`), plus a five-model
  / eleven-feature-set ablation grid and the compute cost of each.
- **Ran SAM again rather than reusing A0's partition.** A0's labels were painted
  region-by-region onto A0's own SAM regions, so classifying those regions has a
  ceiling of *exactly 1.0* with zero boundary error — a test asserts it. A3's
  independent partition (pps 64, 572 masks → 728 regions) has a ceiling of
  0.9246, and every region-based number is on that.
- Shipped `chunks/A3/a3_api.segment_material()` as the default: frozen
  DINOv2-base patch features at two scales + a multinomial logistic probe over
  the 42 frozen patches in `seed_patches.json`. Returns a label map and an
  (uncalibrated) confidence on A0's 768×1024 grid, with provenance attached.
- Scored A2's `height_above_soil` against the A0 labels for the first time
  (`height_report.py`) — the labelled version of the check A2's own FINDINGS
  asked for.
- Recorded, rather than asserted, why approach 4 is SigLIP 2 and not Alpha-CLIP
  (`alpha_clip_check.py`).
- 18 tests, all passing. The load-bearing ones assert that the blocked CV cannot
  learn a block-determined label, and that A0's partition ceiling is 1.0.

**Measured** — see `RESULTS.md`. Headline: winner mean IoU **0.5537 ±0.0197**
against the baseline's **0.2534** (2.19×), with `grass` **0.4084** and
`squash_petiole` **0.3598** against **0.0000** for both. Grass predicted as
squash material **17.8 %** for the shipped default (25.3 % as an approach mean),
against **53.0 %** of grass absorbed into the crop instance for the baseline.
Cost: 4.7 s of DINOv2 features and 40 ms of probe, no SAM, against ~8 min.
Approach 1 (pure shape prior) 0.2459 — the only approach that does *not* beat the
baseline. Approach 2 (+ height) 0.2846. Approach 4 (SigLIP 2 so400m) 0.3977, but
with grass→squash of **84.9 %**, worse than the baseline.

**Decided**
- The winner is the DINOv2 probe, and it is the default.
- **The default does not use `height_above_soil`**, because it was measured to
  add −0.0004 on top of frozen features. A4 still wants the channel — for
  grouping, not classification.
- `soil` is dropped from the predicted label space rather than predicted and
  scored zero: A0 has no soil pixels, so it can be neither learnt nor scored.
- Every headline is a mean over five splits or draws; single splits moved by up
  to 0.09.
- Approach 4 ships SigLIP 2, with Alpha-CLIP recorded as unobtainable rather
  than skipped. The `blend` crop variant tests Alpha-CLIP's idea without its
  weights, and it lost to OVSeg's own crop-and-fill for all three models.

**Surprised us**
- **A0's partition has a ceiling of exactly 1.0**, because the ground truth was
  painted on it. The first A3 run was about to score there. The gap between 1.0
  and the honest 0.9246 is precisely the part of the problem a region framing
  hides from itself.
- **The best approach is also the cheapest by two orders of magnitude** —
  5 seconds and no SAM, against 13 minutes of SAM for every region-based
  approach. The expected trade was the opposite.
- **A0's warning was right, and the answer was to stop labelling at 768×1024,
  not to give up.** Texture and cross-section do not survive that grid — but the
  grid caps the *labels*, not the *features*. Running DINOv2 at 3.5 label px per
  patch is most of the gap between 0.246 and 0.554.
- **Height's contribution to the winner is exactly zero.** A2 hoped the ablation
  "has a real chance of being large". Against the labels A2's ordering holds but
  its margins halve — the hand-placed boxes sit near each class's p75 — and
  grass-vs-petiole separability on height alone is **0.548**, a coin toss.
  Height is worth +0.039 to a shape prior with nothing else and −0.0004 to a
  probe on frozen features.
- **The 2022 CLIP was not the problem.** CLIP ViT-L/14 scores 0.3895 against
  SigLIP 2 so400m's 0.3977 on identical crops and prompts, at a fifth of the
  compute.
- **Prompt ensembling did nothing** (+0.009 / +0.007 / −0.005 across three
  models, sign unstable per cell), against the roadmap's expected few-point gain.
- **Better prose in the prompt made the grass failure five times worse**:
  descriptive class names moved SigLIP 2's grass→squash from 38 % to 85 % while
  mean IoU barely moved. A single aggregate would have called it harmless.
- **Approach 2's grass→squash is worse than approach 1's** (34.5 % vs 22.5 %)
  while its mean IoU is better. Height buys back straw and petiole and pays in
  exactly the confusion this chunk exists to fix.
- **Two clicks per class already beat the baseline**: 14 patches score 0.422.

**Dependencies changed**
- New venv `chunks/A3/.venv` (Python 3.11, torch 2.13.0 + torchvision on MPS,
  transformers 5.16.1, scikit-learn 1.9.0, scipy 1.17.1, numpy 2.4.6, pillow,
  matplotlib). Lock in `chunks/A3/requirements.lock.txt`. `chunks/A1/.venv` and
  `ZeroPlantSeg/.venv` are untouched; SAM still runs from the latter.
- New Hugging Face weights cached: `facebook/dinov2-base` (0.7 GB),
  `google/siglip2-base-patch16-384` (1.4 GB),
  `google/siglip2-so400m-patch14-384` (2.4 GB),
  `openai/clip-vit-large-patch14`. `facebook/dinov3-*` is a **gated** repo and
  returned 403, so DINOv3 was not tested.
- `.gitignore`: add `chunks/A3/preds/*.png`, `chunks/A3/figs/*.png` and
  `chunks/A3/work/` (SAM masks, region maps, cached DINOv2 features — ~100 MB,
  all rebuildable per `chunks/A3/README.md`). Keep `seed_patches.json`,
  `results/*.json`, `results/comparison.md` and the code.

**Next**
- A4 is unblocked. It gets a 5-second material map with no SAM in it, so
  connectivity can be built over the probe's patch grid plus A4's own SAM run.
  Its binding constraint will be `squash_petiole` IoU 0.3598 — the best any A3
  approach reached, and still the weakest plant class — because petioles are
  what tie the plant together.
- A4 should still take A2's height channel: A3's finding is about
  classification, not grouping, and A2's advice to subtract
  `soil_surface_depth` before testing depth continuity stands.
- A7 should note that rewriting prompt prose moved one specific confusion by 5×
  while leaving the aggregate flat. Its two-framing comparison must report the
  confusion that matters, not only the aggregate.
- B1 gets two transfer questions: how many patches the probe needs per new
  scene, and whether approach 1's `mean_width ≤ 15.86 px` split — the one
  genuinely camera-distance-dependent constant A3 produced — moves with camera
  height as predicted.
```

---

## 4. `.gitignore` suggestions

```gitignore
# A3: SAM masks, region maps and cached DINOv2 features (~100 MB).
# Rebuild in ~15 minutes with chunks/A3/README.md.
chunks/A3/work/
chunks/A3/preds/*.png
chunks/A3/figs/*.png
```

`chunks/**/*.npy` and `chunks/**/.venv/` are already covered by the existing
rules. Keep `chunks/A3/seed_patches.json` (the shipped model's training set),
`chunks/A3/results/*.json`, `chunks/A3/results/comparison.md`,
`chunks/A3/results/alpha_clip_check.txt` and `chunks/A3/requirements.lock.txt`
committed.
