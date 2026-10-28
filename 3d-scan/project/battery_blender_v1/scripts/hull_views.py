"""Align a hull to the battery axes (PCA of the body) and render orthographic projections
and slices with a mm grid, for measuring."""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from common import *
pl = sys.argv[1]
d = np.load(os.path.join(OUT, f'hull_{pl}.npz'))
occ, xs, ys, zs = d['occ'], d['xs'], d['ys'], d['zs']
I = np.argwhere(occ); P = np.c_[xs[I[:, 0]], ys[I[:, 1]], zs[I[:, 2]]]
body = P[(P[:, 2] > 10) & (P[:, 2] < 40)]
c = body[:, :2].mean(0); U, s, Vt = np.linalg.svd(body[:, :2] - c, full_matrices=False)
ax = Vt[0]; ang = np.degrees(np.arctan2(ax[1], ax[0]))
print('centre', c, 'long-axis azimuth %.2f deg' % ang)

# refine: angle minimising the width of mid-height slices
sl = P[(P[:, 2] > 15) & (P[:, 2] < 35)][:, :2] - c
best = None
for a in np.arange(ang - 6, ang + 6, 0.05):
    t = np.radians(a); v = np.array([-np.sin(t), np.cos(t)])
    w = np.ptp(sl @ v)
    if best is None or w < best[0]: best = (w, a)
ang = best[1]; print('min-width azimuth %.2f deg, width %.1f' % (ang, best[0]))
t = np.radians(ang); ex = np.array([np.cos(t), np.sin(t)]); ey = np.array([-np.sin(t), np.cos(t)])
L = np.c_[(P[:, :2] - c) @ ex, (P[:, :2] - c) @ ey, P[:, 2]]
# recentre on bbox of body
lo, hi = L.min(0), L.max(0)
mid = (lo + hi) / 2; mid[2] = 0
L -= mid
c2 = c + mid[0] * ex + mid[1] * ey
print('battery frame origin (mat) %.2f %.2f; x=front along azimuth %.2f' % (c2[0], c2[1], ang))
print('extent x %.1f..%.1f  y %.1f..%.1f  z %.1f..%.1f' % (*np.c_[L.min(0), L.max(0)].ravel(),))
json.dump(dict(origin=c2.tolist(), azimuth_deg=float(ang)), open(os.path.join(OUT, f'frame_{pl}.json'), 'w'))
np.save(os.path.join(OUT, f'hullpts_{pl}.npy'), L)

def proj_img(A, B, name, res=0.5):
    """orthographic occupancy projection onto axes A,B (columns of L), 4 px per mm"""
    ppm = 4
    a0, a1 = -80, 80; b0, b1 = -10, 110
    if B != 2: b0, b1 = -60, 60
    W = int((a1 - a0) * ppm); H = int((b1 - b0) * ppm)
    img = np.full((H, W, 3), 255, np.uint8)
    u = ((L[:, A] - a0) * ppm).astype(int); v = ((b1 - L[:, B]) * ppm).astype(int)
    ok = (u >= 0) & (u < W) & (v >= 0) & (v < H)
    cnt = np.zeros((H, W)); np.add.at(cnt, (v[ok], u[ok]), 1)
    cnt = cv2.dilate(cnt, np.ones((3, 3)))
    g = (255 - np.clip(cnt / cnt.max() * 4, 0, 1) * 200).astype(np.uint8)
    img[:] = g[..., None]
    for mm in range(int(a0), int(a1) + 1, 5):
        x = int((mm - a0) * ppm); col = (0, 0, 255) if mm % 10 == 0 else (255, 200, 200)
        cv2.line(img, (x, 0), (x, H - 1), col, 1)
        if mm % 10 == 0: cv2.putText(img, str(mm), (x + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)
    for mm in range(int(b0), int(b1) + 1, 5):
        y = int((b1 - mm) * ppm); col = (0, 0, 255) if mm % 10 == 0 else (255, 200, 200)
        cv2.line(img, (0, y), (W - 1, y), col, 1)
        if mm % 10 == 0: cv2.putText(img, str(mm), (2, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)
    cv2.imwrite(os.path.join(OUT, f'{name}.png'), img)

proj_img(0, 2, f'hull_{pl}_side')   # x (front) vs z
proj_img(1, 2, f'hull_{pl}_end')    # y vs z
proj_img(0, 1, f'hull_{pl}_top')    # x vs y
