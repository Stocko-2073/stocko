"""Plane-sweep stereo: height map of one side of the battery.

For each height h (along the chosen battery axis) every view is rectified onto that plane;
cost = mean of the best-K NCC scores between the reference view and the others.
usage: plane_sweep.py name ref view1,view2,... axis(z|zb|y|-y|x|-x) h0 h1 [step]
"""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from rectify import *

name, ref = sys.argv[1], sys.argv[2]
views = sys.argv[3].split(',')
axis = sys.argv[4]; h0, h1 = float(sys.argv[5]), float(sys.argv[6])
step = float(sys.argv[7]) if len(sys.argv) > 7 else 0.25
PPM = 5; WIN = 9; K = 3
plane_key = {'z': 'z', 'zb': 'zb', 'y': 'y', '-y': 'y', 'x': 'x', '-x': 'x'}[axis]
sign = -1 if axis.startswith('-') else 1
imgs = {}


def gray(im):
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return g


def ncc(a, b):
    k = (WIN, WIN)
    ma = cv2.blur(a, k); mb = cv2.blur(b, k)
    va = cv2.blur(a * a, k) - ma * ma; vb = cv2.blur(b * b, k) - mb * mb
    cab = cv2.blur(a * b, k) - ma * mb
    return cab / np.sqrt(np.maximum(va * vb, 1e-3)), np.minimum(va, vb)


hs = np.arange(h0, h1 + 1e-6, step)
best = None
for h in hs:
    plane = f'{plane_key}={sign * h if plane_key != "zb" else h}'
    R = gray(rectify(ref, plane, PPM, grid=False))
    scores = []
    for v in views:
        Vg = gray(rectify(v, plane, PPM, grid=False))
        s, var = ncc(R, Vg)
        s[var < 4] = -1  # textureless
        scores.append(s)
    S = np.sort(np.stack(scores), 0)[-K:].mean(0)
    if best is None:
        best = S.copy(); hbest = np.full(S.shape, h, np.float32); second = np.full(S.shape, -1, np.float32)
    else:
        upd = S > best
        second = np.where(upd, best, np.maximum(second, S))
        hbest[upd] = h; best[upd] = S[upd]
    print('h=%.2f mean score %.3f' % (h, S.mean()), flush=True) if abs(h * 4 - round(h * 4)) < 1e-6 and int(round(h * 4)) % 20 == 0 else None
np.savez_compressed(os.path.join(OUT, f'sweep_{name}.npz'), h=hbest, score=best, ppm=PPM)
# visualise: height colour map, masked by confidence
conf = best > 0.6
hn = np.clip((hbest - h0) / (h1 - h0), 0, 1)
col = cv2.applyColorMap((hn * 255).astype(np.uint8), cv2.COLORMAP_JET)
col[~conf] = (col[~conf] * 0.25).astype(np.uint8)
col = cv2.resize(col, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
cv2.imwrite(f'/private/tmp/claude-503/-Users-samw3-prj-Make-stocko-3d-scan/9c5addd6-b839-4e81-8b71-1b263a1b3d27/scratchpad/sweep_{name}.png', col)
print('done; confident fraction %.2f' % conf.mean())
