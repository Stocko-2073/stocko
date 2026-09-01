"""A8 — two figures. Both are checks, not decoration.

`fig_gate.png` is the one to look at first: every contact point the gate
considered, on the photograph, coloured by what happened to it. If the single
admitted target were sitting on a squash leaf, this picture is where that would
be obvious.

`fig_operating.png` is the operating-point picture: what the confidence floor
and the tool clearance each do to the target list, and which condition is
actually carrying the safety.

Run:  chunks/A3/.venv/bin/python chunks/A8/figures.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import a8_common as C  # noqa: E402
import a8_tools as T  # noqa: E402

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image  # noqa: E402

FIGS = os.path.join(HERE, "figs")
TOOL = {"name": "placeholder_awaiting_C3", "clearance": 1.0e-2,
        "clearance_units": "rdu"}


def labels():
    doc = C.load_a7_labels()
    return [{"id": int(cid), "label": r["label"],
             "confidence": float(r["confidence"]), "reason": str(r["reason"]),
             "mixed": bool(r["mixed"])}
            for rep in doc["repeats"] for cid, r in sorted(rep.items())]


def fig_gate():
    st = C.load_stack(with_gt=True)
    product, _ = T.load_products()
    inst = {i["instance_id"]: i for i in product["instances"]}
    doc = T.plan_removals(labels(), TOOL, confidence_floor=0.0)
    ship = T.plan_removals(labels(), TOOL)

    rgb = np.asarray(Image.open(os.path.join(C.ROOT, "plants.jpeg"))
                     .resize((768, 1024), Image.BILINEAR)).astype(np.float32) / 255
    comp = st.a4_merge.components
    admitted = {t["instance_id"] for t in doc["targets"]}
    keepplants = set(inst) - admitted

    tint = rgb.copy()
    kp_mask = np.isin(comp, sorted(keepplants)) & (comp > 0)
    tint[kp_mask] = 0.55 * tint[kp_mask] + 0.45 * np.array([0.15, 0.45, 0.95])

    fig, ax = plt.subplots(1, 2, figsize=(15, 11.0))
    for a in ax:
        a.imshow(tint)
        a.set_xticks([]), a.set_yticks([])

    # every admissible candidate the gate looked at
    clear_x, clear_y, in_x, in_y = [], [], [], []
    for t in doc["targets"]:
        for r in [t["target"]] + t["alternate_points"]:
            clear_x.append(r["point_gt_grid_xy"][0]), clear_y.append(r["point_gt_grid_xy"][1])
        for r in t["rejected_points_inside_keepout"]:
            in_x.append(r["point_gt_grid_xy"][0]), in_y.append(r["point_gt_grid_xy"][1])
    for r in doc["rejections"]:
        b = r.get("best_contact")
        if b and b.get("inside_keepout"):
            in_x.append(b["point_gt_grid_xy"][0]), in_y.append(b["point_gt_grid_xy"][1])

    ax[0].scatter(in_x, in_y, s=9, c="#e03030", alpha=.75, linewidths=0,
                  label=f"contact point inside a keep-out ({len(in_x)})")
    ax[0].scatter(clear_x, clear_y, s=26, c="#20d060", edgecolors="k",
                  linewidths=.4, label=f"outside every keep-out ({len(clear_x)})")
    for t in doc["targets"]:
        x, y = t["target"]["point_gt_grid_xy"]
        ax[0].plot(x, y, marker="*", ms=26, mfc="#ffe000", mec="k", mew=1.2,
                   ls="none",
                   label=f"ADMITTED at floor 0.00 — instance {t['instance_id']}")
    for i in st.gt.contacts["instances"]:
        x, y = i["point"]
        ax[0].plot(x, y, marker="x", ms=9, mew=2,
                   c="#ffffff" if i.get("crop") else "#ff9020", ls="none")
    ax[0].set_title(
        "A8 gate, diagnostic floor 0.00 — blue = keep-plant material (204 "
        "instances)\ncrosses: A0 contact points (white = crop). "
        "Every point shown is `observed` and arm-admissible.", fontsize=9)
    ax[0].legend(loc="lower right", fontsize=8, framealpha=.9)

    ax[1].scatter(in_x + clear_x, in_y + clear_y, s=12, c="#e03030",
                  alpha=.8, linewidths=0,
                  label=f"every candidate, all rejected ({len(in_x)+len(clear_x)})")
    ax[1].set_title(
        f"the shipped configuration, floor {ship['summary']['confidence_floor']}"
        f" — {len(ship['targets'])} targets.\nThe floor removes the one target "
        "the geometry had cleared; it removes no crop risk,\nbecause the "
        "geometry had already removed all of it.", fontsize=9)
    ax[1].legend(loc="lower right", fontsize=8, framealpha=.9)

    fig.tight_layout(rect=(0, 0, 1, 0.965))
    os.makedirs(FIGS, exist_ok=True)
    p = os.path.join(FIGS, "fig_gate.png")
    fig.savefig(p, dpi=110)
    plt.close(fig)
    print("wrote", p)


def fig_operating():
    scores = json.load(open(os.path.join(C.RESULTS, "a8_scores.json")))
    abl = json.load(open(os.path.join(C.RESULTS, "a8_ablation.json")))

    fig, ax = plt.subplots(1, 3, figsize=(16, 4.6))

    s = scores["sweep_confidence_floor"]
    f = [r["floor"] for r in s]
    ax[0].plot(f, [r["gt_weed_fraction_reached"] * 100 for r in s], "o-",
               c="#20a060", label="GT weed px reached (%)")
    ax[0].plot(f, [r["gt_crop_fraction_under_the_tool"] * 100 for r in s], "s-",
               c="#e03030", label="GT crop px under the tool (%)")
    ax[0].axvline(0.70, color="k", ls="--", lw=1)
    ax[0].annotate("registered floor 0.70", (0.715, 8), rotation=90,
                   fontsize=8, ha="left")
    ax[0].axvspan(0.58, 0.62, color="#ffc000", alpha=.25)
    ax[0].annotate("the 0.04-wide window A0\nwould tune into (A7's\nrepeat spread is 0.052)",
                   (0.60, 48), fontsize=7, ha="right")
    ax[0].set_xlabel("confidence floor")
    ax[0].set_ylabel("% of ground truth")
    ax[0].set_title("the floor is a cliff, and it only has one side",
                    fontsize=10)
    ax[0].legend(fontsize=8)
    ax[0].grid(alpha=.3)

    rows = [r for r in abl["ablations_at_floor_000"]
            if r["name"] in ("the shipped gate, floor 0.00 (all conditions)",
                             "without `inside_keepout`",
                             "without `label_not_remove`",
                             "semantics only (every geometric condition dropped)",
                             "geometry only (every semantic condition dropped)")]
    names = [r["name"].replace(" (every geometric condition dropped)", "")
                      .replace(" (every semantic condition dropped)", "")
                      .replace(" (all conditions)", "") for r in rows]
    crop = [r["gt_crop_px_under_the_tool"] for r in rows]
    ax[1].barh(range(len(rows)), [max(c, 1) for c in crop],
               color=["#20a060" if c == 0 else "#e03030" for c in crop])
    ax[1].set_yticks(range(len(rows)))
    ax[1].set_yticklabels(names, fontsize=7.5)
    ax[1].set_xscale("log")
    ax[1].set_xlabel("GT crop px under the tool (log; 1 = zero)")
    ax[1].set_title("which condition carries the safety\n(floor 0.00, so the "
                    "floor is not one of them)", fontsize=10)
    for i, (c, r) in enumerate(zip(crop, rows)):
        ax[1].annotate(f"  {c:,} px, {r['n_targets']} targets", (max(c, 1), i),
                       va="center", fontsize=7)
    ax[1].grid(alpha=.3, axis="x")

    cs = [r for r in scores["sweep_clearance"]
          if r["floor"] == "floor_000_diagnostic"]
    ax[2].step([r["clearance_rdu"] for r in cs], [r["n_targets"] for r in cs],
               where="post", c="#2060c0", lw=2, label="targets, floor 0.00")
    cs2 = [r for r in scores["sweep_clearance"] if r["floor"] == "registered"]
    ax[2].step([r["clearance_rdu"] for r in cs2], [r["n_targets"] for r in cs2],
               where="post", c="#a0a0a0", lw=2, ls="--",
               label="targets, registered floor")
    ax[2].set_xscale("symlog", linthresh=1e-3)
    ax[2].set_xlabel("tool clearance (rdu) — A6's (b) placeholder")
    ax[2].set_ylabel("targets admitted")
    ax[2].set_ylim(-0.1, 1.4)
    ax[2].set_title("the clearance A6 is waiting on C3 for\nchanges the answer "
                    "only at the top of its swept range", fontsize=10)
    ax[2].legend(fontsize=8)
    ax[2].grid(alpha=.3)

    fig.tight_layout()
    os.makedirs(FIGS, exist_ok=True)
    p = os.path.join(FIGS, "fig_operating.png")
    fig.savefig(p, dpi=130)
    plt.close(fig)
    print("wrote", p)


if __name__ == "__main__":
    fig_gate()
    fig_operating()
