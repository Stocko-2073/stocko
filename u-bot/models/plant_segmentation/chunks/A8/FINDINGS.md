# Chunk A8 — MCP tool surface and the safety gate

**Date:** 2026-09-01 · **Scale confidence:** `scale_free`; every length in
**rdu**, every image distance in px on a named grid. **Datum: the STRAW mulch
surface**, not soil (A2). **Inputs:** A5 `load_a5(policy="split")`, A6
`keepout.build_keepout` (rebuilt for every instance), A7
`results/labels_A_r2_r{1,2}.json` (framing A, variant r2, both repeats), A4
`load_a4` under both policies, A2 `load_a2()`, A1 `primary_raster`.
**Scorer:** A0's ground truth, through `products/gt_audit.json`. **Transport:**
a hand-written MCP stdio server, verified with the official `mcp` 2.1.1 client.
**Compute:** 39 s to build the products, 0.5 s for the whole end-to-end run,
2.4 s for the 31 tests. **Cost:** $0 — no model is called anywhere in A8.

---

## Headline

Two MCP tools. `segment_garden` returns geometry and no opinion;
`plan_removals` applies R2 in code and returns an ordered target list plus a
rejection report. Everything below went over the wire, through the server, in a
subprocess.

| | shipped (floor **0.70**) | diagnostic (floor 0.00) |
|---|---:|---:|
| instances considered | 207 | 207 |
| **targets admitted** | **0** | **1** (instance 104) |
| instances rejected | 207 | 206 |
| **GT crop px under the tool** | **0** of 421 926 | **0** of 421 926 |
| **any GT crop point admitted?** | **no** | **no** |
| GT weed px reached | 0 % | **71.3 %** |
| GT weed *instances* reached | 0 of 9 | 5 of 9 |

**The central result is the ablation, and it is not the result the chunk was
designed to produce.** The gate has seven semantic conditions and four
geometric ones. Drop them one at a time from the floor-0.00 run and see what
reaches the ground truth (`results/a8_ablation.json`,
`figs/fig_operating.png`):

| gate | targets | **GT crop px under the tool** | GT weed reached | crop-bearing targets |
|---|---:|---:|---:|---|
| **all conditions** | 1 | **0** | 71.3 % | — |
| without `label_not_remove` | 3 | 0 | 71.7 % | — |
| without `not_unanimous` / `mixed_component` / `no_contact_point` / `contact_not_observed` / `contact_not_arm_admissible` / `insufficient_repeats` / `component_unlabelled` / `label_discarded_r3` (each alone) | 1 | 0 | 71.3 % | — |
| **without `inside_keepout`** | 3 | **477** | 71.3 % | **5, 120** |
| semantics only (all geometry dropped) | 3 | **477** | 71.3 % | 5, 120 |
| geometry only (all semantics dropped) | 10 | **414 003** | 97.3 % | **1 — the squash** |

Read the last three rows together. **Neither half of R2 is sufficient and each
one catches what the other misses.** The semantic layer is the only thing
keeping the squash itself off the target list — without it the gate admits
instance 1 and puts 98 % of the crop under the tool. The keep-out test is the
only thing keeping A7's *mislabels* off it — without it the gate admits
instances 5 and 120, which between them hold 477 px of ground-truth squash leaf
that the VLM called `remove` twice in a row at confidence 0.58 and 0.60.

**And the confidence floor — the one constant this chunk was asked to
introduce — catches nothing.** Crop risk is 0 px at *every* floor from 0.00 to
0.90, because the geometry has already removed all of it. What the floor
changes is the weed reach: 71.3 % below 0.62, zero above. On this image the
registered floor is a switch that turns the system off and buys nothing, and
that is reported rather than tuned away.

---

## What was built

`segment_garden(image, depth, intrinsics)` → soil-surface summary + 207
instances. `plan_removals(labels, tool_profile)` → ordered target list +
rejection report. Both are pure functions of products on disk; neither runs a
model, neither touches the network, and
`test_nothing_in_the_tool_surface_can_move_anything` parses both modules to
assert they cannot.

### 1. The transport, and why it is hand-written

`mcp==2.1.1` installs cleanly and brings 20 packages with it (pydantic,
starlette, uvicorn, cryptography). A4, A5, A6 and A7 each shipped a lock file
whose first line says the shared `chunks/A3/.venv` is reused **unchanged**, and
A8 is a tool surface over products that already exist. MCP is JSON-RPC 2.0 over
newline-delimited JSON on stdio; `server.py` implements `initialize`,
`notifications/initialized`, `tools/list`, `tools/call` and `ping` in 150 lines
of standard library.

**The choice is verified rather than asserted.** `mcp_sdk_client.py` runs in a
throwaway client-only venv (`.venv-client`: `mcp` and nothing else, no numpy)
and drives the server with the **official** SDK: `initialize` → `tools/list` →
four `tools/call`s, including both refusal paths.
`results/mcp_conformance.json` records `"verdict": "PASS"`. Using the SDK on
both ends would have made a shared misreading of the spec invisible; this way
two independent implementations have to agree.

### 2. The three seams Phase A left open

A5, A6 and A7 do not agree with each other by default. A8 is where that is
resolved, explicitly, in `a8_common.py`:

**Seam 1 — the policy mismatch.** A5 ships contact points on A4 `split` (742
components, and A5's FINDINGS recommends `split` because `merge` statuses 92 %
of the frame as one `occluded` blob). A6 builds keep-out volumes on `merge`,
and measured that `split` cannot be rescued by any clearance. A7 labelled
`merge`, because that is what a VLM can be shown a picture of.

Resolution: **the tool surface's instance ID is the `merge` component id** —
the id the labeller labelled and the id the keep-out is built on — and each
instance carries its `split` children's contact points as *candidates*. The map
is a **function**, not a vote: all 742 split components' pixels lie inside
exactly one merge component, purity 1.000, asserted in `split_to_merge` (which
raises rather than voting) and re-checked independently in
`test_the_split_to_merge_map_is_a_function`.

**Seam 2 — crop identity.** A6's shipped volume takes its crop from A0's ground
truth as an explicit stand-in for A7. A8 does not call `load_a6` or
`load_crop_component` in the gate at all — both hard-code A0's crop instance.
It rebuilds a keep-out from the same machinery for **every** instance, and that
machinery knows nothing about which one is crop. The rebuild is checked against
A6: for the component A0's crop lands in, the distances agree to **3.7e-9 rdu**
and the reconstructed `is_inside` matches A6's own `classify()` on all 531
points, exactly, including its conservative bracket and its `UNKNOWN ⇒ inside`
rule.

**Seam 3 — the union over keep-plants.** A6: *"the union over multiple
keep-plants is a `min` over `distance_to_material`; do not rebuild volumes per
query."* `build_products.py` builds all 207 volumes once (39 s) and stores a
531 × 207 exact distance table. `plan_removals` then takes a min over whichever
instances the labels make keep-plants, at whatever clearance is asked for, with
no geometry left to compute. That also makes the keep-out test *independent of
the labels* — R3 in the file layout, not only in the prose.

### 3. The gate, and three properties that are deliberate

**Nothing short-circuits.** Every condition is evaluated for every instance and
every failure is returned. A gate that stopped at the first failure would
report `label_not_remove` for a target that was *also* inside the crop's
keep-out. It also means the keep-out column is populated even when the floor
has already refused everything — which is exactly this image's situation — and
it is what makes the ablation above computable by set inclusion rather than by
re-running (the identity is cross-checked against a real re-run in
`analyse.py`).

**The gate cannot be opened from outside.** There is no parameter that turns a
condition off, no `force` flag, and no path where a model-authored string is
evaluated. The only tunable is the floor, and raising it can only close the
gate (`test_the_floor_is_monotone`).

**A model-authored field never reaches geometry.** Labels are validated on the
way in with **A7's own `schema.validate_label`**, reused unchanged, and a label
that fails is discarded to `unsure` rather than patched.

The rejection vocabulary is closed — twelve reasons (eleven about an
instance, one that refuses the whole call), each with its own
paragraph of justification in `a8_gate.REASONS`, and
`test_every_rejection_reason_is_in_the_closed_vocabulary` asserts nothing else
is ever emitted.

### 4. What `segment_garden` refuses to say

The roadmap asks for "a list of instances, each with ID, **crop**, material
class, ...". A8 emits `crop: null` on every instance, with `crop_source` naming
who fills it in. **Nothing in A1–A6 knows which plant is the crop**, and the
only thing that does is the VLM that sees the ids this tool emits. A tool that
filled that field in would be laundering A0's ground truth into a runtime
answer. This is a deliberate deviation from the roadmap's wording and it is
recorded as one rather than hidden. `plan_removals` echoes the caller's label.

One thing this does *not* claim: A3's material vocabulary is A0's, so
`material_class` says `squash_leaf`, and `segment_garden` is not species-blind.
It was never meant to be — the roadmap asks it for a material class. What R3
forbids is a crop-vs-weed *decision* and a coordinate from the labeller, and
neither is there.

---

## What was measured

### 1. The funnel, at the placeholder clearance

`results/a8_scores.json`, `products/rejection_report.json`.

| stage | count |
|---|---:|
| instances | 207 |
| ...with at least one contact candidate | 178 |
| contact candidates (A5 `split`, with a point) | 531 |
| ...`observed` | 472 |
| ...arm-admissible (A5's own `admissible()`, carried not re-derived) | **378** |
| **...and outside every keep-plant's keep-out** | **27** (7.1 %) |
| instances with ≥ 1 arm-admissible candidate | 144 |
| ...all of whose candidates are inside a keep-out | **134** |
| instances geometrically clear **and** semantically refused | 9 |
| instances semantically a `remove` **and** geometrically refused | 2 |
| instances refused by both halves | 195 |
| **targets admitted, floor 0.00 / floor 0.70** | **1 / 0** |

**The keep-out union removes 93 % of the geometrically usable targets in the
image.** That is R2's cost, measured, and it is the physical consequence of
A4's `merge` policy that A6 predicted: the crop component is 69 % of the frame,
so almost everywhere a tool could go is beside something the gate is
protecting.

Rejections by reason (not exclusive — every failure is reported):
`label_not_remove` 204, `component_unlabelled` 134, `label_discarded_r3` 134,
`insufficient_repeats` 134, **`inside_keepout` 134**, `confidence_below_floor`
59 (shipped run only), `no_contact_point` 29, `contact_not_arm_admissible` 23,
`not_unanimous` 15, `contact_not_observed` 11, `mixed_component` 4. The number
of conditions each rejected instance failed: 132 failed five, 54 failed two, 14
failed three, 4 failed one, 2 failed four.

### 2. The three unanimous `remove`s, one by one

A7's shipped condition produces exactly three components that both repeats call
`remove`. This is the whole decision surface of the chunk.

| instance | GT crop px | GT weed px | confidence (r1, r2) | verdict at floor 0.00 | why |
|---:|---:|---:|---|---|---|
| **5** | **453** | 0 | 0.58, 0.58 | **rejected** | `inside_keepout` — distance to instance 1 is **0.0 rdu**: the point is inside the squash's own material |
| **104** | 0 | 12 500 | 0.60, 0.62 | **admitted** | — |
| **120** | **24** | 0 | 0.60, 0.60 | **rejected** | `inside_keepout` — distance to instance 1 is **0.0 rdu** |

Instance 5 is A7's single catastrophic mislabel on this image, and A7 flagged it
as such. **The geometry refuses it at zero clearance and would refuse it at any
label confidence**, because the point is not near the crop, it is *in* it. That
is `test_a_point_inside_the_squash_keep_out_is_rejected`: the test the roadmap
asked for, satisfied by the real failure rather than a synthetic one.

### 3. The confidence floor cannot be tuned on this image, and A8 refused to

The roadmap's Constants table says *"confidence floor for removal — set high,
tuned against A0"*. The tuning was attempted and **refused**. The whole of the
evidence:

* A7's measured `remove` confidence band across every condition is
  **0.518–0.625** — the model essentially never expresses high confidence.
* The crop mislabel (instance 5) sits at **0.58**; the one real weed (104) at
  **0.60–0.62**. The separation a floor would have to exploit is **0.02**.
* A7 measured the model's repeat-to-repeat confidence spread at
  **0.052–0.066** — two to three times that separation.

A floor placed in the 0.04-wide window (0.58, 0.62] would score perfectly on A0
and would be fitted to noise. A7 wrote down exactly this hazard about its own
result — *"a coin on its edge, not a finding, and it is recorded here so that A8
does not inherit it as one"* — and A8 declines to inherit it.

**What justifies 0.70 instead is an A7 measurement that is not about this
image's weeds at all.** A7's confabulation probe drew six regions over
ground-truth *pure straw* and prompted them identically to real ones: 18/18
`keep`, zero `remove`, **mean confidence 0.70**. The model says 0.70 about a
region with no plant in it. A self-reported confidence at or below that carries
no evidence about anything, so R2's "high confidence" cannot mean less. The
floor is set at the number the model assigns to nothing, and its consequence —
zero targets on this image — is reported, not softened.

| floor | 0.00 | 0.50 | 0.55 | 0.58 | 0.60 | **0.62** | 0.65 | **0.70** | 0.90 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| targets | 1 | 1 | 1 | 1 | 1 | **0** | 0 | **0** | 0 |
| GT crop px under the tool | **0** | 0 | 0 | 0 | 0 | 0 | 0 | **0** | 0 |
| GT weed px reached | 71.3 % | 71.3 % | 71.3 % | 71.3 % | 71.3 % | **0 %** | 0 % | **0 %** | 0 % |

The crop row is flat at zero across the whole sweep. **The floor is not a safety
mechanism on this image; it is a volume knob with two settings.**

### 4. The ground-truth weed roll-call — A6's rehearsal, run for real

A6 predicted the gate would refuse 6 of the 9 ground-truth weeds at the
placeholder clearance and asked A8 to report it as *rejections with reasons*.
Here it is, and the shape differs from A6's prediction in an instructive way
(`results/a8_scores.json → gt_weed_rollcall`):

| GT weed | instance | at floor 0.00 | at the registered floor |
|---|---:|---|---|
| 2 purslane, 3 clover LL, 4 mallow, 5 small-right-of-mallow, 6 clover-by-fruit | **104** | **admitted** (one target covers all five) | rejected — `confidence_below_floor` |
| 7 seedling_left | 178 | rejected — `label_not_remove`, `inside_keepout` | + `confidence_below_floor` |
| 8 seedling_mid, 9 ovate_upper, 10 ovate_lower | **1** | rejected — `label_not_remove`, `mixed_component` | same |

**Three of the nine weeds are not separate instances at all** — A4's `merge`
policy absorbed them into the squash component, so they never reach the
keep-out test; they are refused because instance 1 is a keep-plant flagged
`mixed`. A6's rehearsal put GT contact points against the crop's volume and got
6/9 inside; A8's gate asks a different question — *is there an instance I may
target?* — and 3 of the 9 fail before geometry is consulted. Both numbers are
right and they are not the same number. **A segmentation failure and a safety
refusal are indistinguishable in the rejection report**, which is the honest
outcome and also a reason B1 should keep them apart.

Note also that the one admitted target is a *patch*: instance 104 holds five
distinct ground-truth weeds. "5 of 9 weeds reached" and "1 target" describe the
same event.

### 5. The tool profile, and the metre that is refused

`plan_removals` with `clearance_units: "mm"` returns zero targets and a
top-level refusal (`metric_tool_profile_refused`), with every instance carrying
that reason. Nothing is converted. A6's instruction was explicit and the
alternative — a scale factor that does not exist — would resize the keep-out
volume by an unknown amount. `positioning_repeatability`, if supplied, is
*added* to the clearance rather than combined in quadrature: both are (b)
quantities, both widen the protected region, and addition is the conservative
composition.

Clearance sweep, at floor 0.00: 1 target at every clearance from 0 to 2e-2 rdu,
**0** at 5e-2 (9.1 datum-σ). A6's sweep said the clearance decides how much of
the bed the robot may touch rather than whether the crop is safe; at the top of
its range that is now a target list of length zero.

### 6. A validator that fires on 65 % of its input

134 of the 207 labels are discarded by A7's R3 validator, and the cause is not a
model at all: **A7's own code-authored triage rationale names a pixel count** —
*"above A0's 25 px minimum but below A7's 75 px call budget floor"* — and A7's
validator rejects a measurement in a free-text field. A8 validates every label
record identically regardless of who wrote it, which is the correct rule, so
those 134 policy labels are discarded to `unsure`.

Safety consequence: **none.** The discarded labels already said `unsure`, and
the discard produces `unsure`. But a validator firing on two thirds of its input
is worth knowing about before it fires on something that matters, and it is a
concrete instance of a general hazard: an R3 validator that cannot tell a
model's prose from its own operator's prose will eventually silence the wrong
one.

### 7. The keep-plant policy, and what `unsure` protects

Shipped policy: **every instance that is not unanimously `remove` is a
keep-plant** (204 of 207). That is R2 read literally — an instance the labeller
was unsure about is kept, and a kept plant is protected — and it is deliberately
*not* a function of the confidence floor, so raising the floor cannot enlarge or
shrink the protected region as a side effect
(`test_keep_plants_do_not_depend_on_the_confidence_floor`).

The diagnostic alternative, `labelled_keep_only` (35 keep-plants; `unsure`
protects nothing), gives the **same target list** on this image. The policy
choice is unresolved by this image, which is worth stating: the instances
`unsure` adds to the protected region are small and clustered where the
committed `keep` instances already are.

---

## What was decided

1. **The instance ID is the A4 `merge` component id**, and split contact points
   are bound to their merge parent. It is the only choice that keeps the label
   (A7), the geometry (A6) and the targeting (A5) talking about the same object
   without re-deriving any of them.
2. **`segment_garden` emits `crop: null`.** A geometry tool with a crop opinion
   is a geometry tool that has read the ground truth.
3. **The floor ships at 0.70, justified by A7's confabulation probe rather than
   by A0**, and the resulting empty target list is reported as the result.
   Tuning into the 0.04-wide window A0 would select was refused.
4. **Every condition is evaluated for every instance; nothing short-circuits.**
   The rejection report is the product, not a by-product.
5. **A refusal is an error, never an empty answer.** A7 lost a whole run to a
   transport failure being absorbed by a safe-looking default; on this server a
   refused call comes back `isError: true`, and an empty target list — which is
   also a meaningful answer here — cannot be confused with one.
6. **The keep-out distance table is computed before the labels arrive.** R3 in
   the file layout: the geometry cannot be a function of the semantics because
   it is already on disk when the semantics show up.
7. **A metric tool profile is refused, not converted.**

---

## What surprised us

1. **The safety came from the geometry, and the constant this chunk exists to
   introduce contributed nothing.** Going in, the confidence floor was the
   headline deliverable. Crop risk turns out to be 0 px at every floor in the
   sweep, and the only condition whose removal puts crop under the tool is
   `inside_keepout`. The chunk's registered constant is measurably the least
   load-bearing thing in it — on this image.
2. **The keep-out volume caught the VLM's single catastrophic error, at zero
   clearance, at distance exactly 0.0 rdu.** Not "near the crop" — *inside* it.
   A7's mislabelled instance 5 is 62 % ground-truth squash leaf and its contact
   point sits in the squash's own material. R2's third condition did not need a
   tool clearance to work; it needed the crop's shape, which is what A6 built.
3. **Both halves of R2 are load-bearing and neither is close to sufficient.**
   Semantics alone: 477 crop px under the tool. Geometry alone: 414 003 — the
   squash itself, because with no labels there is no keep-plant to protect it.
   The roadmap wrote R2 as a conjunction; this is the first measurement showing
   the conjunction is redundant in neither direction.
4. **Only 27 of 378 arm-admissible contact points survive the keep-out union.**
   93 % of the geometrically usable targets in the photograph are beside
   something the gate is protecting. A6 predicted the direction; the magnitude
   is larger than "6 of 9 weeds" suggested.
5. **A7's R3 validator rejected A7's own operator prose, 134 times, for saying
   "25 px".** The most-fired rule in the whole gate fires on the honest
   description of a triage policy.
6. **A pytest assertion on a 500 KB JSON string turned a 2-second suite into a
   400-second one.** `assert word not in json.dumps(out)` looks free; pytest's
   assertion rewriting builds a repr of both sides. It also hid a *real*
   problem for two runs — the assertion was wrong (A3's material vocabulary
   legitimately contains `squash_leaf`) and the slowness is what exposed it.
7. **The one admitted target's contact point lands on ground-truth `straw`.**
   Correct behaviour, and a reminder of what the product target actually is:
   this is where the weed disappears into the mulch, not where it enters the
   soil. A0 found zero `visible` stem-soil contacts in this photograph and A5
   could not invent one; A8 does not either.

---

## Not done / deferred

* **One image**, as with every Phase A chunk — and here the limitation is at its
  worst: **the entire benefit axis of this chunk is one target**. Every
  statement about weed reach rests on whether instance 104 is admitted. The
  crop-risk axis is better supported (24 crop components, 421 926 px, and three
  independent conditions tested against them).
* **The floor is registered but not validated.** Its justification (A7's
  confabulation probe) is a measurement about *straw*, transferred to a
  statement about `remove` confidences. That transfer is an argument, not a
  measurement, and B1 is where it gets tested.
* **No second look was actually taken.** The gate requires two independent
  repeats and A7 supplied two, but A8 never re-observes anything itself. R4's
  full form — *look again from another pose* — is C1.
* **The `keep_plant_policy` question is undecided by this image.** Both
  policies give the same target list.
* **No sensitivity to A1b's focal length.** A1b runs in parallel and has not
  landed. A8 reads its camera from the A1 manifest through A2 and A6 and will
  re-run unchanged; the gate's outputs are distances, so they are *not*
  focal-invariant and A1b's table should include the target count.
* **The distance table is exact but static.** It is computed for the 531 A5
  contact points. A target elsewhere — a growing point, say, which is what a
  thermal tool would want (C3) — needs a query, not a lookup. `build_keepout`
  is still there for that; it is ~0.3 s for a typical instance.
* **`no_contact_point` does not distinguish "occluded by foliage" from "the
  material simply stops in mid-air".** A5 has the distinction in its JSON
  (`occluder`, `occluder_profile`) and flagged it for A8; A8 carries the field
  through but does not split the reason on it. C1 can help the first kind and
  cannot help the second.
* **No `outputSchema` on either tool.** MCP supports declaring one and the
  documents are large; a schema would make them checkable by the caller.
* **The server is single-session, synchronous and unauthenticated.** It is a
  research tool surface, not a service.

---

## Constants introduced

See `BOOKKEEPING.md` for the exact `CONSTANTS.md` rows. **Two**, and one of them
is a count rather than a threshold:

| name | value | category |
|---|---|---|
| `REMOVAL_CONFIDENCE_FLOOR` | 0.70 | **(c) observation + R2** — A7's confabulation probe: the model's mean confidence on regions containing no plant. A0-tuning attempted and refused (§3). |
| `MIN_LABEL_REPEATS` | 2 | **(c) observation + R4** — A7 measured that unanimity across 2 repeats removes a third of the catastrophic errors for one extra call. A count of observations, not a threshold on a continuous quantity. |

Every other number in the gate is imported from the chunk that measured it: A6's
(b) clearance placeholder and (a) voxel edge, A5's (b) extrapolation budget and
its status rules, A2's datum σ. **No (d) constants**, and no constant that
encodes how gardens are arranged —
`test_no_identifier_encodes_a_belief_about_how_gardens_are_arranged` parses
every A8 module and enforces it. (It fired once, on a variable named `cm`: a
merge-label map a reader could not tell from a centimetre.)

---

## Implications for the roadmap

* **B1 — three questions, in priority order.** (i) **Does the geometry keep
  carrying the safety when the crop is not 69 % of the frame?** Every result in
  this chunk rests on the keep-out being large; on a sparse bed the semantic
  layer may be the only thing left, and it has a measured 1-in-24 catastrophic
  rate. (ii) Does the confidence floor ever become a dial rather than a switch —
  is there a scene where the `remove` band is wider than the repeat spread? If
  not, the floor should be retired from the design and R2's asymmetry should
  live entirely in the structure. (iii) With more than one weed instance, does
  the ordering of the target list mean anything? Right now it is A5's geometry
  confidence, and nothing in this stack can rank *which weed matters most*.
* **C3 — the number that actually matters is not the clearance.** A6 found the
  datum uncertainty under the canopy (1.49 σ) is the same size as the clearance
  (1.83 σ); A8 finds the clearance changes the target list only at the top of
  its swept range (5e-2 rdu). Bring a tool clearance *and* a positioning
  repeatability, and note that a thermal or laser tool changes the target from
  the soil contact to the growing point, which is above the straw and
  observable — that would move this chunk's `no_contact_point` and
  `contact_not_observed` counts more than any constant will.
* **C4 — the rejection report is the interlock's input.** Every refusal here
  carries the specific condition that produced it, so a human reviewing a
  refusal-heavy run can tell "the segmentation failed" (`label_not_remove` on a
  `mixed` instance holding a weed) from "the plant is genuinely unreachable"
  (`inside_keepout`). Keep that distinction when the loop closes.
* **A4 — the skeleton, again, from a third direction.** A4 could not hold the
  squash together with pairwise contiguity; A5 could not find its base with a
  minimum over the component; A8 cannot target three of the nine weeds because
  they are inside the squash's component. Three chunks, three symptoms, one
  missing object.
* **A7 — two contract notes.** (i) The R3 validator needs to distinguish
  model-authored text from operator-authored text, or operators must stop
  writing pixel counts into rationales. (ii) `keep` conflating "crop" and
  "nothing here" cost A8 nothing on this image, but only because a keep-out
  built from a straw component is harmless. On a sparser scene a `keep` on empty
  mulch would protect empty mulch.
* **A6 — one small ask.** `build_keepout` for 207 instances is 39 s and the
  result is a 531 × 207 distance table; that is cheap enough to be the default
  product rather than A8's own. If A6 is re-run, shipping the per-instance
  volumes (or their boundary-voxel trees) would let A8 answer queries about
  points A5 did not emit.
* **A0 — the third gap.** A4 found the asymmetric grass exclusion; A5 found the
  contact metric has no target; A8 finds there is **no ground truth for "was
  this refusal correct?"**. 206 of 207 instances were refused, and A0 can score
  the crop-risk half of that but not the "should this have been reachable" half.
  A per-instance "is this a legitimate target" flag would make the rejection
  report scorable instead of merely enumerable.

---

## Figures

| file | what to look for |
|---|---|
| `figs/fig_gate.png` | every arm-admissible contact point on the photograph, coloured by verdict, over the keep-plant material. **Checked by eye:** the single admitted target (yellow star) sits on the bottom-left weed patch, well clear of the squash; the 144 red points trace the squash's sprawl, which is where they are refused. The right panel is the shipped floor: the same picture with the star gone. |
| `figs/fig_operating.png` | the floor cliff, with the 0.04-wide window A0 would have tuned into marked; the ablation bar showing `inside_keepout` is the only condition whose removal puts crop under the tool; the clearance sweep. |
