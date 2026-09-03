"""A0 step 7 — emit the ground-truth artifacts under groundtruth/.

    cd ZeroPlantSeg && .venv/bin/python ../chunks/A0/build_groundtruth.py

Writes
  groundtruth/plants_material.png    palette PNG, per-pixel material class
  groundtruth/plants_instances.png   grayscale PNG, per-pixel plant instance id
  groundtruth/plants_contacts.json   stem-soil contact points + instance metadata
  groundtruth/plants_regions.png     16-bit PNG of the SAM partition (provenance)
  groundtruth/plants_gt.json         manifest: grid, provenance, class table, stats
"""
import json
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
WORK = os.path.join(HERE, "work")
GT = os.path.join(ROOT, "groundtruth")

CLASSES = ["unlabelled", "squash_leaf", "squash_petiole", "grass",
           "broadleaf_weed", "straw", "soil", "fruit", "other"]
CID = {c: i for i, c in enumerate(CLASSES)}
PALETTE = [
    (0, 0, 0), (0, 190, 0), (0, 255, 255), (255, 240, 0),
    (255, 0, 0), (255, 150, 0), (110, 60, 20), (60, 60, 255), (255, 255, 255),
]

NATIVE = (3000, 4000)
GRID = (768, 1024)
SCALE = NATIVE[0] / GRID[0]          # 3.90625, identical in x and y
GRASS_UNRESOLVED = 255


def main():
    os.makedirs(GT, exist_ok=True)
    regions = np.load(os.path.join(WORK, "regions.npy"))
    per_region = np.load(os.path.join(WORK, "assign.npy"))
    lut = np.concatenate([[0], per_region]).astype(np.uint8)
    material = lut[regions]

    # ---- material map (palette PNG) ----
    im = Image.fromarray(material, mode="P")
    pal = []
    for c in PALETTE:
        pal += list(c)
    im.putpalette(pal + [0] * (768 - len(pal)))
    im.save(os.path.join(GT, "plants_material.png"))

    # ---- instance map ----
    spec = json.load(open(os.path.join(HERE, "instances.json")))
    inst = np.zeros(regions.shape, np.uint8)
    squash_classes = {CID["squash_leaf"], CID["squash_petiole"], CID["fruit"]}
    used = {}
    for e in spec["instances"]:
        if e["regions"] == "ALL_SQUASH":
            ids = [i + 1 for i in range(len(per_region)) if per_region[i] in squash_classes]
        else:
            ids = e["regions"]
            for i in ids:
                cls = per_region[i - 1]
                if cls != CID[e["material"]]:
                    raise ValueError(
                        f"instance {e['id']} claims region {i} as {e['material']} "
                        f"but its material class is {CLASSES[cls]}")
        for i in ids:
            if i in used:
                raise ValueError(f"region {i} claimed by instances {used[i]} and {e['id']}")
            used[i] = e["id"]
            inst[regions == i] = e["id"]
    inst[(material == CID["grass"])] = GRASS_UNRESOLVED
    Image.fromarray(inst, mode="L").save(os.path.join(GT, "plants_instances.png"))

    # any broadleaf_weed pixel not claimed by an instance is a labelling gap
    orphan = (material == CID["broadleaf_weed"]) & (inst == 0)
    if orphan.any():
        ids = sorted(set(np.unique(regions[orphan]).tolist()))
        raise ValueError(f"broadleaf_weed regions with no instance: {ids}")

    # ---- contact points ----
    contacts = {
        "grid": {"width": GRID[0], "height": GRID[1],
                 "native": {"width": NATIVE[0], "height": NATIVE[1]},
                 "scale_native_per_gt_px": SCALE},
        "status_values": ["visible", "under_straw", "out_of_frame"],
        "instances": [
            {"id": e["id"], "name": e["name"], "crop": e["crop"],
             "material": e["material"], **e["contact"]}
            for e in spec["instances"]
        ],
        "unresolved": spec["unresolved"],
    }
    json.dump(contacts, open(os.path.join(GT, "plants_contacts.json"), "w"), indent=1)

    # ---- provenance / manifest ----
    px = material.size
    counts = {c: int((material == CID[c]).sum()) for c in CLASSES}
    inst_counts = {int(v): int((inst == v).sum()) for v in np.unique(inst)}
    manifest = {
        "image": "plants.jpeg",
        "gt_grid": {"width": GRID[0], "height": GRID[1],
                    "derived_from_native": list(NATIVE),
                    "resample": "PIL LANCZOS, uniform scale 3.90625 px native per GT px",
                    "why": "768x1024 is the resolution ZeroPlantSeg runs at, so the "
                           "recorded baseline needs no resampling to be scored."},
        "classes": {c: CID[c] for c in CLASSES},
        "palette": {c: list(PALETTE[CID[c]]) for c in CLASSES},
        "class_pixel_counts": counts,
        "class_pixel_fraction": {c: counts[c] / px for c in CLASSES},
        "unlabelled_fraction": counts["unlabelled"] / px,
        "scored_fraction": 1 - counts["unlabelled"] / px,
        "instance_pixel_counts": inst_counts,
        "grass_unresolved_instance_id": GRASS_UNRESOLVED,
        "n_instances": len(spec["instances"]),
        "provenance": {
            "boundaries": "SAM ViT-H automatic mask generator (points_per_side=48, "
                          "crop_n_layers=1, min_mask_region_area=60) on the 768x1024 "
                          "image; overlapping proposals painted largest-first into a "
                          "688-region partition (chunks/A0/{sam_propose,build_partition}.py).",
            "classes": "Assigned by visual inspection of every region at 4-10x zoom "
                       "(chunks/A0/{render_review,zoom}.py); calls recorded in "
                       "chunks/A0/corrections.json over the heuristic first guess in "
                       "chunks/A0/propose_classes.py. No classifier was used.",
            "instances": "chunks/A0/instances.json",
        },
    }
    json.dump(manifest, open(os.path.join(GT, "plants_gt.json"), "w"), indent=1)

    Image.fromarray(regions.astype(np.uint16), mode="I;16").save(
        os.path.join(GT, "plants_regions.png"))

    print(f"unlabelled {100*counts['unlabelled']/px:.2f}%  instances {len(spec['instances'])}")
    for c in CLASSES:
        print(f"  {c:16s} {counts[c]:8d}  {100*counts[c]/px:6.2f}%")
    print("instance pixel counts:", inst_counts)


if __name__ == "__main__":
    main()
