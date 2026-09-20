"""
A2 — the by-eye check, written down as numbers.

    chunks/A1/.venv/bin/python chunks/A2/material_check.py

The roadmap's acceptance test for this chunk is qualitative: "clover just above
the datum, grass mid-band, squash canopy high". Eyeballing an overlay is how
that gets checked, but an eyeball leaves no record, so the regions used are
hand-placed here, drawn on the RGB for inspection, and turned into a table.

These boxes are **not** ground truth and **not** thresholds. They are a
hand-placed sample used once, to check an ordering. A0 will supersede them with
a real per-pixel labelling; when it lands this script should be re-pointed at
those labels instead. Nothing downstream reads this file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from PIL import Image  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

# (row0, row1, col0, col1) on the 1344x1008 depth grid.
BOXES: dict[str, list[tuple[int, int, int, int]]] = {
    "straw (datum)": [
        (1240, 1300, 250, 340),
        (1040, 1090, 380, 450),
        (950, 1000, 120, 200),
        (690, 730, 610, 680),
    ],
    "low broadleaf weed": [
        (1015, 1060, 180, 245),
        (1095, 1145, 115, 185),
        (795, 845, 150, 265),
    ],
    "grass blade": [
        (200, 280, 850, 950),
        (425, 500, 55, 140),
        (1150, 1215, 430, 520),
    ],
    "squash fruit": [
        (845, 905, 400, 505),
        (600, 660, 400, 462),
    ],
    "squash leaf": [
        (100, 200, 100, 265),
        (1100, 1200, 700, 855),
        (450, 520, 830, 955),
    ],
}

COLOURS = {
    "straw (datum)": "#e6c34a", "low broadleaf weed": "#66d17a",
    "grass blade": "#4ad0e6", "squash fruit": "#e6884a", "squash leaf": "#e64a6f",
}


def main() -> None:
    pdir = HERE / "products"
    H = np.load(pdir / "height_above_soil.npy")
    G = np.load(pdir / "ground_inliers.npy")
    C = np.load(pdir / "coverage_class.npy")
    m = json.loads((pdir / "A2_MANIFEST.json").read_text())
    sigma = m["key_numbers"]["datum_roughness_sigma_rdu"]
    h, w = H.shape
    rgb = np.asarray(Image.open(ROOT / "plants.jpeg").convert("RGB").resize((w, h)))

    out = {
        "sigma_datum_rdu": sigma,
        "scale_confidence": "scale_free",
        "datum": "straw mulch surface, not bare soil",
        "caveat": ("hand-placed boxes, used once to check an ordering. Not ground "
                   "truth, not a threshold, not read by anything downstream."),
        "materials": {},
    }
    for name, boxes in BOXES.items():
        vals, gfrac, cov = [], [], []
        for r0, r1, c0, c1 in boxes:
            vals.append(H[r0:r1, c0:c1].ravel())
            gfrac.append(float(G[r0:r1, c0:c1].mean()))
            cov.append(float((C[r0:r1, c0:c1] == 0).mean()))
        v = np.concatenate(vals)
        out["materials"][name] = {
            "n_boxes": len(boxes), "n_px": int(v.size),
            "p10_rdu": float(np.percentile(v, 10)),
            "median_rdu": float(np.median(v)),
            "p90_rdu": float(np.percentile(v, 90)),
            "median_in_sigma": float(np.median(v) / sigma),
            "ground_inlier_fraction": float(np.mean(gfrac)),
            "per_box_median_rdu": [float(np.median(x)) for x in vals],
        }

    order = sorted(out["materials"], key=lambda k: out["materials"][k]["median_rdu"])
    out["ordering_low_to_high"] = order
    # The roadmap's acceptance test, verbatim: "clover just above the datum,
    # grass mid-band, squash canopy high". The fruit is not part of that claim —
    # it is reported but excluded from the test, because where a fruit resting on
    # the ground should rank was never asserted by anyone.
    tested = ["straw (datum)", "low broadleaf weed", "grass blade", "squash leaf"]
    out["expected_ordering"] = tested
    out["ordering_matches_expectation"] = [k for k in order if k in tested] == tested

    fig, axes = plt.subplots(1, 2, figsize=(13, 8.6))
    axes[0].imshow(rgb)
    hv = H.copy()
    im = axes[1].imshow(hv, cmap="turbo", vmin=np.percentile(hv, 1),
                        vmax=np.percentile(hv, 99))
    plt.colorbar(im, ax=axes[1], fraction=0.04, label="rdu above straw")
    for name, boxes in BOXES.items():
        for r0, r1, c0, c1 in boxes:
            for a in axes:
                a.add_patch(Rectangle((c0, r0), c1 - c0, r1 - r0, fill=False,
                                      ec=COLOURS[name], lw=1.8))
        axes[0].plot([], [], color=COLOURS[name], lw=3,
                     label=f"{name}: {out['materials'][name]['median_rdu']:+.3f} rdu "
                           f"({out['materials'][name]['median_in_sigma']:.0f}σ)")
    axes[0].legend(loc="lower left", fontsize=8, framealpha=0.9)
    for a in axes:
        a.set_xticks([]); a.set_yticks([])
    axes[0].set_title("hand-placed material boxes")
    axes[1].set_title("height above the straw datum")
    fig.suptitle("A2 — material height ordering check "
                 f"({'PASS' if out['ordering_matches_expectation'] else 'MISMATCH'})",
                 fontsize=12)
    fig.tight_layout()
    fig.savefig(HERE / "results" / "fig_material_boxes.png", dpi=130)

    (HERE / "results" / "material_ordering.json").write_text(json.dumps(out, indent=2))
    for k in order:
        d = out["materials"][k]
        print(f"{k:22s} median {d['median_rdu']:+.4f} rdu = {d['median_in_sigma']:6.1f}σ "
              f"  p10 {d['p10_rdu']:+.4f}  p90 {d['p90_rdu']:+.4f}  "
              f"ground-inlier {d['ground_inlier_fraction']*100:5.1f}%")
    print("ordering matches expectation:", out["ordering_matches_expectation"])


if __name__ == "__main__":
    main()
