# A3 — plant material segmentation

Four approaches to per-pixel material class, all scored against the A0 ground
truth on its 768x1024 grid with `chunks/A0/eval.py`. Results in `FINDINGS.md`,
scores in `results/comparison.md`, numbers for the tracking files in
`BOOKKEEPING.md`.

**The shipped default is `a3_api.segment_material()`** — a logistic probe on
frozen DINOv2 patch features, fitted on the 42 patches in `seed_patches.json`.

```python
import sys; sys.path.insert(0, "chunks/A3")
from a3_api import segment_material
out = segment_material()
out.material      # (1024, 768) uint8, A0 material class ids
out.confidence    # (1024, 768) float32, max class probability (uncalibrated)
out.provenance    # what it is, what it scored, what it does not use
```

## Environment

New venv, `chunks/A3/.venv` (Python 3.11, torch 2.13.0 + MPS, transformers
5.16.1, scikit-learn 1.9.0). Lock in `requirements.lock.txt`. SAM still runs
from `ZeroPlantSeg/.venv`, which is untouched.

```bash
uv venv --python 3.11 chunks/A3/.venv
uv pip install --python chunks/A3/.venv/bin/python \
    torch torchvision transformers scikit-learn scipy numpy pillow matplotlib
```

## Rebuild, in order

```bash
# 1. the independent SAM partition (~13 min on MPS, ZeroPlantSeg venv)
cd ZeroPlantSeg && export PYTORCH_ENABLE_MPS_FALLBACK=1 PYTHONPATH=.
.venv/bin/python ../chunks/A3/sam_regions.py --prefix a3f_ \
    --pps 64 --iou 0.82 --stab 0.90 --mmra 25
.venv/bin/python ../chunks/A3/sam_regions.py            # the coarse one, ~80 s
cd ..

# 2. build the two region maps (writes work/regions_a3f.npy, regions_a3.npy)
chunks/A3/.venv/bin/python -c "
import sys, numpy as np; sys.path.insert(0,'chunks/A3'); import a3_common as A
for p in ('a3_','a3f_'):
    np.save(f'chunks/A3/work/regions_{p[:-1]}.npy', A.build_partition(A.load_masks(p)))"

# 3. the four approaches
export PYTORCH_ENABLE_MPS_FALLBACK=1
chunks/A3/.venv/bin/python chunks/A3/shape_prior.py --partition a3f   # 1 and 2
chunks/A3/.venv/bin/python chunks/A3/dino_probe.py                    # 3
chunks/A3/.venv/bin/python chunks/A3/dino_region.py --partition a3f   # 3b
for m in google/siglip2-base-patch16-384 openai/clip-vit-large-patch14 \
         google/siglip2-so400m-patch14-384; do                        # 4
  chunks/A3/.venv/bin/python chunks/A3/open_vocab.py --partition a3f --model $m
done

# 4. the height ablation, the table, the figures, the default, the tests
chunks/A3/.venv/bin/python chunks/A3/height_report.py
chunks/A3/.venv/bin/python chunks/A3/make_seed_patches.py
chunks/A3/.venv/bin/python chunks/A3/a3_api.py --score
chunks/A3/.venv/bin/python chunks/A3/compare.py
chunks/A3/.venv/bin/python chunks/A3/figures.py
chunks/A3/.venv/bin/python chunks/A3/test_a3.py
chunks/A3/.venv/bin/python chunks/A3/alpha_clip_check.py
```

## Files

| File | Role |
|---|---|
| `a3_api.py` | **the default.** Frozen DINOv2 + a 42-patch logistic probe |
| `seed_patches.json` | the 42 fitted patches, with their provenance stated |
| `a3_common.py` | partition construction, region features, blocked CV, scoring |
| `sam_regions.py` | the independent SAM run, and why A0's partition is not reused |
| `shape_prior.py` | approaches 1 and 2, plus the feature-group ablation grid |
| `dino_probe.py` | approach 3, plus the height ablation inside the winner |
| `dino_region.py` | approach 3b — the same features on the SAM substrate |
| `open_vocab.py` | approach 4: SigLIP 2 / CLIP, 3 crop variants x 2 vocabs x 2 prompt modes |
| `alpha_clip_check.py` | why approach 4 is SigLIP 2 and not Alpha-CLIP |
| `height_report.py` | A2's height channel scored against A0 labels for the first time |
| `make_seed_patches.py` | freezes the shipped patch set |
| `compare.py` | the one comparison table + the probe C and patch-count sweeps |
| `figures.py` | five figures, all checked by eye |
| `test_a3.py` | 18 tests; the load-bearing ones are the CV-blindness and partition-leak tests |

`work/` (gitignored) holds the SAM masks, region maps and cached DINOv2
features. `preds/` holds one label-map PNG per approach; `results/` the JSON.

## The one thing to know before reading any number

A0's ground truth was painted region-by-region onto A0's **own** SAM partition.
Classifying those same regions therefore has a ceiling of **exactly 1.0** and
zero boundary error — `test_a3.py::test_a0_partition_ceiling_is_one` asserts it.
So A3 ran SAM again with different settings and every headline number is on that
independent partition, whose ceiling is **0.9246**.
