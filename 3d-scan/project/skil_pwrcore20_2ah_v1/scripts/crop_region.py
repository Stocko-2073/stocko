"""Full-res crops of a battery-frame box region in several views. Usage: crop_region.py x0 x1 y0 y1 z0 z1 name req..."""
import sys, itertools
import cv2, numpy as np
from ac import OUT, Capture, bat_to_obj
x0, x1, y0, y1, z0, z1 = map(float, sys.argv[1:7]); name = sys.argv[7]; reqs = sys.argv[8:]
box = np.array(list(itertools.product([x0, x1], [y0, y1], [z0, z1])))
tiles = []
for r in reqs:
    c = Capture(r); uv = c.project(bat_to_obj(box))
    a, b = uv.min(0).astype(int) - 20, uv.max(0).astype(int) + 20
    a = np.maximum(a, 0); cr = c.image[a[1]:b[1], a[0]:b[0]]
    f = 1000 / max(cr.shape[:2]); cr = cv2.resize(cr, None, fx=f, fy=f)
    t = np.full((1000, 1000, 3), 255, np.uint8); t[:cr.shape[0], :cr.shape[1]] = cr
    cv2.putText(t, r, (6, 28), 0, 0.9, (255, 0, 0), 2); tiles.append(t)
cols = 2 if len(tiles) > 1 else 1
while len(tiles) % cols: tiles.append(np.full_like(tiles[0], 255))
cv2.imwrite(str(OUT / f'{name}.jpg'), np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]))
