# Ground truth for `plants.jpeg` — schema

**This is the contract.** Every chunk from A3 onward reports against it. Treat a
change to the class list, the id values, the grid, or the JSON keys as breaking:
bump a version note here and re-score every recorded result, or the numbers in
`RESULTS.md` stop being comparable.

Produced by chunk A0. Build scripts and the labelling record live in
`chunks/A0/`; `chunks/A0/FINDINGS.md` says how the calls were made.

## The grid

| | |
|---|---|
| Label grid | **768 × 1024** (w × h) |
| Native photograph | 3000 × 4000 |
| Scale | 3.90625 native px per label px, **identical in x and y** |
| Downsample | PIL LANCZOS on the RGB before labelling |

768 × 1024 was chosen because it is the resolution ZeroPlantSeg runs at, so the
recorded baseline is scored with **no resampling at all**. A prediction on any
other grid is resampled to this one by `eval.to_gt_grid`, nearest-neighbour
only — label maps are never interpolated — and the report prints the source
shape so a resampled score is never mistaken for a native one.

To map a label pixel `(x, y)` to native coordinates: `(3.90625·x, 3.90625·y)`,
covering a 3.90625 px square. Thin structures — grass blades are 3–6 px wide
here, 15–25 px native — are correspondingly coarse. That is a real limitation of
this ground truth, recorded in FINDINGS.

## Files

| File | Format | Contents |
|---|---|---|
| `plants_material.png` | 8-bit palette PNG, 768×1024 | per-pixel material class id |
| `plants_instances.png` | 8-bit grayscale PNG, 768×1024 | per-pixel plant instance id |
| `plants_contacts.json` | JSON | stem-soil contact point per instance |
| `plants_regions.png` | 16-bit grayscale PNG | the 688-region SAM partition the labels were painted on (provenance; not needed to score) |
| `plants_gt.json` | JSON | manifest: grid, class table, palette, pixel counts, provenance |

Read the label maps with `PIL.Image.open(...)` then `np.array(...)`. The palette
in `plants_material.png` is for looking at, not for scoring — always compare
integer class ids.

## Layer 1 — material class

| id | name | meaning |
|---:|---|---|
| 0 | `unlabelled` | genuinely ambiguous. **Excluded from scoring**, for every class. |
| 1 | `squash_leaf` | squash leaf blade, including its midrib, shaded parts, specular streaks and shadows cast on it |
| 2 | `squash_petiole` | squash stem material that is not blade or fruit: petioles, vines, peduncles, tendrils |
| 3 | `grass` | grass/monocot blades and sheaths, living |
| 4 | `broadleaf_weed` | living dicot weed foliage and stems |
| 5 | `straw` | dry dead plant material anywhere: the mulch, dried leaves, spent flower sheaths still attached to the squash |
| 6 | `soil` | bare mineral soil. **Zero pixels in this image** — see FINDINGS |
| 7 | `fruit` | squash fruit |
| 8 | `other` | not plant, not ground; here, one feather |

Coverage: `unlabelled` is **1.51 %** of the frame. Everything else is scored.

## Layer 2 — plant instances

`plants_instances.png`, one id per plant:

| id | plant |
|---:|---|
| 0 | not a plant (straw, soil, other, unlabelled) |
| 1 | the squash — **one instance by construction**, covering every `squash_leaf`, `squash_petiole` and `fruit` pixel, so fragmentation is measurable |
| 2–10 | individual broadleaf weeds (names in `plants_contacts.json`) |
| 255 | **grass, unresolved.** Excluded from instance matching |

Grass is clonal and its blades interleave; which blade belongs to which tussock
is not knowable from this image at this grid, so pretending to instance it would
be a fabricated label. It is excluded from instance precision/recall exactly the
way `unlabelled` is excluded from IoU. The failure that actually matters —
grass being swallowed by the crop — is measured instead by
`grass_absorbed_into_crop`, the fraction of GT grass pixels a prediction assigns
to whichever instance it matched to the squash.

## Layer 3 — stem-soil contact points

`plants_contacts.json`, one entry per instance:

```json
{"id": 2, "name": "weed_purslane", "crop": false, "material": "broadleaf_weed",
 "point": [125, 833], "status": "under_straw", "occluded_by": "straw",
 "localisation": "estimated", "note": "..."}
```

* `point` — `[x, y]` on the 768 × 1024 grid.
* `status` — one of `visible`, `under_straw`, `out_of_frame` (the roadmap's three).
* `occluded_by` — `straw` | `foliage` | `frame`. An extension, because "hidden by
  straw" and "hidden by overlying leaves" are different problems for a robot and
  the three-value status cannot say which.
* `localisation` — `observed` | `estimated`. Only `observed` points are ground
  truth in the strong sense; `estimated` points record my best reading of where
  the stem was last seen heading, and must not be used as a scoring target.

**In this image every contact point is `under_straw` and `estimated`. There are
zero `visible` points.** Nothing in the frame shows a stem meeting the ground.
The A5 metric "contact-point error over `visible` points" is therefore empty for
`plants.jpeg`; `eval.py` says so in the report rather than printing a zero.

## Scoring

`chunks/A0/eval.py`:

```python
from eval import load_gt, load_prediction, score, print_report
gt   = load_gt()
pred = load_prediction(material=..., instances=..., contacts={inst_id: (x, y)})
print_report(score(pred, gt, iou_threshold=0.5))
```

* **Per-class IoU** over labelled pixels only.
* **Instance precision / recall / F1** — greedy one-to-one matching, highest IoU
  first, accepted at `iou_threshold` (default **0.5**, a stated convention, a
  keyword argument, swappable; sweep it if a chunk needs to).
* **Contact-point error** — Euclidean distance in grid px, split by GT status.
* Diagnostics: `squash_fragmentation` and `grass_absorbed_into_crop`.

`chunks/A0/test_eval.py` asserts the properties that make the above trustworthy:
the ground truth scores 1.0 against itself, `unlabelled` pixels cannot change an
IoU, absorbing all the grass leaves instance F1 at 1.0 while showing 100 % on
the absorption diagnostic, splitting the squash three ways loses its match, and
resampling invents no label values.
