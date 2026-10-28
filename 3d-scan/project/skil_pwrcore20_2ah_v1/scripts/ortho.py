"""Rectify a capture onto a plane of the battery frame ('up' placement), with a mm grid.

Usage: ortho.py <req> <plane> <h> <u0> <u1> <v0> <v1> [mm_per_px]
  plane: 'z' (u=X, v=Y at Z=h; image up = +Y front), 'x' (u=Y, v=Z at X=h), 'y' (u=X, v=Z at Y=h)
Only points on that plane land where they belong; anything off it is displaced by parallax.
-> out/ortho_<req>_<plane><h>.jpg
"""
import sys
import cv2
import numpy as np
from ac import OUT, Capture, bat_to_obj

req, plane, h = sys.argv[1], sys.argv[2], float(sys.argv[3])
u0, u1, v0, v1 = map(float, sys.argv[4:8])
res = float(sys.argv[8]) if len(sys.argv) > 8 else 0.1
cap = Capture(req)
us = np.arange(u0, u1, res); vs = np.arange(v1, v0, -res)       # image rows go down = v decreasing
U, Vv = np.meshgrid(us, vs)
if plane == "z":
    P = np.c_[U.ravel(), Vv.ravel(), np.full(U.size, h)]
elif plane == "x":
    P = np.c_[np.full(U.size, h), U.ravel(), Vv.ravel()]
else:
    P = np.c_[U.ravel(), np.full(U.size, h), Vv.ravel()]
uv = cap.project(bat_to_obj(P)).astype(np.float32).reshape(U.shape + (2,))
img = cv2.remap(cap.image, uv[..., 0], uv[..., 1], cv2.INTER_CUBIC)
# grid: 1 mm faint, 5 mm, 10 mm with labels
for step, col, th in [(1, (90, 90, 90), 1), (5, (0, 160, 255), 1), (10, (0, 0, 255), 2)]:
    for val in np.arange(np.ceil(u0 / step) * step, u1, step):
        if step == 1 and val % 5 == 0: continue
        x = int(round((val - u0) / res))
        if not 0 <= x < img.shape[1]: continue
        if step == 1: img[:, x] = (img[:, x] * 0.6 + np.array(col) * 0.4).astype(np.uint8)
        else: cv2.line(img, (x, 0), (x, img.shape[0]), col, th)
        if step == 10: cv2.putText(img, f"{val:g}", (x + 3, 20), 0, 0.6, (0, 0, 255), 2)
    for val in np.arange(np.ceil(v0 / step) * step, v1, step):
        if step == 1 and val % 5 == 0: continue
        y = int(round((v1 - val) / res))
        if not 0 <= y < img.shape[0]: continue
        if step == 1: img[y, :] = (img[y, :] * 0.6 + np.array(col) * 0.4).astype(np.uint8)
        else: cv2.line(img, (0, y), (img.shape[1], y), col, th)
        if step == 10: cv2.putText(img, f"{val:g}", (3, y - 4), 0, 0.6, (0, 0, 255), 2)
out = OUT / f"ortho_{req}_{plane}{h:g}.jpg"
cv2.imwrite(str(out), img)
print(out, img.shape)
