"""Register the model (battery frame) into a placement's views by its silhouette.

Energy per view (1/8 res): chamfer distance of rendered model pixels into certain paper, plus
chamfer distance of certain-battery pixels (dark, in the ring interior) the rendering misses.
Starts from out/registration.json "<p>_model" if present, else from "<p>" composed with the
battery frame ('up': the battery frame itself). Writes "<p>_model".

Usage: modelreg.py <placement> [...]
"""
import json
import sys

import cv2
import numpy as np
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation

from ac import OUT, PROJECT, bat_to_obj
from overlay import model_mesh
from register import View, S

REG = OUT / "registration.json"


def T_of(x):
    T = np.eye(4); T[:3, :3] = Rotation.from_rotvec(x[:3]).as_matrix(); T[:3, 3] = x[3:]; return T


def x_of(T):
    return np.r_[Rotation.from_matrix(T[:3, :3]).as_rotvec(), T[:3, 3]]


def bat_frame_T():
    o = bat_to_obj(np.zeros((1, 3)))[0]
    ex = bat_to_obj(np.array([[1, 0, 0]]))[0] - o
    ey = bat_to_obj(np.array([[0, 1, 0]]))[0] - o
    T = np.eye(4); T[:3, 0] = ex; T[:3, 1] = ey; T[:3, 2] = np.cross(ex, ey); T[:3, 3] = o
    return T


def render_sil(view, V_mat, F):
    uv = view.cap.project(V_mat) / S
    im = np.zeros(view.shape, np.uint8)
    pts = np.round(uv * 16).astype(np.int32)
    for f in F:
        cv2.fillConvexPoly(im, pts[f], 1, shift=4)
    return im > 0


def score(view, V_mat, F):
    r = render_sil(view, V_mat, F)
    over = view.paper_dt[r].sum() / view.n_dark
    m = view.dark & ~r
    miss = cv2.distanceTransform((~r).astype(np.uint8), cv2.DIST_L2, 3)[m].sum() / view.n_dark if m.any() else 0.0
    return over + miss


if __name__ == "__main__":
    placements = json.loads((PROJECT / "placements.json").read_text())
    reg = json.loads(REG.read_text())
    mesh = model_mesh()
    V, F = mesh.vertices, mesh.faces
    Tb = bat_frame_T()
    for name in sys.argv[1:]:
        views = [View(r) for r in placements[name]["views"].split()]
        if name + "_model" in reg:
            T0 = np.array(reg[name + "_model"]["T"])
        elif name == "up":
            T0 = Tb
        else:
            T0 = np.array(reg[name]["T"]) @ Tb
        def energy(x):
            T = T_of(x); Vm = V @ T[:3, :3].T + T[:3, 3]
            return float(np.mean([score(v, Vm, F) for v in views]))
        x0 = x_of(T0)
        e0 = energy(x0)
        res = minimize(energy, x0, method="Powell",
                       options={"xtol": 1e-3, "ftol": 1e-5, "maxiter": 3000,
                                "direc": np.diag([0.005, 0.005, 0.005, 0.5, 0.5, 0.5])})
        T = T_of(res.x)
        d = np.linalg.inv(T0) @ T
        Vm = V @ T[:3, :3].T + T[:3, 3]
        per = [round(float(score(v, Vm, F)), 3) for v in views]
        print(f"{name}: energy {e0:.3f} -> {res.fun:.3f} ({res.nfev} evals), moved {np.linalg.norm(d[:3, 3]):.2f} mm "
              f"{np.degrees(np.linalg.norm(Rotation.from_matrix(d[:3, :3]).as_rotvec())):.2f} deg; per view {per}")
        reg[name + "_model"] = {"x": res.x.tolist(), "T": T.tolist(), "energy": float(res.fun), "per_view": per}
        REG.write_text(json.dumps(reg, indent=1))
