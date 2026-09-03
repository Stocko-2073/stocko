"""Depth raster + camera comparison figure for the plants2 probe."""
import json
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from probe_common import CH, FIGS, IMAGE, P, PRIMARY_RASTER, RESULTS
d = np.load(P["A1"] / "depth" / PRIMARY_RASTER / "depth.npy"); d = d / np.median(d)
d0 = np.load(CH["A1"] / "depth" / PRIMARY_RASTER / "depth.npy"); d0 = d0 / np.median(d0)
rgb = np.asarray(Image.open(IMAGE).convert("RGB").resize((1008, 1344), Image.LANCZOS))
cam = json.load(open(RESULTS / "a1_camera.json"))
fig, ax = plt.subplots(1, 3, figsize=(15, 7), dpi=110)
ax[0].imshow(rgb); ax[0].set_title("plants2.jpeg")
im = ax[1].imshow(d, cmap="viridis_r"); ax[1].set_title("DA3 nested-giant res1344 depth (rdu, near=bright)")
plt.colorbar(im, ax=ax[1], fraction=0.03)
for a in ax[:2]: a.set_xticks([]); a.set_yticks([])
rows = cam["runs"]; ref = cam["plants_jpeg_reference"]
xs = np.arange(len(rows))
f2 = [r["f_at_3000x4000_px_mean"] for r in rows]
f1 = [0.5 * (r["plants_jpeg_same_run"]["f_at_3000x4000_from_fx"] + r["plants_jpeg_same_run"]["f_at_3000x4000_from_fy"]) for r in rows]
ax[2].bar(xs - 0.2, f1, 0.4, label="plants.jpeg", color="#888"); ax[2].bar(xs + 0.2, f2, 0.4, label="plants2.jpeg", color="#d9822b")
for i, r in enumerate(rows):
    if not r["physically_consistent"]: ax[2].text(xs[i] + 0.2, f2[i] + 60, "fx/fy\ninconsistent", ha="center", fontsize=7, color="#d9822b")
    if not r["plants_jpeg_same_run"]["physically_consistent"]: ax[2].text(xs[i] - 0.2, f1[i] + 60, "fx/fy\ninconsistent", ha="center", fontsize=7, color="#555")
ax[2].axhline(ref["A1b_adopted_f_px"], color="k", ls="--", lw=1, label=f"A1b adopted f = {ref['A1b_adopted_f_px']:.0f} px")
ax[2].axhline(ref["roadmap_prior_26mm_px"], color="b", ls=":", lw=1, label="26 mm-equiv prior = 3005 px")
ax[2].set_xticks(xs); ax[2].set_xticklabels([r["run"].replace("da3nested-giant-large", "nested").replace("da3-large", "large").replace("_res", "\n@") for r in rows], fontsize=8)
ax[2].set_ylabel("DA3 camera-head focal length at 3000x4000 (px)"); ax[2].legend(fontsize=8, loc="lower right")
ax[2].set_title("same run, two photos: DA3's f is scene-conditioned")
fig.suptitle("plants2 probe - A1", fontsize=12); fig.tight_layout(); fig.savefig(FIGS / "a1_depth_camera.png")
print("ok")
