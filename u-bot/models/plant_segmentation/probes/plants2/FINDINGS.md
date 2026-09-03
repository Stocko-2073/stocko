# Probe findings — `plants2.jpeg` through Phase A

**Status: probe, n = 1, unscored.** No ground truth exists for this photo, so
every number below is descriptive or a by-eye check, and none of it goes in
`RESULTS.md`. B1 stays blocked. What this evening bought is a first look at
*which* Phase A assumptions are scene-specific, which is B1's question, one
image early.

The photo: a pumpkin vine sprawling through a lawn against a white lattice
fence. Three orange fruit, large lobed leaves, tall grass, ground ivy, dead
leaves. **No bare soil, no mulch, oblique view.** Almost the opposite of
`plants.jpeg` (overhead, straw mulch, one dark-green kabocha) on every axis
that matters.

## The one-paragraph result

The geometry stages *run* and produce plausible-looking rasters, but the
datum they rest on is wrong in kind, not in degree: with no soil in the frame,
A2's "ground" becomes the grass canopy plus the fence, and 84 % of the plant
material ends up *inside* the datum's own ±3σ band (12 % on `plants.jpeg`).
Everything downstream of A2 inherits that. Separately, A3's 42-patch material
probe transfers weakly (5 of 15 by-eye boxes; all three fruit boxes miss), and
DA3's camera head gives a focal length 1.3–1.5× shorter on this photo than on
`plants.jpeg` for the same run, which bears directly on A1b's adopted `f`.

---

## A1 — depth and camera

Depth itself looks right: fence near, lawn far, leaves proud of the grass, and
the lattice holes see through to the lawn behind. Nothing to complain about.

**The camera head is scene-conditioned.** Same code, same weights, same
process resolution, two photos:

| run | `plants.jpeg` f @ 3000×4000 | `plants2.jpeg` f @ 3000×4000 | ratio | fx/fy consistent (plants / plants2) |
|---|---:|---:|---:|---|
| nested-giant @504 | 4453 | 3120 | 1.43 | yes / yes |
| nested-giant @700 | 4647 | 3112 | 1.49 | yes / yes |
| da3-large @504 | 4159 | 2335 | 1.78 | yes / **no** (0.928) |
| da3-large @700 | 4695 | 3672 | 1.28 | yes / yes |
| nested-giant @1344 | 2939 | 4407 | — | no / no |

`results/a1_camera.json`. The consistent band is 4159–4695 px on `plants.jpeg`
and 3112–3672 px here. A1b adopted 4453 px for `plants.jpeg` because the depth
field is conditioned on DA3's own estimate and "the scene cannot adjudicate"
between that and the roadmap's 26 mm-equivalent prior (3005 px). Here the
nested model's estimate lands within 4 % of that prior.

Whether the two photos share a lens is not established: identical JPEG
quantisation tables, subsampling, ICC and dimensions are consistent with the
same phone but equally with the same messenger re-encoding both. If they *are*
the same camera, a 1.4× swing in `f` between two photos means DA3's estimate is
a property of the scene, not the instrument, and A1b's `f` is a per-image
guess wearing the camera's clothes. A1b said as much ("category (d), bounded by
the sweep") and its sweep showed A4 is bit-identical in `f` and only the ground
rake moves. This does not change any Phase A number; it does say **ask the
friend for one unstripped original**, which A1b's log already asked for.

**Instrument constants re-measured** (category (a), per image, as A1 does):

| constant | `plants.jpeg` | `plants2.jpeg` | ratio |
|---|---:|---:|---:|
| depth resolution floor (Immerkaer) | 4.15e-5 rdu | 1.35e-4 rdu | 3.3× |
| local planarity p10, win 3 | 2.95e-5 | 5.40e-5 | 1.8× |
| local planarity p10, win 9 | 1.29e-4 | 2.59e-4 | 2.0× |
| local planarity p10, win 33 | 5.67e-4 | 3.46e-3 | 6.1× |

The raster is rougher at every scale and increasingly so at large windows,
because the flattest tenth of *this* scene is grass, not straw. These are the
values the probe's A2 and A4 ran with; copying `plants.jpeg`'s would have been
an R1 violation and would also have made A2's RANSAC threshold 6× too tight.

## A2 — the datum

`chunks/A2/products/`, `chunks/A2/results/fit_report_primary_raster.json`.
Shipped code, shipped constants, every measured quantity re-measured.

| | `plants.jpeg` | `plants2.jpeg` |
|---|---:|---:|
| RANSAC threshold (p10 win33) | 5.45e-4 rdu | 3.46e-3 rdu |
| RANSAC inliers | 1.2 % | 7.0 % |
| final ground inliers (`observed`) | 29.1 % | **67.3 %** |
| datum σ | 5.47e-3 rdu | 1.08e-2 rdu |
| `lam` (grid 1e-3 … 1e7) | 316 | **0.01** |
| effective d.o.f. (of ≈945 basis functions) | 63 | **845** |
| fit scale | 147 px | 40 px |
| max trusted support | 240 px | 20 px |
| interpolated / extrapolated | 69.8 % / 1.1 % | 29.1 % / 3.6 % |
| wall time | ~6 min | 33 min |

Read together: the cross-validation asked for almost no smoothing (`lam` two
grid steps from its floor), the spline is 90 % saturated, and the "ground"
grew to two thirds of the frame. **The datum is a 40-px low-pass of the depth
map itself**, following the grass tops, the ground ivy and the fence slats.
Coverage looks *better* than on `plants.jpeg` — more observed, less
interpolated — and that is exactly backwards: it is observed because the weeds
are the surface.

The consequence, measured with A3's own material map lifted to the depth grid
(`results/comparison_a2_a3.json`):

| A3-plant pixels … | `plants.jpeg` | `plants2.jpeg` |
|---|---:|---:|
| inside the datum's ±3σ band | 12.0 % | **84.4 %** |
| confidently above (> 3σ) | 87.9 % | 12.1 % |
| of which `grass` above 3σ | 77.9 % | 6.1 % |
| of which `broadleaf_weed` above 3σ | 39.6 % | 5.8 % |
| of which `squash_leaf` above 3σ | 99.2 % | 18.1 % |

On `plants.jpeg` the weeds stand on a datum; here the weeds *are* the datum.
A4's input is `relief = datum depth − depth`, and A5's whole status decision
is "where does the material meet the datum". For 84 % of the plant material
here the answer is "everywhere, trivially".

**What kind of failure this is.** Not a constant. No entry in `CONSTANTS.md`
encodes "the ground is the flattest large surface and plants stand above it";
the *method* does — RANSAC for the dominant plane, then a smooth surface
through its inliers, then height above it. That assumption is true of a
mulched bed and false of a lawn. It is the first concrete instance of what B1
was written to find ("constants that turn out to be scene-specific despite
claiming instrument or observation provenance"), except that it is a
structural assumption rather than a constant, so a constant sweep would never
have surfaced it.

**What A2 could have said instead.** It had the evidence to refuse: `lam` at
the grid floor, e.d.f. at saturation, and 67 % of the frame declared ground
when A3 calls 73 % of it plant. Under R4 the honest output is "no surface
smoother than the vegetation exists in this frame", not a height map. That is
a design note for B1, not a fix to make tonight.

## A3 — material

`results/a3_material.json`, `results/a3_spot_check.json`, `figs/a3_*.png`.
The shipped probe — frozen DINOv2, 42 seed patches from `plants.jpeg`,
logistic regression — applied unchanged.

Confidence first, because it is the number that is available without ground
truth:

| median max-class probability | |
|---|---:|
| `plants.jpeg`, all pixels | 0.358 |
| `plants.jpeg`, pixels it gets right | 0.382 |
| `plants.jpeg`, pixels it gets wrong | 0.293 |
| **`plants2.jpeg`, all pixels** | **0.246** |
| chance, 7 classes | 0.143 |

Here it is less sure than it was on the pixels it got *wrong* at home. The
only region above 0.35 is the sunlit lawn top-right, which it calls grass.

By-eye check, 15 boxes the author placed on a gridded view inside
unambiguous material, boundaries avoided (`spot_check.py`; **not ground
truth**, and the lattice has no legitimate class in A0's scheme, so `other`
stands in):

| expected | boxes | majority hits | what it said instead |
|---|---:|---:|---|
| grass (lawn) | 2 | 2 | — |
| squash leaf (pumpkin) | 4 | 3 | broadleaf weed |
| **fruit (orange pumpkin)** | 3 | **0** | petiole, broadleaf weed ×2; 4 % fruit pixels in-box |
| lattice / post | 3 | 0 | petiole ×2, squash leaf |
| ground ivy (broadleaf weed) | 1 | 0 | straw |
| dead leaf (straw) | 1 | 0 | squash leaf |
| vine stem (petiole) | 1 | 0 | squash leaf |

Class fractions over the frame: `squash_petiole` 14 % (8 % at home),
`other` 6.3 % (0.2 % at home — a class fitted on one feather now fires on the
fence), `fruit` 5.8 % — but not on the fruit; it lands on shaded dead leaves
in the centre.

Reading: the two classes that transfer are the two with texture DINOv2 can
recognise independently of this garden — grass blades, broad lobed leaves. The
ones that fail are the ones the 42 patches defined by appearance in one photo:
`fruit` means "dark green kabocha", and an orange pumpkin has nothing in common
with that; `squash_petiole` means "pale elongated thing", which a white lattice
slat also is. A3's FINDINGS predicted exactly this ("it is the reason B1
matters"). Within the stack the damage route is A4: `build_fragments` splits on
class boundaries, so a fruit labelled `broadleaf_weed` starts life as a
separate fragment from its own leaves.

For R2 the direction of the fruit error is the bad one — crop called weed —
though A3 alone decides nothing; the label that gates removal is A7's, and A7
was not run here.

## A4 — grouping

`results/a45.json`, `chunks/A4/products/`, `figs/a4_components_plants2.png`.
Shipped code; the continuity tolerance re-measured (90th percentile of
within-fragment residuals, as A4 does); the depth-resolution floor swapped for
this raster's. SAM partition: 921 masks → 1058 regions (572 → 728 at home).

| | `plants.jpeg` | `plants2.jpeg` |
|---|---:|---:|
| fragments | 1776 | 3446 |
| continuity tolerance | 4.24e-3 rdu | 5.44e-3 rdu |
| edges connected / separated / unresolved | 1375 / 1392 / 1237 | **4397** / 1203 / 1837 |
| components, `split` | 742 | 667 |
| components, `merge` | 207 | 321 |
| largest `split` component, share of plant px | squash in pieces (best IoU 0.46) | **73.3 %** |
| largest `merge` component, share of plant px | squash whole (IoU 0.885) | **92.3 %** |
| A3-`grass` inside the largest component, `split` | 11.8 % (GT grass) | 82.9 % |
| A3-`grass` inside the largest component, `merge` | 83 % (GT grass) | 97.7 % |
| components holding ≥200 px of A3-`fruit`, `split` / `merge` | — | 22 / 6 |

The largest `split` component is 38 % grass, 21 % squash leaf, 19 % petiole,
13 % broadleaf weed and 8 % fruit by A3's labels — the fence, the lawn and
most of the vine as one object, with three quarters of all A3-fruit pixels inside it. Under
`split`, the policy that fragmented the kabocha into 69 pieces at home, this
photo still comes out as one blob: 59 % of adjacent-fragment boundaries are
*connected* here against 34 % at home, because the relief across them is
nothing — both sides sit on the datum.

What survived is instructive. The three large pumpkin leaves at the bottom of
the frame, which genuinely stand proud of the lawn, come out as their own
components under `split` (the distinct blobs in the figure), and each lattice
hole is its own small component because the grass behind the fence lies
*below* the datum. Where relief exists, A4 does what it was built to do. Where
the datum is the canopy, there is no relief to read, and A4 has nothing — which
is A4 being correct about a wrong input, not A4 being wrong.

Component count is not a fragmentation measure: `split` gives *fewer*
components here (667) than at home (742) while merging far more.

## A5 — contact points

`chunks/A5/products/contacts_{split,merge}.json`, `figs/a5_contacts_plants2.png`.

| | `plants.jpeg` split | `plants2.jpeg` split | `plants.jpeg` merge | `plants2.jpeg` merge |
|---|---:|---:|---:|---:|
| observed | 472 (64 %) | **608 (91 %)** | 164 (79 %) | **313 (98 %)** |
| extrapolated | 59 | 7 | 11 | 2 |
| occluded | 211 (28 %) | 52 (8 %) | 32 | 6 |
| arm-admissible | 378 | **493** | 137 | **273** |
| median confidence | 0.72 | 0.86 | 0.81 | 0.89 |
| fabricated points | 0 | 0 | 0 | 0 |

Six hundred and eight components "observed" meeting the datum, at a median
confidence of 0.86, and 493 of them admissible to an arm. Every one of those
points is real in A5's terms — material inside the datum's ground band, no
extrapolation, no fabrication; the refusal machinery held (`fabricated_points`
0 both ways). They are also, almost all of them, **grass meeting grass**: the
white crosses in the figure carpet the lawn. The 52 `occluded` verdicts are
the lattice holes.

This is the sharpest statement of the evening. A5's status vocabulary is
honest by construction *given a datum*. Nothing in A5 can tell that the datum
it was handed is the vegetation, so it reports, correctly and confidently,
several hundred places where the weeds touch themselves. On `plants.jpeg` the
same code's 28 % `occluded` rate was the hard-won honesty A5 was praised for;
here it drops to 8 % and that looks like an improvement. The number that
should have set off alarms lives in A2, and A2 does not currently emit it.

## Not run

**A6, A7, A8.** A6 needs a crop identity, which on `plants.jpeg` came from the
A0 ground truth as a stand-in for A7; A7 costs ~$40 of VLM calls per image and
is the semantic layer B1 most needs to test, but not from a shadow root at
midnight with no ground truth to score it against. Note that had they run,
A6's keep-out would have been built from a component that is 92 % of the plant
material and includes the fence, so the gate would have refused everything —
safe by accident, which is the failure mode A8's FINDINGS warned about: "on a
sparse bed the semantic layer may be all that is left."

## What surprised us

- **A2's coverage numbers got better on the failure case.** 67 % observed, 29 %
  interpolated, against 29 % / 70 % at home. Every headline A2 metric improved
  while the datum stopped meaning anything. Coverage measures how much of the
  frame the fit reached, not whether what it reached was ground.
- **The failure is structural, not a constant.** Every R1 constant in A2 and A4
  is (a) or (c) and was honestly re-measured here; none of them is the problem.
  The assumption "a surface smoother than the plants exists" is in the method,
  and the constant register cannot see it. B1's failure taxonomy needs a
  column for that.
- **A5's confidence went up as its meaning went away.** 0.86–0.89 median on
  contact points that are grass on grass.
- **DA3's focal estimate moved 1.4× between two photos** that very likely came
  from the same phone. A1b's adopted `f` is a scene reading, and A1b's own
  sweep already showed which quantities that moves (ground rake) and which it
  does not (A4, bit-for-bit).
- **Ops:** SAM took 85 min (13 min at home) and A2 took 33 (6 at home) because
  the machine was 24 GB into swap from other applications. Heavy stages want
  memory headroom; the shipped timings assume it.

## What this says for B1

1. **The capture protocol must include no-soil scenes on purpose.** Lawn edges,
   ground cover, mulch-free borders. They are the common case for a garden
   robot's boundary and they are where this stack fails silently.
2. **A2 needs a datum-validity verdict that A4 and A5 consume.** The signals
   are already computed: `lam` at the grid floor, effective d.o.f. near
   saturation, ground fraction against A3's plant fraction, datum σ against
   the local-planarity curve at the fit scale. R4 says the honest output on
   this photo is "no datum", and A5 should then emit no `observed` points at
   all. That is a chunk's worth of work and belongs in B1, not in a probe.
3. **A3's 42 patches from one photo are not a material model** — known, and
   B2's job — but the specific hole is colour: the probe has never seen an
   orange fruit. A B1 scorecard should report fruit separately from foliage.
4. **The per-image scorecard needs a "datum valid?" row** above the IoUs;
   without it, this image would have posted the best A2 coverage and the most
   A5 targets in the set.
5. **Ask for one unstripped original.** Two photos, one camera, two DA3 focal
   lengths 1.4× apart: EXIF would settle A1b's open question in a minute.

## Bookkeeping

- Nothing scored → nothing for `RESULTS.md`.
- No new constants → nothing for `CONSTANTS.md`. The re-measured (a) values
  are per-image instrument readings and live in the probe manifest.
- No dependency changed, no venv touched, no Phase A product written.
- One entry appended to `PROGRESS.md`. B1 remains `blocked`.
