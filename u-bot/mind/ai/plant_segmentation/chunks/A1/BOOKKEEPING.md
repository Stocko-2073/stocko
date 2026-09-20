# A1 — bookkeeping for the manager to apply

Three blocks, to be appended verbatim (or near enough) to `RESULTS.md`,
`CONSTANTS.md` and `PROGRESS.md`. A1 did **not** edit those files.

One extra note that is not any of the three: **`.gitignore` was edited** — added
`chunks/**/.venv/`, `chunks/A1/da3-src/` and `chunks/A1/depth/*/rgb.png`. The A1
venv is 959 MB, the upstream DA3 clone 48 MB, and the rasters 126 MB; all are
rebuildable from `chunks/A1/README.md`. If A0 also touched `.gitignore`, merge
both hunks.

---

## (1) Append to `RESULTS.md`

```markdown
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
```

---

## (2) Append to `CONSTANTS.md` → Active table

```markdown
| A1 | depth resolution floor | 4.15e-5 rdu | (a) | Robust second-difference (Immerkær/MAD) estimator on `primary_raster` (DA3 nested-giant @ res1344). Smallest pixel-to-pixel depth step the float raster distinguishes. Inference is bit-deterministic, so this is instrument, not sampling jitter. **It is a resolution, not an accuracy** — model disagreement is 0.08–0.14 rdu. | n/a | C0 supersedes with a real sensor |
| A1 | local-planarity σ, win 3 / 5 / 9 / 17 / 33 | 2.9e-5 / 6.7e-5 / 1.29e-4 / 2.7e-4 / 5.7e-4 rdu | (a) | 10th-percentile RMS residual of a local plane fit at each window size, on `primary_raster`. Scale-dependent by nature: A2 and A4 must each read it at the scale they operate on rather than sharing one scalar. | n/a | C0 |
| A1 | pixel-aspect tolerance for a usable camera | 0.05 | (a) | \|fx/fy − 1\| ≤ 0.05, since square pixels imply fx = fy. A check applied to the model's output, not a tuned value. | n/a | — |
| A1 | DA3 model-estimated `f` | 4489 px @ 3000×4000 (range 4159–4695, ±12 %) | (c) | Read out of DA3's own `CameraDec.fc_fov` head across the process_res values where it stays physically consistent (≤ 700). An observation about the model, not about the camera. 1.49× A1b's assumed 3005 px. | resolution sweep: 504/700/896/1120/1344/1680 across two presets — see `chunks/A1/results/camera.json` | A1b reconciles; C0 retires |
| A1 | rdu normaliser | median valid depth of the raster | (c) | Scene statistic used to make Phase A output scale-free. Recorded per product in the cloud sidecar so the transform is reversible. | n/a | — |
```

---

## (3) Append to `PROGRESS.md`

Status table: set the A1 row to

```markdown
| A1 | Real depth and honest geometry | — | done | `chunks/A1/FINDINGS.md` |
```

Log entry (append at the bottom):

```markdown
### 002 — 2026-09-01 · A1: real depth and honest geometry

**Chunk:** A1

**Done**
- Ran **Depth Anything 3** locally (ByteDance `depth-anything-3`, commit
  `3d835ec1`) on Apple Silicon MPS and kept the float output. 16 rasters:
  4 presets × up to 6 `process_res` values, each with a `provenance.json`
  recording Hub revision, code commit, depth-vs-disparity semantics,
  preprocessing, and the FOV the model assumed.
- Shipped `depth_to_cloud(depth, intrinsics|None, mode)` with modes `assumed`
  and `scale_free`, **no default focal length anywhere in the module**, and 21
  tests — the load-bearing ones assert the refusals and that halving `f` is not
  absorbable by a similarity transform. `save_cloud` refuses to write an
  artifact without a scale-confidence flag.
- Published `chunks/A1/products/MANIFEST.json`: two products, because one raster
  cannot be both. `primary_geometry` (res 504, camera physically consistent) and
  `primary_raster` (res 1344, 2.8× sampling, camera **not** usable — replaced by
  the res-504 camera rescaled).

**Measured** — see `RESULTS.md`.
- Depth resolution floor **4.15e-5 rdu**; local-planarity σ from 2.9e-5 (3 px
  window) to 5.7e-4 rdu (33 px). Cross-model disagreement 0.079–0.143 rdu — the
  accuracy, three orders of magnitude above the resolution.
- DA3's own FOV estimate, over `process_res` 504→1680: f swings 4695→2939 px at
  3000×4000 and goes physically impossible (fx/fy 0.99→0.47) above ~900 px.
  In the usable band f = 4489 ± 12 % px, **1.49× A1b's assumed 3005 px**.
- 8-bit preview cost: soil-plane residual 0.006316 → 0.006335 rdu (0.3 %), but
  75 % of adjacent-pixel depth differences flattened to zero and 81 → 3 distinct
  depth levels per 9×9 window.

**Decided**
- Phase A stays **scale-free**, even though the nested model reports metres —
  its metres are `depth × f/300`, i.e. proportional to the focal length it
  guessed, and that guess drifts 50 % with processing resolution.
- `scale_free` still needs a focal length (f changes the *shape*, not just the
  size, of the reconstruction) but never invents one: it uses DA3's own K,
  labelled `model_estimated`, and normalises by the median scene depth. If no
  camera is available from any source it raises. `assumed` mode additionally
  **rejects** `model_estimated` intrinsics so DA3's guess cannot be laundered
  into a metric claim.
- The registered (a) constant is the resolution floor, recorded explicitly as
  *not* an accuracy.

**Surprised us**
- DA3 has a camera head and it is badly resolution-dependent — physically
  impossible above ~900 px, and invisible to anyone using the CLI default of
  504. The roadmap asked us to record any assumed FOV; there is not one number
  to record but a curve.
- DA3's metric scale is literally one line, `depth * f/300`.
- The preview was *fine for A2* (0.3 % on a soil-plane residual) and only fatal
  for A4. The harm was concentrated, not general.
- `da3metric-large` on its own is not metric: `apply_metric_scaling` lives in
  the nested wrapper and needs intrinsics the standalone preset never predicts.
- Depth "noise" is not one number — the local-planarity residual scales with
  window size, so A2 and A4 need different values.

**Dependencies changed**
- New dedicated venv `chunks/A1/.venv` (Python 3.11, torch 2.13.0, torchvision
  0.28.0, numpy 2.4.6, evo, plyfile, pillow_heif, pytest; full lock in
  `chunks/A1/requirements.lock.txt`). Kept separate from `ZeroPlantSeg/.venv`,
  whose torch 2.2.2 / transformers 4.38.2 pins are untouched.
- New upstream clone `chunks/A1/da3-src` (ByteDance-Seed/depth-anything-3,
  `3d835ec1`), **unpatched** — its heavy optional imports (`xformers`, `gsplat`,
  `pycolmap`, `moviepy`, `open3d`, `e3nn`) are stubbed in `sys.modules` by
  `da3_infer.py` instead.
- ~11 GB of DA3 weights in the Hugging Face cache. Revisions recorded per run.
- `.gitignore`: added `chunks/**/.venv/`, `chunks/A1/da3-src/`,
  `chunks/A1/depth/*/rgb.png`.

**Next**
- A1b, with a widened `f` sweep: DA3's 4159–4695 px band falls in the gap
  between the planned 3236 and 6009, so the sweep as written steps over the
  value the depth was actually produced under. Also fix `process_res` before
  refining, or `f` refinement is not self-consistent with the depth it refines
  against.
- A2 should take its RANSAC threshold from `local_planarity_p10` at the patch
  scale it fits over, not from a single depth-noise scalar. Note that the straw
  datum's own roughness (~6e-3 rdu) dominates the instrument floor by two orders
  of magnitude — the limit is the straw, not the sensor.
```
