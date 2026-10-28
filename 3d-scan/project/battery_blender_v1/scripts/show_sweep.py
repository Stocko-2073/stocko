"""Visualise a sweep height map with a grid + legend; print profiles.
usage: show_sweep.py name conf_thresh [profile specs 'y=0' 'x=10' ...]"""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from common import *
name = sys.argv[1]; th = float(sys.argv[2])
d = np.load(os.path.join(OUT, f'sweep_{name}.npz')); H, S, ppm = d['h'], d['score'], int(d['ppm'])
u0, v1 = {"top": (-66, 44), "bot": (-66, 44)}.get(name, (-44, 52) if name in ("front", "back") else (-66, 52))
Hm = H.copy().astype(float); Hm[S < th] = np.nan
# median filter to denoise
Hf = cv2.medianBlur(np.nan_to_num(Hm, nan=-10).astype(np.float32), 5); Hf[np.isnan(Hm)] = np.nan
lo, hi = np.nanpercentile(Hf, 2), np.nanpercentile(Hf, 99.5)
hn = np.clip((np.nan_to_num(Hf, nan=lo) - lo) / (hi - lo), 0, 1)
col = cv2.applyColorMap((hn * 255).astype(np.uint8), cv2.COLORMAP_TURBO)
col[np.isnan(Hf)] = 40
sc = 2; col = cv2.resize(col, None, fx=sc, fy=sc, interpolation=cv2.INTER_NEAREST); P = ppm * sc
Hh, Ww = col.shape[:2]
for mm in range(-60, 61, 10):
    x = int((mm - u0) * P); cv2.line(col, (x, 0), (x, Hh - 1), (255, 255, 255), 1); cv2.putText(col, str(mm), (x + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
for mm in range(-40, 51, 10):
    y = int((v1 - mm) * P); cv2.line(col, (0, y), (Ww - 1, y), (255, 255, 255), 1); cv2.putText(col, str(mm), (2, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
# legend
for i in range(11):
    hv = lo + (hi - lo) * i / 10; c = cv2.applyColorMap(np.array([[int(i * 25.5)]], np.uint8), cv2.COLORMAP_TURBO)[0, 0].tolist()
    cv2.rectangle(col, (Ww - 90, 20 + i * 22), (Ww - 70, 40 + i * 22), c, -1); cv2.putText(col, '%.1f' % hv, (Ww - 65, 36 + i * 22), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
cv2.imwrite(f'/private/tmp/claude-503/-Users-samw3-prj-Make-stocko-3d-scan/9c5addd6-b839-4e81-8b71-1b263a1b3d27/scratchpad/sweepv_{name}.png', col)
np.save(os.path.join(OUT, f'sweepf_{name}.npy'), Hf)
for s in sys.argv[3:]:
    a, v = s.split('='); v = float(v)
    if a == 'y':
        row = int((v1 - v) * ppm); prof = np.nanmedian(Hf[row - 2:row + 3], 0)
        print(s, ' '.join('%d:%s' % (u0 + (i + 0.5) / ppm, '--' if np.isnan(p) else '%.1f' % p) for i, p in enumerate(prof) if i % (ppm * 2) == 0))
    else:
        c = int((v - u0) * ppm); prof = np.nanmedian(Hf[:, c - 2:c + 3], 1)
        print(s, ' '.join('%d:%s' % (v1 - (i + 0.5) / ppm, '--' if np.isnan(p) else '%.1f' % p) for i, p in enumerate(prof) if i % (ppm * 2) == 0))
