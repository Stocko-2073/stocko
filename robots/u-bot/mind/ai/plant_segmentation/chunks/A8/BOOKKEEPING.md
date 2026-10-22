# A8 — bookkeeping

A1b runs in parallel, so A8 did **not** edit `RESULTS.md`, `CONSTANTS.md` or
`PROGRESS.md`. The exact blocks to append are below, in the order they should
be applied.

---

## 1. `RESULTS.md` — append this block

```markdown
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
```

---

## 2. `CONSTANTS.md` — append these rows to the **Active** table

Column order matches the existing table: `Chunk | Name | Value | Cat |
Justification | Sweep | Retired by`.

```markdown
| A8 | confidence floor for removal | 0.70 | (c) + R2 | The VLM confidence below which a `remove` is refused, applied in code after unanimity. **Not tuned against A0, deliberately.** The separation A0 would fit it to is 0.02 wide — A7's one crop mislabel (component 5) at 0.58 against its one real weed (component 104) at 0.60–0.62 — while A7 measured the model's repeat-to-repeat confidence spread at 0.052–0.066, so a floor inside that window is fitted to noise (A7 named this hazard about its own result: "a coin on its edge, not a finding"). The value comes instead from A7's confabulation probe: six regions over ground-truth **pure straw**, prompted identically to real ones, returned 18/18 `keep` at a **mean confidence of 0.70**. 0.70 is the confidence this model expresses about a region containing no plant at all, so R2's "high confidence" cannot mean less. Consequence, reported not hidden: on `plants.jpeg` it admits **zero** targets and removes **zero** crop risk, because the keep-out test had already removed all of it. | 0.00 / 0.50 / 0.55 / 0.58 / 0.60 / 0.62 / 0.65 / **0.70** / 0.90 → targets 1/1/1/1/1/0/0/**0**/0, GT crop px under the tool **0 at every value**, GT weed px reached 71.3 % up to 0.60 then 0 %. `chunks/A8/results/a8_scores.json` → `sweep_confidence_floor` | B1 — which should test whether the floor is ever a dial rather than a switch, and retire it from the design if not |
| A8 | min label repeats | 2 | (c) + R4 | Independent VLM looks that must **agree** before a `remove` is considered. A count of observations, not a threshold on a continuous quantity. A7 measured that unanimity across 2 repeats removes a third of the catastrophic errors in its weaker conditions (6→4 under A/neutral, 17→12 under B/neutral) for the price of one extra call. Enforced structurally, not advisorily: supplying one look per instance refuses **all 207** instances with `insufficient_repeats` whatever the labels say (`test_one_look_can_never_open_the_gate`). | 1 vs 2 looks → 1/0 targets admitted at floor 0.00. Above 2 is untested: A7 ran 2 repeats and A8 did not commission more. | B1 — the flip rates carry no interval at 2 repeats |
```

**A7's row is now answered.** `A7 | confidence floor for `remove` | 0.00
shipped … | Retired by: A8` — A8 sets it to 0.70. If the register tracks that,
update A7's **Retired by** cell to point at the A8 row rather than leaving it
open.

**Reused unchanged, and deliberately not re-registered:** A6's
`DEFAULT_CLEARANCE_RDU` (1.0e-2 rdu, (b) placeholder awaiting C3) and
`DEFAULT_CELL_RDU` (3.5e-3 rdu, (a) resolution); A5's
`MAX_EXTRAPOLATION_SIGMA`, `GROUND_BAND_K`, `BASAL_BAND_K`, `MEDIAN_WINDOW`,
`MIN_AXIS_POINTS`; A2's datum σ; A0's 25 px minimum reviewable region via A7.
A8 introduces **no (d) constant**, no length in the image plane, and nothing
that encodes how gardens are arranged.

---

## 3. `PROGRESS.md`

### 3a. Status table — replace the A8 row

```markdown
| A8 | MCP tool surface and the safety gate | A5, A6, A7 | done | `chunks/A8/FINDINGS.md` |
```

And update the **Next up** line, which currently reads
`**Next up:** A1b + A8 (in progress, parallel) — the last two Phase A chunks.`
— once A1b lands too, Phase A is complete and B1 is the next chunk, blocked on
an image set.

### 3b. Log — append this entry

```markdown
### NNN — 2026-09-01 · A8: MCP tool surface and the safety gate

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
```

---

## 4. `.gitignore` — suggested additions

```gitignore
# A8: the keep-out distance table and the instance product (1.4 MB), the
# figures (3.3 MB), and the client-only conformance venv. Rebuild the products
# in ~40 s with `chunks/A8/build_products.py` and the figures in ~10 s with
# `chunks/A8/figures.py`; recreate the venv with the two commands at the top of
# `chunks/A8/requirements-client.lock.txt`.
chunks/A8/products/*.npz
chunks/A8/figs/*.png
chunks/A8/.venv-client/
```

**Deliberately NOT ignored** (small, and they are the chunk's evidence):
`chunks/A8/products/segment_garden_plants.json` (1.1 MB — the instance table a
reader needs to check any claim in FINDINGS), `target_list.json`,
`rejection_report.json`, `target_list_floor000_diagnostic.json`,
`gt_audit.json`, and everything in `chunks/A8/results/`.

Note the existing `chunks/**/*.npy` rule does not cover `.npz`, which is why
the rule above is explicit.
