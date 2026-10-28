"""Side-by-side sheet: photo | material render from the same calibrated camera | edge overlay.

usage: compare_sheet.py out.jpg rid [rid ...]
"""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from common import *

out = sys.argv[1]; rids = sys.argv[2:]
views = json.load(open(os.path.join(OUT, 'views.json')))
T = 520
rows = []
for rid in rids:
    photo = cv2.imread(os.path.join(OUT, 'undist', rid + '.jpg'))
    pretty = cv2.imread(os.path.join(OUT, 'pretty', f'match_{rid}.png'))
    rend = cv2.imread(os.path.join(OUT, 'render', rid + '.png'), cv2.IMREAD_UNCHANGED)
    if pretty.shape[:2] != photo.shape[:2]:
        pretty = cv2.resize(pretty, (photo.shape[1], photo.shape[0]))
    a = rend[..., 3] > 127
    g = cv2.cvtColor(rend[..., :3], cv2.COLOR_BGR2GRAY)
    e = (cv2.Canny(g, 12, 30) > 0) & (cv2.erode(a.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
    sil = (cv2.dilate(a.astype(np.uint8), np.ones((3, 3), np.uint8)) - a.astype(np.uint8)) > 0
    ov = photo.copy(); ov[e] = (255, 255, 0); ov[sil] = (0, 255, 255)
    ys, xs = np.nonzero(a); pad = 50
    x0, x1, y0, y1 = max(0, xs.min() - pad), min(a.shape[1], xs.max() + pad), max(0, ys.min() - pad), min(a.shape[0], ys.max() + pad)
    tiles = []
    for im in (photo, pretty, ov):
        c = im[y0:y1, x0:x1]
        rot = views[rid]['upright']
        if rot == 270: c = cv2.rotate(c, cv2.ROTATE_90_COUNTERCLOCKWISE)
        elif rot == 90: c = cv2.rotate(c, cv2.ROTATE_90_CLOCKWISE)
        sc = T / max(c.shape[:2]); c = cv2.resize(c, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
        can = np.full((T, T, 3), 255, np.uint8); oy = (T - c.shape[0]) // 2; ox = (T - c.shape[1]) // 2
        can[oy:oy + c.shape[0], ox:ox + c.shape[1]] = c
        tiles.append(can)
    row = np.hstack(tiles)
    cv2.putText(row, rid, (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 220), 2)
    rows.append(row)
hdr = np.full((40, 3 * T, 3), 255, np.uint8)
for i, t in enumerate(('photo (undistorted)', 'Blender render, same camera', 'model edges on photo')):
    cv2.putText(hdr, t, (i * T + 12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (40, 40, 40), 2)
cv2.imwrite(out, np.vstack([hdr] + rows), [cv2.IMWRITE_JPEG_QUALITY, 88])
print(out)
