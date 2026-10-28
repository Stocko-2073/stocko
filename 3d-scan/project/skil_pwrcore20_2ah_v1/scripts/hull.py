"""Visual hull of the battery in the object frame (the 'up' placement's mat frame): keep voxels
that no view sees as bare paper. Views of other placements go through out/registration.json.

Usage: hull.py <voxel_mm> <out.npy> <placement> [...]   (grid in out/hull.npz)
"""
import json
import sys

import cv2
import numpy as np
from scipy import ndimage

from ac import OUT, PROJECT, Capture

vox = float(sys.argv[1]); out_name = sys.argv[2]; names = sys.argv[3:]
placements = json.loads((PROJECT / "placements.json").read_text())
reg = json.loads((OUT / "registration.json").read_text()) if (OUT / "registration.json").exists() else {}

# Object-frame grid around the battery (from the 'up' hull: center (-3.5, -3.7), yaw -125.4 deg).
lo, hi = np.array([-80, -80, -2.0]), np.array([75, 75, 80.0])
xs, ys, zs = (np.arange(lo[i] + vox / 2, hi[i], vox) for i in range(3))
keep = np.ones((len(xs), len(ys), len(zs)), bool)
X, Y = np.meshgrid(xs, ys, indexing="ij")
views = []
for n in names:
    T = np.array(reg[n]["T"]) if n != "up" else np.eye(4)
    for r in placements[n]["views"].split():
        views.append((Capture(r), cv2.imread(str(OUT / "mask" / f"{r}.png"), 0) > 0, T))
for k, z in enumerate(zs):
    pts = np.c_[X.ravel(), Y.ravel(), np.full(X.size, z)]
    ok = np.ones(len(pts), bool)
    for c, m, T in views:
        uv = np.round(c.project(pts @ T[:3, :3].T + T[:3, 3])).astype(int)
        inside = (uv[:, 0] >= 0) & (uv[:, 0] < m.shape[1]) & (uv[:, 1] >= 0) & (uv[:, 1] < m.shape[0])
        hit = np.zeros(len(pts), bool)
        hit[inside] = m[uv[inside, 1], uv[inside, 0]]
        ok &= hit | ~inside
    keep[:, :, k] = ok.reshape(X.shape)

# Crop to the battery: the largest component inside a box around it, above the mat.
Xg, Yg, Zg = np.meshgrid(xs, ys, zs, indexing="ij")
c = np.array([-3.476, -3.722]); f = np.array([-0.5789, -0.8154]); Xb = np.array([f[1], -f[0]])
bx = (Xg - c[0]) * Xb[0] + (Yg - c[1]) * Xb[1]; by = (Xg - c[0]) * f[0] + (Yg - c[1]) * f[1]
keep &= (abs(bx) < 48) & (abs(by) < 72) & (Zg > 0)
lab, n = ndimage.label(keep)
if n:
    sizes = ndimage.sum(keep, lab, range(1, n + 1)); keep = lab == (np.argmax(sizes) + 1)
np.savez_compressed(OUT / "hull.npz", xs=xs, ys=ys, zs=zs, vox=vox)
np.save(OUT / out_name, keep)
print(f"{out_name}: {len(views)} views, volume {keep.sum() * vox ** 3 / 1000:.1f} cm3")
