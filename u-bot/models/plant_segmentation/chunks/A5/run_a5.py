"""A5 — run the contact-point stage over both A4 policies and write the products.

    ../A3/.venv/bin/python run_a5.py

Writes, under `products/`:
    contacts_split.json / contacts_merge.json   per-component contact records
    contacts_gt_instances.json                  the same code on A0's GT instance
                                                masks (diagnostic: isolates A5
                                                from A4's grouping)
    a5_status_<policy>.json                     the status counts
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from a5_common import (ROOT, gt_to_depth, load_a3_material_depth_grid,  # noqa: E402
                       load_a4, load_scene)
from contact_points import contact_points, status_counts, to_json  # noqa: E402

PRODUCTS = os.path.join(HERE, "products")
RESULTS = os.path.join(HERE, "results")
POLICIES = {"split": "default", "merge": "merge"}


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def main():
    os.makedirs(PRODUCTS, exist_ok=True)
    os.makedirs(RESULTS, exist_ok=True)
    scene = load_scene()
    material = load_a3_material_depth_grid()
    log(f"scene {scene.shape}, sigma_datum {scene.sigma_datum:.4e} rdu, "
        f"datum = straw")

    summary = {}
    for policy, tag in POLICIES.items():
        a4 = load_a4(tag=tag)
        log(f"--- {policy} ({tag}) ---")
        t0 = time.time()
        cs = contact_points(scene, a4.components_depth, material, a4.unresolved)
        log(f"{len(cs)} components in {time.time()-t0:.1f} s")
        sc = status_counts(cs)
        log(f"  {sc}")
        doc = to_json(cs, scene, policy, {"status_counts": sc})
        json.dump(doc, open(os.path.join(PRODUCTS, f"contacts_{policy}.json"), "w"),
                  indent=1)
        summary[policy] = sc

    # --- diagnostic: the same code on A0's ground-truth instance masks --------
    from PIL import Image
    inst = np.array(Image.open(os.path.join(ROOT, "groundtruth",
                                            "plants_instances.png")))
    inst = np.where(inst == 255, 0, inst)      # grass is unresolved in A0
    cs = contact_points(scene, gt_to_depth(inst), material, None)
    sc = status_counts(cs)
    log(f"GT-instance-mask oracle: {sc}")
    json.dump(to_json(cs, scene, "gt_instances", {
        "status_counts": sc,
        "note": "A5's algorithm run on A0's own instance masks. Diagnostic "
                "only: it removes A4's grouping from the loop so the contact "
                "stage can be judged on its own."}),
        open(os.path.join(PRODUCTS, "contacts_gt_instances.json"), "w"), indent=1)
    summary["gt_instances"] = sc

    json.dump(summary, open(os.path.join(RESULTS, "status_counts.json"), "w"),
              indent=1)
    log("done")


if __name__ == "__main__":
    main()
