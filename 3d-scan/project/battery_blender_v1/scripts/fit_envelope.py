"""Alternate: refine placement poses (B/C/D) and envelope dimensions against all views."""
import sys, time
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from envelope import *
from scipy.optimize import minimize

rids = [r for r in cams]
D = Data(rids)
poses = {k: np.array(v) for k, v in json.load(open(os.path.join(OUT, 'poses.json'))).items()}
pfile = os.path.join(OUT, 'envelope_params.json')
p = dict(DEFAULT)
if os.path.exists(pfile): p.update(json.load(open(pfile)))
rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 2


def rest_on_mat(q, shape):
    """shift the pose vertically so the lowest point of the envelope touches the mat"""
    T = pose_mat(q)
    z = min((V @ T[:3, :3].T + T[:3, 3])[:, 2].min() for V in pieces(shape))
    q = q.copy(); q[5] -= z
    return q


def compose(base, dp):
    q = base.copy()
    q[:3] = (Rot.from_rotvec(np.radians(dp[:3])) * Rot.from_rotvec(base[:3])).as_rotvec()
    q[3:5] = base[3:5] + dp[3:5]
    return rest_on_mat(q, p)


def refine_pose(pl):
    vids = [r for r in PLACEMENTS[pl] if r in D.mask]
    base = rest_on_mat(poses[pl], p)
    def f(dp):
        pp = dict(poses); pp[pl] = compose(base, dp)
        return total_cost(p, pp, D, rids=vids)
    b = [(-8, 8)] * 3 + [(-8, 8)] * 2
    r = minimize(f, np.zeros(5), method='Powell', bounds=b, options=dict(xtol=0.02, ftol=1e-4, maxfev=800))
    poses[pl] = compose(base, r.x)
    return r.fun, r.x


SHAPE_KEYS = [k for k in DEFAULT]
# plausible ranges (mm) around the photo-read values; the fitter may not wander outside them
BOUNDS = dict(x_back=(-62, -56), x_front=(50, 56), half_w=(35.5, 39), deck_z=(27, 33), bot_ch=(1, 4), side_top_ch=(2, 8),
              front_top_ch=(1, 7), back_top_ch=(1, 7), corner_ch_back=(3, 11), corner_ch_front=(1, 7),
              lb_x1=(-36, -27), lb_hw=(22, 32), lb_z1=(43, 48.5), lb_back_ch=(2, 10), lb_side_ch=(1, 7),
              t_x1=(30, 40), t_plate_x1=(24, 33), t_plate_hw=(21.5, 27), t_plate_z1=(42, 46), t_base_hw=(20, 25),
              foot_y0=(10, 17), foot_y1=(26, 33), foot_x1=(56, 63), foot_top_back=(24, 32), foot_top_front=(20, 30))


def refine_shape(keys):
    x0 = np.array([p[k] for k in keys])
    def f(x):
        pp = dict(p); pp.update(dict(zip(keys, x)))
        try:
            return total_cost(pp, poses, D)
        except Exception:
            return 1e3
    r = minimize(f, x0, method='Powell', bounds=[BOUNDS[k] for k in keys], options=dict(xtol=0.05, ftol=1e-4, maxfev=3000))
    p.update(dict(zip(keys, r.x)))
    return r.fun


for pl in ['B1', 'B2', 'C2', 'D1', 'D2']:
    q = rest_on_mat(poses[pl], p); print(pl, 'rest shift %.2f mm' % (q[5] - poses[pl][5])); poses[pl] = q
print('start cost %.4f' % total_cost(p, poses, D))
for rnd in range(rounds):
    for pl in ['B1', 'B2', 'C2', 'D1', 'D2']:
        c, dx = refine_pose(pl)
        print('round %d pose %s cost %.3f  delta rot(deg) %s xy(mm) %s' % (rnd, pl, c, np.round(dx[:3], 2), np.round(dx[3:], 2)), flush=True)
    for pl in ['B1', 'B2', 'C2', 'D1', 'D2']: poses[pl] = rest_on_mat(poses[pl], p)
    t = time.time()
    c = refine_shape(SHAPE_KEYS)
    print('round %d shape cost %.4f (%.0fs)' % (rnd, c, time.time() - t), flush=True)
    print(json.dumps({k: round(v, 2) for k, v in p.items()}), flush=True)
    json.dump(p, open(pfile, 'w'), indent=1)
    json.dump({k: v.tolist() for k, v in poses.items()}, open(os.path.join(OUT, 'poses.json'), 'w'), indent=1)
c = total_cost(p, poses, D, detail=True)
for pl, v in PLACEMENTS.items():
    print(pl, ' '.join('%s:%.2f' % (r, c[r]) for r in v if r in c))
