# A7 — VLM instance labelling

The semantic layer. Given the A4 `merge` components, ask a vision model which
ones a weeding tool may cut, and report the answer as `keep` / `remove` /
`unsure` per instance ID — **with no coordinate anywhere in the reply (R3)**.

Read `FINDINGS.md` for what was measured and decided. This file is how to run it.

## The short version

| | |
|---|---|
| Instances labelled | A4 `merge` components, `a4_api.load_a4(tag="merge")` — **207**, of which **73** are shown to the model |
| Model | `claude-opus-5` via the `claude` CLI, non-interactive, images on disk |
| Framings compared | **A** one call per region · **B** one global scene description, then one call binding it to every ID |
| Prompt variants | `neutral` (both mistakes equally costly) vs `r2` (crop loss catastrophic, default to keep) |
| Repeats | 2 per condition, byte-identical prompt |
| Ground truth | `groundtruth/` (A0) |
| Output | `results/labels_{framing}_{variant}_r{rep}.json` — ID → label, confidence, rationale |

## Layout

| Path | What it is |
|---|---|
| `a7_data.py` | components, the two triage tiers, and the A0 ground-truth accounting per component |
| `render.py` | **the only place image geometry becomes pixels.** Framing A's 3-panel stimulus and framing B's numbered montage |
| `prompts.py` | every prompt fragment; the exact text sent is also written to `prompts/rendered/` |
| `schema.py` | the output contract, and **R3 enforced in code** — coordinates are rejected, not requested-against |
| `vlm.py` | the CLI call, the isolated arena, and the transport-failure guard |
| `run_a7.py` | runs framings A and B |
| `hard.py` | the context ablation (the seedling proxy), and the null-region confabulation probe |
| `tier2_audit.py` | what the call-budget floor silenced, measured |
| `baseline.py` | the no-VLM baselines this layer has to beat |
| `score.py` | scoring against A0 — the R2-critical confusion first, aggregate accuracy second |
| `figs.py` | figures |
| `test_a7.py` | 32 assertions: R3, no-ID-dropped, keep-by-default, arena isolation, prompt hygiene |
| `BOOKKEEPING.md` | the exact text to merge into `RESULTS.md`, `CONSTANTS.md`, `PROGRESS.md` |

## Reproducing

Rendering and scoring reuse A3's venv; the model calls need the `claude` CLI on
`PATH` and an authenticated session.

```bash
cd chunks/A7
../A3/.venv/bin/python -m pytest test_a7.py -q     # 32 assertions, no network

../A3/.venv/bin/python run_a7.py render            # ~4 min, 73 + 26 PNGs, 268 MB
../A3/.venv/bin/python baseline.py                 # free, no model

./run_all.sh                                       # every condition, ~1 h, ~$40
../A3/.venv/bin/python tier2_audit.py              # ~24 calls
../A3/.venv/bin/python score.py                    # prints the table
../A3/.venv/bin/python figs.py
```

`run_all.sh` is **resumable**. Every model reply is cached under `results/raw/`
by condition and region, so a run that dies partway re-uses everything that
completed. A reply that never arrived — a usage limit, a timeout, a crash — is
*never* cached (`vlm.TransportError`), so a resume repeats exactly the calls
that failed and nothing else.

## Three things that are easy to get wrong here

**1. The model must not be able to read this repository.** Every call runs with
its working directory inside a scratch arena holding nothing but render PNGs.
`CLAUDE.md` at the project root states the crop, names the weeds, and spells out
R2 and R3; a model invoked inside the project would read all of it as context
and the experiment would measure a leak instead of a capability.
`test_arena_is_isolated` asserts no `CLAUDE.md` is reachable at or above the
arena, and `test_arena_holds_only_images` asserts nothing but PNGs is in it.

**2. The prompt must not name the answer.** `test_prompt_never_names_the_crop_
or_the_weeds` greps every fragment for `squash`, `clover`, `grass`, `straw` and
friends. It caught a real leak: the first draft illustrated the `mixed` field
with "for example crop leaf and grass blades together", which hands over the one
fact the chunk exists to test. See FINDINGS § *What surprised us*.

**3. A non-answer is not an `unsure`.** The first attempt at this chunk cached
90 usage-limit notices as if they were model replies and scored them as
`unsure`. Those runs were discarded, not repaired. `vlm.is_transport_failure`
and `test_no_shipped_run_holds_a_transport_failure` are what stop it recurring.

## What this chunk does not do

Acting on the labels is A8. Nothing here plans a motion, chooses a target, or
touches a coordinate — by construction, not by convention. The output is a label
per ID and the confidence-floor curve that A8's `plan_removals` gate is set from.
