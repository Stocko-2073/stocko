"""Probe stage A3 step 2 — build the region partition from the probe's SAM
masks with A3's own `build_partition` (identical construction to A0's).
Runs in chunks/A3/.venv.
"""
import json
import numpy as np

from probe_common import P, RESULTS, on_path

on_path("A3", "A0")
import a3_common as A  # noqa: E402

A.WORK = str(P["A3"] / "work")
masks = A.load_masks("a3f_")
regions = A.build_partition(masks)
np.save(P["A3"] / "work" / "regions_a3f.npy", regions)
meta = json.load(open(P["A3"] / "work" / "a3f_sam_meta.json"))
rep = {"n_masks": meta["n_masks"], "sam_seconds": meta["seconds"],
       "n_regions": int(regions.max()),
       "plants_jpeg_n_regions": int(np.load(str(A.WORK).replace("probes/plants2/", "") + "/regions_a3f.npy").max()),
       "settings": {k: meta[k] for k in ("points_per_side", "pred_iou_thresh", "stability_score_thresh", "min_mask_region_area")}}
json.dump(rep, open(RESULTS / "a3_partition.json", "w"), indent=1)
print(rep)
