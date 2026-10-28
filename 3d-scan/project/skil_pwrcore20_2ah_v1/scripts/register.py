"""Register each placement to the object frame (the 'up' placement's mat frame).

T_P maps object-frame points to placement P's mat frame. For a voxel shape known in the
object frame, the pose is scored in P's views by
  - rendered shape over certain paper (chamfer distance into the paper), and
  - certain-battery pixels (dark, inside the ring) the rendering fails to cover.
The upright hull is inflated above its flat tops (views from 55 deg can't carve there), so the
two terms use different shapes: the lower body (z <= 28, eroded sideways; a subset of the battery)
must stay off the paper, and the hull below 46 (a superset) must cover every certain-battery pixel.
A coarse search over the 24 axis-aligned orientations x 24 yaws, then Powell refinement.

Usage: register.py <shape.npy> <placement> [...] [--refine]  -> updates out/registration.json
"""
import json
import sys

import cv2
import numpy as np
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation

from ac import OUT, PROJECT, Capture

S = 8                          # downscale for scoring
REG = OUT / "registration.json"


# From the upright SIFT cloud: the tower top is at z ~ 44 and the front shoulder at ~ 31, so the
# hull above 46 is carving artifact. Contact shadows widen the hull's base, so the subset is
# eroded sideways only (keeping the exact z = 0 base plane).
SUB_Z = (0.5, 28.0)
SUP_ZMAX = 46.0


def shape_points(npy: str, step: int = 2, sub: bool = False) -> np.ndarray:
    from scipy import ndimage
    h = np.load(OUT / "hull.npz"); xs, ys, zs = h["xs"], h["ys"], h["zs"]
    k = np.load(OUT / npy)
    if sub:
        band = (zs >= SUB_Z[0]) & (zs <= SUB_Z[1])
        k = ndimage.binary_erosion(k & band[None, None, :], structure=np.ones((3, 3, 1), bool), iterations=3)
    else:
        k = k & (zs <= SUP_ZMAX)[None, None, :]
    ij = np.argwhere(k[::step, ::step, ::step]) * step
    return np.c_[xs[ij[:, 0]], ys[ij[:, 1]], zs[ij[:, 2]]]


class View:
    def __init__(self, req: str):
        self.cap = Capture(req)
        notp = cv2.imread(str(OUT / "mask" / f"{req}.png"), 0) > 0
        H, W = notp.shape
        self.shape = (H // S, W // S)
        paper = ~notp
        # certain paper at low res: all sub-pixels paper
        p8 = paper[:self.shape[0] * S, :self.shape[1] * S].reshape(self.shape[0], S, self.shape[1], S).all((1, 3))
        self.paper = p8
        self.paper_dt = cv2.distanceTransform(p8.astype(np.uint8), cv2.DIST_L2, 3)
        v = cv2.cvtColor(self.cap.image, cv2.COLOR_BGR2HSV)[..., 2]
        dark = (v < 110) & notp
        # only inside the ring interior at z=0 (not markers/desk)
        field = np.zeros(v.shape, np.uint8)
        w, h = 87.0, 118.0
        poly = self.cap.project(np.array([[-w, -h, 0], [w, -h, 0], [w, h, 0], [-w, h, 0]]))
        cv2.fillPoly(field, [np.round(poly).astype(np.int32)], 1)
        dark &= field > 0
        d8 = dark[:self.shape[0] * S, :self.shape[1] * S].reshape(self.shape[0], S, self.shape[1], S).mean((1, 3)) > 0.5
        self.dark = d8
        self.n_dark = max(1, int(d8.sum()))

    def render(self, pts_mat: np.ndarray) -> np.ndarray:
        uv = np.round(self.cap.project(pts_mat) / S).astype(int)
        ok = (uv[:, 0] >= 0) & (uv[:, 0] < self.shape[1]) & (uv[:, 1] >= 0) & (uv[:, 1] < self.shape[0])
        im = np.zeros(self.shape, np.uint8)
        im[uv[ok, 1], uv[ok, 0]] = 1
        return cv2.dilate(im, np.ones((3, 3), np.uint8)) > 0

    def score(self, sub_mat: np.ndarray, sup_mat: np.ndarray) -> float:
        over = self.paper_dt[self.render(sub_mat)].sum() / self.n_dark
        r = self.render(sup_mat)
        miss_mask = self.dark & ~r
        if miss_mask.any():
            dt = cv2.distanceTransform((~r).astype(np.uint8), cv2.DIST_L2, 3)
            miss = dt[miss_mask].sum() / self.n_dark
        else:
            miss = 0.0
        return over + miss


def transform(x: np.ndarray, pts: np.ndarray) -> np.ndarray:
    return Rotation.from_rotvec(x[:3]).apply(pts) + x[3:]


def axis_rotations() -> list[np.ndarray]:
    out = []
    for perm in [(0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0)]:
        for signs in np.ndindex(2, 2, 2):
            M = np.zeros((3, 3))
            for i, (p, s) in enumerate(zip(perm, signs)):
                M[p, i] = 1 if s == 0 else -1
            if np.linalg.det(M) > 0:
                out.append(M)
    return out


def register(sub: np.ndarray, sup: np.ndarray, views: list[View], x0: np.ndarray | None = None,
             up_sign: float | None = None) -> tuple[np.ndarray, float]:
    """up_sign: if given, only orientations whose object +z points that way (+1 up, -1 down)."""
    ctr = sub.mean(0)
    top = views[0]  # the straight-down view: its dark blob centroid gives x, y
    ys_, xs_ = np.nonzero(top.dark)
    c_uv = np.array([xs_.mean(), ys_.mean()]) * S
    sub_s, sup_s = sub[::2], sup[::4]

    def energy(x, which=views):
        return float(np.mean([v.score(transform(x, sub_s), transform(x, sup_s)) for v in which]))

    def refine(x):
        res = minimize(energy, x, method="Powell",
                       options={"xtol": 1e-3, "ftol": 1e-4, "maxiter": 4000,
                                "direc": np.diag([0.02, 0.02, 0.02, 2, 2, 2])})
        return res.x, res.fun

    if x0 is not None:
        return refine(x0)
    cands = []
    if True:
        for M in axis_rotations():
            for yaw in np.radians(np.arange(0, 360, 15)):
                R = Rotation.from_euler("z", yaw) * Rotation.from_matrix(M)
                if up_sign is not None and R.as_matrix()[2, 2] * up_sign < 0.5:
                    continue
                q = R.apply(sub_s - ctr)
                z0 = -q[:, 2].min()
                guess = top.cap.on_plane_z(c_uv, z0)[0]
                x = np.r_[R.as_rotvec(), np.array([guess[0], guess[1], z0]) - R.apply(ctr)]
                cands.append((energy(x), x))
    # Refine the best few coarse candidates (a 15 deg yaw grid can rank the right pose low).
    cands.sort(key=lambda c: c[0])
    out = [refine(x) for _, x in cands[:8]]
    print("  refined candidates:", [round(e, 3) for _, e in out])
    return min(out, key=lambda r: r[1])


if __name__ == "__main__":
    shape_file, names = sys.argv[1], sys.argv[2:]
    placements = json.loads((PROJECT / "placements.json").read_text())
    reg = json.loads(REG.read_text()) if REG.exists() else {}
    names = [n for n in names if not n.startswith("--")]
    sub, sup = shape_points(shape_file, sub=True), shape_points(shape_file)
    for name in names:
        views = [View(r) for r in placements[name]["views"].split()]
        x0 = np.array(reg[name]["x"]) if name in reg and "--refine" in sys.argv else None
        up_sign = placements[name].get("object_z_up")
        x, e = register(sub, sup, views, x0, up_sign)
        T = np.eye(4); T[:3, :3] = Rotation.from_rotvec(x[:3]).as_matrix(); T[:3, 3] = x[3:]
        per = [round(float(v.score(transform(x, sub[::2]), transform(x, sup[::4]))), 3) for v in views]
        print(f"{name}: energy {e:.3f} per view {per}\n  T=\n{np.round(T, 3)}")
        reg[name] = {"x": x.tolist(), "T": T.tolist(), "energy": float(e), "per_view": per}
        REG.write_text(json.dumps(reg, indent=1))
