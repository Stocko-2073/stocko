"""Carve the joint hull at fine resolution with the fitted poses; save it and render
orthographic projections + slices in the battery frame with a mm grid."""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from joint_carve import *
from segment import project_pts

res = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
MISS = int(sys.argv[2]) if len(sys.argv) > 2 else 3
excl = set(sys.argv[3].split(',')) if len(sys.argv) > 3 else set()
poses = {k: np.array(v) for k, v in json.load(open(os.path.join(OUT, 'poses.json'))).items()}
full = {}
for rid in cams:
    m = cv2.imread(os.path.join(OUT, 'masks', rid + '.png'), 0)
    if m is not None: full[rid] = m > 127
G, ax = grid(res)
miss = np.zeros(len(G), np.int16)
for pl, T in poses.items():
    T = pose_mat(T)
    for rid in PLACEMENTS[pl]:
        if rid not in full or rid in excl: continue
        m = full[rid]
        for s in range(0, len(G), 2_000_000):
            Xm = G[s:s + 2_000_000] @ T[:3, :3].T + T[:3, 3]
            uv = np.round((project_pts(cams[rid], Xm) + 0.5) * 0.5 - 0.5).astype(int)
            ok = (uv[:, 0] >= 0) & (uv[:, 1] >= 0) & (uv[:, 0] < m.shape[1]) & (uv[:, 1] < m.shape[0])
            hit = np.zeros(len(uv), bool); hit[ok] = m[uv[ok, 1], uv[ok, 0]]
            miss[s:s + 2_000_000] += ~hit
occ = (miss < MISS).reshape([len(a) for a in ax])
np.savez_compressed(os.path.join(OUT, 'hull_joint.npz'), occ=occ, xs=ax[0], ys=ax[1], zs=ax[2])
I = np.argwhere(occ); P = np.c_[ax[0][I[:, 0]], ax[1][I[:, 1]], ax[2][I[:, 2]]]
print('voxels', len(P), 'extent', P.min(0) - res / 2, P.max(0) + res / 2)
