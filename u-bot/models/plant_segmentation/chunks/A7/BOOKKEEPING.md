# A7 — bookkeeping to merge into the repo-level files

I did not edit `RESULTS.md`, `CONSTANTS.md` or `PROGRESS.md` — A5 and A6 are in
progress in parallel. Below is the exact text to append to each, plus
`.gitignore` suggestions.

---

## 1. Append to `RESULTS.md`

```markdown
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
```

---

## 2. Append to `CONSTANTS.md` → Active

```markdown
| A7 | call-budget floor | 75 label px | (d) | Components below this are labelled `unsure` in code and never shown to the model. Purely a cost control — each per-instance call costs ~$0.09 and the call count is the whole cost of the chunk. Cut on region size alone and **blind to the ground truth** (`test_the_budget_floor_is_blind_to_the_ground_truth`), because a floor chosen by looking at which components are crop would decide the experiment's own answer. Silences 56 of 129 components holding **0.09 % of GT crop px and 0.00 % of GT weed px**; all 4 weed-majority components lie above it. | **required** — floor ∈ {25, 50, 75, 100, 150, 200, 300, 500} px → calls 129/85/73/55/44/40/28/19, crop px dropped 0.000/0.044/0.090/0.189/0.263/0.303/0.602/0.685 %, weed px dropped 0.00 % until floor 100 then 0.82 %. Direct audit: a seeded half of the silenced tier put through the shipped prompt gave **3 `keep`, 0 `remove`** on its 3 crop components (`results/tier2_audit.json`). | a real call budget, or B1 deciding it from data across images |
| A7 | min reviewable region | 25 px | (a) | **A0's registered constant, reused unchanged.** Below it a region cannot be judged by eye at the label grid, so no render can carry evidence about it either; such components are `unsure` by policy, never dropped. 78 of 207 components. | n/a | — |
| A7 | render context margin | 0.75 × the region's larger extent | (c) convention | Padding around a component's bbox in framing A's detail panels. **Scale-relative**, so it encodes no belief about how far apart plants grow (R1). | 0.00 / 0.75 / 3.00 over 36 hard-set components → keep 23/22/22, remove 3/2/1, crop→remove 1/1/1, but **41.7 % of individual labels changed**. `results/hard_scores_r2.json` | B1 |
| A7 | min render crop | 256 native px | (c) convention | Floor on the detail panel's source crop, so a small region is not upsampled more than ~3× past the sensor. A property of the render, not of the garden. | the pad sweep above subsumes it — at pad 0.00 this floor is what is binding for the smallest regions | — |
| A7 | montage tile | 1000 native px (3×4 tiles = the frame) | (c) convention | Framing B's tiling. Chosen to divide 3000×4000 exactly, so no region is cut by a tile edge more than once. **This constant turned out to be the operative variable in the A-vs-B result** — at this resolution a squash petiole is not separable from a grass blade — and it was not swept. | **not swept** — flagged as the chunk's main deferred experiment (FINDINGS § Not done) | B1 |
| A7 | confidence floor for `remove` | 0.00 shipped; swept 0.00–0.95 | (c) + R2 | Below this a `remove` is downgraded to `unsure`, in code. Shipped at 0.00 because the sweep shows the floor is a **cliff**: at 0.70 three of four conditions lose *all* weed reach along with all crop risk. A8 sets the real value. | 0.00/0.50/0.70/0.80/0.90/0.95 for every condition — `results/a7_scores.json` → `confidence_floor_sweep` | A8 |
| A7 | null-probe box | 20 label px, seed 20260901 | (a) | Size of the synthetic straw-only regions in the confabulation probe; ~78 native px, chosen to match the smallest real weed components so the stimulus is not distinguishable by scale. Placement is rejection-sampled over pixels A0 calls straw and A4 calls not-plant. | n/a — the probe's result (0/18 `remove`) is invariant to it at any size that renders | — |
```

**Note for whoever merges this.** One (d) constant, and it carries both a
parameter sweep and a direct empirical audit rather than only a sweep, because
what it actually risks is a *label* being missed rather than a metric moving.
It is the only constant in this chunk that exists for money rather than for
evidence, and `a7_data.py` says so at the definition site. The `montage tile`
row is registered as **not swept** on purpose: it is a (c) convention that the
results then revealed to be load-bearing, and hiding that behind a plausible
justification would be exactly the failure R1 exists to prevent. No constant in
A7 encodes a belief about how gardens are arranged, and A7 introduces no
constant with a unit of length in the world.

---

## 3. Append to `PROGRESS.md` → Log (and set A7 → `done` in the status table)

Status table row becomes:

```markdown
| A7 | VLM instance labelling | A4 | done | `chunks/A7/FINDINGS.md` |
```

Log entry:

```markdown
### NNN — 2026-09-01 · A7: VLM instance labelling

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
```

---

## 4. `.gitignore` suggestions

Append:

```gitignore
# A7: the stimulus PNGs (418 MB) and the figures (2.7 MB).
# Rebuild the renders in ~4 min with `run_a7.py render`; the replies cost $41
# and cannot be regenerated identically, so they are kept OUT of the ignore
# list deliberately — see the note below.
chunks/A7/renders/
chunks/A7/work/
chunks/A7/figs/*.png
```

**What to keep, and why.** `chunks/A7/results/` stays in the repository in
full — including `results/raw/`, all 511 raw replies at 4.1 MB. That is a
deliberate exception to this repo's habit of ignoring bulk artifacts, on two
grounds. First, the model is non-deterministic and the CLI version will move, so
these replies are **not reproducible**: deleting them destroys the only evidence
for every number in `RESULTS.md`, and re-running costs $41. Second, each record
carries its own model id, CLI version, prompt hash and full prompt text, which
is precisely what the roadmap's "prompt and model version recorded for
reproducibility" asks for — storing the summary and discarding the record would
satisfy the letter of that and not the point.

`renders/` is ignored because it is 418 MB and is a pure function of committed
code plus `plants.jpeg`. Note the consequence honestly: **the raw replies are
kept but the exact pixels they were shown are not**, so an audit reproduces the
stimulus from code rather than reading it off disk. `render.py` is deterministic
and `run_a7.py render` rebuilds it, but that is a reconstruction, not a record.
If the repo ever gains an artifact budget, the ~40 MB of framing-B montages are
the half worth keeping, because they are the stimulus the A-vs-B result turns on.

**One judgement call worth flagging.** `chunks/A7/results/hard_r2.json` embeds
the full raw reply text for each of the 126 hard-case calls (the `raw` field),
which duplicates `results/raw/`. It is left in place rather than stripped,
because the hard-case rationales are quoted directly in FINDINGS and having them
in one file makes the claim checkable without a join.
