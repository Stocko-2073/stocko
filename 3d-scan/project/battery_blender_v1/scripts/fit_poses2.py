"""Fix the upside-down placements (front end = feet toward image bottom = mat -y, seen in
r0094/r0106), then jointly refine all placement poses together."""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from fit_poses import *

poses = {k: np.array(v) for k, v in json.load(open(os.path.join(OUT, 'poses.json'))).items()}
res = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
G, ax = grid(res)
vA = [r for r in PLACEMENTS['A'] if r in MASKS]
for pl in ['D2', 'D1']:
    cand = [c for c in candidates(pl) if (Rot.from_rotvec(c[:3]).as_matrix()[:, 0])[1] < 0][0]
    p = dict(poses); p[pl] = cand
    vbp = {'A': vA, pl: [r for r in PLACEMENTS[pl] if r in MASKS]}
    q, s = refine(p, pl, vbp, res, 2, G, iters=150)
    poses[pl] = q
    print(pl, 'refined (feet toward -y) score %.4f' % s)
# joint refinement: all placements together
vall = {pl: [r for r in v if r in MASKS] for pl, v in PLACEMENTS.items()}
vall = {k: v for k, v in vall.items() if v and k in poses}
for rnd in range(2):
    for pl in [k for k in vall if k != 'A']:
        q, s = refine(poses, pl, vall, res, 3, G, iters=80, step=(1.0, 1.0))
        poses[pl] = q
        print('round', rnd, pl, 'joint score %.4f' % s)
json.dump({k: v.tolist() for k, v in poses.items()}, open(os.path.join(OUT, 'poses.json'), 'w'), indent=1)
s, occ, d = score(poses, vall, res, 3, G)
for pl, v in vall.items(): print(pl, ' '.join('%s:%.3f' % (r, d[r]) for r in v))
