"""Fit SCAD parameters to the silhouettes of the 'up' views (coordinate descent, step halving).

Energy per view at 1/4 res: chamfer distance (px) of rendered model pixels lying on certain paper,
plus that of certain-battery pixels (V < 90: black plastic, never the paper's shadows, which read
107+) the rendering misses, both per certain-battery pixel. The model can also shift/turn in the
frame (frame_dx, frame_dy, frame_yaw) so a frame error doesn't bias symmetric parameters.

Usage: fitparams.py <group> [rounds]   (groups below)  -> prints the fitted values
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
import trimesh

from ac import OUT, PROJECT, Capture, bat_to_obj
from stereo import roi_mask

SCAD = PROJECT / "skil_pwrcore20_2ah.scad"
S = 4
VIEWS = (PROJECT / "views_upright.txt").read_text().split()

GROUPS = {
    # (name, index or None, step)
    "body": [("frame_dx", None, 0.3), ("frame_dy", None, 0.3), ("frame_yaw", None, 0.2),
             *[("body_hw", i, 0.3) for i in range(1, 5)],
             *[("body_back", i, 0.3) for i in range(1, 5)],
             *[("body_front", i, 0.3) for i in range(2, 5)],
             ("body_bch", 3, 0.5), ("body_bch", 4, 0.5), ("body_fch", 3, 0.5), ("body_fch", 4, 0.5),
             ("deck_half_w", None, 0.3), ("deck_front", None, 0.3)],
    "top": [("cap_half_w", None, 0.2), ("cap_z", 1, 0.2), ("collar_z", None, 0.3), ("collar_half", None, 0.3),
            ("pillar_back", 1, 0.4), ("pillar_back", 0, 0.4), ("button_z", 0, 0.4), ("button_z", 1, 0.4),
            ("latch_top", 1, 0.3), ("finger_y", None, 0.3), ("lug_front_y", None, 0.3), ("lug_top", None, 0.3)],
}


class View:
    def __init__(self, r):
        c = Capture(r); self.c = c
        H, W = c.image.shape[:2]; h, w = H // S, W // S
        v = cv2.cvtColor(cv2.resize(c.image, (w, h), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2HSV)[..., 2]
        notp = cv2.imread(str(OUT / "mask" / f"{r}.png"), 0) > 0
        paper = ~notp[:h * S, :w * S].reshape(h, S, w, S).any((1, 3))
        roi = cv2.resize(roi_mask(c, np.eye(4), (H, W)), (w, h)) > 0
        field = np.zeros((h, w), np.uint8)
        poly = c.project(np.array([[-87, -118, 0], [87, -118, 0], [87, 118, 0], [-87, 118, 0.0]])) / S
        cv2.fillPoly(field, [np.round(poly).astype(np.int32)], 1)
        dark = (v < 90) & ~paper & roi & (field > 0)
        self.dark = cv2.morphologyEx(dark.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)) > 0
        self.n = max(1, int(self.dark.sum()))
        self.paper_dt = cv2.distanceTransform(paper.astype(np.uint8), cv2.DIST_L2, 3)
        self.shape = (h, w)

    def score(self, V, F):
        uv = self.c.project(V) / S
        im = np.zeros(self.shape, np.uint8)
        pts = np.round(uv * 16).astype(np.int32)
        for f in F:
            cv2.fillConvexPoly(im, pts[f], 1, shift=4)
        r = im > 0
        over = self.paper_dt[r].sum() / self.n
        m = self.dark & ~r
        miss = cv2.distanceTransform((~r).astype(np.uint8), cv2.DIST_L2, 3)[m].sum() / self.n if m.any() else 0.0
        return over + miss


def scad_value(name):
    """Current value of a top-level assignment in the SCAD file (number or vector)."""
    for line in SCAD.read_text().splitlines():
        if line.startswith(name + " ") or line.startswith(name + "="):
            rhs = line.split("=", 1)[1].split(";")[0].strip()
            return json.loads(rhs)
    raise KeyError(name)


def render(params):
    defs = []
    for k, v in params.items():
        if k.startswith("frame_"):
            continue
        defs += ["-D", f"{k}={json.dumps(v)}"]
    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as t:
        path = t.name
    subprocess.run(["openscad", "-q", "-o", path, "--export-format", "binstl", *defs, str(SCAD)], check=True,
                   capture_output=True)
    m = trimesh.load(path, force="mesh"); Path(path).unlink()
    V = m.vertices.copy()
    a = np.radians(params.get("frame_yaw", 0.0))
    R = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    V = V @ R.T + [params.get("frame_dx", 0.0), params.get("frame_dy", 0.0), 0]
    return bat_to_obj(V), m.faces


def main():
    group = sys.argv[1]; rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    spec = GROUPS[group]
    views = [View(r) for r in VIEWS]
    params = {}
    for name, idx, _ in spec:
        if name.startswith("frame_"):
            params[name] = 0.0
        elif name not in params:
            params[name] = scad_value(name)

    def get(p, name, idx):
        return p[name] if idx is None else p[name][idx]

    def with_(p, name, idx, val):
        q = json.loads(json.dumps(p))
        if idx is None:
            if isinstance(q[name], list):                       # shift a whole vector (e.g. profile points)
                q[name] = (np.array(q[name]) + (val - get(p, name, None) if not isinstance(val, list) else 0)).tolist()
            else:
                q[name] = val
        else:
            q[name][idx] = val
        return q

    def energy(p):
        V, F = render(p)
        return float(np.mean([v.score(V, F) for v in views]))

    e = energy(params)
    print(f"start energy {e:.4f}", flush=True)
    for rnd in range(rounds):
        for name, idx, step in spec:
            st = step / (2 ** rnd)
            for _ in range(6):
                cur = get(params, name, idx)
                if isinstance(cur, list):        # vector shift: move every element (profile points' Y, Z both)
                    tries = [(np.array(cur) + d).tolist() for d in (st, -st)]
                    cands = [json.loads(json.dumps(params)) for _ in tries]
                    for c, t in zip(cands, tries): c[name] = t
                else:
                    cands = [with_(params, name, idx, cur + d) for d in (st, -st)]
                es = [energy(c) for c in cands]
                k = int(np.argmin(es))
                if es[k] < e - 1e-5:
                    params, e = cands[k], es[k]
                else:
                    break
            print(f"  r{rnd} {name}{'' if idx is None else f'[{idx}]'} = {json.dumps(get(params, name, idx))}  E {e:.4f}", flush=True)
    print("fitted:", json.dumps(params))
    (OUT / f"fit_{group}.json").write_text(json.dumps(params, indent=1))


if __name__ == "__main__":
    main()
