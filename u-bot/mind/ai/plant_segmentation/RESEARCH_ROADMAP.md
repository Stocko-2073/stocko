# Weeding Perception — Research Roadmap

Working document for the perception stack behind autonomous garden weeding.
Each chunk below is sized to be picked up on its own. The **Goal** block in each
chunk is written to be pasted straight into `/goal` as an implementer brief.

Target architecture (end state):

1. User says "weed the garden".
2. A VLM reasons over a camera image about what is crop and what is weed.
3. An MCP call segments plants, locates where each stem meets the soil, and
   returns 3D points with an observed / extrapolated / occluded status.
4. An arm with a weeding tool targets each point.

This roadmap works backwards from that, starting with what one photograph can
prove. Chunks that need hardware we do not have are listed with explicit
prerequisites and are **not** ready to start.

---

## Where we are

A trial of [ZeroPlantSeg](https://github.com/JunhaoXing/ZeroPlantSeg)
(arXiv 2509.09116) on `plants.jpeg` established the baseline and its limits.
Full write-up: `ZeroPlantSeg/viz/`, working port with venv in `ZeroPlantSeg/`.

| Result | Finding |
|---|---|
| Squash vs. broadleaf weeds | **Works.** Clover patch correctly split off as its own plant instance. |
| Squash as one plant | **Partial.** Comes out as 3 instances; corner leaves attach off-frame so their roots never reach the crown. |
| Squash vs. grass | **Fails.** Grass blades pass the "green leaf" CLIP filter and get absorbed into the squash. |
| Runtime | ~8 min/image (stage 3 is ~2.4 s per leaf mask). Not viable in-loop. |

Pipeline shape: SAM ViT-H proposes masks → OVSeg CLIP keeps "leaf" masks →
GroundingDINO attention on "stem" estimates a 2D leaf-root point per leaf →
DBSCAN over those points groups leaves into plants.

Why it does not extend: the grouping is **2D distance clustering with a
hard-coded `eps`**. The usable window on this image is narrow — at `eps=100`
the clover is correctly isolated, at `eps=130` it is swallowed by the squash.
The published configs hard-code `eps` per dataset *and capture date*. On a
moving robot that constant would have to track camera height and plant size.

**Conclusion carried into this roadmap:** keep ZeroPlantSeg as a possible
auto-labeler, but do not build the product on leaf-root distance clustering.
Group by *observed connectivity* against a *measured soil surface* instead.

---

## Design rules

These are the standing constraints. Every chunk is reviewed against them.

### R1 — The threshold rule

Every numeric constant in the pipeline must trace to one of:

- **(a) Instrument** — sensor noise, depth quantisation, camera calibration residual.
- **(b) Tool geometry** — kerf, clearance, reach, positioning repeatability.
- **(c) Observation** — something measured in *this* scene, this visit, or a prior visit.
- **(d) Assumed, with a documented sensitivity bound** — a value we cannot yet
  measure, pinned to a stated default and accompanied by a sweep showing which
  conclusions it can and cannot change. Permitted only where (a)–(c) are
  genuinely unavailable.

No constant may encode a belief about how gardens are arranged, how far apart
plants grow, or how large a crop gets. "Plants are ~40 cm apart" is exactly the
kind of constant this rule exists to forbid.

Each chunk records a **Constants** table: name, value, and which category
justifies it. A constant that cannot be assigned a category is a defect. So is a
(d) constant with no sensitivity sweep — the sweep is what separates a bounded
assumption from a hidden bias. Every (d) entry names the chunk that will retire
it.

### R2 — Asymmetric cost

Destroying a crop plant is catastrophic; leaving a weed standing costs almost
nothing. Every decision defaults to **keep**. A removal requires *all* of:

- the VLM classifies the instance as a weed with high confidence, **and**
- the soil contact point was *observed*, not extrapolated, **and**
- the point lies outside the keep-out volume of every keep-plant.

### R3 — Semantics and geometry stay separated

The VLM labels instances by ID. It never emits coordinates. Geometric safety
checks run in code, after labelling, so a VLM misread cannot on its own produce
a physically unsafe motion.

### R4 — Prefer looking again over guessing

When the robot is mobile, low confidence about an occluded point should trigger
re-observation from another pose, not a fabricated estimate. Until then,
occlusion is reported honestly and the target is skipped.

---

## Asset inventory

| Asset | State |
|---|---|
| `plants.jpeg` | 3000×4000 kabocha squash, straw mulch, grass + clover weeds. Third-party photo, **camera not available**, EXIF stripped — no intrinsics, and calibration is impossible. |
| `plants_depth.webp` | Depth Anything V3 output, but an **8-bit normalised preview** (223 levels, brighter = nearer). Not usable for geometry as-is. |
| `ZeroPlantSeg/` | Working port: Python 3.11 venv, torch 2.2.2 + MPS, patched for Apple Silicon. `configs/squash.yaml`, outputs in `output_p/`, figures in `viz/`. |
| `ZeroPlantSeg/recluster.py` | Re-runs clustering from cached keypoints in seconds. Useful for ablations. |

### Known gaps blocking metric claims

1. **No intrinsics, and no way to get them for this image.** The camera belongs
   to someone else and the EXIF is gone. DA-V3's metric head must therefore have
   estimated FOV, so its "metric" output carries unquantified error. Handled in
   A1b by assuming intrinsics and *bounding* the cost, not by pretending.
2. **Absolute scale is unresolved and stays that way.** No fiducial, no known
   dimension. Deriving scale from "a kabocha is about 18 cm" would violate R1,
   so Phase A is written to be scale-free; nothing in it needs absolute units.
   A6 clearance is the first place scale bites, and by then it is the robot's
   own camera.
3. **Depth is a preview, not data.** Need raw float output.
4. **Two distinct unknowns, easily conflated.** Focal length changes the *shape*
   of the reconstruction (how much perspective); scale changes absolute size.
   Assuming a focal length is recoverable-from-scene and cheap to bound;
   assuming a scale is neither.

---

# Phase A — What one image can prove

No hardware required. Ready to start now.

Ordering note: A0 comes first because without ground truth every later chunk
degenerates into eyeballing overlays.

---

## A0 — Ground truth for one image

**Status:** ready · **Depends on:** nothing

### Goal

> Build the evaluation substrate for `plants.jpeg`. Hand-label the image once,
> carefully, and ship a loader plus a scoring function that every later chunk
> reports against. Label three layers: (1) per-pixel material class —
> `squash_leaf`, `squash_petiole`, `grass`, `broadleaf_weed`, `straw`, `soil`,
> `fruit`, `other`; (2) plant instances, with the three squash fragments merged
> into one instance so fragmentation is measurable; (3) stem-soil contact
> points, each tagged `visible`, `under_straw`, or `out_of_frame`. Store labels
> as PNG label maps plus a JSON sidecar for the points. Provide
> `eval.py score(pred, gt)` returning per-class IoU, instance-level
> precision/recall/F1 with a documented matching rule, and contact-point
> distance error in pixels. Labels are the contract — treat schema changes as
> breaking.

### Done when
- Label maps + JSON committed under `groundtruth/`.
- `eval.py` scores a prediction and prints a table; ZeroPlantSeg's current
  output is scored as the recorded baseline.
- Ambiguous regions are explicitly marked `unlabelled` and excluded from scoring.

### Out of scope
- Labelling any other image. One image, done well.

### Constants
| Name | Value | Category |
|---|---|---|
| instance match IoU | 0.5 | (c) convention, documented and swappable |

### Notes
- Expect genuine ambiguity where grass passes behind squash petioles. Mark it
  `unlabelled` rather than guessing; a scoring set with honest holes beats a
  confident wrong one.

---

## A1 — Real depth and honest geometry

**Status:** ready · **Depends on:** nothing

### Goal

> Replace the 8-bit depth preview with raw float depth, and establish what can
> honestly be claimed about scale. Run Depth Anything V3 locally so the float
> output is retained, saved as a `.npy` or 16-bit-plus format alongside a JSON
> recording model version, checkpoint, whether the output is depth or
> disparity, and any FOV the model assumed. Then write a back-projection to a
> point cloud that takes intrinsics as an explicit argument and refuses to
> silently invent them. Since `plants.jpeg` has no EXIF, support two modes:
> `assumed` (intrinsics supplied by hand, flagged in all downstream output) and
> `scale_free` (geometry computed up to an unknown similarity transform, with
> all distances reported in relative units). Quantify how much the 8-bit
> preview cost by comparing the fitted soil surface residual from float vs.
> preview depth.

### Done when
- Float depth for `plants.jpeg` on disk with provenance JSON.
- `depth_to_cloud(depth, intrinsics|None, mode)` returning an Nx3 cloud, and
  raising rather than guessing when `mode="assumed"` with no intrinsics.
- A one-paragraph written finding on whether the preview was good enough.
- Every downstream artifact carries the scale-confidence flag.

### Out of scope
- Camera calibration itself (see A1b).

### Constants
| Name | Value | Category |
|---|---|---|
| depth quantisation | measured from float output | (a) instrument |

### Notes
- If DA-V3 estimated FOV internally, record it. That number is the largest
  unquantified error in the whole stack right now.

---

## A1b — Assumed intrinsics, bounded rather than hidden

**Status:** ready · **Depends on:** A1

### Goal

> The camera that took `plants.jpeg` belongs to someone else and the EXIF is
> stripped, so calibration is impossible and assumed intrinsics are the only
> option. The job is to make that assumption explicit, refined where the scene
> allows, and bounded by a sensitivity sweep — so it is a documented (d)
> constant rather than a hidden bias. Start from a pinhole model: no distortion,
> principal point at the image centre, and `f = 3005 px`, which is a
> 26 mm-equivalent phone main camera at 3000×4000
> (`f_px = f_eq × diag_px / 43.27 mm`; note `f ≈ image width`, a useful sanity
> check). Then refine it with no camera access at all, using scene
> self-consistency: the straw surface is locally planar, so back-project the A1
> float depth across a range of candidate `f` and choose the value minimising
> planarity residual over the soil band. Finally, bound what the assumption can
> cost by running the Phase A stack at `f ∈ {1502, 2774, 3005, 3236, 6009}` px
> (13 / 24 / 26 / 28 / 52 mm-equivalent) and reporting which downstream
> conclusions move and which are invariant. Treat absolute scale as a separate
> unknown and leave it unresolved — do not fake it.

### Done when
- `calib/plants_assumed.json`: model, chosen `f`, provenance `assumed+refined`,
  and the planarity-refinement curve.
- Sensitivity table across the five candidate `f` values, reporting A2 residual,
  A4 instance count and F1, and A5 contact-point error for each.
- A written statement of which Phase A conclusions are focal-invariant. The
  expectation to test: material classification (A3) and connectivity grouping
  (A4) should be nearly invariant, since both are ratio-based; absolute
  distances in A5 and A6 are not.
- Every absolute distance in any output is either omitted or flagged
  `assumed_scale`.

### Out of scope
- Real calibration. That needs a camera we can hold — see C0.
- Recovering absolute scale. Not honestly possible for this image.

### Constants
| Name | Value | Category |
|---|---|---|
| `f` initial | 3005 px | (d) assumed — retired by C0 |
| `f` refined | planarity minimum | (c) observation |
| principal point | image centre | (d) assumed — retired by C0 |
| distortion | zero | (d) assumed; phone ISPs pre-correct most of it |
| absolute scale | **unresolved** | not assigned — deliberately absent |

### Notes
- The refinement is degenerate if DA-V3 internally assumed an FOV: you would
  recover *their* assumption rather than ground truth. That is still worth
  doing. It makes the geometry self-consistent with the depth being fed in, and
  it records the number instead of burying it. A1 already requires logging any
  FOV the model reports — if it does, compare.
- The image looks like a normal main camera, not an ultrawide: the perspective
  in the depth map is moderate. The 13 mm and 52 mm entries in the sweep are
  there as bounds, not as serious candidates.
- Worth one message: if your friend still has the original file, an unstripped
  copy gives focal length and sensor size for free. Ask, but do not block on it.

---

## A2 — Soil surface and height above soil

**Status:** ready · **Depends on:** A1

### Goal

> Fit the soil surface from depth and derive the single most useful channel in
> the stack: height above soil. Gardens are not flat, so fit a robust smooth
> height field rather than a single plane — RANSAC plane as the initial estimate,
> then a robust spline or local-plane refinement over inlier regions, with the
> straw surface treated as the datum since bare soil is largely not visible.
> Emit a `height_above_soil` raster aligned to the image, a per-pixel validity
> mask, and a fit-quality report: inlier fraction, residual RMS, and a coverage
> map showing where the surface is interpolated rather than observed. Nothing
> here may assume the ground is level or that the camera is at a known height —
> the surface is whatever the depth says it is.

### Done when
- `height_above_soil.npy` + validity mask for `plants.jpeg`.
- Fit report with residual RMS and interpolated-coverage fraction.
- A visualisation overlaying height bands on the RGB, checked by eye against
  the known scene: clover just above the datum, grass mid-band, squash canopy
  high.
- Documented behaviour where the surface is fully occluded by canopy.

### Out of scope
- Using height to classify anything. That is A3.

### Constants
| Name | Value | Category |
|---|---|---|
| RANSAC inlier threshold | from A1 depth noise | (a) instrument |
| spline smoothing | chosen by cross-validation on inliers | (c) observation |

### Notes
- The straw mulch is the datum, not soil. Say so explicitly in the output —
  it shifts every height by the straw depth, which matters for the arm later.

---

## A3 — Plant material segmentation

**Status:** ready · **Depends on:** A0, A2

### Goal

> Segment plant *material* into classes, without any instance reasoning.
> Target classes: `broadleaf`, `grass`, `stem_petiole`, `straw`, `soil`,
> `fruit`. Evaluate four approaches against the A0 ground truth and write up
> which wins and why: (1) a geometric shape prior over SAM masks using
> elongation, solidity, and boundary complexity — grass blades are elongated,
> smooth-boundaried and near-constant-width, squash leaves are large, lobed and
> boundary-complex; (2) the same, plus the `height_above_soil` channel from A2
> as an extra feature; (3) a linear or k-NN probe on frozen DINOv2/v3 patch
> features over a few dozen hand-labelled patches; (4) an open-vocabulary
> classifier upgrade — Alpha-CLIP, which takes an alpha channel marking the
> region instead of destroying the surround the way OVSeg's crop-and-fill does,
> or SigLIP 2 in place of the 2022-era mask-tuned CLIP. Report per-class IoU for
> each, and the compute cost of each.

### Done when
- All four scored on the same ground truth, in one table.
- Grass/squash confusion reported specifically — that is the failure this
  chunk exists to fix.
- A recommendation with reasoning, and the winner wired up as the default.
- Ablation showing what `height_above_soil` contributed on its own.

### Out of scope
- Instance separation, plant grouping, contact points.

### Constants
| Name | Value | Category |
|---|---|---|
| shape-prior thresholds | fitted on ground truth, reported with margins | (c) observation |

### Notes
- Baseline to beat: the current prompt trade-off. `"green leaf,soil"` gives 167
  masks with grass contamination; `"broad flat leaf,grass blade,soil,dry straw"`
  rejects grass cleanly but drops to 23 masks, losing the petioles — and the
  petioles are what tie the plant together. Any winner must keep petioles *and*
  reject grass.
- Cheap prerequisite worth trying inside option 4: prompt ensembling. OVSeg uses
  a single `f'a photo of {name}'`; averaging over a dozen templates is a
  known few-point gain and a two-line change.

---

## A4 — Grouping by connectivity, not distance

**Status:** ready · **Depends on:** A2, A3

### Goal

> Replace distance clustering with observed 3D connectivity. Build a graph over
> plant material where nodes are mask fragments and edges assert physical
> contiguity in 3D — adjacent in image space *and* continuous in depth, within
> the depth noise established in A1. Connected components are plants. There must
> be no `eps`-style spacing parameter: the only threshold is whether two pieces
> of material are contiguous, which is an instrument-scale quantity, not an
> agronomic one. Score against A0 instance ground truth and compare directly to
> the ZeroPlantSeg baseline of 5 instances with the squash split into 3. Where
> the graph cannot connect two fragments because the link is occluded, record
> that as an explicit unresolved edge rather than silently splitting or merging.

### Done when
- Components produced with no spacing constant anywhere in the code path.
- Instance F1 against ground truth, alongside the recorded baseline.
- Specifically reported: does the squash come out as one component, and does
  the clover stay separate?
- Unresolved-edge list, with a visualisation of where connectivity was
  ambiguous.

### Out of scope
- Resolving occluded links by moving the camera. That is C1.

### Constants
| Name | Value | Category |
|---|---|---|
| depth-continuity tolerance | from A1 noise | (a) instrument |
| pixel adjacency | 8-connected | (a) instrument |

### Notes
- Petiole tracing is the likely mechanism. The A1 depth resolves individual
  petioles as continuous structures radiating from the crown, which is what
  makes this chunk plausible at all.
- Grass tussocks are clonal — many blades from one base. Merging a tussock into
  one component is correct behaviour for targeting, not a bug.

---

## A5 — Stem-soil contact points

**Status:** ready · **Depends on:** A2, A4

### Goal

> Produce the output the arm actually needs. For each plant component from A4,
> find where its material meets the soil surface from A2, and report it as a 3D
> point with an honest status: `observed` when material is visible down to the
> datum, `extrapolated` when the stem direction was continued to the surface
> across a gap, or `occluded` when no defensible estimate exists. For
> extrapolated points, report the extrapolation distance and derive a confidence
> from it. Handle the case this scene is full of: straw mulch means the true
> stem-soil intersection is frequently unobservable from any angle, so also emit
> a `lowest_visible_stem_point` per component, which may be the more honest
> target for a mechanical tool. Score contact-point error against the A0 points
> tagged `visible`.

### Done when
- Per-component: contact point, status, extrapolation distance, confidence,
  and lowest-visible-stem-point.
- Contact-point error in pixels (and metric, if A1b has landed) for `visible`
  ground-truth points.
- Counts by status across the image, with the straw-occlusion rate called out.
- No component silently receives a fabricated point.

### Constants
| Name | Value | Category |
|---|---|---|
| max extrapolation distance | tool-dependent; placeholder until Phase C | (b) tool geometry |

### Notes
- Decide and record whether the product target is "enters soil" or "lowest
  visible stem". The latter is measurable; the former often is not.

---

## A6 — Keep-out volumes

**Status:** ready · **Depends on:** A4

### Goal

> Define the protected region around crop plants from their own observed
> geometry rather than a radius. Squash sprawls, so a circle around the crown is
> both too large in some directions and too small in others. Take the crop
> component's 3D material from A4, dilate it by a tool-clearance parameter, and
> emit a keep-out volume as a voxel set or mesh, plus a fast
> `is_inside(point)` test. The clearance value is the only constant and must be
> traceable to tool geometry and positioning repeatability, so leave it as a
> named parameter with a documented placeholder until the actuator exists.

### Done when
- Keep-out volume for the squash component, visualised over the RGB.
- `is_inside(point)` with tests, including points near the vines rather than
  only near the crown.
- Clearance is a single named parameter, documented as awaiting Phase C.

### Constants
| Name | Value | Category |
|---|---|---|
| tool clearance | placeholder, named | (b) tool geometry |

---

## A7 — VLM instance labelling

**Status:** ready · **Depends on:** A4

### Goal

> Build the semantic layer, respecting R3: the VLM labels instances by ID and
> never emits coordinates. Given the components from A4, render a crop per
> instance with its context, and ask the model to return `keep`, `remove`, or
> `unsure` per ID with a confidence and a one-line reason. Compare two framings
> and report which is more reliable: per-instance classification, versus one
> global scene description that is then bound back to IDs. Include the failure
> mode that matters — seedlings, where a squash volunteer and a weed look
> nearly identical — by evaluating on deliberately hard crops. Output is a JSON
> mapping instance ID to label, confidence, and rationale, with the prompt and
> model version recorded for reproducibility.

### Done when
- Per-instance labels for `plants.jpeg`, checked against A0.
- Both framings evaluated, with a recommendation.
- Behaviour on ambiguous crops documented: does it say `unsure`, or
  confabulate?
- Prompts and model version committed.

### Out of scope
- Acting on the labels. That is A8.

### Notes
- "Weeds are plants not typically in a vegetable garden" is elegant for mature
  plants and weak on seedlings and crop volunteers. Test that boundary
  explicitly rather than around it.

---

## A8 — MCP tool surface and the safety gate

**Status:** ready · **Depends on:** A5, A6, A7

### Goal

> Expose the stack as two MCP tools with the safety asymmetry of R2 built into
> the structure, not into a prompt. `segment_garden(image, depth, intrinsics)`
> returns the soil surface summary and a list of instances, each with ID, crop,
> material class, height statistics, contact point, contact status,
> extrapolation distance, geometry confidence, and keep-out volume.
> `plan_removals(labels, tool_profile)` takes the VLM's per-ID labels and emits
> an ordered target list, admitting a target only when the label is `remove`
> with high confidence *and* the contact status is `observed` *and* the point is
> outside every keep-plant's keep-out volume. Every rejected target is returned
> with the specific reason it was rejected. No motion is planned or commanded
> here — this ends at a target list.

### Done when
- Both tools implemented and callable, with schemas.
- End-to-end run on `plants.jpeg` producing a target list plus a rejection
  report.
- Tests proving the gate: a high-confidence `remove` with `extrapolated` status
  is rejected; a point inside the squash keep-out volume is rejected.
- The gate is enforced in code, not by instructing the model.

### Constants
| Name | Value | Category |
|---|---|---|
| confidence floor for removal | set high, tuned against A0 | (c) + R2 |

---

# Phase B — Needs more data, no hardware

## B1 — Generalisation beyond one image
**Prerequisite:** 20–50 garden photos to the A1b capture protocol, with depth,
spanning different crops, weeds, lighting, and camera angles.

### Goal
> Re-run the Phase A stack across the image set and report where it breaks.
> Identify which constants from the Phase A Constants tables turn out to be
> scene-specific despite claiming instrument or observation provenance — those
> are the real hidden biases. Produce a per-image scorecard and a written
> failure taxonomy.

## B2 — Auto-labelling and a fast model
**Prerequisite:** B1 complete; a labelling-correction loop.

### Goal
> Use the Phase A stack as an offline auto-labeller to bootstrap a supervised
> dataset, correcting fragmentation by hand where needed, then train a small
> model that runs at frame rate on the robot's compute. Pre-train on public sets
> where useful — PhenoBench, GrowliFlower, SugarBeets2016, CVPPP — and evaluate
> against the A0 ground truth so the numbers stay comparable all the way back.

---

# Phase C — Needs robot hardware

Not ready. Listed so the Phase A interfaces do not paint us into a corner.

## C0 — Calibrate the robot camera

**Prerequisites:** the robot's camera in hand.

### Goal
> Do the calibration properly once the sensor is chosen, and retire every (d)
> constant introduced in A1b. Produce intrinsics, distortion coefficients and
> RMS reprojection error from a printed checkerboard, plus extrinsics for the
> camera's mount on the base. Define the standing capture protocol: EXIF
> preserved, and an ArUco marker of caliper-measured edge length in frame
> whenever absolute scale is needed. Then re-run the A1b sensitivity table with
> the true intrinsics to confirm which Phase A conclusions actually held.

### Constants
| Name | Value | Category |
|---|---|---|
| checkerboard square | measured with calipers | (a) instrument |
| ArUco marker edge | measured from print | (a) instrument |

## C1 — Multi-view and active re-observation
**Prerequisites:** mobile base with repeatable pose; camera extrinsics
calibrated to the base; wheel-encoder odometry good enough for a stereo
baseline.

### Goal
> Turn occlusion from an error term into a control decision. When A5 reports
> `occluded` or a long extrapolation, plan a second viewpoint and re-observe.
> Use the encoder baseline for true stereo as an independent check on
> monocular depth. Fuse observations across poses into one plant model.

## C2 — Persistent garden map
**Prerequisites:** C1; localisation repeatable across visits; timestamped
revisit capability.

### Goal
> Accumulate plants across visits so priors come from observation history
> instead of assumption. A plant present last week that has grown 4 cm is a
> different proposition from one that appeared since the last pass. Under R1
> this is category (c) — the strongest weed signal available, and the only one
> that is pure observation.

## C3 — Actuator selection and precision budget
**Prerequisites:** candidate tools in hand; bench measurement rig.

### Goal
> Choose the weeding tool and measure the precision budget it imposes, then
> feed real numbers back into the placeholder constants in A5 and A6. The budget
> differs by roughly an order of magnitude across options: a mechanical tine
> wants the soil entry point to about a centimetre; thermal or laser wants the
> growing point rather than the soil entry, needing tighter aim but no soil
> contact; targeted spray barely needs depth at all. Perception is currently
> being specified for a tool that has not been chosen.

## C4 — Closed-loop targeting and verification
**Prerequisites:** C3; arm; tool; safety interlocks.

### Goal
> Execute removals and verify them, re-imaging after each action to confirm the
> weed is gone and no keep-plant was touched. Treat a keep-plant contact as a
> hard stop requiring human review.

---

## Open questions

1. **Is "enters soil" the right target at all?** Under straw mulch it is often
   unobservable. `lowest_visible_stem_point` may be both more honest and
   sufficient. Resolve in A5, revisit after C3.
2. **Does instance segmentation earn its place in v1?** Semantic classes plus a
   soil surface plus connected components may be enough for targeting. A4
   should be evaluated against that simpler alternative, not assumed superior.
3. **What is the scale story long-term?** A fiducial in every frame is reliable
   but operationally annoying. Calibrated intrinsics plus a fixed camera mount
   at known height on the robot removes the need for most work — decide before
   the capture protocol hardens in C0. Until then Phase A stays scale-free,
   which is a constraint worth keeping even after scale is available, because it
   forces every conclusion to rest on ratios.
4. **Where does ZeroPlantSeg end up?** Likely an auto-labeller in B2 rather than
   anything in the runtime path. Worth an explicit kill decision once A4 lands.
