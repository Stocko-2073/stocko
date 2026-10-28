"""Silhouette comparison: model (battery frame, 'up' placement) vs photo.
red = model where the photo shows paper (model too big); blue = certain battery the model misses.
Certain battery: V < 120 inside the ROI and not paper. Prints the counts in mm^2-ish px.

Usage: silcmp.py <req> [...] [--out name]
"""
import sys
import cv2, numpy as np
from ac import OUT, Capture, bat_to_obj
from overlay import model_mesh
from stereo import roi_mask

args = [a for a in sys.argv[1:] if not a.startswith('--')]
name = 'silcmp'
if '--out' in sys.argv: name = sys.argv[sys.argv.index('--out') + 1]; args.remove(name)
mesh = model_mesh(); V = bat_to_obj(mesh.vertices); F = mesh.faces
S = 0.5
tiles = []
for r in args:
    c = Capture(r)
    img = cv2.resize(c.image, None, fx=S, fy=S, interpolation=cv2.INTER_AREA)
    v = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 2]
    notp = cv2.resize(cv2.imread(str(OUT / 'mask' / f'{r}.png'), 0), (img.shape[1], img.shape[0])) > 0
    roi = cv2.resize(roi_mask(c, np.eye(4), c.image.shape[:2]), (img.shape[1], img.shape[0])) > 0
    uv = c.project(V) * S
    sil = np.zeros(v.shape, np.uint8)
    for f in F:
        cv2.fillConvexPoly(sil, np.round(uv[f] * 16).astype(np.int32), 1, shift=4)
    sil = sil > 0
    field = np.zeros(v.shape, np.uint8)
    poly = c.project(np.array([[-87, -118, 0], [87, -118, 0], [87, 118, 0], [-87, 118, 0.0]])) * S
    cv2.fillPoly(field, [np.round(poly).astype(np.int32)], 1)
    dark = (v < 120) & notp & roi & (field > 0)
    dark = cv2.morphologyEx(dark.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
    paper = ~notp
    over = sil & paper
    miss = dark & ~sil
    out = img.copy()
    out[over] = (0.3 * out[over] + [0, 0, 180]).astype(np.uint8)
    out[miss] = (0.3 * out[miss] + [180, 0, 0]).astype(np.uint8)
    cnts, _ = cv2.findContours(sil.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(out, cnts, -1, (0, 255, 255), 1)
    x, y, w, h = cv2.boundingRect(sil.astype(np.uint8)); p = 40
    crop = out[max(0, y - p):y + h + p, max(0, x - p):x + w + p]
    f = 900 / max(crop.shape[:2]); crop = cv2.resize(crop, None, fx=f, fy=f)
    t = np.full((900, 900, 3), 255, np.uint8); t[:crop.shape[0], :crop.shape[1]] = crop
    cv2.putText(t, f'{r} over {over.sum()} miss {miss.sum()}', (6, 28), 0, 0.8, (255, 0, 0), 2)
    tiles.append(t)
    print(r, 'over', int(over.sum()), 'miss', int(miss.sum()))
cols = min(3, len(tiles))
while len(tiles) % cols: tiles.append(np.full_like(tiles[0], 255))
cv2.imwrite(str(OUT / f'{name}.jpg'), np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]))
