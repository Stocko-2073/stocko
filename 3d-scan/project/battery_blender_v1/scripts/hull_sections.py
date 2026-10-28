"""Render the joint hull as projections and slices (battery frame) on a mm grid.
usage: hull_sections.py [name] [slice specs like x=10 y=0 z=30 ...]"""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from common import *
d = np.load(os.path.join(OUT, 'hull_joint.npz'))
occ, xs, ys, zs = d['occ'], d['xs'], d['ys'], d['zs']
occ = occ & (zs >= 0)[None, None, :]
PPM = 6
RANGES = {'x': (-66, 66), 'y': (-44, 44), 'z': (-3, 52)}
AX = {'x': 0, 'y': 1, 'z': 2}
COORD = {'x': xs, 'y': ys, 'z': zs}


def draw(img2d, ha, va, title, fname):
    """img2d indexed [h-axis coord index, v-axis coord index] boolean or float"""
    h0, h1 = RANGES[ha]; v0, v1 = RANGES[va]
    W = int((h1 - h0) * PPM); H = int((v1 - v0) * PPM)
    out = np.full((H, W, 3), 255, np.uint8)
    hc, vc = COORD[ha], COORD[va]
    for i, h in enumerate(hc):
        for j, v in enumerate(vc):
            pass
    # vectorised fill
    hh, vv = np.meshgrid(hc, vc, indexing='ij')
    val = img2d.astype(float)
    u = ((hh - h0) * PPM).astype(int); w = ((v1 - vv) * PPM).astype(int)
    step = int(np.ceil((hc[1] - hc[0]) * PPM))
    for du in range(step):
        for dv in range(step):
            uu = np.clip(u + du - step // 2, 0, W - 1); ww = np.clip(w + dv - step // 2, 0, H - 1)
            g = (255 - np.clip(val, 0, 1) * 190).astype(np.uint8)
            m = val > 0
            out[ww[m], uu[m]] = g[m][:, None]
    for mm in range(int(h0), int(h1) + 1):
        if mm % 5: continue
        x = int((mm - h0) * PPM); col = (0, 0, 230) if mm % 10 == 0 else (240, 180, 180)
        cv2.line(out, (x, 0), (x, H - 1), col, 1)
        if mm % 10 == 0: cv2.putText(out, str(mm), (x + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 230), 1)
    for mm in range(int(v0), int(v1) + 1):
        if mm % 5: continue
        y = int((v1 - mm) * PPM); col = (0, 0, 230) if mm % 10 == 0 else (240, 180, 180)
        cv2.line(out, (0, y), (W - 1, y), col, 1)
        if mm % 10 == 0: cv2.putText(out, str(mm), (2, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 230), 1)
    cv2.putText(out, title, (40, H - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 0, 0), 2)
    cv2.imwrite(os.path.join(OUT, fname), out)
    return out


if __name__ == '__main__':
    name = sys.argv[1] if len(sys.argv) > 1 else 'joint'
    specs = sys.argv[2:]
    if not specs:
        draw(occ.any(1), 'x', 'z', 'side projection (along Y)', f'{name}_proj_side.png')
        draw(occ.any(0), 'y', 'z', 'end projection (along X)', f'{name}_proj_end.png')
        draw(occ.any(2), 'x', 'y', 'top projection (along Z)', f'{name}_proj_top.png')
    for s in specs:
        a, v = s.split('='); v = float(v); k = np.argmin(abs(COORD[a] - v))
        if a == 'x': draw(occ[k], 'y', 'z', f'slice x={v}', f'{name}_slice_x{v:g}.png')
        if a == 'y': draw(occ[:, k], 'x', 'z', f'slice y={v}', f'{name}_slice_y{v:g}.png')
        if a == 'z': draw(occ[:, :, k], 'x', 'y', f'slice z={v}', f'{name}_slice_z{v:g}.png')
