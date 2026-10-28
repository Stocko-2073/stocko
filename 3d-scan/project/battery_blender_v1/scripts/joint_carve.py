"""Joint visual hull over all placements, in the battery frame.

Battery frame: origin at the footprint centre on the bottom face, +X toward the terminal
(front) end, +Z up through the rails, +Y = Z x X.  Each placement P has a rigid pose
T_P (battery -> mat).  Poses are refined by coordinate descent to maximise the mean IoU
between each view's silhouette and the projection of the joint hull.
"""
import sys, time
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from common import *
from segment import project_pts
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation as Rot

cams = json.load(open(os.path.join(OUT, 'cams.json')))
QS = 0.25  # work at quarter resolution
MASKS = {}
for rid in cams:
    m = cv2.imread(os.path.join(OUT, 'masks', rid + '.png'), 0)
    if m is None: continue
    MASKS[rid] = cv2.resize(m, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA) > 127


def grid(res, box=((-72, 72), (-46, 46), (-4, 70))):
    ax = [np.arange(a, b, res) + res / 2 for a, b in box]
    return np.stack(np.meshgrid(*ax, indexing='ij'), -1).reshape(-1, 3), ax


def pose_mat(p):
    T = np.eye(4); T[:3, :3] = Rot.from_rotvec(p[:3]).as_matrix(); T[:3, 3] = p[3:]; return T


def view_uv(rid, Xmat):
    uv = (project_pts(cams[rid], Xmat) + 0.5) * QS - 0.5
    return np.round(uv).astype(int)


def carve(G, poses, views_by_pl, miss_max):
    miss = np.zeros(len(G), np.int16)
    for pl, vids in views_by_pl.items():
        T = pose_mat(poses[pl]); Xm = G @ T[:3, :3].T + T[:3, 3]
        for rid in vids:
            m = MASKS[rid]; uv = view_uv(rid, Xm)
            ok = (uv[:, 0] >= 0) & (uv[:, 1] >= 0) & (uv[:, 0] < m.shape[1]) & (uv[:, 1] < m.shape[0])
            hit = np.zeros(len(G), bool); hit[ok] = m[uv[ok, 1], uv[ok, 0]]
            miss += ~hit
    return miss < miss_max


def ious(G, occ, poses, views_by_pl, res):
    out = {}
    P = G[occ]
    for pl, vids in views_by_pl.items():
        T = pose_mat(poses[pl]); Xm = P @ T[:3, :3].T + T[:3, 3]
        for rid in vids:
            m = MASKS[rid]; uv = view_uv(rid, Xm)
            ok = (uv[:, 0] >= 0) & (uv[:, 1] >= 0) & (uv[:, 0] < m.shape[1]) & (uv[:, 1] < m.shape[0])
            img = np.zeros(m.shape, np.uint8); img[uv[ok, 1], uv[ok, 0]] = 1
            r = max(1, int(round(res * cams[rid]['K'][0][0] * QS / 300 * 0.8)))
            img = cv2.dilate(img, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))) > 0
            out[rid] = (img & m).sum() / max(1, (img | m).sum())
    return out


def score(poses, views_by_pl, res, miss_max, G):
    occ = carve(G, poses, views_by_pl, miss_max)
    if occ.sum() < 100: return 0.0, occ, {}
    d = ious(G, occ, poses, views_by_pl, res)
    # every placement counts equally, however many views it has
    per = [np.mean([d[r] for r in v]) for v in views_by_pl.values()]
    return float(np.mean(per)), occ, d


if __name__ == '__main__':
    pass
