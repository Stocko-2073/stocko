# Progress

Status table is the single source of truth for *where we are*.
The log below it is **append-only** — add entries at the bottom, never edit or
tidy earlier ones. The reasoning in old entries is the point.

Statuses: `not started` · `in progress` · `blocked` · `done`

## Status

| Chunk | Title | Depends on | Status | Findings |
|---|---|---|---|---|
| A0 | Ground truth for one image | — | done | `chunks/A0/FINDINGS.md` |
| A1 | Real depth and honest geometry | — | done | `chunks/A1/FINDINGS.md` |
| A1b | Assumed intrinsics, bounded rather than hidden | A1 | done | `chunks/A1b/FINDINGS.md` |
| A2 | Soil surface and height above soil | A1 | done | `chunks/A2/FINDINGS.md` |
| A3 | Plant material segmentation | A0, A2 | done | `chunks/A3/FINDINGS.md` |
| A4 | Grouping by connectivity, not distance | A2, A3 | done | `chunks/A4/FINDINGS.md` |
| A5 | Stem-soil contact points | A2, A4 | done | `chunks/A5/FINDINGS.md` |
| A6 | Keep-out volumes | A4 | done | `chunks/A6/FINDINGS.md` |
| A7 | VLM instance labelling | A4 | done | `chunks/A7/FINDINGS.md` |
| A8 | MCP tool surface and the safety gate | A5, A6, A7 | done | `chunks/A8/FINDINGS.md` |
| B1 | Generalisation beyond one image | A8 + image set | blocked | needs 20–50 photos to protocol |
| B2 | Auto-labelling and a fast model | B1 | blocked | needs B1 |
| C0 | Calibrate the robot camera | robot camera | blocked | needs hardware |
| C1 | Multi-view and active re-observation | C0 + mobile base | blocked | needs hardware |
| C2 | Persistent garden map | C1 | blocked | needs hardware |
| C3 | Actuator selection and precision budget | candidate tools | blocked | needs hardware |
| C4 | Closed-loop targeting and verification | C3 + arm | blocked | needs hardware |

**Next up:** Phase A is complete (A0–A8 all done). B1 is next, blocked on a 20–50 image set to the capture protocol; Phase C blocked on hardware.

---

## Log

### 001 — 2026-08-30 → 2026-09-01 · Baseline trial and roadmap

**Chunk:** none (pre-roadmap exploration)

**Done**
- Ported ZeroPlantSeg to Apple Silicon and ran it end-to-end on `plants.jpeg`.
  Rebuilt on torch 2.2.2 + MPS under Python 3.11; added `zps_device.py` to
  route the hardcoded `.cuda()` calls; cast sample points to float32 in
  segment-anything's `automatic_mask_generator.py` (MPS has no float64).
- Found `ckpt_download.sh` serves the wrong file: its Google Drive link returns
  the full 2.0 GB OVSeg model, not the CLIP checkpoint the code loads.
  Extracted the 446 `clip_adapter.clip_model.*` tensors into the 1.7 GB
  `ovseg_clip_l_9a1909.pth` the code expects — size match confirms it.
- Fixed a latent bug in `get_leaf_root_wls`: `calc_leaf_keypoints` has three
  return shapes and one silently unpacked a single coordinate into two scalars,
  corrupting the clustering.
- Swept DBSCAN `eps` and added `recluster.py` to re-run clustering from cached
  keypoints in seconds.
- Authored `RESEARCH_ROADMAP.md`; scaffolded tracking (this file,
  `CONSTANTS.md`, `RESULTS.md`, `chunks/`, `/goal`).

**Measured** — see `RESULTS.md` for the recorded baseline.

**Decided**
- Do not build on leaf-root distance clustering. The `eps` window is narrow
  (100 isolates the clover, 130 swallows it) and the published configs hard-code
  it per dataset *and* capture date. Group by observed 3D connectivity against a
  measured soil surface instead.
- ZeroPlantSeg's likely long-term role is offline auto-labeller (B2), not
  runtime. Explicit kill decision deferred until A4 lands.
- Adopted rules R1–R4. R1 gained category (d) once it became clear the camera
  for `plants.jpeg` is unavailable and intrinsics must be assumed.

**Surprised us**
- Depth Anything V3 resolves individual petioles as continuous 3D structures
  radiating from the crown. That is what makes connectivity-based grouping (A4)
  plausible at all, and it was the part I was least confident about.
- The photo has no EXIF and came from a third party, so calibration is
  impossible. Absolute scale is unresolvable for this image and Phase A is
  written to be scale-free as a result.

**Next**
- A0: hand-label `plants.jpeg` and ship `eval.py`.

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

### 003 — 2026-09-01 · A0 ground truth and the scoring contract

*(Numbered 003 because A1, run in parallel, landed first as 002.)*

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
- A3 unblocks once A2 lands.
- A5's done-criteria need re-reading against the finding that no contact point in
  this image is observable.

### 004 — 2026-09-01 · A2: soil surface and height above soil

*(Numbered 004 — the bookkeeping draft said 003, but A0's entry landed as 003.)*

**Chunk:** A2

**Done**
- Fitted the datum as a **robust smooth height field**, not a plane: RANSAC
  plane for the initial estimate, then a penalised tensor-product cubic B-spline
  (2nd-difference penalty, Tukey-bisquare IRLS) over ground inliers, iterated
  with the ground band re-derived each round.
- Shipped nine rasters on the A1 depth grid plus `products/A2_MANIFEST.json`:
  `height_above_soil` (along the **local** surface normal), the plane-normal
  variant, `validity_mask`, `coverage_class`, `support_distance_px`,
  `height_sigma`, `ground_inliers`, `soil_surface_depth`,
  `soil_surface_plane_offset`. `a2_api.py` is the loader A3/A4/A5 should import;
  it carries the datum caveat and the `scale_free` flag on every field.
- Extended A1's local-planarity curve from win33 to win129, because A2's fit
  scale is 147 px and reading an (a) constant off the end of someone else's
  table is not reading it at the scale you fit over.
- 18 tests. The load-bearing ones are a synthetic curved garden with known
  heights under a canopy covering most of the frame, and an explicit check that
  a single-plane answer would have failed that same scene.

**Measured** — see `RESULTS.md`.
- Inlier fraction **29.1 %**, inlier residual RMS **6.85e-3 rdu**, against
  1.41e-2 rdu for a single plane over the same inliers — the smooth field halves
  the residual. Datum roughness σ = **5.47e-3 rdu**.
- Coverage: **29.1 % observed, 69.8 % interpolated, 1.1 % extrapolated.**
- The cost of interpolating under canopy, measured by blanking disks: gap-fill
  RMS 1.3σ at zero support rising only to 2.4σ at 240 px. Shipped per-pixel as
  `height_sigma`.
- By-eye check, quantified: straw 0σ, clover 7σ, grass 52σ, squash leaf 93σ —
  the roadmap's ordering, passing by wide margins.
- Fitted on both A1 depth products: heights agree at r = 0.975 and 5 % in raw
  rdu, but the two plane normals differ by **7.6°**.

**Decided**
- **The datum is the straw, and it is stated in the manifest, the loader and
  every figure title** — height above straw, offset from height above soil by an
  unmeasurable straw depth.
- Ground is the **lower envelope**: the datum roughness is estimated from the
  below-surface half of the residual distribution only, which cannot contain
  canopy.
- The plane normal is oriented **toward the camera**, never toward gravity.
  Nothing in A2 knows which way is down or how high the camera is.
- `lam` is cross-validated on hold-outs **shaped like the job** — canopy-sized
  disks. Small-block CV would have picked a surface ten times rougher.
- Validity comes from the measured gap-fill curve, not a chosen number, and is
  published as a lower bound because the curve never crossed the line.

**Surprised us**
- The straw's roughness (5.47e-3 rdu, from the residual distribution) and A1's
  instrument-floor curve read at A2's own fit scale (6.0e-3 rdu at win129) are
  the **same number to 10 %**. Two unrelated estimators, one measurement. At
  this scale "how flat is a flat thing" and "how rough is the straw" stop being
  different questions.
- The RANSAC threshold is safe across a **30× band** and then falls off a cliff:
  at 100× the recovered normal jumps 36° because RANSAC finds the canopy.
- Interpolating the datum under the squash is nearly free — 1.3σ → 2.4σ across
  the whole frame — because this bed has no structure at the scale of its holes.
  That is a property of this bed, not of gardens; B1 tests it.
- 71 % of the frame is canopy and the fit still lands within 1.3σ of held-out
  truth.
- The two A1 depth products agree on heights to 5 % but disagree about which way
  the ground tilts by 7.6°. Ratios survive the product choice; directions do not.
- The fitted datum is **26σ from being a plane**. Assuming level ground would
  have injected a 13σ systematic — larger than the entire "clover just above the
  datum" signal this chunk exists to produce.

**Dependencies changed**
- None. A2 runs entirely inside `chunks/A1/.venv`.

**Next**
- A3 is unblocked (A0 and A2 both done). It should reason in
  `height_in_sigma()` and take `height_sigma` as a weight.
- A4 must **not** reuse A2's tolerance: its continuity threshold is
  `local_planarity_p10` at win3–win9, and it should subtract
  `soil_surface_depth` first so a sloping bed does not split fragments.
- A5 should note that a `lowest_visible_stem_point` here is a point on the
  **straw**; "enters soil" is not observable in this scene at all. That is most
  of an answer to roadmap open question 1.
- A1b gains a second reconciliation target: the 7.6° normal disagreement between
  depth products, measured on the surface its planarity refinement uses.

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

### 007 — 2026-09-01 · A5: stem-soil contact points

**Chunk:** A5

**Done**
- Contact points for every A4 component under **both** policies, with an honest
  three-way status and a reason in words. `split`: 742 components, **472
  observed / 59 extrapolated / 211 occluded**. `merge`: 207 → **164 / 11 / 32**.
  The same code on A0's ten GT instance masks (diagnostic, A4 removed from the
  loop): **8 / 1 / 1**. **Zero components anywhere received a fabricated point.**
- `lowest_visible_point` for 741 of 742 components and
  `lowest_visible_stem_point` for 299 — `null`, never substituted, where a
  component has no `squash_petiole` material (A0/A3 have no other stem class).
- `chunks/A5/a5_api.py` for A8, with `admissible()` enforcing the geometric half
  of R2 in code: `observed` status **and** an observed (not interpolated) datum
  **and** no `leaves_frame` unresolved edge from A4. 378 of 742 pass.
- 25 tests, mostly on a synthetic scene with known geometry, because the
  property under test is a refusal. The load-bearing ones: an isotropic blob is
  refused rather than given an axis; material below the datum is refused;
  raising the (b) placeholder never creates an `observed`; a steeply banked bed
  is handled identically to a level one; no shipped `occluded` component carries
  a point.
- Six figures, all carrying the datum caveat in the title, all read back by eye.

**Measured** — see `RESULTS.md`.
- **Straw**: 45.2 % of the material immediately around the components' lowest
  visible material; the majority material for 39.6 % of `split` components and
  67.6 % of `merge` ones. For **97 of 270** non-observed `split` components
  there is *nothing* in the way — the material just stops.
- **Circularity**: **410 of 472** `observed` contacts (86.9 %) stand on a pixel
  A2 used as a ground inlier. Median non-plant share of the local datum support
  is 0.52.
- **Consistency vs A0's estimated points** (diagnostic, not accuracy — there are
  zero `visible` GT points): contact median **26.4 px** on the GT masks,
  61.4 px under `split`. Two trivial image-space baselines beat it, and collapse
  on the crop (477.9 px vs A5's 142.3 px).
- **Policy disagreement**: 531 vs 175 actionable points. `merge`'s single
  938 k-px component holds 488 `split` components carrying 319 points, and is
  itself `occluded`.
- Sweeps over all five knobs; the (b) placeholder moves 152 components between
  `extrapolated` and `occluded` and **zero** into or out of `observed`.

**Decided**
- **Open Question 1 is resolved: the product target is the lowest visible point
  and its height above the STRAW datum. "Enters soil" is not a claim this stack
  may make from one overhead view of a mulched bed** — A0 sees no stem meet the
  ground, A2 has no soil to fit, and A5 measures the plant disappearing into
  mulch. Revisit after C3, which may moot it: a thermal or laser tool wants the
  growing point, which is above the straw and observable.
- **A8 takes contact points from `split`; A6 keeps `merge` for keep-out
  volumes.** `merge` returns one `occluded` blob for 92 % of the scene.
- **Material more than 3σ below the fitted datum is `occluded`, not a contact.**
  Nothing lies under the ground, so that is the surface disagreeing with the
  material, and R4 says report it rather than snap a point to zero.
- **`confidence` is an ordering, not a probability** (A3's caveat, restated).
  The safety field is `status`, and `admissible()` is the gate.
- The status vocabulary stays the roadmap's. `observed` is misleading for the
  soil question and the fix is the `product_target` field that travels with
  every record, not a private renaming.

**Surprised us**
- **A minimum over a large component finds the tail of the height error, not the
  plant's base.** Only 0.5 % of plant pixels sit more than 3σ below the datum,
  but a minimum over 750 k pixels goes straight to them: the GT squash's lowest
  point is a frame-edge leaf 582 px from its crown. **The bigger the plant, the
  worse the estimator** — the opposite of the usual expectation.
- **"Lowest point of the component" is the wrong concept for a vine.** The right
  object is a skeleton rooted at the crown — the same missing algorithm A4
  arrived at from the opposite direction.
- **`observed` was expected to be the rare status and came out at 63.6 %**,
  because the datum is the straw and plants do reach the straw.
- **86.9 % of those `observed` verdicts stand where A2 and A3 disagree** — a
  pixel A3 calls plant and A2 fitted its ground to.
- **The one (b) constant is structurally unable to open the R2 gate.** That was
  not designed in; it fell out, and it is now a test.
- **Two trivial baselines beat the 3-D method against A0's points**, because
  those points are a 2-D human reading. Both roadmap metrics for this image
  reward the simpler method for reasons unrelated to correctness.

**Next**
- A8 (needs A6 and A7): `segment_garden` / `plan_removals`, gate on
  `a5_api.admissible()`.
- A2 should publish a plant-excluded datum before B1 — it is the difference
  between `observed` meaning something and meaning "A2 and A3 disagreed here".

### 008 — 2026-09-01 · A6: keep-out volumes

**Chunk:** A6 — Keep-out volumes

**Done**
- Built the keep-out volume the roadmap asked for, from the crop's **own
  observed 3-D geometry**: A4's `merge` component 1 → 3-D material → vertical
  extrusion to the A2 straw datum → voxel solid → Euclidean dilation by one
  named clearance. Shipped `products/keepout_squash_merge.npz` (7.9 MB) and
  `a6_api.load_a6()`.
- **`is_inside(point)` with 21 tests**, including the ones the roadmap named:
  points on the vines and petioles rather than only the crown (> 99 % inside),
  and the safety-critical half of the "a radius is wrong" claim — crop material
  lying *outside* an equal-area disk round the crown is > 99 % inside the
  keep-out. Distance comes from a k-d tree over boundary voxel centres, so it is
  exact up to the voxel bracket; the bracket always resolves toward *inside*.
- **Everything happens in a datum-aligned rigid frame** (a rotation of the A1
  camera frame onto A2's plane normal), so no distance is ever rescaled. The
  extrusion is **vertical, never along the camera ray**: this view is 41°
  oblique and ray extrusion builds the plant's occlusion shadow, not the plant.
- **Treated A4's unresolved edges as unseen volume, not empty space**, as A4
  instructed, and split them by what they actually are: the 1 204 `occluded_by`
  links put 170 fragments (36 058 px) into the volume as a separate
  `TIER_UNSEEN`; the 83 `leaves_frame` links cannot become voxels, so the volume
  is flagged `frame_open` and `classify()` returns **UNKNOWN**, never OUTSIDE,
  for a point that projects off the photograph. Nothing is extrapolated (R4).
- Swept the placeholder clearance over two decades (0 … 5e-2 rdu = 0 … 9.14
  datum-σ), plus the occupancy assumption, the unseen halo, the voxel resolution
  and the A4 policy. Five figures, all checked by eye at full size.
- Crop identity taken from **A0 ground truth as an explicit stand-in for A7**
  (which ran in parallel), recorded in the product's own provenance string and
  asserted by a test. Nothing else in A6 knows which component is the crop (R3).

**Measured** — see `RESULTS.md`. Headline: **GT squash covered 99.44 % at zero
clearance and 100.00 % at the placeholder**; **GT weed material shielded 85.1 %
→ 87.2 %**, of which **74.6 points were already inside A4's `merge` component**;
**4 of 9 GT weed contact points are inside the keep-out before any clearance
exists**, 6 of 9 at the placeholder. An equal-area disk round the crown covers
only **76.6 %** of the sprawl and is 23 % empty; the smallest covering disk costs
**2.10×** the area and is 52 % empty. The largest `split` component tops out at
**70.8 %** crop coverage at nine times the placeholder clearance.

**Decided**
- **Build on `merge`, as A4 instructed — and report loudly what it costs.** The
  instruction is vindicated (`split` cannot be rescued by any clearance) and the
  price is that the keep-out shields 85 % of the weed material.
- **The unobserved column between a leaf and the ground is occupied.** R4
  forbids asserting unseen space is empty; R2 makes over-covering the cheap
  error. Shipped as `occupancy="column"`, with `shell` as a diagnostic.
- **`is_inside` is conservative by default and says so**: the voxel bracket and
  `UNKNOWN` both resolve toward *inside*, both switchable so A8 can measure the
  cost of the defaults.
- **The clearance is the only parameter of the shape**, enforced by a test that
  parses every A6 module for spacing-like identifiers and asserts
  `build_keepout` takes exactly three float defaults.
- **The clearance stays in rdu.** A8 must refuse a millimetre `tool_profile`
  rather than convert one.

**Surprised us**
- **The one constant the chunk is built around barely matters, and it is not the
  largest error term.** Two decades of clearance move crop coverage 0.56 points.
  Meanwhile the volume's *floor* is A2's datum, which under this crop is **92.6 %
  interpolated** with a median uncertainty of **1.49 datum-σ against a 1.83-σ
  clearance**. The number C3 was going to supply is the same size as the
  uncertainty already underneath the volume.
- **A keep-out built the way A4 asked for shields 85 % of the weeds at zero
  clearance**, and puts 4 of 9 weed stem points off-limits before any tool
  parameter exists. A4's 83.3 % grass absorption was a score; here it is a robot
  that does not weed. The safety product and the segmentation failure turn out
  to be the same object.
- **The `split` component cannot be rescued by clearance at all.** A4 warned of
  "a volume with 68 holes"; the truth is worse — at 9.1 σ the largest piece still
  misses 29 % of the crop, because a clearance grows a boundary and cannot attach
  a leaf the grouping never found. The strongest argument yet for A4's untried
  skeleton-rooted-at-the-crown.
- **The occupancy assumption doubles the volume and is invisible to every metric
  on this image.** `column` vs `shell`: 2.23× the volume, 0.03 points of crop
  coverage. A0's ground truth is a label map, so it can only probe observed
  surfaces, and observed surfaces are in both. **The most consequential decision
  in the chunk is one this evaluation substrate structurally cannot score.**
- **Ray extrusion instead of vertical extrusion is a factor-of-secant error and
  is the obvious thing to write.** "Walk from the surface to the datum along the
  same ray" was the first implementation; on a 41° oblique view it gives a median
  column of 0.364 rdu against a true height of 0.327 rdu, aimed away from the
  plant, and everything downstream still runs.
- **Rendering the keep-out silhouette by projecting voxel centres was wrong and
  looked right.** One voxel subtends 3–10 px at this camera, so the scatter left
  a lattice of holes: it reported 63.1 % of the frame occluded where ray marching
  says 83.4 %, and the holes read by eye as real gaps over the corner leaves.
  Caught only by opening the figure at full size — a 20-point error in a headline
  number, invisible in the code.

**Dependencies changed**
- **None.** A6 reuses `chunks/A3/.venv` unchanged; `chunks/A6/requirements.lock.txt`
  is a byte-identical package set to `chunks/A4/requirements.lock.txt`. No new
  package, no new weights, no model run of any kind.
- `.gitignore`: see `chunks/A6/BOOKKEEPING.md` §4.

**Next**
- **A8** gets the gate it needs: `classify()` returns OUTSIDE / INSIDE /
  **UNKNOWN** and never a coordinate-bearing opinion from a model, so R2's third
  condition is enforceable in code. Four things it must not get wrong: keep both
  conservative defaults; refuse to print or accept a metre; expect to reject 6 of
  9 GT weeds at the placeholder and report *why*; take the union over keep-plants
  as a `min` over `distance_to_material` rather than rebuilding volumes.
- **A5** should record `distance_to_crop_material_rdu` beside each contact point
  — one call, and it makes A8's rejection report explain itself.
- **A7** should know that the component it will be asked to label contains 83 %
  of the grass and 24 % of the broadleaf weed.
- **A4** — the `merge`/`split` question is now decidable on physical grounds
  rather than on instance F1, and **neither policy is acceptable**: `split`
  cannot be rescued by any clearance, `merge` shields the garden. The gap between
  them is where the skeleton-rooted-at-the-crown idea has to live.
- **A2** — the datum uncertainty under a canopy (1.49 σ, 92.6 % interpolated) is
  now load-bearing, not a diagnostic.
- **A0 / B1** — a label map can only probe observed surfaces, so the occupancy
  assumption is unscorable here. One scene captured from two viewpoints would
  turn the argument into a measurement.
- **C3** — bring a tool clearance *and* a positioning repeatability, *and* C0's
  scale, or the number cannot be used against this volume.

### 009 — 2026-09-01 · A7: VLM instance labelling

**Chunk:** A7 — VLM instance labelling

**Done**

- Built the semantic layer: A4 `merge` components → triage → render → one
  `claude-opus-5` call → schema validation → `{id: {label, confidence,
  rationale}}`. **R3 is enforced in code**, not requested in prose: the schema is
  closed to six keys, geometric key names are rejected, and the free-text fields
  are scanned for coordinate pairs, units and geometry words.
- **Two framings, two prompt variants, 2 repeats each.** Framing A is one call
  per region over a 3-panel stimulus (whole frame marked, marked zoom, and the
  identical zoom with nothing drawn on it). Framing B is one scene description
  with no region numbers anywhere, then one call binding it to all 73 IDs over
  12 full-resolution numbered tiles. The `neutral` and `r2` variants differ in
  exactly one length-matched paragraph, so the ablation measures the asymmetry
  claim and not verbosity.
- **Triage in two tiers, no ID ever dropped.** 78 components below A0's 25 px
  minimum reviewable region, a further 56 below A7's own 75 px call-budget
  floor; both `unsure` by policy in code, both present in every output file. 73
  shown to the model.
- **Isolation.** Every call ran with its cwd inside a scratch arena holding
  nothing but PNGs, because this repo's `CLAUDE.md` names the crop and the weeds
  and spells out R2 and R3. Two tests assert no `CLAUDE.md` is reachable at or
  above the arena.
- Hard-case probes: a context ablation over 36 components at `pad_fraction`
  0.00/0.75/3.00 as the seedling proxy, and 6 synthetic regions over pure straw
  as a confabulation probe. 32 tests, all pass. 511 calls, $41.28.

**Measured** — see `RESULTS.md`. Headline: **framing A wins decisively, and only
on the axis that matters.** At *identical* weed reach (**71.3 %** both),
per-instance classification puts **0.1131 %** of the ground-truth crop under the
tool against framing B's **0.6688 %** — **5.9× less crop at risk for the same
benefit**; under the neutral prompt, 0.5150 % vs 1.4218 % at 73.9 % vs 74.0 %,
**2.8×**. Against the no-VLM baseline (A3's material class voted per component,
the policy A4's Open Question 2 scored) the shipped condition is **14× safer** —
0.1131 % vs **1.5953 %** — at 71.3 % vs 73.9 % weed reached, so **the semantic
layer earns its place on R2 grounds**. Framing B wins on exactly one thing,
stability (flip rate 12.3 % vs 20.5 %). **Zero R3 violations of any kind, hard or
soft, across 584 model-authored labels**, and framing B's binding never broke:
73/73 IDs returned, 0 omitted, 0 hallucinated, in all 4 repeats.

**Decided**

- **Framing A ships**, with the `r2` prompt variant. Framing B stays in the repo
  for its scene description, which is excellent, and not for its ID binding.
- **Two repeats with unanimity required is part of the output contract**, not an
  evaluation convenience — R4 applied to semantics, and measurably worth its
  cost (it removes a third of A/neutral's catastrophic errors for one extra
  call).
- The shipped confidence floor is **0.00**, because the sweep shows the floor is
  a cliff rather than a dial. A8 sets the real value, and not from this image.
- The 75 px call-budget floor is registered as **(d)** and audited empirically,
  not just swept. It is the only constant in A7 that exists for money.
- `keep` is doing double duty for "this is crop" and "there is nothing here to
  cut". The vocabulary is insufficient and A8 must not paper over it.

**Surprised us**

- **The first attempt scored 90 usage-limit notices as `unsure`.** A session
  limit returns exit code 1 with *"You've hit your session limit"* in the
  `result` field; `vlm.call` cached it, the parser rejected it, and the R2
  fallback turned it into `unsure` — correct behaviour for a bad reply, and
  therefore completely silent. The run "completed" with a label distribution
  that was a billing artifact. **A safety default that swallows a transport
  error produces a plausible, safe-looking, entirely fictitious result.** Those
  runs were discarded rather than repaired; transport failure and model
  uncertainty are now separate code paths, with a test.
- **The prompt leaked the answer, in the field designed to detect the leak.**
  The output-schema paragraph illustrated the `mixed` field with "for example
  crop leaf and grass blades together" — handing over the one fact A7 exists to
  test, inside the very field used to measure whether the model noticed it. One
  completed repeat (129 calls, ~$12) was discarded. The headline mixed-component
  finding is from the de-leaked prompt.
- **Framing B's scene description is excellent and it does not help.** Unprimed,
  it named the crop as kabocha-type *Cucurbita maxima* and the weeds as grass,
  purslane, mallow and clover — **matching A0's instance list
  species-for-species** — then predicted its own failure in the
  `hard_to_tell_apart` field ("a narrow grass strap merges into the leaf
  beneath it") and committed exactly that error 12 times. **The semantic
  knowledge was never the bottleneck; binding it to a numbered outline at tile
  resolution was.** That is a rendering budget, not a reasoning budget.
- **All six of framing B's crop mislabels in one repeat are the same error** —
  squash material read as grass, every rationale naming a blade, a strap or
  parallel venation. A4's forwarded hazard arrived exactly as predicted, and as
  a resolution limit rather than a reasoning limit.
- **Accuracy inverts the ranking.** The best accuracy in the table (0.548)
  belongs to the no-VLM baseline that risks 14× more crop; among VLM conditions
  the best accuracy is the worst on crop risk. A3 warned the aggregate hides the
  confusion; here it does not merely hide it, it reverses it.
- **The context ablation moved 42 % of individual labels while moving the
  aggregate by one component.** Per-pad totals alone would have concluded
  "context does not matter"; the per-region agreement says the opposite, and
  per-region is what a robot acts on.
- **The confidence floor is a cliff.** At 0.70 three of four conditions lose all
  weed reach along with all crop risk, because the model uses a ~0.15-wide
  confidence band for every decision it makes. The prompt-side asymmetry and the
  code-side floor turn out to be partly redundant, and stacking them switches
  the system off.
- **The whole weed-reach axis on this image is one component.** 71.3 % of GT
  weed pixels is component 104; the next largest holds 2.2 %. Every statement
  about *benefit* in this chunk rests on a single binary event, and the apparent
  "A/neutral dominates at floor 0.70" result is one component's confidence
  landing 0.02 above a threshold.

**Dependencies changed**

- None. Rendering, scoring and figures reuse `chunks/A3/.venv` unchanged; the
  model calls use the `claude` CLI 2.1.257 already on `PATH`. No new packages,
  no new weights.
- `.gitignore`: see `chunks/A7/BOOKKEEPING.md` §4.

**Next**

- **A8** takes `chunks/A7/results/labels_A_r2_r*.json`, requires unanimity
  across the two repeats, and must not set its confidence floor from this
  chunk's numbers — the floor is a cliff and the weed axis is one component
  wide. Two contract points: a `keep` may mean "nothing here" rather than
  "crop", and `unsure` is 48–70 % of components, so the gate's dominant
  behaviour will be refusal.
- **A8** should treat the `mixed` flag as a hard input: component 1 is flagged
  mixed and holds 83 % of the grass, so a `remove` inside a mixed component
  should be refused outright — the component is not a plant.
- **B1** gets three questions in priority order: (i) does the A-vs-B gap survive
  giving framing B the same resolution? — the clean ablation was not run and the
  rationales say resolution is the operative variable; (ii) a real squash
  seedling beside a weed seedling, because A7 predicts a catastrophic-direction
  failure there and a prediction should be tested rather than assumed; (iii)
  does the prompt-side/code-side redundancy reproduce where the weed axis is not
  one component wide?
- **A0** has no ground truth for "this component contains more than one plant",
  so A7's mixed-flag result is a rate rather than a score. A per-component
  mixture flag is cheap and would make it measurable.

### 010 — 2026-09-01 · A8: MCP tool surface and the safety gate

**Chunk:** A8 — MCP tool surface and the safety gate

**Done**

- **Two MCP tools, callable, with schemas.** `segment_garden(image, depth,
  intrinsics)` returns the soil-surface summary and 207 instances with material
  class, height statistics above the datum, contact point, contact status,
  extrapolation distance, geometry confidence and a keep-out descriptor — and
  **no crop flag**, because nothing in A1–A6 knows which plant is the crop and a
  tool that filled that field in would be laundering A0's ground truth into a
  runtime answer. `plan_removals(labels, tool_profile)` applies R2 in code and
  returns an ordered target list plus a rejection report over a **closed
  twelve-reason vocabulary** (eleven about an instance, one that refuses the
  whole call).
- **Transport: a hand-written JSON-RPC 2.0 stdio server** (`server.py`, standard
  library only — the shared `chunks/A3/.venv` stays unchanged, as A4–A7 each
  promised). **Verified with the official `mcp` 2.1.1 Python client** driving it
  from a separate client-only venv: `initialize` → `tools/list` → four
  `tools/call`s including both refusal paths. `results/mcp_conformance.json`:
  PASS. Two independent implementations have to agree, which using the SDK on
  both ends would not have tested.
- **The end-to-end run goes over the wire.** `run_a8.py` starts the server in a
  subprocess and never imports the tool module, so "callable as an MCP tool" is
  a thing that was done rather than claimed.
- **Nothing short-circuits.** Every gate condition is evaluated for every
  instance and every failure is returned, so a rejection carries the complete
  set of reasons and the keep-out column is populated even when the confidence
  floor has already refused everything.
- 31 tests, 2.4 s. Build 39 s, run 0.5 s, **$0** — A8 calls no model.

**Measured** — see `RESULTS.md`. On `plants.jpeg`: **0 targets at the registered
confidence floor of 0.70; 1 target at the diagnostic floor 0.00** (instance 104,
which holds five of the nine ground-truth weeds, 71.3 % of GT weed pixels); and
**zero ground-truth crop pixels under the tool at every floor in the sweep**.

The headline is an ablation rather than a threshold. Dropping each gate
condition in turn from the floor-0.00 run: **`inside_keepout` is the only
condition whose removal puts crop under the tool** — 477 px, instances 5 and
120, both A7 mislabels — while dropping the semantic half entirely admits
instance 1, the squash itself (414 003 px, 98 % of the crop). **Both halves of
R2 are load-bearing and neither is close to sufficient.**

Funnel: 531 contact candidates → 472 `observed` → 378 arm-admissible (A5's own
`admissible()`, carried not re-derived) → **27 outside every keep-plant's
keep-out** (7.1 %). The keep-out union refuses 93 % of the geometrically usable
targets in the photograph — R2's cost, measured, and the physical consequence of
A4's `merge` policy that A6 predicted.

**Decided**

- **The instance id is the A4 `merge` component id** — the id A7 labelled and
  the id A6's volume is built on — with A5's `split` contact points bound to
  their merge parent. The map is verified to be a *function*: all 742 split
  components lie inside exactly one merge component, purity 1.000, and
  `split_to_merge` raises rather than voting if that ever stops being true.
- **A6's A0-ground-truth crop stand-in is replaced by A7's labels and nothing
  else.** Keep-out volumes are rebuilt for all 207 instances from A6's own
  `build_keepout`, which knows nothing about which component is crop; the
  rebuild reproduces A6's shipped volume to **3.7e-9 rdu** and its `is_inside`
  matches A6's `classify()` on 531/531 points, conservative bracket and
  `UNKNOWN ⇒ inside` included. Neither default was flipped.
- **The union over keep-plants is a `min` over a precomputed 531 × 207 distance
  table**, as A6 instructed — which also puts the geometry on disk *before* the
  labels arrive. R3 in the file layout, not only in the prose.
- **A keep-plant is any instance not unanimously `remove`** (204 of 207): R2
  read literally, and deliberately not a function of the confidence floor.
- **A metric `tool_profile` is refused, not converted.**

**Surprised us**

- **The safety came from the geometry, and the constant this chunk exists to
  introduce contributed nothing.** Crop risk is 0 px at every floor from 0.00 to
  0.90. The floor's entire effect on this image is to move weed reach from
  71.3 % to 0 %.
- **The keep-out volume caught the VLM's single catastrophic error at zero
  clearance, at distance exactly 0.0 rdu** — not near the crop, *inside* it.
  A7's instance 5 is 62 % ground-truth squash leaf and both repeats called it
  `remove`. R2's third condition did not need a tool clearance; it needed the
  crop's shape.
- **A0-tuning the floor was attempted and refused.** The separation is 0.02
  wide against a measured repeat spread of 0.052–0.066. The shipped 0.70 comes
  from A7's confabulation probe instead — the confidence the model expresses
  about regions containing no plant at all.
- **A7's own R3 validator discards 134 of A7's 207 labels**, because A7's
  code-authored triage rationale names a pixel count ("25 px", "75 px"). Safety
  consequence nil — the discarded labels already said `unsure` — but a validator
  that cannot tell a model's prose from its operator's will eventually silence
  the wrong one.
- **Three of the nine ground-truth weeds are inside the squash's own
  component**, so they never reach the keep-out test and are refused as
  `label_not_remove` + `mixed_component`. **A segmentation failure and a safety
  refusal are indistinguishable in the rejection report** — the third A0 gap
  this stack has found, and the reason A0 could use a per-instance "is this a
  legitimate target" flag.
- A pytest assertion on a 500 KB JSON string turned a 2-second suite into a
  400-second one, and the slowness is what exposed the assertion being wrong.

**Dependencies changed**

- `chunks/A3/.venv` is **UNCHANGED**. A8 adds no package to the shared compute
  venv; `uv pip freeze` against it is still byte-identical to
  `chunks/A4/requirements.lock.txt`.
- **New, client-only:** `chunks/A8/.venv-client` holds `mcp==2.1.1` and its 27
  transitive dependencies and **nothing else** — no numpy, no access to the
  products. It exists solely so `mcp_sdk_client.py` can drive the hand-written
  stdio server with the official SDK as an independent conformance check.
  Lock file and the two commands that recreate it:
  `chunks/A8/requirements-client.lock.txt`.
- `.gitignore`: see `chunks/A8/BOOKKEEPING.md` §4.

**Next**

- **B1**, three questions in priority order: (i) **does the geometry keep
  carrying the safety when the crop is not 69 % of the frame?** Every result in
  A8 rests on the keep-out being large; on a sparse bed the semantic layer may
  be all that is left, and it has a measured 1-in-24 catastrophic rate. (ii) Is
  the confidence floor ever a dial rather than a switch — is there a scene where
  the `remove` band is wider than the repeat spread? If not, retire it and put
  R2's asymmetry entirely in the structure. (iii) With more than one weed
  instance, does the target list's *ordering* mean anything? It is A5's geometry
  confidence today, and nothing in this stack can rank which weed matters most.
- **C3** — the clearance moves the A8 target list only at the top of A6's swept
  range, and A6 already found the datum uncertainty under the canopy is the same
  size as the clearance. Bring a clearance *and* a positioning repeatability,
  and note that a thermal or laser tool changes the target from the soil contact
  to the growing point, which is above the straw and observable — that would
  move A8's `no_contact_point` and `contact_not_observed` counts more than any
  constant will.
- **C4** — the rejection report is the interlock's input. Keep
  `inside_keepout` (genuinely unreachable) distinct from `label_not_remove` on a
  `mixed` instance (the segmentation failed) when the loop closes.
- **A4/A5/A8 together** — the crown-rooted skeleton is now asked for from a
  third direction: A4 could not hold the squash together, A5 could not find its
  base, and A8 cannot target three weeds because they are inside it.

### 011 — 2026-09-01 · A1b: assumed intrinsics, bounded rather than hidden

**Chunk:** A1b → done

**Done**
- Ran the roadmap's planarity refinement of `f` as specified — 72 focal lengths
  from 400 to 60 000 px, both A1 depth products (`process_res` fixed per curve
  as A1 required), A2's `ground_inliers` as the soil band, three normalisations,
  bootstrap band — and **found it degenerate**.
- Shipped `calib/plants_assumed.json`: pinhole, no distortion, principal point
  at the image centre, square pixels, **f = 4453 px at 3000×4000**
  (38.5 mm-equivalent), provenance `assumed+refined`, carrying the full
  refinement curve and the sentence `refinement_outcome: DEGENERATE`.
- Re-ran the whole downstream stack at nine focal lengths — the roadmap's five
  widened with `{4159, 4453, 4489, 4695}` per A1's FINDINGS so DA3's own band is
  covered — plus a reference row on A1's actual camera. **10 complete A2 fits,
  20 A4 builds, 20 A5 runs.** Nothing was frozen: A2's RANSAC threshold and
  `lam` and A4's continuity tolerance were re-measured off the image at each `f`,
  as those chunks do per image.
- Answered A2's second question: the 7.6° plane-normal disagreement between A1's
  two depth products, as a function of `f`, three ways (closed form,
  least-squares refit, RANSAC refit).
- Swept the principal point; declared distortion unbounded with the reason
  measured rather than asserted.
- 15 tests. The load-bearing ones assert the algebra, the degeneracy (including
  a test that fails if the refinement ever starts working), and that nothing
  here can present an assumed camera as measured.
- **No new dependency, no new venv.** A2's re-fits ran in `chunks/A1/.venv`,
  A4/A5's in `chunks/A3/.venv`, each in the venv its own chunk shipped with.

**Measured** — see `RESULTS.md`.
- The refinement has **no interior optimum, and cannot have one**: changing `f`
  maps the cloud by the linear map `diag(s, s, 1)`, which preserves planes
  exactly. An exactly planar depth map has residual 1e-16 rdu at *every* focal
  length; a synthetic rough locally-planar surface with a **known** `f` of 1502 /
  3005 / 6009 px returns the grid edge every time.
- **24 of 39 reported quantities are bit-identical across a 4× range of `f`.**
  All three A4 verdicts — squash not one component under `split` and one
  component under `merge`, clover separate, 11.8 % grass absorbed — are identical
  at every focal length, as are 742 components, F1 0.008772, squash IoU 0.4619
  and 1237 unresolved edges. A5 moves by ≤1.3 % on admissibility.
- What *does* move: the **absolute orientation of the ground**, 16.3° → 49.4°
  from the optical axis over the sweep (spread 85 %). A2's residual, datum σ and
  RANSAC threshold move 39.7 % — and their **ratios are flat to four decimals**,
  so that is a change of unit, not of conclusion.
- Reference row reproduces every shipped Phase A number to **0.35 %**.
- Principal point: ±5 % of image width moves the ground normal ≤1.11°.

**Decided**
- **`f` = 4453 px, adopted rather than measured**, because the depth field is
  conditioned on DA3's own estimate and the scene cannot adjudicate between that
  and the roadmap's 26 mm prior (3005 px, 1.48× smaller). It stays category (d);
  `assumed` mode still refuses `model_estimated` intrinsics, and A1b supplies its
  own object rather than laundering DA3's.
- **Report the refinement as failed**, ship the whole curve and both controls,
  and put the failure in the calib file next to the value so they cannot be read
  apart.
- **Hold A2's RANSAC seed fixed across the sweep** (transported by the exact
  closed form), because otherwise the sweep measures A2's seed lottery. Ship the
  free-seed sweep too, as the evidence.
- **No Phase A result needs re-scoring**: A1b's chosen `f` *is* the camera Phase
  A used.
- **Absolute scale stays unresolved.** Nothing in `calib/plants_assumed.json`
  implies otherwise, and a test enforces it.
- A3 declared focal-invariant by inspection — its winner uses no geometry —
  rather than by nine identical rows.

**Surprised us**
- The refinement is degenerate **regardless of DA3**. The roadmap expected to
  recover DA3's assumption instead of truth; in fact there is nothing to
  recover, and the synthetic control proves it with DA3 out of the room.
- A4 is not "nearly" invariant, it is **bit-identical** — because its input,
  `relief = A2 soil depth − A1 depth`, is a difference of two z-depths, and z is
  the one coordinate a focal length does not touch. That can be derived, not
  just observed.
- The biggest thing `f` decides is **how steeply the bed is believed to rake
  away**: 13° at 1502 px, 42° at 6009 px. Not size, not flatness — rake.
- **A2's RANSAC seed is less stable than the entire focal-length assumption.**
  Seeded at 1.2 % inliers, the winning plane jumps ~40° somewhere between
  f = 4159 and 4453 px and the outer loop diverges: squash IoU 0.462 → 0.314,
  A5 admissible targets 381 → 94. A1b went looking for the cost of an unknown
  camera and the most actionable finding is about a different chunk.
- A quantity can move 40 % and mean nothing: A2's residual and its own σ move
  together, and the ratio is flat.

**Next**
- A6 is the one Phase A stage A1b did not re-run and the only one that consumes
  an absolute orientation; it should either be re-run against `work/f3005` and
  `work/f6009` or state that its clearance dominates the 16°–49° tilt spread.
- A2 should fix its seed — cheapest robustness win in the stack.
- Ask whoever took `plants.jpeg` for the unstripped original. It is the only
  thing that would close the 3005-vs-4453 question, and C0 will not.

### 012 — 2026-09-01 → 2026-09-02 · Probe: `plants2.jpeg` through Phase A

**Chunk:** none (pre-B1 probe, n = 1, unscored). B1 stays `blocked`.

A second photo from the same source turned up before the B1 image set did — a
pumpkin vine through a lawn against a lattice fence, no soil or mulch anywhere,
oblique. Ran the Phase A stack on it from a **shadow root**
(`probes/plants2/`), the way A1b's `run_stage.py` re-ran A2/A4/A5: every stage
is the shipped code imported from `chunks/<id>/` with only its input/output
directories substituted, every image-measured constant re-measured. Nothing
written into any Phase A product. Full account in `probes/plants2/FINDINGS.md`.

**Done**
- A1 (5 DA3 runs, manifest with re-measured instrument constants), A2, A3,
  A3's SAM partition, A4 both policies, A5 both policies. A6–A8 not run: they
  need a crop identity, which on `plants.jpeg` came from ground truth (A6) and
  ~$40 of VLM calls (A7).
- A by-eye spot check of the A3 map (15 author-placed boxes; **not** ground
  truth) and one figure per stage.

**Measured** (descriptive; no ground truth, so none of this enters `RESULTS.md`)
- **DA3's camera head gives f = 3112–3672 px here vs 4159–4695 px on
  `plants.jpeg` for the same runs** (nested-giant @504: 3120 vs 4453). JPEG
  fingerprints of the two files are identical, so very likely one phone; if
  so, DA3's `f` is a scene reading and A1b's adopted 4453 px is a per-image
  guess. The nested estimate here sits within 4 % of the roadmap's 26 mm prior.
- Instrument floor 1.35e-4 rdu (3.3× `plants.jpeg`); local planarity p10 at
  win33 3.46e-3 rdu (6.1×). Grass is not straw.
- **A2: 67 % of the frame became the datum** (29 % at home), `lam` fell to 0.01
  (316 at home; grid floor 1e-3), e.d.f. 845 of ≈945, fit scale 40 px. The datum
  is a 40-px low-pass of the depth map following the grass tops and the fence.
  **84 % of A3-plant pixels lie inside the datum's ±3σ band** (12 % at home).
  Wall time 33 min (6 at home; machine was 24 GB into swap).
- A3 probe, unchanged: median confidence 0.246 (0.358 at home; 0.293 on the
  pixels it gets *wrong* at home). Spot boxes 5/15: grass 2/2, pumpkin leaf
  3/4, **orange fruit 0/3**, fence 0/3 (called petiole/leaf), straw 0/1,
  petiole 0/1, ground ivy 0/1.
- A4 `split`: 667 components, **largest = 73 % of plant px** (fence + lawn +
  vine; 83 % of A3-grass inside it); `merge`: 321, largest 92 %. The three big
  leaves standing proud of the lawn do separate correctly.
- A5 `split`: **608 of 667 components "observed" at the datum, 493
  arm-admissible, median confidence 0.86, 0 fabricated** — almost all grass
  meeting grass. Occluded 8 % (28 % at home) — the lattice holes.

**Decided**
- Nothing changes in Phase A. No constant, product or score is touched.
- The failure is **structural, not a constant**: "a surface smoother than the
  plants exists" is in A2's method, every R1 constant was honestly re-measured
  and none is at fault, and a constant sweep would never have found it. B1's
  failure taxonomy needs a column for method assumptions.
- For B1: (i) the capture protocol must include no-soil scenes deliberately;
  (ii) A2 should emit a datum-validity verdict (signals already computed: `lam`
  at grid floor, e.d.f. saturation, ground fraction vs A3 plant fraction) that
  A4/A5 consume, so the R4-honest output on a lawn is "no datum" and A5 emits
  no `observed` points; (iii) the per-image scorecard gets a "datum valid?" row
  above the IoUs; (iv) fruit scored separately from foliage in A3.
- Ask the photo's owner for **one unstripped original** — the A1b question
  (3005 vs 4453 px) is now two data points wide and EXIF would close it.

**Surprised us**
- Every A2 headline metric *improved* on the failure case (more observed, less
  interpolated), and A5's confidence rose as its meaning left. The stack's
  self-reported numbers are worst exactly where they look best.
- A4 `split` produced fewer components here than at home while merging far
  more; component count is not fragmentation.
- SAM 85 min vs 13, A2 33 vs 6: swap pressure from unrelated apps. The shipped
  timings assume memory headroom.

**Next**
- B1 when the image set exists; fold the probe's five points into its brief.
- Delete or keep `probes/plants2/` as the first row of B1's scorecard; its
  bulk arrays are gitignored and rebuild in ~40 min with headroom.
