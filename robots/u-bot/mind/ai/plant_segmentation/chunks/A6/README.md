# A6 — Keep-out volumes

The protected region around a crop plant, built from the plant's **own observed
3-D geometry** rather than from a radius, plus a fast `is_inside(point)` test
for A8's safety gate.

```python
import sys; sys.path.insert(0, "chunks/A6")
from a6_api import load_a6

k = load_a6()                       # the shipped squash keep-out, ~1 s
k.is_inside(xyz)                    # (3,) or (N, 3) camera-frame rdu -> bool
k.classify(xyz)                     # OUTSIDE / INSIDE / UNKNOWN
k.is_inside(xyz, clearance=0.02)    # any clearance up to max_clearance_rdu
k.clearance_rdu                     # 1.0e-2 — a PLACEHOLDER, category (b)
k.volume_rdu3(0.02)                 # rdu^3
k.footprint(0.02)                   # the shadow on the datum plane
```

**Read `FINDINGS.md` before using this.** Two things about this product are
easy to misuse and are not opinions:

1. **Every length is in rdu**, and the clearance is in rdu. When C3 measures a
   real tool clearance it will arrive in millimetres and **cannot be compared
   to this number** until C0 supplies an absolute scale.
2. **The volume built from A4's `merge` component covers 87 % of the
   photograph** at the placeholder clearance and shields 87 % of the
   ground-truth weed material — three quarters of which A4's component already
   contained before A6 added anything. It protects the crop essentially
   perfectly and it protects most of the weeds too.

## Layout

| Path | What |
|---|---|
| `a6_common.py` | scene loading, the datum-aligned frame, the crop component + its unresolved-edge halo |
| `keepout.py` | `build_keepout`, `KeepOutVolume`, `is_inside` / `classify`, save/load |
| `metrics.py` | coverage, shielding, contact-point gate rehearsal, footprint-vs-circle |
| `run_a6.py` | builds the product, writes `results/a6_report.json` and `results/sweeps.json` |
| `figures.py` | the five figures in `figs/` |
| `a6_api.py` | **the loader A8 should import** |
| `test_a6.py` | 21 tests: unit geometry, the real scene, and the R1 discipline checks |
| `products/keepout_squash_merge.npz` | the shipped volume (7.9 MB) |
| `results/` | the numbers behind every table in `FINDINGS.md` |

## Reproducing

Uses `chunks/A3/.venv` **unchanged** — same package set as A4's lock, no new
dependency (`requirements.lock.txt`).

```bash
cd chunks/A6
../A3/.venv/bin/python run_a6.py        # ~5 min, ~3.5 GB peak
../A3/.venv/bin/python figures.py       # ~5 min (the silhouettes are ray-marched)
../A3/.venv/bin/python -m pytest test_a6.py -q     # ~4 s
```

`run_a6.py --quick` skips the ablations and takes ~4 min (the silhouette
fractions dominate).

## What it depends on

* **A4** — `load_a4(tag="merge")`, as A4's FINDINGS instructed: a crop split
  into 69 pieces gives a volume with 68 holes. `unresolved_for(component)` is
  read, and the material behind an undecided link becomes `TIER_UNSEEN` volume,
  never empty space.
* **A2** — the straw datum (the volume's floor) and `datum_roughness_sigma_rdu`
  (the unit every clearance is also reported in).
* **A1** — `primary_raster` float depth at its native 1344×1008, back-projected
  with `depth_to_cloud(..., mode="scale_free")` under the manifest camera. The
  depth is never resampled.
* **A0** — ground truth, for scoring *and*, as a documented stand-in for A7,
  for deciding which component is the crop.

## What it is not

* Not a claim about metres. Not a claim about what is behind an occluder.
* Not A7: the crop identity here is A0's label, wired to A7's in A8.
* Not a motion plan. This ends at a point-in-volume test.
