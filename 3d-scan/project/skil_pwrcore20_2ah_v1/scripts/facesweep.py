"""Locate a flat textured face by sweeping its plane: rectify a patch of the plane into each view
and find the plane offset where the views agree best (mean pairwise ZNCC).

Usage: facesweep.py <plane x|y|z> <u> <v> <half_u> <half_v> <h0> <h1> <views...>
  plane x: patch spans (Y=u, Z=v) on X=h;  y: (X=u, Z=v) on Y=h;  z: (X=u, Y=v) on Z=h.
Placement 'up' only (battery frame via bat_to_obj).
"""
import itertools
import sys

import cv2
import numpy as np

from ac import Capture, bat_to_obj

plane = sys.argv[1]
u, v, hu, hv, h0, h1 = map(float, sys.argv[2:8])
reqs = sys.argv[8:]
caps = [Capture(r) for r in reqs]
grays = [cv2.GaussianBlur(cv2.cvtColor(c.image, cv2.COLOR_BGR2GRAY).astype(np.float32), (0, 0), 0.8) for c in caps]
R = 0.04
gu = np.arange(-hu, hu + 1e-9, R); gv = np.arange(-hv, hv + 1e-9, R)
GU, GV = np.meshgrid(u + gu, v + gv)
HS = np.arange(h0, h1 + 1e-9, 0.05)


def pts(h):
    n = GU.size
    if plane == "x": return np.c_[np.full(n, h), GU.ravel(), GV.ravel()]
    if plane == "y": return np.c_[GU.ravel(), np.full(n, h), GV.ravel()]
    return np.c_[GU.ravel(), GV.ravel(), np.full(n, h)]


scores = []
for h in HS:
    P = bat_to_obj(pts(h)); ims = []
    for c, g in zip(caps, grays):
        uv = c.project(P).astype(np.float32).reshape(GU.shape + (2,))
        im = cv2.remap(g, uv[..., 0], uv[..., 1], cv2.INTER_LINEAR)
        ims.append((im - im.mean()) / (im.std() + 1e-6))
    scores.append(np.mean([(a * b).mean() for a, b in itertools.combinations(ims, 2)]))
scores = np.array(scores); k = int(np.argmax(scores))
if 0 < k < len(HS) - 1:
    y0, y1, y2 = scores[k - 1:k + 2]; den = y0 - 2 * y1 + y2
    hb = HS[k] + (0.5 * (y0 - y2) / den * 0.05 if abs(den) > 1e-9 else 0)
else:
    hb = HS[k]
# sharpness: width of the peak at 90% of max
above = HS[scores > scores[k] - 0.1 * (scores[k] - np.median(scores))]
print(f"{plane}-face at ({u:g},{v:g}): h = {hb:.2f}  zncc {scores[k]:.3f} (median {np.median(scores):.3f}), "
      f"peak span {above.min():.2f}..{above.max():.2f}")
