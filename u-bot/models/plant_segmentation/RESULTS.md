# Results

Scores per chunk, on `plants.jpeg`. This table — not the status flags in
`PROGRESS.md` — is how we know whether anything actually improved.

Append a block per chunk. Always state what you compared against. If something
could not be measured, write "not measured" and why; never leave a blank that
reads as a pass.

---

## Baseline — ZeroPlantSeg, as published

**Config:** `ZeroPlantSeg/configs/squash.yaml`, `eps=100`, `min_samples=2`
**Image:** `plants.jpeg` resized to 768×1024
**Date:** 2026-08-30

Descriptive only. **Not scored against ground truth — A0 does not exist yet.**
Once A0 lands, re-score this baseline and record the numbers here so every
later chunk has something real to beat.

| Quantity | Value |
|---|---|
| Leaf mask candidates (stage 1) | 167 |
| Leaf instances (stage 2) | 127 |
| Plant instances (stage 3) | 5 |
| Squash fragments | **3** (ids 2, 4, 5) — should be 1 |
| Squash coverage | 52.2% of frame |
| Other plants | 2.6% (clover patch, id 3, correctly separated) |
| Grass | absorbed into the squash instance — **failure** |
| Runtime | ~8 min (stage 3 ≈ 2.4 s per leaf mask) |
| Per-class IoU | pending A0 |
| Instance F1 | pending A0 |
| Contact-point error | n/a — pipeline does not produce contact points |

**`eps` sensitivity** (from `recluster.py`, cached keypoints):

| eps | Instances | Reading |
|---|---|---|
| 40 | 65 | shattered |
| 60 | 24 | heavily fragmented |
| 80 | 16 | squash core forming |
| **100** | **5** | squash consolidates, clover stays separate |
| 130 | 4 | over-merged, clover absorbed |
| 160+ | 1 | everything one plant |

The 100→130 boundary is where the method fails. Recorded because any
replacement must be stable across a wider band than this.

**Prompt variant** (`configs/squash2.yaml`, `"broad flat leaf,grass blade,soil,dry straw"`):
23 masks → 17 leaf instances → 10 plant instances. Grass cleanly rejected, but
petioles dropped, so the plant fragments worse. Both failure modes trade
against each other — any A3 winner must keep petioles *and* reject grass.

---
