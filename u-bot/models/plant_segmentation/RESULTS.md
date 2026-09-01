# Results

Scores per chunk, on `plants.jpeg`. This table — not the status flags in
`PROGRESS.md` — is how we know whether anything actually improved.

Append a block per chunk. Always state what you compared against. If something
could not be measured, write "not measured" and why; never leave a blank that
reads as a pass.

---

## Baseline — ZeroPlantSeg, as published

**Config:** `ZeroPlantSeg/configs/squash.yaml`, `eps=100`, `min_samples=2`
**Image:** `plants.jpeg` resized to 768×1024
**Date:** 2026-08-30

Descriptive only. **Not scored against ground truth — A0 does not exist yet.**
Once A0 lands, re-score this baseline and record the numbers here so every
later chunk has something real to beat.

| Quantity | Value |
|---|---|
| Leaf mask candidates (stage 1) | 167 |
| Leaf instances (stage 2) | 127 |
| Plant instances (stage 3) | 5 |
| Squash fragments | **3** (ids 2, 4, 5) — should be 1 |
| Squash coverage | 52.2% of frame |
| Other plants | 2.6% (clover patch, id 3, correctly separated) |
| Grass | absorbed into the squash instance — **failure** |
| Runtime | ~8 min (stage 3 ≈ 2.4 s per leaf mask) |
| Per-class IoU | see "Baseline re-scored against A0" below |
| Instance F1 | see "Baseline re-scored against A0" below |
| Contact-point error | n/a — pipeline does not produce contact points |

**`eps` sensitivity** (from `recluster.py`, cached keypoints):

| eps | Instances | Reading |
|---|---|---|
| 40 | 65 | shattered |
| 60 | 24 | heavily fragmented |
| 80 | 16 | squash core forming |
| **100** | **5** | squash consolidates, clover stays separate |
| 130 | 4 | over-merged, clover absorbed |
| 160+ | 1 | everything one plant |

The 100→130 boundary is where the method fails. Recorded because any
replacement must be stable across a wider band than this.

**Prompt variant** (`configs/squash2.yaml`, `"broad flat leaf,grass blade,soil,dry straw"`):
23 masks → 17 leaf instances → 10 plant instances. Grass cleanly rejected, but
petioles dropped, so the plant fragments worse. Both failure modes trade
against each other — any A3 winner must keep petioles *and* reject grass.

---

## A1 — Real depth and honest geometry

**Model:** Depth Anything 3, `depth-anything/DA3NESTED-GIANT-LARGE-1.1`
(rev `b2359bdf`), code commit `3d835ec1`, torch 2.13.0 on MPS
**Image:** `plants.jpeg` (3000×4000, sha256 `91a45b16…`)
**Date:** 2026-09-01 · **Scale confidence:** `scale_free` — all distances in
**rdu** (relative depth units, 1 rdu = median scene depth). No metric claim.

### Depth products

| Product | Model / res | Raster | Camera usable? |
|---|---|---|---|
| `primary_geometry` | nested-giant @ 504 | 504×378 | **yes** (fx/fy = 0.991) |
| `primary_raster` | nested-giant @ 1344 | 1344×1008 | **no** (fx/fy = 0.543) — use the res-504 camera rescaled |

Float32 `.npy`, z-depth along the optical axis (not disparity, not ray length).
Inference is bit-for-bit deterministic. Manifest: `chunks/A1/products/MANIFEST.json`.

### Depth quantisation (the A2/A4 input)

Measured on `primary_raster`. Three quantities, deliberately kept apart:

| Quantity | Value |
|---|---|
| Representation step, float32 `.npy` | 5.1e-7 rdu · 1 238 305 distinct values / 1 354 752 px · 20.2 effective bits |
| **Depth resolution floor** (Immerkær/MAD) | **4.15e-5 rdu** |
| Local-planarity p10, win 3 / 5 / 9 / 17 / 33 | 2.9e-5 / 6.7e-5 / 1.29e-4 / 2.7e-4 / 5.7e-4 rdu |
| Model *disagreement* (accuracy, not resolution) | 0.079–0.143 rdu rms across DA3 variants after affine alignment |

The floor is a **resolution**, not an accuracy: the raster is smooth to 4e-5 rdu
and wrong by up to 0.14 rdu.

### DA3's internally estimated FOV

`CameraDec.fc_fov` regresses (fov_h, fov_w); K gets the principal point pinned
to the image centre, zero skew, no distortion. `da3metric-*` and `da3mono-*`
have no camera head at all.

| process_res | DA3-LARGE f @3000×4000 | nested-giant f @3000×4000 | fx/fy (nested) | physically consistent |
|---|---|---|---|---|
| 504 | 4159 | 4453 | 0.991 | yes |
| 700 | 4695 | 4647 | 0.983 | yes |
| 896 | 4176 | 3834 | 0.899 | no |
| 1120 | 3731 | 3204 | 0.690 | no |
| 1344 | 3424 | 2939 | 0.543 | no |
| 1680 | 3527 | 3013 | 0.467 | no |

Usable band (`process_res ≤ 700`): **f = 4159–4695 px, mean 4489 px, ±12 %** —
a 36–41 mm equivalent lens, **1.49× A1b's assumed 3005 px**.

DA3's metric depth is `depth × f/300` (`utils.alignment.apply_metric_scaling`),
so its absolute scale is *directly proportional* to that unstable f. Not used.

### The 8-bit preview: what it cost

`plants_depth.webp` (1008×1344) is on the same grid as `primary_raster` and best
matches it (R² = 0.982, Spearman ρ = −0.990), linear in **depth**, brighter =
nearer, 220 surviving levels.

| Container | levels | step (rdu) | adjacent px forced equal | median levels / 9×9 | soil-plane inlier RMS @0.012 rdu |
|---|---|---|---|---|---|
| float (as produced) | 1 238 305 | 5.1e-7 | 0.005 % | 81 | **0.006316** |
| same depth → 8 bit | 256 | 4.87e-3 | 74.1 % | 4 | **0.006266** |
| same depth → 8 bit + lossy WebP | 220 | 4.87e-3 | 77.3 % | 3 | 0.006380 |
| actual `plants_depth.webp` | 220 | 4.46e-3 | 74.9 % | 3 | 0.006335 |

**Verdict.** Good enough for A2, fatal for A4. The soil-plane residual moves by
0.3 % — the straw's own roughness (~6e-3 rdu) already exceeds the 8-bit step, so
A2 would have reached the same answer from the preview. But the 8-bit step is
**38× the float resolution floor**, it flattens **75 % of adjacent-pixel depth
differences to exactly zero**, and it leaves a median of **3 depth levels per
9×9 window** against 81 — and adjacent-pixel depth difference is precisely what
A4 groups on. Caveat: the actual-preview row also contains a separate inference
run (affine-aligned residual 0.036 rdu, 7× the step), which is why the isolated
`float → 8 bit` row is the honest measurement of the container.

### Not scored against ground truth

A0 does not exist yet, and A1 produces no segmentation, so there is no IoU / F1 /
contact-point number here. The comparisons above are all internal (float vs.
preview, model vs. model, resolution vs. resolution) and stand on their own.

---

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

---

## A2 — Soil surface and height above soil

**Input:** A1 `primary_raster` (DA3 nested-giant @ res 1344, 1344×1008) via
`chunks/A1/products/MANIFEST.json`, back-projected with the res-504 camera
rescaled, as that manifest requires. Cross-checked on A1 `primary_geometry`.
**Date:** 2026-09-01 · **Scale confidence:** `scale_free` — all distances in
**rdu**. No metric claim.
**Datum:** the **straw mulch surface**, not bare soil. Every height is offset
from height-above-soil by the straw depth, which one photograph cannot measure.

### Fit quality

| Quantity | Value |
|---|---|
| Ground inlier fraction | **29.1 %** (394 340 / 1 354 752 px) |
| Inlier residual RMS | **6.85e-3 rdu** (MAD 6.21e-3, p95 abs 1.43e-2) |
| Same inliers against a single RANSAC plane | 1.41e-2 rdu |
| **Smooth field vs. plane** | **51 % lower residual** |
| Datum roughness σ (below-surface estimator) | **5.47e-3 rdu** |
| Fitted datum − plane | RMS 1.89e-2 rdu; peak-to-peak 0.143 rdu = **26 σ** |
| Datum tilt away from the plane | median 5.9°, p90 14.3°, max 60.9° |
| Effective d.o.f. / fit scale | 63 / **147 px** |
| Cross-validated `lam` | **316** (canopy-hole hold-out); 31.6 with block CV |

### Coverage — observed vs. interpolated

| Class | Fraction |
|---|---|
| observed (a ground inlier) | **29.1 %** |
| interpolated (within the measured trust distance) | **69.8 %** |
| extrapolated (beyond it) | **1.1 %** |
| valid | 98.9 % |

Support distance to the nearest ground observation: p50 16 px, p90 125 px,
p99 245 px, max 349 px. Occlusion is one connected sheet — 69.2 % of the frame
is a single component with no ground inside it — so it is reported by depth:
47.2 % of the frame is more than 20 px from any ground observation, 19.1 % more
than 80 px, 1.1 % beyond the trust distance in two regions, both touching the
frame edge.

### The cost of interpolating under canopy — measured, not assumed

Ground blanked inside disks of radius 20/40/80/160 px, surface refitted, error
scored on the hidden pixels:

| support distance (px) | 0–5 | 10–20 | 40–60 | 80–120 | 160–240 |
|---|---|---|---|---|---|
| gap-fill RMS (rdu) | 7.0e-3 | 7.5e-3 | 8.2e-3 | 8.9e-3 | 1.33e-2 |
| in datum σ | 1.3 | 1.4 | 1.5 | 1.6 | 2.4 |

It never reached the 3σ ground band inside the radii tested, so the trust
distance is published as **≥ 240 px — a lower bound set by the largest disk
measured**, not a resolved value. Shipped per-pixel as `height_sigma.npy`.

### Sensitivity

| Swept | Range | Effect |
|---|---|---|
| RANSAC threshold | 1×–30× (5.4e-4 → 1.6e-2 rdu) | plane normal moves **< 1°** |
| RANSAC threshold | 100×–300× | normal jumps **36°** — RANSAC finds canopy, not ground |
| Ground band | 2σ–5σ | inlier fraction 22.8–32.4 %; surface moves ≤ 1.0e-2 rdu (1.8σ) |
| Spline basis | 24×32 → 16×21 | surface moves 2.0e-3 rdu (0.36σ) — `lam`, not the basis, decides |
| A1 depth product | res 1344 vs res 504 | heights r = **0.975**, raw-rdu gain 1.048, ground-mask IoU 0.80, but **plane normals differ by 7.6°** |

### By-eye check, quantified (hand-placed boxes, not ground truth)

| material | median height | in datum σ |
|---|---|---|
| straw (the datum) | +0.0001 rdu | **0** |
| low broadleaf weed ("clover") | +0.040 rdu | **7** |
| squash fruit | +0.119 rdu | 22 |
| grass blade | +0.286 rdu | **52** |
| squash leaf | +0.511 rdu | **93** |

The roadmap's acceptance test — clover just above the datum, grass mid-band,
squash canopy high — **passes**, by 7× and 1.8× margins with the straw pinned at
zero. Figures: `chunks/A2/results/fig_height_overlay_primary_raster.png`,
`fig_zooms_primary_raster.png`, `fig_material_boxes.png`.

### Not scored against ground truth

**A0 did not exist while A2 ran** (the two executed in parallel), so there is no
per-class IoU, no instance F1 and no contact-point error in this block, and the
material table above is a hand-placed sample checked by eye — not a labelled
set. Every number here is internal: hold-out against hidden ground, sweep
against sweep, depth product against depth product. Nothing in A2 was compared
against the ZeroPlantSeg baseline, which produces no soil surface to compare
with.

---

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

---

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

---

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

---

## A6 — Keep-out volumes

**Ground truth:** `groundtruth/` (A0), 768×1024 · **Scorer:** A6's own coverage
and shielding measures — `chunks/A0/eval.py` scores *instances*, and a keep-out
volume is not an instance, so there is **no `eval.py` number for this chunk** and
no baseline to beat. The recorded ZeroPlantSeg baseline produces no keep-out
volume at all; the honest comparison is the **`merge` vs `split` policy pair**
below, and a **disk around the crown**, which is what A6 replaces.
**Inputs:** A4 `load_a4(tag="merge")` component 1 (A4's explicit instruction),
A2 straw datum + plane normal, A1 `primary_raster` (1344×1008 float, **never
resampled**)
**Date:** 2026-09-01 · **Scale confidence:** `scale_free`, all lengths in
**rdu**, also reported in **A2 datum-σ** (1 σ = 5.4696e-3 rdu) · **Datum: the
STRAW surface**, not soil
**Findings:** `chunks/A6/FINDINGS.md` · **Loader:** `chunks/A6/a6_api.py`

**Crop identity is A0 ground truth (instance 1, `crop: true`), an explicit
stand-in for A7**, which ran in parallel and was not available. A8 wires the
real path; nothing else in A6 knows which component is the crop (R3).

### The clearance sweep — the one constant, and what it can change

`clearance` is category **(b) tool geometry** and is a **PLACEHOLDER**: the tool
does not exist. Shipped value **1.0e-2 rdu = 1.83 datum-σ**. Retired by C3.

| clearance (rdu) | 0 | 1e-3 | 2e-3 | 5e-3 | **1e-2** | 2e-2 | 5e-2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| in datum-σ | 0 | 0.18 | 0.37 | 0.91 | **1.83** | 3.66 | 9.14 |
| volume (rdu³) | 0.1323 | 0.1323 | 0.1323 | 0.2048 | **0.2395** | 0.2956 | 0.4418 |
| datum footprint (rdu²) | 0.584 | 0.584 | 0.584 | 0.772 | **0.841** | 0.942 | 1.172 |
| **GT squash covered** | **99.44 %** | 99.69 % | 99.80 % | 99.96 % | **100.00 %** | 100 % | 100 % |
| GT squash missed (px of 433 104) | 2 426 | 1 345 | 846 | 152 | **8** | 0 | 0 |
| **GT weed material shielded** | **85.1 %** | 85.4 % | 85.7 % | 86.3 % | **87.2 %** | 89.6 % | 99.0 % |
| · grass | 95.1 % | 95.5 % | 95.7 % | 96.3 % | **97.1 %** | 98.4 % | 100 % |
| · broadleaf weed | 28.3 % | 28.5 % | 28.7 % | 29.2 % | **30.8 %** | 39.6 % | 93.0 % |
| GT straw/soil inside | 37.4 % | 40.8 % | 43.6 % | 50.3 % | **58.9 %** | 71.2 % | 92.5 % |
| whole labelled frame inside | 79.7 % | 80.9 % | 81.8 % | 83.8 % | **86.4 %** | 90.3 % | 97.7 % |
| silhouette (of the photograph) | 83.4 % | — | — | 85.4 % | **87.3 %** | — | 98.5 % |

**Over two decades of clearance, crop coverage moves 0.56 points and weed
shielding moves 14.** The clearance buys almost nothing in the direction R2
cares about and costs everything in the other one. Whatever C3 measures, the
crop is already protected; the real number only decides how much of the bed the
robot refuses to touch.

Below one voxel edge (3.5e-3 rdu) the volume and footprint rows are
resolution-limited and flat; `is_inside` is not (it uses an exact k-d tree
distance), which is why the coverage rows still move at 1e-3 and 2e-3.

### Weed material shielded — where it comes from

| | fraction of all GT weed material |
|---|---:|
| inside the keep-out @ 1e-2 rdu | **87.2 %** |
| …because **A4's `merge` component already contained it** | **74.6 pts** |
| …added by A6 (occupancy assumption + clearance) | **12.5 pts** |
| A4 inheritance, for reference: GT grass in the crop component | 83.5 % |
| A4 inheritance: GT broadleaf weed in the crop component | 24.0 % |

**Three quarters of the shielding is A4's, not A6's.** A4 recorded 83.3 % grass
absorption as a score; A6 turns it into a physical consequence.

### Gate rehearsal — GT weed contact points inside the crop's keep-out

All A0 contact points are `under_straw` / `estimated` (this image has **zero**
`visible` stems), so these are gate rehearsals, not accuracy scores.

| clearance | 0 | 1e-2 (shipped) | 5e-2 |
|---|---:|---:|---:|
| **GT weeds whose contact point is inside** | **4 of 9** | **6 of 9** | **9 of 9** |
| ids inside | 7, 8, 9, 10 | + 4, 5 | + 2, 3, 6 |

Distances from each weed's contact point to the crop material (rdu): id 10 =
0.0000, id 8 = 0.0020, id 7 = 0.0021, id 9 = 0.0022, id 4 = 0.0092, id 5 =
0.0101, id 3 = 0.0195, id 2 = 0.0214, id 6 = 0.0258.

### A radius around the crown is wrong in both directions — measured

Footprint on the datum plane @ 1e-2 rdu vs the best disk centred on A0's crown:

| | value |
|---|---:|
| keep-out footprint area | 0.841 rdu² |
| crown→footprint distance, p50 / p90 / max | 0.394 / 0.598 / 0.903 rdu |
| **equal-area disk** (r = 0.517): covers | **76.6 %** of the sprawl |
| …and 23.4 % of that disk is not plant | |
| **smallest covering disk** (r = 0.903): area | **2.10×** the footprint |
| …and 52.4 % of that disk is not plant | |

### A4 policy — `merge` (A4's instruction) vs the largest `split` component

| | `merge`, id 1 | `split`, id 37 |
|---|---:|---:|
| component size | 938 112 px (69 % of frame) | 383 426 px |
| material volume | 0.1323 rdu³ | 0.0636 rdu³ |
| **GT squash covered @ clearance 0** | **99.4 %** | **60.0 %** |
| **GT squash covered @ 5e-2 rdu (9.1 σ)** | **100 %** | **70.8 %** |
| GT weed shielded @ 1e-2 rdu | 87.2 % | 45.1 % |

**A4's instruction is vindicated, and more strongly than A4 put it.** The
largest `split` component cannot be rescued by *any* clearance in the swept
range: at nine times the placeholder it still misses 29 % of the crop. A
clearance grows a boundary; it cannot attach a leaf the grouping never found.

### Ablations

| ablation | material volume | vol @ 1e-2 | GT squash covered | GT weed shielded |
|---|---:|---:|---:|---:|
| occupancy `column` (shipped) | 0.1323 | 0.2395 | 100.00 % | 87.2 % |
| occupancy `shell` (diagnostic) | 0.0593 | 0.1717 | 99.97 % | 87.0 % |
| `include_unseen=True` (shipped) | 0.1323 | 0.2395 | 100.00 % | 87.2 % |
| `include_unseen=False` | 0.1272 | 0.2337 | 99.76 % | 85.6 % |
| voxel cell 7.0e-3 / 5.0e-3 / **3.5e-3** | 0.1792 / 0.1562 / **0.1323** | 0.2534 / 0.2441 / **0.2395** | 100 / 100 / **100 %** | 88.0 / 87.4 / **87.2 %** |

The occupancy assumption **doubles the volume (2.23×) and moves crop coverage by
0.03 points**: the ground truth is a label map, so it can only probe *observed
surfaces*, which are in both variants. **The most consequential decision in the
chunk is structurally unscorable on this evaluation substrate**, and was
therefore made on R2/R4 grounds, stated, tiered and left switchable.

### Unresolved edges (A4) → unseen volume

| kind, on the crop component | count | treatment |
|---|---:|---|
| `occluded_by` | **1 204** | the 170 fragments behind them (36 058 px, 3.8 % of the crop) enter the volume as `TIER_UNSEEN` |
| `leaves_frame` | **83** (363 380 px, 39 % of the component) | cannot become voxels — the volume is flagged `frame_open` and `classify()` returns **UNKNOWN**, never OUTSIDE, off-frame |

Nothing is extrapolated; no link is resolved (R4).

### Honesty numbers that belong next to the score

* The **floor** of this volume is A2's datum, which under the crop is **5.8 %
  observed, 92.6 % interpolated, 1.6 % extrapolated**, median per-pixel datum σ
  **8.14e-3 rdu = 1.49 datum-σ** — the *same size as the 1.83-σ placeholder
  clearance*. The tool number is not currently the dominant error term.
* `is_inside` is conservative by default (the voxel bracket, ±3.03e-3 rdu,
  resolves toward *inside*; `UNKNOWN` resolves toward *inside*). Exact-bracket
  crop coverage at clearance 0 is 99.10 % against the conservative 99.44 %.

### Runtime

~5 s to build the volume (3.5 GB peak, 351×425×279 = 41.6 M voxels), ~10 µs per
`is_inside` query, ~1 min per ray-marched silhouette. 21 tests in 4 s.

### Contact points

n/a — A6 consumes contact points, it does not produce them. That is A5.

---

## A7 — VLM instance labelling

**Ground truth:** `groundtruth/` (A0) · **Instances:** A4 `merge` components,
`a4_api.load_a4(tag="merge")` — 207 components, of which **73** were shown to
the model · **Model:** `claude-opus-5` via the `claude` CLI 2.1.257,
non-interactive · **Repeats:** 2 per condition, byte-identical prompt ·
**Date:** 2026-09-01 · **Findings:** `chunks/A7/FINDINGS.md` ·
**Default:** framing A, `r2` prompt variant · **Cost:** 511 calls, $41.28.

### The two framings, and the confusion that matters

Majority vote of 2 repeats (with two repeats, "majority" is
unanimous-else-`unsure`). `crop mislab` counts crop-majority components called
`remove`; `crop px at risk` is the same failure in ground-truth crop pixels and
is the threshold-free version. Accuracy is reported last, deliberately.

| condition | crop mislab | **crop px at risk** | weed keeps | **weed px reached** | grass px | unsure | acc | flip |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **A / r2 (default)** | **1/24** | **0.1131 %** | 14/36 | **71.3 %** | 2.9 % | 47.9 % | 0.315 | 20.5 % |
| A / neutral | 4/24 | 0.5150 % | 5/36 | 73.9 % | 8.0 % | 57.5 % | 0.274 | 28.8 % |
| B / r2 | 5/24 | 0.6688 % | 0/36 | 71.3 % | 7.6 % | 69.9 % | 0.233 | 12.3 % |
| B / neutral | 12/24 | 1.4218 % | 0/36 | 74.0 % | 10.5 % | 37.0 % | **0.397** | 28.8 % |
| baseline — A3 material vote per component, no VLM | 18/24 | 1.5953 % | 2/36 | 73.9 % | 12.2 % | 0.0 % | **0.548** | — |
| baseline — all `keep` | 0/24 | 0.0000 % | 36/36 | 0.0 % | 0.0 % | 0.0 % | 0.507 | — |
| baseline — all `remove` | 24/24 | 99.8602 % | 0/36 | 100.0 % | 99.6 % | 0.0 % | 0.493 | — |

Per-repeat spread (min–max), the numbers the majority vote summarises:

| condition | crop mislab | crop px at risk | weed px reached | unsure |
|---|---:|---:|---:|---:|
| A / r2 | 1 – 1 | 0.1131 – 0.1131 % | 71.3 – 71.3 % | 37.0 – 38.4 % |
| A / neutral | 6 – 6 | 0.5880 – 0.6900 % | 73.9 – 73.9 % | 38.4 – 43.8 % |
| B / r2 | 6 – 7 | 0.7320 – 0.8840 % | 71.3 – 71.8 % | 57.5 – 65.8 % |
| B / neutral | 12 – 17 | 1.4220 – 1.6170 % | 74.0 – 74.0 % | 8.2 – 37.0 % |

**Answer: framing A, decisively, on the axis that matters.** At *identical* weed
reach (71.3 % both), per-instance classification puts **5.9×** less crop under
the tool than the global-description framing (0.113 % vs 0.669 %); under the
neutral prompt, **2.8×** (0.515 % vs 1.422 %) at 73.9 % vs 74.0 %. Framing B
wins only on stability (12.3 % vs 20.5 % flip rate).

**Against the no-VLM baseline.** Voting A3's material class per A4 component —
the policy A4's Open Question 2 scored — puts **1.5953 %** of the crop at risk.
A/r2 puts **0.1131 %** there: **14× safer**, at 71.3 % vs 73.9 % weed reached.
The semantic layer earns its place on R2 grounds, not on accuracy.

### Accuracy inverts the ranking — A3's warning, confirmed and worsened

A3 forwarded the finding that rewriting prompt prose moved one specific
confusion 5× while the aggregate stayed flat. Here the aggregate does not stay
flat; it points the wrong way. Stating R2's asymmetry in the prompt halves the
crop at risk in both framings for under 3 points of weed reach — and in framing
B, accuracy **falls 0.164** while doing it. The best accuracy in the whole
table (0.548) belongs to the baseline that risks 14× more crop.

### Why framing B loses: one confusion, six times

All six of B/r2's crop mislabels in one repeat are squash material read as
**grass** — every rationale names a blade, a strap or parallel venation. At tile
resolution a thin squash petiole is not separable from a grass blade. This is
A4's forwarded hazard ("expect the crop component to contain 83 % of the grass")
arriving as a *rendering* limit, not a reasoning one: framing B's own scene
description names the crop and every weed correctly and even predicts this exact
failure before committing it.

### The mixed component, confabulation, and R3

| probe | result |
|---|---|
| Component 1 flagged `mixed` (holds 98 % of GT crop **and 83 % of GT grass**) | framing A **2/2** repeats · framing B **0/4** |
| Null regions — 6 pure-straw regions, prompted identically, 3 repeats | **18/18 `keep`, 0 `remove`, confabulation 0.0 %** |
| Non-plant components called `remove` | A/r2 **0/13** · B/r2 0/13 · A/neutral 2/13 · B/neutral 5/13 |
| R3 violations (coordinates, boxes, measurements, frame-relative prose) | **0 hard, 0 soft, over 584 model-authored labels** |
| Framing B ID binding | **73/73 returned, 0 omitted, 0 hallucinated, 0 rejects**, all 4 repeats |

### The seedling boundary, by context ablation

`plants.jpeg` has no squash seedling, so the boundary is reached by removing the
surround: a squash leaf fragment with its vine cropped out is visually a
broadleaf seedling. 36 hard-set components at `pad_fraction` 0.00 / 0.75 / 3.00.

| pad | keep | remove | unsure | crop → remove |
|---|---:|---:|---:|---:|
| 0.00 — context removed | 23 | 3 | 10 | 1/23 |
| 0.75 — as shipped | 22 | 2 | 12 | 1/23 |
| 3.00 — context restored | 22 | 1 | 13 | 1/23 |

**The aggregate barely moves; 15 of 36 regions (41.7 %) changed label anyway.**
The model is reading the context, not the leaf — so on a real seedling the
honest expectation is failure, in the catastrophic direction.

### The confidence floor is a cliff, not a dial

At a floor of 0.70 every condition reaches zero crop at risk, and three of four
also reach **zero weed reached**. Only A/neutral survives with its benefit
intact — and that rests on one component's confidence landing 0.02 above the
threshold. **71.3 % of all GT weed pixels is component 104 and nothing else**;
the weed axis on this image is a single binary event. Recorded as a limitation,
not as an operating point.

### Contact points

n/a — A7 produces no contact points and no geometry of any kind. That is A5,
and R3 is why A7 cannot produce them.

---

## A8 — MCP tool surface and the safety gate

**Date:** 2026-09-01 · Scale confidence `scale_free`, every length in **rdu**.
Datum: the **straw** mulch surface, not soil. Instances are A4 `merge`
components; contact points are A4 `split` contacts (A5's recommendation) bound
to their merge parent. Labels: A7 framing A / variant r2, both repeats. Tool
profile: A6's `DEFAULT_CLEARANCE_RDU = 1.0e-2` (1.83 datum-σ), a (b)
placeholder awaiting C3. Scored against A0 via `chunks/A8/products/gt_audit.json`.
Everything below was produced through the MCP server, over stdio.

### End-to-end on `plants.jpeg`

| | shipped (floor 0.70) | diagnostic (floor 0.00) |
|---|---:|---:|
| instances | 207 | 207 |
| **targets admitted** | **0** | **1** (instance 104) |
| instances rejected | 207 | 206 |
| **GT crop px under the tool** | **0** / 421 926 | **0** / 421 926 |
| **no GT crop point admitted** | **true** | **true** |
| GT weed px reached | 0.0 % | **71.3 %** |
| GT weed instances reached | 0 / 9 | 5 / 9 |

### Rejections by reason (reasons are NOT exclusive: every condition is
evaluated for every instance and every failure is reported)

| reason | shipped | floor 0.00 |
|---|---:|---:|
| `label_not_remove` | 204 | 204 |
| `component_unlabelled` | 134 | 134 |
| `label_discarded_r3` | 134 | 134 |
| `insufficient_repeats` | 134 | 134 |
| `inside_keepout` | 134 | 134 |
| `confidence_below_floor` | 59 | 0 |
| `no_contact_point` | 29 | 29 |
| `contact_not_arm_admissible` | 23 | 23 |
| `not_unanimous` | 15 | 15 |
| `contact_not_observed` | 11 | 11 |
| `mixed_component` | 4 | 4 |
| `metric_tool_profile_refused` | 0 | 0 (207 when a mm clearance is passed) |

### The funnel

| stage | count |
|---|---:|
| instances | 207 |
| contact candidates with a point (A5 `split`) | 531 |
| ...`observed` | 472 |
| ...arm-admissible (A5's own `admissible()`) | 378 |
| **...outside every keep-plant's keep-out** | **27** (7.1 %) |
| instances with ≥ 1 arm-admissible candidate | 144 |
| ...all candidates inside a keep-out | 134 |
| keep-plants (policy `r2_default_keep`) | 204 / 207 |

### Which condition carries the safety (ablation at floor 0.00)

| gate | targets | GT crop px under the tool | GT weed reached | crop-bearing targets |
|---|---:|---:|---:|---|
| all conditions | 1 | **0** | 71.3 % | — |
| without `label_not_remove` | 3 | 0 | 71.7 % | — |
| without any one other condition | 1 | 0 | 71.3 % | — |
| **without `inside_keepout`** | 3 | **477** | 71.3 % | **5, 120** |
| semantics only (geometry dropped) | 3 | **477** | 71.3 % | 5, 120 |
| geometry only (semantics dropped) | 10 | **414 003** | 97.3 % | **1 (the squash)** |

**Both halves of R2 are load-bearing and neither is sufficient.** The keep-out
test is the only condition whose removal puts crop under the tool; the semantic
layer is the only thing keeping the squash itself off the list.

### Confidence-floor sweep — the cliff, and the fact that it has one side

| floor | 0.00 | 0.50 | 0.55 | 0.58 | 0.60 | 0.62 | 0.65 | **0.70** | 0.90 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| targets | 1 | 1 | 1 | 1 | 1 | 0 | 0 | **0** | 0 |
| GT crop px under the tool | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **0** | 0 |
| GT weed px reached | 71.3 % | 71.3 % | 71.3 % | 71.3 % | 71.3 % | 0 % | 0 % | **0 %** | 0 % |

Crop risk is zero at every floor. A0-tuning was attempted and **refused**: the
separation between the crop mislabel (0.58) and the real weed (0.60–0.62) is
0.02, against A7's measured repeat-to-repeat confidence spread of 0.052–0.066.

### Clearance sweep (A6's (b) placeholder), floor 0.00

| clearance (rdu) | 0 | 1e-3 | 2e-3 | 5e-3 | **1e-2** | 2e-2 | 5e-2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| targets | 1 | 1 | 1 | 1 | **1** | 1 | **0** |
| GT crop px under the tool | 0 | 0 | 0 | 0 | **0** | 0 | 0 |

Keep-plant policy (`r2_default_keep`, 204 keep-plants vs `labelled_keep_only`,
35): identical target list on this image.

### GT weed roll-call (A6 §6's gate rehearsal, run for real)

| GT weeds | instance | floor 0.00 | registered floor |
|---|---:|---|---|
| 2, 3, 4, 5, 6 | 104 | **admitted** (one target covers all five) | `confidence_below_floor` |
| 7 | 178 | `label_not_remove`, `inside_keepout` | + `confidence_below_floor` |
| 8, 9, 10 | 1 | `label_not_remove`, `mixed_component` | same |

Three of the nine weeds are inside the squash's own component and never reach
the keep-out test — a segmentation failure reported as a safety refusal.

### Gate tests (the two the roadmap names, plus the suite)

| test | result |
|---|---|
| a high-confidence (1.0) unanimous `remove` on an instance whose only contacts are `extrapolated` | **rejected** — `contact_not_observed` |
| a high-confidence (1.0) unanimous `remove` on instance 5, whose contact is inside the squash keep-out (distance 0.0 rdu to instance 1) | **rejected** — `inside_keepout` |
| identical labels differing only in persuasive prose | identical verdict |
| one look per instance instead of two | 207/207 `insufficient_repeats`, 0 targets |
| repeats disagree | `not_unanimous`, 0 targets |
| `remove` on a `mixed` instance | `mixed_component`, refused outright |
| label carrying a coordinate ("(412, 806), bbox 40x40") | discarded to `unsure` (A7's validator), cannot open the gate |
| `tool_profile` clearance in mm | whole call refused, `metric_tool_profile_refused` |
| raising the floor | monotone: can only close the gate |
| rebuilt keep-out vs A6's shipped volume | distances agree to 3.7e-9 rdu; `is_inside` matches `classify()` on 531/531 points |
| split→merge map | a function: 742/742, purity 1.000 |
| **31 tests** | **31 passed in 2.4 s** |

### MCP conformance

`server.py` is a hand-written JSON-RPC 2.0 stdio server (standard library
only; the shared `chunks/A3/.venv` is unchanged). Verified by driving it with
the **official** `mcp` 2.1.1 Python client from a separate client-only venv:
`initialize` (protocol 2025-06-18) → `tools/list` (2 tools) → 4 `tools/call`s
including both refusal paths. `results/mcp_conformance.json`: **PASS**.

### Compute

Build products 39 s (~3.5 GB peak, 207 keep-out volumes) · end-to-end run 0.5 s
· tests 2.4 s · **$0** — A8 calls no model.

---

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

---
