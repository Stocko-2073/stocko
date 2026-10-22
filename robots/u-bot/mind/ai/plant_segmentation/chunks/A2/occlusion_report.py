"""
A2 — what happens where the canopy hides the ground completely.

    chunks/A1/.venv/bin/python chunks/A2/occlusion_report.py

The roadmap requires this behaviour to be documented rather than discovered
later. Here it is measured: every connected region with no ground observation
inside it is listed with its area, its worst support distance, and the datum
uncertainty the fit carries there — read off the measured gap-fill curve, not
guessed. Writes `results/occlusion.json` and a figure.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import scipy.ndimage as ndi  # noqa: E402
from PIL import Image  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def main() -> None:
    p = HERE / "products"
    G = np.load(p / "ground_inliers.npy")
    S = np.load(p / "support_distance_px.npy")
    C = np.load(p / "coverage_class.npy")
    sig = np.load(p / "height_sigma.npy")
    m = json.loads((p / "A2_MANIFEST.json").read_text())
    sigma_d = m["key_numbers"]["datum_roughness_sigma_rdu"]
    trust = m["key_numbers"]["max_trusted_support_px"]
    h, w = G.shape

    # "How occluded is the ground" has no single answer, because the canopy is
    # one connected sheet: 69 % of the frame is a single component of
    # not-ground. What matters is how deep inside it a pixel sits, so the set is
    # sliced by support distance and the components are counted at each depth.
    # The last slice, at the measured trust distance, is the operationally
    # meaningful one: those are the pixels whose datum is not defensible.
    depth_slices = []
    for thr in (0, 10, 20, 40, 80, 160, float(trust)):
        deep = S > thr
        dl, dn = ndi.label(deep)
        szs = (ndi.sum_labels(np.ones_like(dl), dl, index=np.arange(1, dn + 1))
               if dn else np.zeros(0))
        depth_slices.append({
            "support_gt_px": thr,
            "area_fraction": float(deep.mean()),
            "n_components": int(dn),
            "largest_component_px": int(szs.max()) if dn else 0,
            "largest_component_fraction": float(szs.max() / (h * w)) if dn else 0.0,
        })

    lab, n = ndi.label(~G)
    sizes = ndi.sum_labels(np.ones_like(lab), lab, index=np.arange(1, n + 1))
    order = np.argsort(sizes)[::-1][:12]
    holes = []
    for i in order:
        idx = i + 1
        mask = lab == idx
        rows, cols = np.nonzero(mask)
        holes.append({
            "label": int(idx),
            "area_px": int(mask.sum()),
            "area_fraction_of_frame": float(mask.mean()),
            "bbox_rows": [int(rows.min()), int(rows.max())],
            "bbox_cols": [int(cols.min()), int(cols.max())],
            "max_support_px": float(S[mask].max()),
            "median_support_px": float(np.median(S[mask])),
            "max_datum_sigma_rdu": float(np.nanmax(sig[mask])),
            "max_datum_sigma_in_units_of_datum_roughness":
                float(np.nanmax(sig[mask]) / sigma_d),
            "fraction_beyond_trust_distance": float((S[mask] > trust).mean()),
        })

    out = {
        "scale_confidence": "scale_free",
        "datum": "straw mulch surface, not bare soil",
        "n_regions_with_no_ground_observation": int(n),
        "occlusion_depth_slices": depth_slices,
        "largest_regions": holes,
        "trust_distance_px": trust,
        "sigma_datum_rdu": sigma_d,
        "behaviour": (
            "Where the canopy hides the ground the surface is continued by the "
            "spline's roughness penalty alone — no ground pixel inside the hole "
            "contributes. That is a smooth continuation of the surrounding datum, "
            "not a measurement, and it is labelled as such in coverage_class "
            "(1 = interpolated, 2 = extrapolated) and priced in height_sigma, "
            "which is read off the measured gap-fill error curve. Nothing is "
            "silently filled: a pixel whose support distance exceeds the trust "
            "distance is marked invalid, and the height there must not be used "
            "for a removal decision (R2, R4). Both regions that exceed the trust "
            "distance in this image touch the frame edge — the top-left leaf and "
            "the bottom-right leaf — which is exactly the case where the surface "
            "is constrained from one side only and has nothing on the far side "
            "to bracket it. The coverage class is what makes that visible."
        ),
        "limitation": (
            "The gap-fill error curve was measured by blanking disks over ground "
            "that IS observed. It therefore measures how well the surface "
            "predicts ground of the kind it can see. Whether the ground under a "
            "squash canopy is the same kind of ground cannot be checked from one "
            "photograph — R4's answer is to look again from another pose (C1), "
            "not to widen the claim."
        ),
    }
    (HERE / "results" / "occlusion.json").write_text(json.dumps(out, indent=2))

    rgb = np.asarray(Image.open(ROOT / "plants.jpeg").convert("RGB").resize((w, h)))
    fig, ax = plt.subplots(1, 3, figsize=(16, 8.2))
    ax[0].imshow(rgb); ax[0].set_title("RGB")
    big = np.isin(lab, [d["label"] for d in holes[:6]])
    ov = np.zeros((h, w, 4))
    ov[big] = (0.6, 0.1, 0.7, 0.55)
    ax[1].imshow(rgb); ax[1].imshow(ov)
    ax[1].set_title("the six largest canopy holes\n(no ground observation inside)")
    im = ax[2].imshow(np.where(G, np.nan, S), cmap="magma")
    plt.colorbar(im, ax=ax[2], fraction=0.04, label="px")
    ax[2].contour(S, levels=[trust], colors="cyan", linewidths=1.2)
    ax[2].set_title(f"support distance inside the holes\ncyan = trust limit {trust:.0f} px")
    for a in ax:
        a.set_xticks([]); a.set_yticks([])
    fig.suptitle("A2 — behaviour where the canopy hides the ground", fontsize=12)
    fig.tight_layout()
    fig.savefig(HERE / "results" / "fig_occlusion.png", dpi=130)

    print(f"{n} regions with no ground observation, "
          f"the largest {holes[0]['area_fraction_of_frame']*100:.1f} % of the frame "
          f"(the canopy is one connected sheet).")
    print("depth into the occluded set:")
    for d in depth_slices:
        print(f"  support > {d['support_gt_px']:6.1f} px : "
              f"{d['area_fraction']*100:6.2f} % of frame in "
              f"{d['n_components']:4d} components, "
              f"largest {d['largest_component_fraction']*100:5.2f} %")


if __name__ == "__main__":
    main()
