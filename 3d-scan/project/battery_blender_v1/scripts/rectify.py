"""Ortho-rectify a photo onto a plane given in the battery frame, with a mm grid.

usage: rectify.py rid plane name [ppm]
  plane = 'z=46' (top-down: u=+X right... ), 'y=39', 'y=-39', 'x=-60', 'x=52'
Output image: horizontal axis u, vertical axis v (up), labelled in battery-frame mm.
"""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from joint_carve import pose_mat, cams, PLACEMENTS
from common import *
from segment import project_pts

poses = {k: np.array(v) for k, v in json.load(open(os.path.join(OUT, 'poses.json'))).items()}


def rectify(rid, plane, ppm=10, ranges=None, grid=True):
    pl = next(p for p, v in PLACEMENTS.items() if rid in v)
    T = pose_mat(poses[pl])
    a, val = plane.split('='); val = float(val)
    # (u axis, v axis) per plane, chosen so the image reads naturally when viewed from outside
    if a == 'z':   U, V, N = np.array([1, 0, 0.]), np.array([0, 1, 0.]), 2      # from above, front to the right
    if a == 'y' and val > 0: U, V, N = np.array([-1, 0, 0.]), np.array([0, 0, 1.]), 1  # left side, seen from +Y
    if a == 'y' and val <= 0: U, V, N = np.array([1, 0, 0.]), np.array([0, 0, 1.]), 1  # right side, seen from -Y
    if a == 'x' and val > 0: U, V, N = np.array([0, 1, 0.]), np.array([0, 0, 1.]), 0   # front, seen from +X
    if a == 'x' and val <= 0: U, V, N = np.array([0, -1, 0.]), np.array([0, 0, 1.]), 0  # back, seen from -X
    if a == 'zb': U, V, N = np.array([1, 0, 0.]), np.array([0, -1, 0.]), 2          # bottom seen from below
    if ranges is None:
        ranges = {'z': ((-66, 66), (-44, 44)), 'zb': ((-66, 66), (-44, 44)), 'y': ((-66, 66), (-4, 52)), 'x': ((-44, 44), (-4, 52))}[a]
    (u0, u1), (v0, v1) = ranges
    if U[0] < 0 or U[1] < 0: pass
    W = int((u1 - u0) * ppm); H = int((v1 - v0) * ppm)
    uu, vv = np.meshgrid(u0 + (np.arange(W) + 0.5) / ppm, v1 - (np.arange(H) + 0.5) / ppm)
    P = np.zeros((H * W, 3)); P[:, N] = val
    P += uu.reshape(-1, 1) * U + vv.reshape(-1, 1) * V
    Xm = P @ T[:3, :3].T + T[:3, 3]
    uv = project_pts(cams[rid], Xm).astype(np.float32).reshape(H, W, 2)
    img = load_image(rid)
    out = cv2.remap(img, uv[..., 0], uv[..., 1], cv2.INTER_LINEAR, borderValue=(255, 255, 255))
    if grid:
        for mm in range(int(np.ceil(u0)), int(u1) + 1):
            if mm % 5: continue
            x = int((mm - u0) * ppm); col = (0, 0, 255) if mm % 10 == 0 else (255, 160, 0)
            cv2.line(out, (x, 0), (x, H - 1), col, 1)
            if mm % 10 == 0: cv2.putText(out, str(mm), (x + 2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
        for mm in range(int(np.ceil(v0)), int(v1) + 1):
            if mm % 5: continue
            y = int((v1 - mm) * ppm); col = (0, 0, 255) if mm % 10 == 0 else (255, 160, 0)
            cv2.line(out, (0, y), (W - 1, y), col, 1)
            if mm % 10 == 0: cv2.putText(out, str(mm), (2, y - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
    return out


if __name__ == '__main__':
    rid, plane, name = sys.argv[1:4]
    ppm = float(sys.argv[4]) if len(sys.argv) > 4 else 10
    rng = None
    if len(sys.argv) > 5:
        a = list(map(float, sys.argv[5].split(','))); rng = ((a[0], a[1]), (a[2], a[3]))
    out = rectify(rid, plane, ppm, rng)
    p = f'/private/tmp/claude-503/-Users-samw3-prj-Make-stocko-3d-scan/9c5addd6-b839-4e81-8b71-1b263a1b3d27/scratchpad/{name}.jpg'
    cv2.imwrite(p, out, [cv2.IMWRITE_JPEG_QUALITY, 90]); print(p, out.shape)
