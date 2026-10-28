"""Register the model into a placement with one model face pinned to a plane measured by stereo.

The face (model point p_m, outward normal n_m) lies on the mat-frame plane z = a x + b y + c,
facing up. That leaves an in-plane turn and shift, fitted to the silhouettes (modelreg.score).

Usage: planereg.py <placement> <px> <py> <pz> <nx> <ny> <nz> <a> <b> <c>   -> "<p>_model"
"""
import json
import sys

import numpy as np
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation

from ac import OUT, PROJECT
from modelreg import REG, score
from overlay import model_mesh
from register import View

name = sys.argv[1]
p_m = np.array(sys.argv[2:5], float); n_m = np.array(sys.argv[5:8], float); n_m /= np.linalg.norm(n_m)
a, b, c = map(float, sys.argv[8:11])
n_w = np.array([-a, -b, 1.0]); n_w /= np.linalg.norm(n_w)
placements = json.loads((PROJECT / "placements.json").read_text())
reg = json.loads(REG.read_text())
mesh = model_mesh(); V, F = mesh.vertices, mesh.faces
views = [View(r) for r in placements[name]["views"].split()]

R0, _ = Rotation.align_vectors([n_w], [n_m])          # model normal -> plane normal
e1 = np.cross(n_w, [0, 1, 0]); e1 /= np.linalg.norm(e1); e2 = np.cross(n_w, e1)


def T_of(q):
    th, u, v = q
    Rm = Rotation.from_rotvec(n_w * th) * R0
    x, y = u, v
    pw = np.array([x, y, a * x + b * y + c])
    T = np.eye(4); T[:3, :3] = Rm.as_matrix(); T[:3, 3] = pw - Rm.apply(p_m)
    return T


def energy(q):
    T = T_of(q); Vm = V @ T[:3, :3].T + T[:3, 3]
    return float(np.mean([score(v, Vm, F) for v in views]))


# start: in-plane turn from the previous registration, if any; else a coarse sweep
if name + "_model" in reg:
    Tp = np.array(reg[name + "_model"]["T"])
    pw0 = Tp[:3, :3] @ p_m + Tp[:3, 3]
    best = None
    span = float(__import__("os").environ.get("THETA_SPAN", "360"))
    th_c = float(__import__("os").environ.get("THETA_CENTER", "0"))
    for th in np.radians(th_c + np.arange(-span / 2, span / 2, 2 if span < 360 else 10)):
        q = np.array([th, pw0[0], pw0[1]]); e = energy(q)
        if best is None or e < best[0]: best = (e, q)
    q0 = best[1]
else:
    q0 = np.array([0.0, 0.0, 0.0])
res = minimize(energy, q0, method="Powell", options={"xtol": 1e-4, "ftol": 1e-6, "direc": np.diag([0.01, 0.5, 0.5])})
T = T_of(res.x); Vm = V @ T[:3, :3].T + T[:3, 3]
per = [round(float(score(v, Vm, F)), 3) for v in views]
print(f"{name}: energy {res.fun:.3f}, theta {np.degrees(res.x[0]):.2f} deg, per view {per}")
reg[name + "_model"] = {"T": T.tolist(), "energy": float(res.fun), "per_view": per,
                        "plane": [a, b, c], "face": {"p": p_m.tolist(), "n": n_m.tolist()}}
REG.write_text(json.dumps(reg, indent=1))
