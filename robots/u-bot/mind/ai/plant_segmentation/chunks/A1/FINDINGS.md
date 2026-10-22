# Chunk A1 — Real depth and honest geometry

**Sessions:** 2026-09-01 · **Status:** done

## What was built

Everything under `chunks/A1/`. Rebuild instructions in `README.md`.

| File | Role |
|---|---|
| `da3_infer.py` | Runs Depth Anything 3 locally on `plants.jpeg`, saves **float32 `.npy`** depth + confidence + the model's own intrinsics, and writes a `provenance.json` recording model repo, Hub revision, code commit, depth-vs-disparity semantics, preprocessing, the FOV the model assumed, and runtime. Never normalises or clips. |
| `depth_to_cloud.py` | `depth_to_cloud(depth, intrinsics|None, mode)` -> `PointCloud`. Modes `assumed` and `scale_free`. Contains **no default focal length anywhere**; raises `MissingIntrinsicsError` rather than guessing. `save_cloud` refuses to write an artifact without a scale-confidence flag. |
| `test_depth_to_cloud.py` | 21 tests. The load-bearing ones assert the refusals, and that halving `f` is *not* absorbable by a similarity transform. |
| `camera_report.py` | Extracts and audits DA3's internally-estimated FOV across models and processing resolutions; determinism check. |
| `measure_quantisation.py` | Three separate things people call "quantisation", measured separately. Local-planarity noise floor by window size; RANSAC soil-plane threshold sweep; cross-model disagreement. |
| `compare_preview.py` | Forensics on `plants_depth.webp` plus the isolated cost of the 8-bit container. |
| `export_products.py` | Publishes the two depth products and `products/MANIFEST.json`. |
| `results/*.json`, `results/fig_*.png` | Numbers and figures. |
| `products/MANIFEST.json` | **What A1b / A2 / A3 / A4 should read.** |

Environment: a dedicated Python 3.11 venv at `chunks/A1/.venv` (torch 2.13.0,
MPS), separate from `ZeroPlantSeg/.venv` so the pinned torch 2.2.2 /
transformers 4.38.2 there is not disturbed. Upstream DA3 clone at
`chunks/A1/da3-src` (commit `3d835ec1`), unpatched — heavy optional imports are
stubbed in `sys.modules` instead. Full lock in `requirements.lock.txt`.

## What was measured

Scores in `RESULTS.md`; raw output in `chunks/A1/results/*.json`.

### 1. Float depth exists, and it is depth

Depth Anything 3 (**DA3**, ByteDance — the real V3, not V2) runs on Apple
Silicon MPS in 1.6-13 s per image. Four presets across six processing
resolutions were run; 16 rasters on disk, each with provenance.

The output is **depth**, not disparity: `pixel_space_to_camera_space` computes
`K^-1 [u,v,1] * d`, the pinhole z-depth convention, on integer pixel centres.
`depth_to_cloud` uses the identical convention, so our cloud and DA3's differ by
nothing. Inference is **bit-for-bit deterministic** across runs, which is what
lets the noise floor below be called an instrument property rather than jitter.

### 2. The FOV DA3 assumed — the roadmap's "largest unquantified error"

It exists, it is recoverable exactly, and it is **not stable**.

DA3's `CameraDec.fc_fov` regresses `(fov_h, fov_w)` in radians;
`pose_encoding_to_extri_intri` turns them into K with the principal point pinned
to the image centre, zero skew, and no distortion model — the same assumptions
A1b was going to register as category (d), except DA3 made them first, silently.
The presets `da3metric-*` and `da3mono-*` have **no camera head at all** and
predict nothing.

For this one fixed image, DA3's own estimate of the focal length, expressed at
3000x4000:

| process_res | DA3-LARGE f (px) | nested-giant f (px) | fx/fy (nested) |
|---|---|---|---|
| 504 | 4159 | 4453 | 0.991 |
| 700 | 4695 | 4647 | 0.983 |
| 896 | 4176 | 3834 | 0.899 |
| 1120 | 3731 | 3204 | 0.690 |
| 1344 | 3424 | 2939 | 0.543 |
| 1680 | 3527 | 3013 | 0.467 |

Above ~700 px the head returns **fx/fy far from 1** — a non-square-pixel camera,
which no phone produces. It also returns a vertical FOV *smaller* than the
horizontal one for a portrait image, which is geometrically impossible. So the
camera estimate is usable only at `process_res <= 700`, and there it gives
**f = 4159-4695 px at 3000x4000 (mean 4489, spread +/-12%)**, i.e. a ~36-41 mm
equivalent lens.

That is **1.49x A1b's assumed 3005 px** (26 mm-equivalent phone main camera).
One of the two is wrong and this image cannot say which.

### 3. DA3's metric claim is a linear function of its own FOV guess

`utils.alignment.apply_metric_scaling`:

```python
focal_length = (K[0,0] + K[1,1]) / 2
return depth * (focal_length / 300.0)
```

The nested model's "metres" are directly proportional to the focal length it
guessed. Given the +/-12% spread inside the physically-consistent band and the
1.5x drift outside it, the metric output inherits at minimum that error, on top
of everything else. `da3nested-giant-large @ res504` reports 0.85-2.50 m for
this scene, plausible for a standing photo of a garden bed — but plausible is
not measured, and A1 does not use it. **Phase A stays scale-free.**

### 4. Depth quantisation — the (a) instrument constant

Three different quantities get this name. Measured separately, on the primary
raster (`da3nested-giant-large @ res1344`, 1344x1008), in **rdu** (relative
depth units, 1 rdu = median scene depth):

| Quantity | Value | What it means |
|---|---|---|
| **Representation step** (float32 `.npy`) | 5.1e-7 rdu; 1 238 305 distinct values over 1 354 752 pixels (20.2 effective bits) | the container throws nothing away |
| **Depth resolution floor** (Immerkaer, robust MAD) | **4.15e-5 rdu** | smallest pixel-to-pixel step the raster distinguishes; any threshold below this is meaningless |
| Local-planarity p10 by window | win3 2.9e-5 · win5 6.7e-5 · win9 1.29e-4 · win17 2.7e-4 · win33 5.7e-4 rdu | how flat a flat thing comes out, at the scale you look at it |
| Model disagreement (a *different* quantity) | 0.079-0.143 rdu rms after affine alignment | accuracy — three orders of magnitude worse |

The registered constant is `depth_resolution_floor = 4.15e-5 rdu`, category (a).
**It is a resolution, not an accuracy.** The raster is smooth to 4e-5 rdu and
wrong by up to 0.14 rdu; those are different facts, and conflating them would be
exactly the mistake R1 exists to prevent.

The local-planarity number is a *function of window size*, so A2 and A4 must
each read it off at the scale they actually operate on rather than sharing one
"depth noise" scalar. That was not obvious before measuring it.

### 5. What the 8-bit preview cost

`plants_depth.webp` is 1008x1344 — both multiples of the ViT patch size 14, and
exactly what DA3 produces from 3000x4000 at `process_res=1344`. It therefore
sits on the same grid as our primary raster and can be compared pixel for pixel
with no resampling. Forensics: it matches `da3nested-giant-large @ res1344` best
(R^2 = 0.982, Spearman rho = -0.990) and matches **depth**, not disparity — so
it is a linear normalisation of depth, brighter = nearer, with 220 levels
surviving lossy WebP.

| Container | distinct levels | step | adjacent pixels forced equal | median levels per 9x9 window | soil-plane inlier RMS @ 0.012 rdu |
|---|---|---|---|---|---|
| float (as produced) | 1 238 305 (20.2 bits) | 5.1e-7 rdu | 0.005 % | 81 | **0.006316 rdu** |
| same depth -> 8 bit | 256 (8.0 bits) | 4.87e-3 rdu | 74.1 % | 4 | **0.006266 rdu** |
| same depth -> 8 bit + lossy WebP | 220 (7.8 bits) | 4.87e-3 rdu | 77.3 % | 3 | 0.006380 rdu |
| the actual `plants_depth.webp` | 220 (7.8 bits) | 4.46e-3 rdu | 74.9 % | 3 | 0.006335 rdu |

**The one-paragraph finding.** The preview was good enough for exactly one of
the two things Phase A needs depth for, and useless for the other. For fitting a
soil surface (A2) it cost essentially nothing: the plane-fit inlier residual is
0.006316 rdu on float and 0.006335 rdu on the preview, a 0.3 % difference,
because the straw surface's own roughness (~6e-3 rdu) is larger than the 8-bit
step (4.9e-3 rdu) and quantisation noise adds in quadrature — A2 would have
reached the same conclusions from the preview. For grouping by depth
*continuity* (A4) it is fatal: the 8-bit step is **38x the float depth
resolution floor**, it forces **75 % of adjacent pixel pairs to exactly equal
depth**, and it leaves a median of **3 distinct depth levels inside a 9x9
window** against 81 in the float, with 14 % of 9x9 windows completely flat. A4's
entire premise is reading depth differences between neighbouring fragments of
plant material, and three-quarters of those differences do not exist in the
preview. Replacing it was necessary, and the necessity is specific to A4 rather
than general. One caveat on the last table row: the difference between the
actual preview and our float run is *mostly not quantisation* — the
affine-aligned residual is 0.036 rdu, seven times the 8-bit step, because the
preview came from a separate inference run. That is why the isolated
`float -> 8 bit` row exists; it is the honest measurement of the container alone.

## What was decided

1. **Two primary products, not one.** `products/MANIFEST.json` names
   `primary_geometry` (nested-giant @ res 504 — the camera is physically
   consistent there) and `primary_raster` (nested-giant @ res 1344 — 2.8x the
   sampling, resolves petioles, same grid as the preview, but its own camera is
   physically impossible and is replaced by the res-504 camera rescaled). One
   raster cannot be both, and pretending otherwise would smuggle a broken camera
   into A2's plane normals.
2. **`scale_free` still requires a focal length, and says so.** `f` sets the
   *shape* of the reconstruction; a similarity transform cannot absorb it
   (roadmap Known gaps #4 — and there is a test asserting exactly this). What
   `scale_free` avoids is *inventing* one: it uses DA3's own K, labelled
   `model_estimated`, which makes the geometry self-consistent with the depth
   being fed in — the strongest claim available for this image — and then
   divides every coordinate by the median scene depth so the output is in
   relative units. If neither hand intrinsics nor model intrinsics exist, it
   raises. There is no third path and no default camera anywhere in the module.
3. **`assumed` mode refuses `model_estimated` intrinsics.** Laundering DA3's
   guess through the hand-supplied door would let it be presented as metric.
   A1b supplies its own, tagged `assumed`.
4. **Absolute scale stays unresolved**, even though the nested model offers
   metres. Its metres are `depth * f/300` with an `f` we have just shown drifts
   50 %; accepting them would create a metric claim resting on a number nothing
   in the scene can check.
5. **The category (a) constant is the resolution floor, not the accuracy.**
   Registered as such, with the accuracy reported beside it so neither is read
   as the other.

## Constants introduced

| Chunk | Name | Value | Cat | Justification |
|---|---|---|---|---|
| A1 | depth resolution floor | 4.15e-5 rdu | (a) | Robust second-difference (Immerkaer/MAD) estimator on the primary raster. Smallest pixel-to-pixel depth step the float raster distinguishes. Inference is bit-deterministic, so this is instrument, not sampling noise. |
| A1 | local-planarity sigma (win 3/5/9/17/33) | 2.9e-5 / 6.7e-5 / 1.29e-4 / 2.7e-4 / 5.7e-4 rdu | (a) | 10th-percentile RMS residual of a local plane fit at each window size. Scale-dependent by nature — A2 and A4 must each read it at the scale they operate on. |
| A1 | pixel-aspect tolerance for a usable camera | 0.05 | (a) | fx/fy must be within 5 % of 1 for square pixels. A check on the model, not a tuned value. |
| A1 | DA3 model-estimated `f` | 4489 px @ 3000x4000 (range 4159-4695) | (c) | Read out of DA3's own camera head across the resolutions where it is physically consistent. An observation *about the model*, feeding A1b. |
| A1 | rdu normaliser | median valid depth, per raster | (c) | Scene statistic, recorded per product so the transform is reversible. |

Nothing in A1 encodes a belief about how gardens are arranged.

## What surprised us

1. **DA3 estimates a camera, and it is badly resolution-dependent.** The
   roadmap's expectation was "if DA-V3 estimated FOV internally, record it". It
   does — and the number swings from 4695 px to 2939 px for the *same image*
   depending only on the processing resolution, going physically impossible
   (fx/fy = 0.47; vertical FOV below horizontal on a portrait image) above
   ~900 px. The default `process_res=504` happens to sit inside the good band,
   so anyone using the CLI defaults never sees this.
2. **DA3's metric scale is literally `f/300`.** A one-line multiplication makes
   its absolute-depth claim proportional to its own guessed focal length. That
   single line is the strongest possible argument for the roadmap's decision to
   keep Phase A scale-free.
3. **The preview was fine for A2.** The expectation going in was that 8 bits had
   cost us something everywhere. It cost 0.3 % on a soil-plane residual and
   75 % of adjacent-pixel depth distinctions — the harm is entirely concentrated
   in the fine-scale work, and A4 is precisely the chunk that needed the fix.
4. **`da3metric-large` on its own is not metric.** `apply_metric_scaling` lives
   in the *nested* wrapper and needs intrinsics, which the standalone metric
   preset does not predict. Run alone it gives relative depth with a
   metric-sounding name.
5. **Depth "noise" is not one number.** The local-planarity residual grows
   roughly linearly with window size from 3 to 33 px. A single shared
   `depth_noise` constant for A2 and A4 would have been wrong for at least one
   of them.

## Not done / deferred

- **No metric validation.** No fiducial and no known dimension in frame, so
  DA3's metre claim is recorded and not tested. Out of scope by design; C0
  retires it.
- **Camera calibration** — explicitly A1b/C0, untouched here.
- **The FOV disagreement is quantified, not resolved.** A1b's planarity
  refinement now has a concrete job: reconcile A1b's 3005 px prior against DA3's
  ~4489 px. See Implications.
- **`process_res` is a genuine trade-off A1 has not settled.** 504 gives a
  trustworthy camera and a 378x504 raster; 1344 gives 2.8x the detail and a
  broken camera. A1 ships both, flagged; A2/A4 should report which they used.
- **The soil-plane RANSAC in `measure_quantisation.py` is a measurement device,
  not a soil-surface fit.** It fits one global plane to the whole scene purely
  to give the float/preview comparison a common yardstick. A2 does the real job.
- **Only `plants.jpeg`.** Everything here is one image; whether the FOV
  instability is scene-specific or general is a B1 question.

## Implications for the roadmap

- **A1b must widen its `f` sweep.** The planned set is
  `{1502, 2774, 3005, 3236, 6009}` px. DA3's own estimate is 4159-4695 px, which
  falls in the gap between 3236 and 6009 — the sweep as written steps straight
  over the value the depth was actually produced under. Add ~4489 px, ideally
  with 4159 and 4695 as band edges. A1b's note that "the refinement is
  degenerate if DA-V3 internally assumed an FOV: you would recover *their*
  assumption" is confirmed as the live case, and there is now a number to
  compare against.
- **A1b should fix `process_res` before refining, or treat `f` as
  resolution-dependent.** Refining `f` against a depth field produced under a
  different internal `f` is not self-consistent.
- **A2's RANSAC inlier threshold cannot come from a single "A1 depth noise"
  number.** Use `local_planarity_p10` at the patch scale A2 fits over
  (win33 ~ 5.7e-4 rdu), and note the whole-scene dominant plane only stabilises
  around 1e-2 rdu (`results/quantisation.json`, `soil_fit_sensitivity`). The
  straw datum's own roughness (~6e-3 rdu) dominates the instrument floor by two
  orders of magnitude: the limit on A2 is the straw, not the sensor.
- **A4's depth-continuity tolerance has a hard floor of 4.15e-5 rdu** and should
  be read off `local_planarity_p10` at whatever window A4 links across. A4 is
  also the chunk the preview would have destroyed, and is now unblocked.
- **Open question 3 (the scale story) gains evidence.** A monocular model that
  derives metres from its own guessed focal length is not a scale source. Either
  a fiducial or a calibrated camera at known height is required; there is no
  third option hiding inside the depth model.
