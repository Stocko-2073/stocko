"""Material map overlay for plants2 — for looking at, since there is no GT."""
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from probe_common import FIGS, IMAGE, P, on_path
on_path("A0")
import eval as a0eval  # noqa: E402

W, H = 768, 1024
mat = np.load(P["A3"] / "material.npy")
conf = np.load(P["A3"] / "confidence.npy")
rgb = np.asarray(Image.open(IMAGE).convert("RGB").resize((W, H), Image.LANCZOS)) / 255.0

COL = {1: (0.10, 0.75, 0.20), 2: (0.95, 0.85, 0.10), 3: (1.00, 0.55, 0.00),
       4: (0.90, 0.15, 0.15), 5: (0.55, 0.40, 0.20), 6: (0.30, 0.30, 0.30),
       7: (0.95, 0.40, 0.85), 8: (0.20, 0.55, 1.00)}
over = rgb * 0.35
for cid, c in COL.items():
    m = mat == cid
    over[m] = over[m] * 0.4 + np.array(c) * 0.6

fig, ax = plt.subplots(1, 3, figsize=(15, 7.2), dpi=110)
ax[0].imshow(rgb); ax[0].set_title("plants2.jpeg (768x1024)")
ax[1].imshow(over); ax[1].set_title("A3 material probe (fitted on plants.jpeg, unchanged)")
im = ax[2].imshow(conf, vmin=0.14, vmax=0.6, cmap="magma"); ax[2].set_title("max class probability")
plt.colorbar(im, ax=ax[2], fraction=0.03)
for a in ax:
    a.set_xticks([]); a.set_yticks([])
frac = {cid: float((mat == cid).mean()) for cid in COL}
ax[1].legend(handles=[Patch(color=COL[c], label=f"{a0eval.CLASSES[c]} {frac[c]*100:.0f}%") for c in COL if frac[c] > 0],
             loc="lower left", fontsize=8, framealpha=0.85)
fig.suptitle("plants2 probe - A3 transfer, no ground truth, no score", fontsize=12)
fig.tight_layout()
fig.savefig(FIGS / "a3_material_plants2.png")
print("wrote", FIGS / "a3_material_plants2.png")
