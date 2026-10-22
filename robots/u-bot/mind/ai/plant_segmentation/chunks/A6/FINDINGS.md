# Chunk A6 — Keep-out volumes

**Date:** 2026-09-01 · **Scale confidence:** `scale_free`, every length in
**rdu** (1 rdu = median scene depth) and, where it helps, in **A2 datum-σ**
(1 σ = 5.4696e-3 rdu). **Datum: the STRAW mulch surface**, not soil.
**Inputs:** A4 `load_a4(tag="merge")` component 1, A2 straw datum +
`height_above_soil_plane_normal` + RANSAC plane, A1 `primary_raster` float depth
at native 1344×1008 (never resampled), back-projected with A1's
`depth_to_cloud(mode="scale_free")` under the manifest camera.
**Crop identity:** A0 ground-truth instance 1 (`crop: true`), an explicit
**stand-in for A7**, which runs in parallel.

---

## Headline

| | value |
|---|---:|
| **GT squash covered**, clearance 0 / 1e-2 rdu (0 / 1.83 σ) | **99.44 % / 100.00 %** |
| **GT weed material shielded**, same two clearances | **85.1 % / 87.2 %** |
| …of which A4's `merge` component already contained | **74.6 pts of the 87.2** |
| …added by A6's occupancy assumption + clearance | **12.5 pts** |
| **GT straw/soil inside the keep-out** @ 1e-2 rdu | **58.9 %** |
| **Silhouette**, fraction of the photograph the volume occludes @ 1e-2 | **87.3 %** |
| Keep-out volume, material only → @ 1e-2 → @ 5e-2 rdu | 0.1323 → **0.2395** → 0.4418 rdu³ |
| GT weed *contact points* inside the keep-out @ 0 / 1e-2 / 5e-2 | **4 / 6 / 9 of 9** |
| An equal-area disk around the crown covers | **77 %** of the sprawl, and 23 % of it is not plant |
| The smallest disk that *covers* the sprawl costs | **2.10×** the area, 52 % of it not plant |

**The chunk's central result is not the keep-out — it is what the keep-out
reveals about A4's `merge` policy.** The volume does its job: it protects
99.4 % of the crop before a single unit of clearance is added, and it follows
the sprawl rather than a radius, which is measured, not asserted. But built on
the component A4 told A6 to use, it also shields **85 % of the weed material and
puts 4 of the 9 ground-truth weeds' stem points off-limits at zero clearance**.
Under R2 that is the safe direction, and it is also close to "do not weed".

---

## What was built

`A4 merge component → 3-D material → vertical extrusion to the A2 datum →
voxel solid → Euclidean dilation by one named clearance → is_inside`.

### 1. The frame

Everything happens in a **datum-aligned frame**: a rigid rotation of the A1
camera frame whose third axis is A2's RANSAC plane normal, with `w` = height
above that plane. It is a rotation plus a translation along one axis, so every
Euclidean distance is the same distance it was in the reconstruction. Nothing is
rescaled anywhere in A6.

### 2. The occupancy assumption, and why it is the biggest decision in the chunk

The depth is **one view**. Behind a leaf is unobserved. Two readings are
available:

| reading | what it says | verdict |
|---|---|---|
| *empty* | a tool may pass under the canopy | a fabricated claim about space the camera never saw — **R4 forbids it**, and it is unsafe in the catastrophic direction |
| *occupied* | the column between a leaf and the ground beneath it belongs to the plant | over-covers — **R2 says that is the cheap error** |

A6 takes the second. Each observed crop pixel contributes the **vertical**
segment from its own surface down to the A2 datum directly beneath it; the union
over a ground cell is exactly `[floor, ceiling]`, so the solid is a height field
with a floor, which is what makes the whole thing cheap.

**The extrusion is vertical, along the datum normal — never along the camera
ray.** That is not a detail. The view is 41° oblique (A2's fitted plane normal
against the optical axis), so ray extrusion builds the plant's *occlusion
shadow*: the along-ray gap from canopy to datum has a median of **0.364 rdu**
and a p95 of **1.22 rdu**, against a true perpendicular height of 0.327 rdu
median. Extruding along the ray would have inflated the volume by roughly the
secant of the obliquity and pointed it away from the plant.

The cost of the assumption is measured, not assumed: `occupancy="shell"` (the
observed surface voxels only) is shipped as a diagnostic. See §"What was
measured", 3.

### 3. Unresolved edges are volume, not empty space

A4's instruction, followed literally. `unresolved_for(component 1)` returns
**1 287 undecided links** — 1 204 `occluded_by` and 83 `leaves_frame`. They are
handled in two different ways because they are two different problems:

* **`occluded_by`** — the material on the far side is *visible*, it is only its
  *membership* that is undecided. Those 170 fragments (36 058 px, 3.8 % of the
  crop) enter the volume as **`TIER_UNSEEN`**, a separate tier, so the volume can
  be reported with and without them. Including them adds 4.0 % to the material
  volume and takes GT squash coverage from 99.76 % to 100.00 % at the placeholder
  clearance. `test_unresolved_edges_only_ever_add_volume` asserts inclusion can
  only ever protect *more* points.
* **`leaves_frame`** — the material is **outside the photograph**. No amount of
  R2 generosity can turn it into voxels. 83 edges, 363 380 px of the component
  (39 % of it) touch the border. The volume is flagged **`frame_open`**, and
  `classify()` returns **`UNKNOWN`**, never `OUTSIDE`, for a query point that
  projects off the image; `is_inside` resolves `UNKNOWN` to *inside* by R2
  default, switchable. A "not in the keep-out" verdict about a region the camera
  never saw would be exactly the fabrication R4 exists to prevent.

Nothing is extrapolated. No unresolved link is resolved.

### 4. The one constant, and the resolution that is not one

| | |
|---|---|
| `DEFAULT_CLEARANCE_RDU = 1.0e-2` (1.83 datum-σ) | **(b) tool geometry — a PLACEHOLDER awaiting C3.** The only parameter of the shape. Swept over 0 … 5e-2 rdu (0 … 9.14 σ). |
| `DEFAULT_CELL_RDU = 3.5e-3` (0.64 σ) | **(a) resolution ceiling / compute budget, not a threshold** — the same category as A2's spline basis. Swept 7e-3 / 5e-3 / 3.5e-3. |

`test_a6.py` enforces the discipline A4 established: no identifier in any A6
module may be `eps`, `radius`, `spacing`, `max_gap`, `cm`, `mm`, … ; every
module-level numeric constant must appear in `ALLOWED_CONSTANTS` with its R1
category; and `build_keepout`'s signature is asserted to take **exactly three
float defaults** — `clearance`, `max_clearance` and `cell` — so a fourth length
cannot be added without the test noticing. (A4's word `eps` was avoided
deliberately: A6's voxel bracket is called `voxel_bracket`.)

### 5. `is_inside`, and why it is conservative by default

The solid is voxelised, so the test brackets rather than pretends:

    d - voxel_bracket  <=  dist(q, true solid)  <=  d

where `d` is the exact Euclidean distance from `q` to the nearest occupied
*boundary* voxel centre (a k-d tree, so `d` itself is not quantised — only the
solid is) and `voxel_bracket = cell·√3/2 = 3.03e-3 rdu`. The shipped test uses
the **lower** bracket, which can only over-cover. `conservative=False` gives the
other end; both are reported at every clearance and the gap is small everywhere
it matters (GT squash coverage 99.44 % vs 99.10 % at clearance 0).

Cost: a k-d tree query. ~10 µs per point, batched.

---

## What was measured

All numbers: `results/a6_report.json`, `results/sweeps.json`.

### 1. The clearance sweep — what the placeholder can and cannot change

| clearance (rdu) | 0 | 1e-3 | 2e-3 | 5e-3 | **1e-2** | 2e-2 | 5e-2 |
|---|---:|---:|---:|---:|---:|---:|---:|
| in datum-σ | 0 | 0.18 | 0.37 | 0.91 | **1.83** | 3.66 | 9.14 |
| volume (rdu³) | 0.1323 | 0.1323 | 0.1323 | 0.2048 | **0.2395** | 0.2956 | 0.4418 |
| datum footprint (rdu²) | 0.584 | 0.584 | 0.584 | 0.772 | **0.841** | 0.942 | 1.172 |
| **GT squash covered** | 99.44 % | 99.69 % | 99.80 % | 99.96 % | **100.00 %** | 100 % | 100 % |
| GT squash *missed* (px) | 2 426 | 1 345 | 846 | 152 | **8** | 0 | 0 |
| **GT weed shielded** | 85.1 % | 85.4 % | 85.7 % | 86.3 % | **87.2 %** | 89.6 % | 99.0 % |
|  · grass | 95.1 % | 95.5 % | 95.7 % | 96.3 % | **97.1 %** | 98.4 % | 100 % |
|  · broadleaf weed | 28.3 % | 28.5 % | 28.7 % | 29.2 % | **30.8 %** | 39.6 % | 93.0 % |
| GT straw/soil inside | 37.4 % | 40.8 % | 43.6 % | 50.3 % | **58.9 %** | 71.2 % | 92.5 % |
| whole labelled frame inside | 79.7 % | 80.9 % | 81.8 % | 83.8 % | **86.4 %** | 90.3 % | 97.7 % |
| silhouette (of the photograph) | 83.4 % | — | — | 85.4 % | **87.3 %** | — | 98.5 % |

**Reading it.** Over the whole two-decade sweep the crop coverage moves
**0.56 points** (99.44 → 100.00) and the weed shielding moves **14 points**
(85.1 → 99.0). *The clearance buys almost nothing in the direction R2 cares
about and costs everything in the other one.* Whatever number C3 eventually
produces, the crop is already protected; the only thing the real number decides
is how much of the garden the robot refuses to touch. That is the bound this
sweep exists to give, and it is a much more comfortable answer than the reverse
would have been.

Two caveats stated plainly:

* Below one voxel edge (3.5e-3 rdu) the **volume** and **footprint** columns are
  resolution-limited and flat — the distance field is quantised at the cell,
  even though `is_inside` is not (it uses the k-d tree, which is why the
  coverage row still moves at 1e-3 and 2e-3).
* The clearance is **not currently the dominant uncertainty**. The floor of this
  volume is A2's datum, which under the crop is **5.8 % observed, 92.6 %
  interpolated, 1.6 % extrapolated**, with a median per-pixel datum σ of
  **8.14e-3 rdu = 1.49 datum-σ**. The placeholder clearance is 1.83 σ. **The
  uncertainty in where the floor is, is the same size as the clearance itself.**

### 2. The roadmap's claim, measured: a radius around the crown is wrong

Footprint on the datum plane at the placeholder clearance, against the best a
disk centred on A0's recorded crown can do (`figs/fig_footprint_vs_circle.png` —
the shape is a starfish, with a finger per leaf):

| | value |
|---|---:|
| keep-out footprint area | 0.841 rdu² |
| distance from the crown to the footprint, p50 / p90 / max | 0.394 / 0.598 / **0.903** rdu |
| **equal-area disk** (r = 0.517) — fraction of the sprawl it covers | **76.6 %** |
| … fraction of that disk which is not plant | **23.4 %** |
| **smallest covering disk** (r = 0.903) — area inflation | **2.10×** |
| … fraction of that disk which is not plant | **52.4 %** |

So: *a circle sized to be safe is twice as big as it needs to be and is more
than half empty; a circle sized to be reasonable misses a quarter of the plant.*
Both errors at once, which is what the roadmap predicted. `test_a6.py` asserts
the safety-critical half directly — the crop material lying outside the
equal-area disk is > 99 % inside the keep-out.

### 3. The occupancy assumption costs less than expected

| | material volume | GT squash covered @ 1e-2 | GT weed shielded @ 1e-2 |
|---|---:|---:|---:|
| `column` (shipped) | 0.1323 rdu³ | 100.00 % | 87.2 % |
| `shell` (diagnostic) | 0.0593 rdu³ | 99.97 % | 87.0 % |

The column assumption **more than doubles** the material volume (2.23×) and buys
0.03 points of crop coverage while adding 0.2 points of weed shielding. On this
image the two are almost indistinguishable *by these metrics*, because the
metrics probe *observed surfaces*, and an observed surface is in the shell by
construction. The difference is entirely in the space between the canopy and the
ground — space no ground-truth pixel lives in and no metric here can score,
which is precisely why the decision had to be made on R2/R4 grounds rather than
on a number. **The shipped choice is the one that cannot be scored.** It is
stated, tiered and switchable so C3/C4 can revisit it with a real tool.

### 4. Unresolved edges

| | material volume | vol @ 1e-2 | GT squash covered | GT weed shielded |
|---|---:|---:|---:|---:|
| `include_unseen=False` | 0.1272 | 0.2337 | 99.76 % | 85.6 % |
| `include_unseen=True` (shipped) | 0.1323 | 0.2395 | **100.00 %** | 87.2 % |

3.8 % of the crop's pixel count, 4.0 % of its volume, worth **0.24 points** of
crop coverage and **1.5 points** of weed shielding. Small, and pointed the way
R2 wants.

### 5. A4's policy is the whole ball game

The same A6 machinery on the largest **`split`** component instead of `merge`:

| | `merge` (shipped, A4's instruction) | largest `split` component |
|---|---:|---:|
| component | id 1, 938 112 px (69 % of the frame) | id 37, 383 426 px |
| unresolved edges on it | 1 204 `occluded_by`, 83 `leaves_frame` | 1 539 `occluded_by`, 203 `ambiguous`, 14 frame |
| material volume | 0.1323 rdu³ | 0.0636 rdu³ |
| **GT squash covered @ 0** | **99.4 %** | **60.0 %** |
| **GT squash covered @ 5e-2 (9.1 σ)** | **100 %** | **70.8 %** |
| GT weed shielded @ 1e-2 | 87.2 % | 45.1 % |

**A4 was right and the reason is stronger than A4's own wording.** A4 said a
crop in 69 pieces gives "a volume with 68 holes". The measurement says worse:
the largest `split` piece cannot be rescued by *any* clearance in the swept
range. At **9.1 datum-σ** — nine times the placeholder, at which point 65 % of
the weed material is already shielded — it still leaves **29 % of the crop
unprotected**. Growing a clearance moves a boundary; it does not find a leaf the
grouping never attached.

### 6. The gate rehearsal — which weeds would A8 refuse?

Each A0 contact point lifted to the straw datum along its own ray. (All are
`under_straw` / `estimated`; there is not one `visible` stem in this photograph,
so these are gate rehearsals, not accuracy scores.)

| GT id | name | distance to crop material (rdu) | inside @ 0 | @ 1e-2 | @ 5e-2 |
|---:|---|---:|:--:|:--:|:--:|
| 1 | squash (the crop) | 0.0038 | – | ✔ | ✔ |
| 2 | weed_purslane | 0.0214 | ✗ | ✗ | ✔ |
| 3 | weed_clover_patch_lower_left | 0.0195 | ✗ | ✗ | ✔ |
| 4 | weed_mallow | 0.0092 | ✗ | **✔** | ✔ |
| 5 | weed_small_right_of_mallow | 0.0101 | ✗ | **✔** | ✔ |
| 6 | weed_clover_by_fruit | 0.0258 | ✗ | ✗ | ✔ |
| 7 | weed_seedling_left | 0.0021 | **✔** | ✔ | ✔ |
| 8 | weed_seedling_mid | 0.0020 | **✔** | ✔ | ✔ |
| 9 | weed_ovate_upper | 0.0022 | **✔** | ✔ | ✔ |
| 10 | weed_ovate_lower | 0.0000 | **✔** | ✔ | ✔ |

**4 of 9 weeds are already unreachable at zero clearance; 6 of 9 at the
placeholder; 9 of 9 at 9 σ.** Weeds 7–10 sit *inside* the squash — id 10's
contact point is inside the crop material itself, distance exactly 0 — which is
correct behaviour and also the reason a keep-out volume alone is not a weeding
strategy. The three weeds furthest out (2, 3, 6, at 0.020–0.026 rdu ≈ 3.6–4.7 σ)
are the ones the eventual tool number actually decides.

### 7. Resolution

| cell (rdu) | grid | material volume | vol @ 1e-2 | GT squash covered | GT weed shielded |
|---:|---|---:|---:|---:|---:|
| 7.0e-3 | 179×216×143 | 0.1792 | 0.2534 | 100.00 % | 88.0 % |
| 5.0e-3 | 247×298×196 | 0.1562 | 0.2441 | 100.00 % | 87.4 % |
| **3.5e-3** | **351×425×279** | **0.1323** | **0.2395** | **100.00 %** | **87.2 %** |

The dilated volume is stable to **5.5 %** over a 2× change in cell; the raw
material volume is not (35 %), because voxelising thin leaf surfaces over-counts
at a coarse cell. Every *decision* number (coverage, shielding) moves under one
point. The cell is reported as a resolution, and no conclusion rests on it.

---

## What was decided

1. **Build on `merge`, as A4 instructed — and report loudly what that costs.**
   §5 vindicates the instruction (`split` tops out at 70.8 % crop coverage at
   any clearance) and §1 shows the price (85 % of the weed material shielded
   before A6 does anything). Both are in `RESULTS.md`, not just here.
2. **The unobserved column under the canopy is occupied.** R4 forbids asserting
   it is empty; R2 makes over-covering the cheap error. Shipped as `column`,
   with `shell` as a measurable diagnostic, because no metric on this image can
   settle it.
3. **Extrude vertically, never along the ray.** The view is 41° oblique; ray
   extrusion builds the occlusion shadow, not the plant.
4. **`occluded_by` unresolved links become `TIER_UNSEEN` volume;
   `leaves_frame` links become the `frame_open` flag and an `UNKNOWN` verdict.**
   The two are different problems and are not conflated.
5. **`is_inside` is conservative by default, and says so.** The voxel bracket
   resolves toward *inside*; `UNKNOWN` resolves toward *inside*. Both are
   keyword arguments so A8 can measure what the defaults cost.
6. **The clearance is the only parameter of the shape, and a test enforces it.**
   `build_keepout` takes exactly three float defaults and the discipline tests
   fail on any spacing-like identifier.
7. **Crop identity is A0's, labelled as a stand-in for A7 in the product's own
   provenance string** (`test_the_shipped_product_on_disk_carries_its_caveats`
   asserts the string mentions A7). Nothing else in A6 knows which component is
   the crop — R3 kept intact.

---

## What surprised us

1. **The clearance — the one constant the whole chunk is built around — is
   nearly irrelevant to crop safety, and it is not the largest error term.**
   Over two decades of sweep, crop coverage moves 0.56 points. Meanwhile the
   *floor* of the volume is A2's datum, which under this crop is 92.6 %
   interpolated with a median uncertainty of **1.49 datum-σ against a 1.83-σ
   clearance**. The number C3 was going to supply is the same size as the
   uncertainty already sitting underneath the volume. Getting the tool number
   right matters much less than getting the datum under a canopy right, and
   nothing in Phase A had suggested that.
2. **A keep-out volume built the way A4 asked for shields 85 % of the weeds at
   zero clearance.** The `merge` component is 69 % of the frame; A4 recorded
   that it absorbs 83.3 % of the grass, and A6 turns that number into a physical
   consequence: 4 of the 9 ground-truth weeds are unreachable before any
   clearance exists. The safety product and the segmentation failure are the
   same object. A4 reported the grass absorption as a score; here it is a robot
   that does not weed.
3. **The `split` component cannot be rescued by clearance at all.** A4's warning
   was about holes; the truth is worse. At 9.1 datum-σ the largest `split`
   component still misses 29 % of the crop, because a clearance grows a boundary
   and cannot attach a leaf the grouping never found. This is the strongest
   argument yet for A4's untried "skeleton rooted at the crown".
4. **Ray extrusion versus vertical extrusion is a factor-of-secant error, and it
   is easy to write by accident.** The obvious implementation — "walk from the
   surface to the datum along the same ray" — was the first one written, and on
   a 41° oblique view it produces a median column of 0.364 rdu against a true
   height of 0.327 rdu, aimed away from the plant. It builds the occlusion
   shadow and calls it the plant. Everything downstream still *runs*.
5. **The occupancy assumption more than doubles the volume and is invisible to
   every metric on this image.** `column` vs `shell`: 2.23× the volume, 0.03
   points of crop coverage. Because the ground truth is a *label map* it can only
   ever probe observed surfaces, and observed surfaces are in both. The single
   most consequential decision in the chunk is the one the evaluation substrate
   structurally cannot score — worth knowing before B1 builds more of the same
   substrate.
6. **The footprint is a starfish and looks nothing like a disk.** A radius sized
   to cover it is 2.10× the area and 52 % empty; a radius sized to match its
   area misses 23 % of the plant. The roadmap asserted this; it is now measured,
   and the shape (`figs/fig_footprint_vs_circle.png`) is the clearest single
   picture in the chunk.
7. **Rendering the silhouette by projecting voxel centres was wrong and looked
   right.** At this camera one voxel subtends 3–10 px, so a scatter leaves a
   lattice of holes — it reported 63.1 % of the frame occluded where ray
   marching says **83.4 %**, and the holes read by eye as genuine gaps in the
   volume over the corner leaves. It was caught only by looking at the figure at
   full size. A 20-point error in a headline number, invisible in the code.

---

## Not done / deferred

* **One image**, as with every Phase A chunk.
* **One plant.** The API builds a keep-out for *a* component; the roadmap asked
  for the squash and that is what is shipped. A8 needs the union over every
  keep-plant, which is a `min` over `distance_to_material` and is trivial — but
  it is not written here because A7's labels do not exist yet.
* **No metric clearance.** Category (b) with no tool. C3 retires it. The
  conversion also needs C0's scale; the placeholder is in rdu on purpose.
* **The occupancy assumption is unscored**, and on this evaluation substrate it
  is unscorable (§ surprise 5). C4's re-imaging after action is the first thing
  that could test it.
* **The volume is open at the frame** and stays open. C1's second viewpoint is
  the only fix; 39 % of the crop component touches the border.
* **`height_sigma` is loaded and reported but not used to thicken the floor.**
  Under R2 the floor arguably should drop by k·σ where the datum is
  interpolated — which is 92.6 % of the area under this crop. The clearance
  dilation extends the floor downward uniformly instead, which is not the same
  thing. Flagged rather than done: it would add a second constant, and given
  surprise 1 it is probably the more important of the two.
* **No sensitivity to A1b's focal length.** A1b has not landed. A6 reads the
  camera from the A1 manifest and will re-run unchanged.
* **Compute:** ~5 s to build the volume (3.5 GB peak), ~10 µs per `is_inside`
  query, ~1 min per ray-marched silhouette figure.

---

## Constants introduced

See `BOOKKEEPING.md` for the exact `CONSTANTS.md` rows. One **(b)** placeholder
(the tool clearance, swept over two decades, retired by C3) and one **(a)**
resolution ceiling (the voxel edge, swept 2×). **No (c) and no (d) constants**,
and no constant that encodes how gardens are arranged.

---

## Implications for the roadmap

* **A8 — what the gate must know.**
  1. `is_inside` defaults to **conservative** and to **`UNKNOWN` ⇒ inside**. Do
     not flip either to make the target list longer.
  2. The keep-out is in **rdu**. Refuse to print a metre. A `tool_profile`
     carrying a millimetre clearance cannot be used against this volume until
     C0 lands; A8 should raise rather than convert.
  3. Expect the gate to reject **6 of the 9** ground-truth weeds at the
     placeholder clearance, and **4 of 9 even at zero clearance**. That is not a
     bug in A8 and it should be reported as a rejection *reason*
     (`inside_keep_out_of_instance_1`), which is exactly the roadmap's ask.
  4. The union over multiple keep-plants is a `min` over `distance_to_material`;
     do not rebuild volumes per query.
  5. R2's third condition is already satisfiable in code: `classify()` gives
     `OUTSIDE` / `INSIDE` / `UNKNOWN` and never a coordinate-bearing opinion
     from a model.
* **A7** — the component this volume is built on contains 83 % of the grass and
  24 % of the broadleaf weed. When the VLM is asked "is instance 1 a weed?", a
  `remove` answer would put a keep-out-sized region of the bed under the tool.
  A8's gate must not be the only thing standing between that answer and motion.
* **A5** — the contact points A5 produces are exactly the queries this volume
  will be asked about. A5 should record `distance_to_crop_material_rdu` next to
  each point; it is one call and it makes A8's rejection report explain itself.
* **A4** — the `merge`/`split` question is now decidable on physical grounds
  rather than on F1: `split` cannot be rescued by any clearance, `merge` shields
  the garden. **Neither is acceptable and the gap between them is where the
  skeleton-rooted-at-the-crown idea has to live.** That is the single most
  valuable thing A6 can hand back.
* **A2** — the datum uncertainty under a canopy (1.49 σ, 92.6 % interpolated) is
  now a load-bearing number, not a diagnostic. It sits underneath every keep-out
  volume and it is the same size as the tool clearance.
* **A0** — the ground truth is a label map, so it can only probe observed
  surfaces. The occupancy assumption is therefore structurally unscorable. If
  B1's capture protocol can afford it, one scene with a second viewpoint would
  turn this from an argument into a measurement.
* **C3** — the number this chunk is waiting for. The sweep says: anywhere in
  0 … 9 datum-σ protects the crop; what it decides is how much of the bed the
  robot may touch. Bring a tool clearance *and* a positioning repeatability, and
  bring C0's scale, or the number cannot be used.
* **B1** — two transfer questions. (i) Does "the crop's keep-out covers most of
  the frame" hold on a bed where the crop is not 69 % of the picture, or is it
  an artifact of this close, oblique, one-plant photograph? (ii) Does the datum
  uncertainty under a canopy stay comparable to the clearance, or was this scene
  unusually occluded?

---

## Figures

| file | what to look for |
|---|---|
| `figs/fig_keepout_overlay.png` | the volume's silhouette over the RGB at four clearances, with the A0 squash outlined. **Checked by eye:** it covers the crown, the vine runs, the fruit and *both* corner leaves; the bottom-left weed patch is the only substantial region left outside. |
| `figs/fig_keepout_zooms.png` | the same at 4× on the crown, an upper-right petiole run, and the two corner leaves. **Checked by eye:** the extremities are covered exactly as the crown is — the shape follows the sprawl, not a radius. |
| `figs/fig_footprint_vs_circle.png` | the datum-plane footprint (a starfish, one finger per leaf) against the equal-area and covering disks. |
| `figs/fig_clearance_sweep.png` | growth, coverage/shielding, and `merge` vs `split`. |
| `figs/fig_unseen_and_slice.png` | the unresolved-link halo, the frame-open border, and a vertical slice showing the columns standing on the fitted datum. |
