# Garden weeding perception

Perception stack for autonomous garden weeding: segment plants, decide crop vs.
weed, and return 3D stem-soil points a weeding arm can target. Research-stage,
implemented in chunks across many sessions.

## Where things live

| File | Role |
|---|---|
| `RESEARCH_ROADMAP.md` | **The contract.** Chunk goals and done-criteria. Change only on a deliberate scope decision, never to match what got built. |
| `PROGRESS.md` | Status table + append-only session log. Never edit or rewrite past entries. |
| `CONSTANTS.md` | R1 register. Every numeric constant with its justification category. |
| `RESULTS.md` | Eval scores per chunk. The real measure of progress. |
| `chunks/<id>/` | Per-chunk artifacts and `FINDINGS.md`. |

## Standing rules (full text in RESEARCH_ROADMAP.md § Design rules)

- **R1 — Threshold rule.** Every numeric constant traces to (a) instrument,
  (b) tool geometry, (c) observation, or (d) assumed-with-sensitivity-sweep.
  Register it in `CONSTANTS.md`. A (d) constant with no sweep is a defect.
  No constant may encode a belief about how gardens are arranged.
- **R2 — Asymmetric cost.** Destroying a crop plant is catastrophic; leaving a
  weed standing is not. Every decision defaults to keep.
- **R3 — Separation.** The VLM labels instances by ID and never emits
  coordinates. Geometric safety checks run in code, after labelling.
- **R4 — Look again.** Prefer re-observation over a fabricated estimate.

## Starting work

`/goal <chunk-id>` — e.g. `/goal A0` — loads that chunk's brief from the roadmap.

Do not start a chunk whose dependencies are not `done` in `PROGRESS.md`.
Phase B needs more images; Phase C needs robot hardware. Both are blocked.

## Definition of done

A chunk is finished only when all four are true:

1. `chunks/<id>/FINDINGS.md` written — what was built, what was measured, what
   was decided, and what surprised us.
2. Scores appended to `RESULTS.md` and compared against the recorded baseline.
3. Any new constants registered in `CONSTANTS.md`.
4. An entry appended to `PROGRESS.md`.

Claiming a chunk done without scores is the failure mode this checklist exists
to prevent. If something could not be measured, say so explicitly.

## Environment

ZeroPlantSeg is ported and working on Apple Silicon (MPS):

```bash
cd ZeroPlantSeg
export PYTORCH_ENABLE_MPS_FALLBACK=1 PYTHONPATH=.
.venv/bin/python <script>
```

That venv is **patched** — see `ZeroPlantSeg/zps_device.py` and the porting
notes in the roadmap. Record any dependency change in `PROGRESS.md`.
Weights live in `ZeroPlantSeg/{weights,GroundingDINO/weights,OVSeg/weights}/`.

Source data: `plants.jpeg` (3000×4000, no EXIF, third-party camera) and
`plants_depth.webp` (8-bit preview — not geometry-grade; A1 replaces it).
