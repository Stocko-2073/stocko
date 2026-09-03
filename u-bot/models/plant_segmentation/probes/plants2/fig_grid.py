"""plants2 on the 768x1024 grid with labelled 64-px gridlines, for placing
by-eye check boxes."""
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from probe_common import FIGS, IMAGE
W, H = 768, 1024
rgb = np.asarray(Image.open(IMAGE).convert("RGB").resize((W, H), Image.LANCZOS))
fig, ax = plt.subplots(figsize=(9, 12), dpi=120)
ax.imshow(rgb)
for x in range(0, W + 1, 64):
    ax.axvline(x, color="w", lw=0.5, alpha=0.7); ax.text(x + 2, 12, str(x), color="yellow", fontsize=7)
for y in range(0, H + 1, 64):
    ax.axhline(y, color="w", lw=0.5, alpha=0.7); ax.text(2, y - 3, str(y), color="yellow", fontsize=7)
ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.set_xticks([]); ax.set_yticks([])
fig.tight_layout(); fig.savefig(FIGS / "grid_reference.png")
