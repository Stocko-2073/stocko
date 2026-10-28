"""Visual hull of one placement by space carving in the mat frame.

A voxel survives unless it lands outside the silhouette in >= MISS views (tolerates a
few segmentation dropouts).  Saves out/hull_<placement>.npz and prints per-view
consistency (how much of each silhouette the hull explains).
"""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from common import *
from segment import project_pts

cams = json.load(open(os.path.join(OUT, 'cams.json')))
placement = sys.argv[1]
res = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
MISS = int(sys.argv[3]) if len(sys.argv) > 3 else 2
views = [r for r in PLACEMENTS[placement] if r in cams]
S = 0.5
xs = np.arange(-95, 95, res) + res / 2; ys = np.arange(-110, 110, res) + res / 2; zs = np.arange(0, 140, res) + res / 2
G = np.stack(np.meshgrid(xs, ys, zs, indexing='ij'), -1).reshape(-1, 3)
miss = np.zeros(len(G), np.uint8)
masks = {}
for rid in views:
    m = cv2.imread(os.path.join(OUT, 'masks', rid + '.png'), 0) > 0
    masks[rid] = m
    uv = (project_pts(cams[rid], G) + 0.5) * S - 0.5
    u = np.round(uv[:, 0]).astype(int); v = np.round(uv[:, 1]).astype(int)
    inside = (u >= 0) & (v >= 0) & (u < m.shape[1]) & (v < m.shape[0])
    hit = np.zeros(len(G), bool); hit[inside] = m[v[inside], u[inside]]
    miss += (~hit).astype(np.uint8)
occ = miss < MISS
vol = occ.reshape(len(xs), len(ys), len(zs))
np.savez_compressed(os.path.join(OUT, f'hull_{placement}.npz'), occ=vol, xs=xs, ys=ys, zs=zs)
P = G[occ]
print('voxels', occ.sum(), 'bbox min', P.min(0), 'max', P.max(0))
for rid in views:
    m = masks[rid]
    uv = (project_pts(cams[rid], P) + 0.5) * S - 0.5
    u = np.clip(np.round(uv[:, 0]).astype(int), 0, m.shape[1] - 1); v = np.clip(np.round(uv[:, 1]).astype(int), 0, m.shape[0] - 1)
    proj = np.zeros_like(m, np.uint8); proj[v, u] = 1
    proj = cv2.morphologyEx(proj, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)) > 0
    cov = (proj & m).sum() / m.sum(); extra = (proj & ~m).sum() / m.sum()
    print(rid, 'silhouette explained %.3f  hull outside silhouette %.3f' % (cov, extra))
