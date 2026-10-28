"""Find each placement's pose (battery -> mat) by joint-hull silhouette consistency."""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from joint_carve import *

H0, W0, L0 = 46.0, 75.0, 120.0
fr = json.load(open(os.path.join(OUT, 'frame_A.json')))


def pose_from_axes(ex, ey, ez, origin):
    R = np.c_[ex, ey, ez]
    return np.r_[Rot.from_matrix(R).as_rotvec(), origin]


def rect_of(rid, z):
    """minAreaRect of the top-down silhouette back-projected to height z"""
    from segment import project_pts
    m = cv2.imread(os.path.join(OUT, 'masks', rid + '.png'), 0)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cnts, key=cv2.contourArea).reshape(-1, 2).astype(float)
    uv = (c + 0.5) / 0.5 - 0.5
    cam = cams[rid]; K = np.array(cam['K']); T = np.array(cam['camera_to_mat']); k1, k2 = cam['dist']
    x = (uv[:, 0] - K[0, 2]) / K[0, 0]; y = (uv[:, 1] - K[1, 2]) / K[1, 1]; xu, yu = x.copy(), y.copy()
    for _ in range(10):
        r2 = xu ** 2 + yu ** 2; f = 1 + k1 * r2 + k2 * r2 * r2; xu = x / f; yu = y / f
    d = np.c_[xu, yu, np.ones_like(xu)] @ T[:3, :3].T; o = T[:3, 3]; t = (z - o[2]) / d[:, 2]
    P = (o + d * t[:, None])[:, :2]
    (cx, cy), (w, h), a = cv2.minAreaRect(P.astype(np.float32))
    if w < h: a += 90  # angle of the long side
    return np.array([cx, cy]), np.radians(a)


def candidates(pl):
    out = []
    if pl == 'A':
        t = np.radians(fr['azimuth_deg']); ex = np.array([np.cos(t), np.sin(t), 0]); ez = np.array([0, 0, 1.])
        out.append(pose_from_axes(ex, np.cross(ez, ex), ez, np.r_[fr['origin'], 0]))
        return out
    top = PLACEMENTS[pl][0]
    if pl.startswith('B'):
        c, a = rect_of(top, W0)
        for th in (a, a + np.pi):
            ex = np.array([np.cos(th), np.sin(th), 0])
            for s in (1, -1):
                ey = np.array([0, 0, s]); ez = np.cross(ex, ey)
                out.append(pose_from_axes(ex, ey, ez, np.r_[c - H0 / 2 * ez[:2], W0 / 2]))
    elif pl.startswith('C'):
        c, a = rect_of(top, L0)
        for k in range(4):
            ph = a + k * np.pi / 2
            ez = np.array([np.cos(ph), np.sin(ph), 0]); ex = np.array([0, 0, 1.]); ey = np.cross(ez, ex)
            out.append(pose_from_axes(ex, ey, ez, np.r_[c - H0 / 2 * ez[:2], L0 / 2]))
    elif pl.startswith('D'):
        c, a = rect_of(top, H0)
        for th in (a, a + np.pi):
            ex = np.array([np.cos(th), np.sin(th), 0]); ez = np.array([0, 0, -1.]); ey = np.cross(ez, ex)
            out.append(pose_from_axes(ex, ey, ez, np.r_[c, H0]))
    return out


def refine(poses, pl, vbp, res, miss, G, iters=150, step=(2.0, 2.0)):
    base = poses[pl].copy()
    def f(dp):
        p = dict(poses); q = base.copy()
        dR = Rot.from_rotvec(np.radians(dp[:3])); q[:3] = (dR * Rot.from_rotvec(base[:3])).as_rotvec(); q[3:] = base[3:] + dp[3:]
        p[pl] = q
        return -score(p, vbp, res, miss, G)[0]
    x0 = np.zeros(6)
    simplex = [x0] + [x0 + np.eye(6)[i] * (step[0] if i < 3 else step[1]) for i in range(6)]
    r = minimize(f, x0, method='Nelder-Mead', options=dict(maxfev=iters, initial_simplex=np.array(simplex), xatol=0.05, fatol=1e-5))
    q = base.copy(); dR = Rot.from_rotvec(np.radians(r.x[:3])); q[:3] = (dR * Rot.from_rotvec(base[:3])).as_rotvec(); q[3:] = base[3:] + r.x[3:]
    return q, -r.fun


if __name__ == '__main__':
    res = 2.0
    G, ax = grid(res)
    poses = {'A': candidates('A')[0]}
    vA = [r for r in PLACEMENTS['A'] if r in MASKS]
    s0 = score(poses, {'A': vA}, res, 2, G)[0]
    print('A alone mean IoU %.4f' % s0)
    for pl in ['B2', 'C2', 'D2', 'B1', 'D1']:
        vbp = {'A': vA, pl: [r for r in PLACEMENTS[pl] if r in MASKS]}
        best = None
        for i, cand in enumerate(candidates(pl)):
            p = dict(poses); p[pl] = cand
            q, s = refine(p, pl, vbp, res, 2, G, iters=50, step=(3.0, 4.0))
            p[pl] = q
            _, _, d = score(p, vbp, res, 2, G)
            sp = np.mean([d[r] for r in vbp[pl]])
            print(pl, 'candidate', i, 'score %.4f  own-view IoU %.4f' % (s, sp))
            if best is None or sp > best[0]: best = (sp, q)
        poses[pl] = best[1]
        q, s = refine(poses, pl, vbp, res, 2, G)
        poses[pl] = q
        print(pl, 'refined IoU %.4f' % s, 'pose', np.round(q, 3))
    json.dump({k: v.tolist() for k, v in poses.items()}, open(os.path.join(OUT, 'poses.json'), 'w'), indent=1)
