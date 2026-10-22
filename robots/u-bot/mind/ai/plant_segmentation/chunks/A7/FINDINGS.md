# Chunk A7 — VLM instance labelling

**Date:** 2026-09-01 · **Model:** `claude-opus-5` via the `claude` CLI
**2.1.257**, non-interactive, images on disk · **Instances:** A4 `merge`
components, `a4_api.load_a4(tag="merge")` · **Ground truth:** `groundtruth/`
(A0) · **Repeats:** 2 per condition, byte-identical prompt · **Cost:** 511 model
calls, **$41.28**.

Prompts as sent: `prompts/rendered/`. Every reply, with its model id, CLI
version, prompt hash and full prompt text: `results/raw/`.

---

## Headline

Majority vote of 2 repeats, over the **73 components the model was asked about**.
`crop mislab` is crop-majority components called `remove` — the catastrophic
direction. `crop px` is the same failure in ground-truth crop *pixels*, which is
the threshold-free version. `weed px` is the benefit side.

| condition | crop mislab | **crop px at risk** | weed keeps | **weed px reached** | grass px | unsure | acc | flip |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **A / r2 (shipped)** | **1/24** | **0.1131 %** | 14/36 | **71.3 %** | 2.9 % | 47.9 % | 0.315 | 20.5 % |
| A / neutral | 4/24 | 0.5150 % | 5/36 | 73.9 % | 8.0 % | 57.5 % | 0.274 | 28.8 % |
| B / r2 | 5/24 | 0.6688 % | 0/36 | 71.3 % | 7.6 % | 69.9 % | 0.233 | 12.3 % |
| B / neutral | 12/24 | 1.4218 % | 0/36 | 74.0 % | 10.5 % | 37.0 % | **0.397** | 28.8 % |
| baseline — A3 material vote, no VLM | 18/24 | 1.5953 % | 2/36 | 73.9 % | 12.2 % | 0.0 % | **0.548** | — |
| baseline — all `keep` | 0/24 | 0.0000 % | 36/36 | 0.0 % | 0.0 % | 0.0 % | 0.507 | — |
| baseline — all `remove` | 24/24 | 99.8602 % | 0/36 | 100.0 % | 99.6 % | 0.0 % | 0.493 | — |

**The three answers the roadmap asks for, plainly.**

* **Which framing is more reliable? Framing A, decisively, and on the only axis
  that matters.** At *identical* weed reach (71.3 % both), per-instance
  classification puts **0.113 %** of the crop under the tool against framing B's
  **0.669 %** — **5.9× less crop at risk for the same benefit**. Under the
  neutral prompt the gap is the same shape: 0.515 % vs 1.422 % at 73.9 % vs
  74.0 % weed reach, **2.8×**. Framing B is better at exactly one thing — it is
  twice as *stable* (12.3 % vs 20.5 % flip rate) — and being stably wrong about
  the crop is not a recommendation.
* **Does it say `unsure`, or confabulate?** It says `unsure`, and on the
  controlled probe it does not confabulate at all. Six regions drawn over
  material A0 labels as **pure straw**, prompted identically to real ones:
  **18 of 18 judgements were `keep`, zero `remove`, confabulation rate 0.0 %**,
  and every rationale said in so many words that there was no living foliage
  there ("only dry brown straw/mulch debris, no living green foliage; nothing
  weedy to cut here"). It did not invent a plant to have an opinion about.
* **Does the VLM notice the mixed component?** **Framing A does; framing B never
  does.** Component 1 holds 98 % of the ground-truth crop *and 83 % of the
  grass* (A4). Framing A flagged it `mixed` in **2 of 2** shipped repeats,
  unprompted — *"Mostly squash foliage/fruit, but the mask also picks up bits of
  grass and small volunteers."* Framing B flagged it in **0 of 4** repeats
  across both variants, at confidence 0.97, while flagging 26–27 *other*
  components as mixed.

**Against the baseline this layer has to beat.** The stack could already decide
crop-vs-weed without a VLM, by voting A3's material class per A4 component —
A4's Open Question 2 policy. That baseline puts **1.5953 %** of the crop under
the tool. A/r2 puts **0.1131 %** there: **14× less crop at risk**, at 71.3 % vs
73.9 % weed reached. **The semantic layer earns its place, and it earns it on
R2 grounds rather than on accuracy.**

---

## What was built

`A4 merge components → triage → render → one CLI call → validate → label JSON`.

1. **Triage, in two tiers, and no ID is ever dropped.** 207 components. 78 fall
   below A0's registered 25 px minimum reviewable region — no render can carry
   evidence about them. A further 56 fall below A7's own 75 px **call-budget**
   floor. Both tiers are labelled `unsure` **by policy, in code**, with the
   policy recorded as the rationale, and both are present in every output file.
   73 components are actually shown to the model. The two floors are kept apart
   in the code and in this document because one is an evidence limit and the
   other is a money limit, and conflating them would launder the second into the
   first.
2. **Rendering** (`render.py`) is the only place image geometry becomes pixels.
   Framing A's stimulus is three panels — the whole frame with the region
   tinted, a zoom with it outlined, and *the identical zoom with nothing drawn
   on it*. The third panel exists because A3 measured that OVSeg-style
   crop-and-fill destroys the surround; here the marking is additive and the
   material can always be seen as it really is. Framing B's stimulus is the
   frame in 12 full-resolution tiles with every region outlined and stamped with
   its ID, plus an unmarked overview. `figs/fig_stimulus.png`.
3. **Two framings × two prompt variants.** Framing **A** is one call per region.
   Framing **B** is one call that describes the scene with no region numbers
   anywhere, then a second call that binds that description to every ID at once.
   The variants differ in exactly one paragraph — `neutral` says both mistakes
   cost the same, `r2` states the asymmetry — and the two paragraphs are matched
   for length and register, so the difference is attributable to the claim and
   not to verbosity (`test_variants_differ_in_exactly_one_paragraph`).
4. **R3 enforced in code** (`schema.py`), not requested in prose. The schema is
   closed to six keys; geometric key names are rejected; the free-text fields
   are scanned for coordinate pairs, units of length and geometry words. A reply
   that fails is **not patched** — it falls back to `unsure`, which is R2's
   default applied by the code rather than by the model.
5. **Isolation.** Every call runs with its working directory inside a scratch
   arena containing nothing but render PNGs. This repository's `CLAUDE.md`
   states the crop, names the weeds and spells out R2 and R3; a model invoked
   inside the project would read all of it and the experiment would measure a
   leak. Two tests assert no `CLAUDE.md` is reachable at or above the arena and
   that nothing but PNGs is in it.

---

## What was measured

### 1. Framing A vs framing B — and *why* B loses

The aggregate does not show it. B/neutral has the **best** accuracy of any VLM
condition (0.397) and the **worst** crop risk (1.422 %). The mechanism is
visible only in the rationales, and it is one specific confusion:

> **B, on component 6** (crop-majority, crop fraction 0.72): *"Cluster of narrow
> arching grass blades crossing the scene, no lobes, teeth or bristly petiole."*
> **B, on component 20** (crop fraction 0.95): *"Grass foliage: stiff strap
> blades fanning out of the mulch, no reticulate venation."*

**All six** of B/r2's crop mislabels in rep 1 are squash material read as
**grass** — every one of the six rationales names a blade, a strap or parallel
venation. Not a scatter of errors with a common cause: one error, six times.
At tile resolution, with only an outline and a number, a thin squash petiole or
a leaf sliver is not distinguishable from a grass blade. Framing A's dedicated
zoom is; its single mislabel (component 5, at confidence 0.58) has the identical
mechanism and is the only one left.

**This is A4's forwarded hazard arriving exactly as predicted** — "the VLM will
be asked *is this a weed?* about a component that is mostly squash and partly
grass" — and it is a *rendering* problem, not a reasoning problem. See §3.

### 2. The prompt prose moves the R2-critical confusion, and the aggregate lies

A3's warning, restated: rewriting prose moved one specific confusion 5× while
the aggregate stayed flat. It reproduces here, in the same direction, and the
aggregate does worse than stay flat — it moves the *wrong way*.

| | crop px at risk | weed px reached | **accuracy** |
|---|---:|---:|---:|
| A / neutral | 0.5150 % | 73.9 % | 0.274 |
| **A / r2** | **0.1131 %** (**4.6× safer**) | 71.3 % (−2.6 pt) | 0.315 |
| B / neutral | 1.4218 % | 74.0 % | **0.397** |
| **B / r2** | **0.6688 %** (**2.1× safer**) | 71.3 % (−2.7 pt) | 0.233 (**−0.164**) |

Stating the asymmetry roughly halves the crop at risk in both framings for under
three points of weed reach, and in framing B it does so while accuracy **falls
by 0.164**. A single aggregate would have called the R2 paragraph a regression.
It also removed confabulation entirely: components whose ground truth is *not a
plant* were called `remove` 5/13 times under B/neutral and **0/13** under B/r2.

### 3. The seedling boundary, reached by taking the context away

`plants.jpeg` contains no squash seedling, so the brief's failure mode — a crop
volunteer and a weed that look nearly identical — cannot be sampled directly. It
is reached the only honest way one image allows: **a small squash leaf fragment
with its vine cropped out is visually a broadleaf seedling.** The 36 hard-set
components (rule fixed before scoring: crop-majority components other than the
crop itself, weed-majority components, and grass-majority components holding
≥ 10 % crop) were re-rendered at `pad_fraction` 0.00 and 3.00 against the
shipped 0.75, with nothing else changed. `figs/fig_hard_context.png`.

| pad | keep | remove | unsure | crop → remove |
|---|---:|---:|---:|---:|
| 0.00 — context removed | 23 | 3 | 10 | 1/23 |
| **0.75 — as shipped** | 22 | 2 | 12 | 1/23 |
| 3.00 — context restored | 22 | 1 | 13 | 1/23 |

**The distribution barely moves and the individual labels churn underneath it:
15 of 36 regions (41.7 %) did not get the same label at all three pads.** The
aggregate is stable; the decisions are not. Only one flip is in the dangerous
direction — component 20, crop fraction 0.95, `keep` (0.72) as shipped and
`remove` (0.68) once its surround is cropped away — and it is the clearest
single picture in the chunk of what a real seedling would cost.

**Reading:** the model is substantially reading the *context*, not the leaf.
When the vine, the fruit and the neighbouring lobed leaves are in frame it gets
the fragment right; when they are not, a squash sliver becomes a weed. For a
seedling — which by definition has no vine, no fruit and no lobed neighbours —
the honest expectation from this measurement is that **it would fail**, and that
the failure would be in the catastrophic direction.

### 4. Confabulation: it does not

Six regions over pure straw, prompted identically to real ones, 3 repeats each.
**18/18 `keep`, 0 `remove`, mean confidence 0.70.** Zero confabulation at the
`remove`-at-confidence-≥-0.70 definition, and zero at any definition — it never
said `remove` at all. The rationales are honest about *why*, naming straw and
the absence of living foliage in all six.

One schema gap this exposed, and A8 needs it: the label set has **no "there is
no plant here" option**, so `keep` is doing double duty for "this is crop" and
"there is nothing to cut". Both are safe under R2, so nothing is wrong with the
output — but A8 must not read a `keep` as evidence of a crop plant.

### 5. Stability, and the fact that looking twice is itself a safety mechanism

Flip rate is the fraction of the 73 components that did not get the same label
in both repeats: **A/r2 20.5 %, A/neutral 28.8 %, B/r2 12.3 %, B/neutral
28.8 %.** Mean confidence spread across repeats is small (0.052–0.066), so the
model is not wavering about its confidence — it is changing its mind.

With two repeats a "majority vote" is really **unanimous-else-`unsure`**, and
that tie-break is on R2's safe side. It shows up as the majority-vote column
sitting *below* the range of the two runs it summarises:

| condition | crop mislabels, per repeat | unanimity-of-2 |
|---|---:|---:|
| A / r2 | 1 – 1 | **1** |
| A / neutral | 6 – 6 | **4** |
| B / r2 | 6 – 7 | **5** |
| B / neutral | 12 – 17 | **12** |

**Running the model twice and requiring agreement removes a third of
A/neutral's catastrophic errors and up to a third of B/neutral's, for the price
of one extra call.** That is R4 — prefer looking again over trusting one look —
applied to the semantic layer, and it is the cheapest safety win in the chunk.

### 6. The confidence floor, and why it cannot simply be turned up

`score.py` sweeps the floor below which a `remove` is downgraded to `unsure`;
this is the curve A8's gate is set from. `figs/fig_operating.png`.

| floor | A/r2 crop px | A/r2 weed px | A/neutral crop px | A/neutral weed px | B/r2 crop px | B/r2 weed px |
|---|---:|---:|---:|---:|---:|---:|
| 0.00 | 0.1131 % | 71.3 % | 0.5150 % | 73.9 % | 0.6688 % | 71.3 % |
| 0.50 | 0.1131 % | 71.3 % | 0.4944 % | 73.9 % | 0.6428 % | 71.3 % |
| **0.70** | **0 %** | **0 %** | **0 %** | **71.3 %** | **0 %** | **0 %** |
| 0.90 | 0 % | 0 % | 0 % | 0 % | 0 % | 0 % |

At a floor of 0.70 every condition reaches zero crop at risk — and **three of the
four also reach zero weed**. The gate does not discriminate; it switches the
system off. Only A/neutral survives it with its benefit intact, which on this
image looks like the dominant operating point: zero crop at risk *and* 71.3 %
weed reached, strictly better than A/r2 at any floor.

**That result is one component wide and it should not be shipped as a
recommendation.** 71.3 % of all ground-truth weed pixels is component 104 and
nothing else (the next largest weed component holds 2.2 %). The whole weed-reach
axis on this image is a single binary event: did the model call component 104
`remove`? Its confidence was **0.72 under `neutral` and 0.60–0.62 under `r2`** —
so "A/neutral dominates at floor 0.70" is the statement that one component's
confidence landed 0.02 above a threshold. That is a coin on its edge, not a
finding, and it is recorded here so that A8 does not inherit it as one.

The real lesson is the one that survives: **the R2 prose and the confidence
floor are partly redundant, and stacking them over-suppresses.** The prose
already shifts the confidence distribution down; the floor then removes
everything. Put the asymmetry in *one* place.

### 7. R3, and the tier-2 budget floor

**Zero R3 violations of any kind, in any condition — 0 hard, 0 soft, across all
584 model-authored labels.** No coordinate, no bounding box, no measurement, and not
even a frame-relative phrase ("lower left of the frame"), which the validator
records as a soft hit rather than rejecting. The model was given IDs and used
IDs. The prompt asking for this is not why it held — `schema.py` is — but on
this model, with this prompt, it did not need to fire.

Framing B's binding, which was the obvious thing to expect to break, did not:
**73 of 73 IDs returned, 0 omitted, 0 hallucinated IDs, 0 rejects, in every one
of the 4 repeats.** B's failure is semantic, not structural.

The 75 px call-budget floor was audited rather than assumed. It silences 56
components holding **0.09 % of the crop pixels and 0.00 % of the weed pixels**,
and all four weed-majority components lie above it. A seeded random half of the
56 (28 components) was then put through the shipped prompt anyway: of the 3
crop-majority components in the sample, **3 `keep`, 0 `remove`**. The floor cost
nothing in the R2-critical direction on this sample. Cost of knowing: $2.42.

---

## What was decided

1. **Framing A ships.** Per-instance classification, one call per region, at
   5.9× less crop at risk than the global-description framing for identical weed
   reach. Framing B is kept in the repository because its *scene description* is
   excellent (§ surprised us, 2) and A8 or B1 may want it as a prior; its
   ID-binding is not the mechanism to build on.
2. **The asymmetry goes in the code, not in the prompt — but the prompt keeps
   it too, for now.** The shipped condition is A/r2 because it is the safest
   single point measured without relying on a threshold. The measurement in §6
   says the prompt-side and code-side asymmetries interact badly, and B1 should
   test putting it *only* in code; this image cannot settle it because the weed
   axis is one component wide.
3. **Two repeats with unanimity required is part of the output contract**, not
   an evaluation convenience. It is R4 applied to semantics and it is measurably
   worth its cost (§5).
4. **No ID is dropped, ever, at either triage tier**, and every fallback is
   `unsure` at confidence 0.0. Four tests enforce it.
5. **The label vocabulary is insufficient and A8 must not paper over it.**
   `keep` means both "this is crop" and "there is nothing here to cut" (§4).
6. **A transport failure is not an answer.** See below.

---

## What surprised us

1. **The first attempt at this chunk scored 90 usage-limit notices as
   `unsure`.** `vlm.call` cached whatever the CLI returned; a session limit
   returns exit code 1 with the string *"You've hit your session limit · resets
   2pm"* sitting in the `result` field. Those were cached as model replies,
   parsed as unparseable, and converted to `unsure` by the fallback path — which
   is R2's *correct* behaviour for a bad reply and therefore completely silent.
   The run "completed" with a label distribution that was a billing artifact.
   **The failure mode is specific and worth naming: a safety default that
   swallows a transport error produces a plausible, safe-looking, entirely
   fictitious result.** Those runs were discarded, not repaired;
   `vlm.is_transport_failure` now aborts loudly and refuses to write, and
   `test_no_shipped_run_holds_a_transport_failure` asserts no shipped label
   carries the fingerprint.
2. **Framing B's scene description is genuinely excellent, and it does not
   help.** Unprimed, with no region numbers in the images, it named the crop as
   *"Winter squash (Cucurbita, kabocha/buttercup-type — most consistent with
   Cucurbita maxima)"* and the weeds as grass, purslane, mallow/ground-ivy and
   clover — **matching A0's instance list species-for-species** (`squash`,
   `weed_purslane`, `weed_mallow`, two clover patches, four seedlings), in all
   four repeats. It then went further and *predicted its own failure* in the
   `hard_to_tell_apart` field: *"grass blades lie directly across and behind the
   squash leaves and petioles, so at the boundaries a region can contain both,
   and a narrow grass strap merges into the leaf beneath it."* It then committed
   exactly that error, 12 times under `neutral`. **The semantic knowledge was
   never the bottleneck; binding it to a numbered outline at tile resolution
   was.** That is a rendering budget, not a reasoning budget, and it is the
   single most actionable thing in this chunk.
3. **The prompt leaked the answer, in the field designed to detect the leak.**
   `SCHEMA_COMMON` illustrated the `mixed` field with *"for example crop leaf
   and grass blades together"* — handing the model the one fact A7 exists to
   test, in the very field used to measure whether it noticed. It was caught by
   `test_prompt_never_names_the_crop_or_the_weeds`, which had been written and
   never run against the final wording. One completed repeat (129 calls, ~$12)
   was discarded rather than reported. **Framing A's 2/2 mixed detection on
   component 1 is from the de-leaked prompt**; had the leak shipped, the
   headline finding of this chunk would have been an artifact of its own prompt.
4. **Accuracy points the wrong way, twice, and it would have picked the worst
   system.** The single best accuracy in the whole table belongs to the *no-VLM
   baseline* (0.548), which puts 14× more crop under the tool than the shipped
   condition. Among VLM conditions the best accuracy (B/neutral, 0.397) is the
   worst on crop risk. A3 warned that the aggregate hides the confusion; on this
   chunk the aggregate does not merely hide it, it **inverts the ranking**.
5. **The model is more conservative than its own confidence suggests, and it
   uses a narrow band.** Mean confidence on `keep` is 0.647–0.670 and on
   `remove` 0.518–0.625 across every condition — a ~0.15 spread covering the
   entire decision. It essentially never expressed high confidence about
   anything, which is why the floor sweep in §6 is a cliff rather than a curve:
   there is almost no probability mass between 0.62 and 0.72 to tune against.
6. **`keep` on 14 of 36 weed components did not cost weed reach at all.** A/r2
   keeps far more weed components than any other condition (14/36 vs B's 0/36)
   and reaches *the same* 71.3 % of weed pixels. The components it keeps are
   tiny; the one that matters it removes. Component counts and pixel mass
   disagree violently in this scene, which is why both are reported and why the
   pixel version is the one called threshold-free.
7. **The context ablation moved 42 % of individual labels while moving the
   aggregate by one component.** Reporting only the per-pad totals would have
   concluded "context does not matter". Reporting the per-region agreement says
   the opposite, and it is the per-region answer a robot acts on.

---

## Not done / deferred

* **One image**, as with every Phase A chunk — and here the limitation bites
  harder than usual: **the weed-reach axis is one component wide** (§6). Every
  statement in this document about *benefit* rests on a single binary event.
  The crop-risk axis is better supported (24 crop components, 421 926 px).
* **No real seedling.** The context ablation is a proxy and is labelled as one.
  A squash volunteer beside a weed seedling is a B1 capture-protocol item, and
  it is the single most valuable image the project could add for this chunk.
* **Two repeats, not more.** Enough to detect instability, not enough to
  estimate its rate precisely; the flip rates carry no interval.
* **One model.** No comparison across models or across sizes, and the finding in
  §5 that confidences occupy a 0.15-wide band may be specific to this one.
* **The 75 px budget floor is a (d) constant.** It is audited (§7) and blind to
  the ground truth by construction, but it exists because calls cost $0.09 each,
  and it is the only constant in this chunk that is about money.
* **Framing B was never given framing A's stimulus.** The comparison is
  framing-and-resolution confounded: B is one call *and* tile resolution *and*
  all IDs at once. §1 argues the resolution is the operative variable, from the
  rationales, but the clean ablation — B's one-call binding over A's zoomed
  crops — was not run. That is the experiment B1 should run first.
* **No `mixed` ground truth.** A0 has no per-component "is this mixed" label, so
  the mixed-flag result is reported as a rate against the one component known
  from A4 to be mixed, not scored.

---

## Constants introduced

See `BOOKKEEPING.md` for the exact `CONSTANTS.md` rows. One **(d)** — the 75 px
call-budget floor, with its sensitivity audited in §7 and its retiring
condition named — and three **(c) conventions** for the render geometry, swept
in §3. Every other value is reused unchanged from A0.

---

## Implications for the roadmap

* **A8 — the gate.** Take the labels from `results/labels_A_r2_r*.json`, require
  **unanimity across two repeats** (§5), and note that the confidence floor is a
  cliff, not a dial (§6): a floor of 0.70 zeroes the crop risk *and* the weed
  reach on this image. Do not set the floor from this chunk's numbers alone. Two
  further contract points: a `keep` may mean "nothing here", not "crop" (§4);
  and `unsure` is 48–70 % of components, so the gate's dominant behaviour will
  be refusal, which is correct and should be reported rather than tuned away.
* **A8 — the mixed flag is a hard input.** Component 1 is flagged `mixed` and it
  holds 83 % of the grass. Under R2, a `remove` inside a component flagged
  `mixed` should be refused outright, because the component is not a plant.
* **A5 / A6** are unaffected — A7 emits no geometry by construction.
* **B1 — three questions, in priority order.** (i) Does the A-vs-B gap survive
  giving B the same resolution? The rationales say resolution is the operative
  variable and the ablation was not run. (ii) A real squash seedling next to a
  weed seedling; §3 predicts a catastrophic-direction failure and that
  prediction should be tested, not assumed. (iii) Does the prompt-side/code-side
  redundancy in §6 reproduce where the weed axis is not one component wide?
* **A0 — one gap this chunk hit.** There is no ground truth for "this component
  contains more than one plant", so the mixed-flag finding is a rate rather than
  a score. If A0 is ever re-versioned, a per-component mixture flag is cheap and
  would make the Headline's third answer measurable instead of merely observed.
* **Every chunk that shells out to a model.** A safety default that converts a
  failed call into a safe label is not safe — it is silent (§ surprised us, 1).
  Transport failure and model uncertainty must be different code paths.
