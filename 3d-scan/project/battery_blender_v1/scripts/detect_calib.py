"""Detect mat markers in every battery capture and refine camera poses.

Per image: 6-DoF pose.  Shared: radial distortion k1, k2 (normalized coords) and a
common focal scale.  Per-image fx/cx/cy come from ARKit (focus breathing changes fx).
Writes out/cams.json with refined K, dist and camera_to_mat for each capture.
"""
import sys, json
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from common import *
from scipy.optimize import least_squares

aruco = cv2.aruco
_P = aruco.DetectorParameters()
_P.adaptiveThreshWinSizeMin, _P.adaptiveThreshWinSizeMax, _P.adaptiveThreshWinSizeStep = 5, 63, 6
_P.minMarkerPerimeterRate = 0.01
det = aruco.ArucoDetector(aruco.getPredefinedDictionary(aruco.DICT_4X4_100), _P)
DS = 0.35  # detect on a downscaled copy (more robust to blur), refine corners at full res
M3 = marker_corners_3d()

data = {}
for p, ids in PLACEMENTS.items():
    for rid in ids:
        img = load_image(rid)
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners, mids, _ = det.detectMarkers(cv2.resize(g, None, fx=DS, fy=DS, interpolation=cv2.INTER_AREA))
        corners = [(c + 0.5) / DS - 0.5 for c in corners]
        crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.01)
        obj, imgp = [], []
        for c, i in zip(corners, mids.flatten() if mids is not None else []):
            if int(i) not in M3: continue
            c = cv2.cornerSubPix(g, c.reshape(4, 1, 2).astype(np.float32), (9, 9), (-1, -1), crit).reshape(4, 2)
            obj.append(M3[int(i)]); imgp.append(c)
        if len(obj) < 6:
            print(rid, 'skipped: only', len(obj), 'markers'); continue
        m = load_meta(rid)
        K = np.array(m['intrinsics']['K'])
        T = np.array(m['pose']['camera_to_mat'])
        data[rid] = dict(obj=np.concatenate(obj), img=np.concatenate(imgp), K=K, T=T, placement=p)
        print(rid, len(obj), 'markers')

rids = list(data)

def T2rt(T):
    Tm = np.linalg.inv(T)  # mat->camera
    r, _ = cv2.Rodrigues(Tm[:3, :3]); return np.r_[r.ravel(), Tm[:3, 3]]

def project(X, rt, K, k1, k2):
    R, _ = cv2.Rodrigues(rt[:3]); Xc = X @ R.T + rt[3:]
    x = Xc[:, :2] / Xc[:, 2:3]
    r2 = (x ** 2).sum(1, keepdims=True)
    x = x * (1 + k1 * r2 + k2 * r2 * r2)
    return np.c_[K[0, 0] * x[:, 0] + K[0, 2], K[1, 1] * x[:, 1] + K[1, 2]]

def unpack(v):
    k1, k2, fs = v[:3]
    return k1, k2, fs, v[3:].reshape(-1, 6)

def resid(v, robust_mask=None):
    k1, k2, fs, rts = unpack(v)
    out = []
    for i, rid in enumerate(rids):
        d = data[rid]; K = d['K'].copy(); K[0, 0] *= fs; K[1, 1] *= fs
        out.append((project(d['obj'], rts[i], K, k1, k2) - d['img']).ravel())
    return np.concatenate(out)

v0 = np.r_[0, 0, 1.0, np.concatenate([T2rt(data[r]['T']) for r in rids])]

def report(v, tag):
    r = resid(v).reshape(-1, 2)
    e = np.linalg.norm(r, axis=1)
    print(tag, 'rms px %.3f  median %.3f  p95 %.3f' % (np.sqrt((e ** 2).mean()), np.median(e), np.percentile(e, 95)))

report(v0, 'arkit poses, no dist:')
# first poses only (no distortion) for a fair baseline
sol0 = least_squares(lambda w: resid(np.r_[0, 0, 1.0, w]), v0[3:], loss='huber', f_scale=2.0)
report(np.r_[0, 0, 1.0, sol0.x], 'pnp poses, no dist:')
# drop misdetected markers (any corner > 12 px off after the pose-only fit)
r0 = resid(np.r_[0, 0, 1.0, sol0.x]).reshape(-1, 2); off = 0
for rid in rids:
    n = len(data[rid]['obj']); e = np.linalg.norm(r0[off:off + n], axis=1).reshape(-1, 4).max(1); off += n
    keep = np.repeat(e < 12, 4)
    if (~keep).any(): print(rid, 'dropping', int((~keep).sum() // 4), 'marker(s)')
    data[rid]['obj'] = data[rid]['obj'][keep]; data[rid]['img'] = data[rid]['img'][keep]
report(np.r_[0, 0, 1.0, sol0.x], 'after outlier drop, no dist:')
sol = least_squares(resid, np.r_[0, 0, 1.0, sol0.x], loss='huber', f_scale=2.0)
k1, k2, fs, rts = unpack(sol.x)
report(sol.x, 'with k1 k2 fscale:')
print('k1 %.4f k2 %.4f fscale %.5f' % (k1, k2, fs))

# per-image rms
r = resid(sol.x).reshape(-1, 2); off = 0
cams = {}
for i, rid in enumerate(rids):
    n = len(data[rid]['obj']); e = np.linalg.norm(r[off:off + n], axis=1); off += n
    R, _ = cv2.Rodrigues(rts[i][:3]); Tm = np.eye(4); Tm[:3, :3] = R; Tm[:3, 3] = rts[i][3:]
    Tc2m = np.linalg.inv(Tm)
    K = data[rid]['K'].copy(); K[0, 0] *= fs; K[1, 1] *= fs
    shift = np.linalg.norm(Tc2m[:3, 3] - data[rid]['T'][:3, 3])
    print(rid, 'rms %.2f px, eye moved %.2f mm vs arkit' % (np.sqrt((e ** 2).mean()), shift))
    cams[rid] = dict(K=K.tolist(), dist=[k1, k2], camera_to_mat=Tc2m.tolist(), placement=data[rid]['placement'],
                     rms_px=float(np.sqrt((e ** 2).mean())), w=4032, h=3024)
json.dump(cams, open(os.path.join(OUT, 'cams.json'), 'w'), indent=1)
