"""Measure where a straight edge of the battery really is in a photo.

An edge is a 3D segment in the battery frame plus the direction it would move if the dimension
grew ('push', a unit 3D vector). The segment is projected into the view (through the placement's
registration), the image is sampled along the projected push direction at points along it, and the
strongest brightness step (sub-pixel, sign-agnostic) within +-W px is taken. The median offset is
converted to mm along 'push' by projecting a 1 mm push. Positive = the real edge lies further along
'push' than the model's.

Import measure(); or run for a quick test.
"""
import json

import cv2
import numpy as np

from ac import OUT, Capture, bat_to_obj


def placement_T(placement):
    if placement == "up":
        return None
    reg = json.loads((OUT / "registration.json").read_text())
    return np.array(reg[placement + "_model"]["T"])


def to_mat(P, T):
    P = np.asarray(P, float).reshape(-1, 3)
    return bat_to_obj(P) if T is None else P @ T[:3, :3].T + T[:3, 3]


_gray = {}


def gray(cap):
    if cap.req not in _gray:
        g = cv2.cvtColor(cap.image, cv2.COLOR_BGR2GRAY).astype(np.float32)
        _gray[cap.req] = cv2.GaussianBlur(g, (0, 0), 1.2)
    return _gray[cap.req]


def measure(req, placement, a, b, push, W=25, n=30, trim=0.15, debug=False, sil=False, frac=0.5):
    """sil=True: a silhouette edge against paper; take the outermost 50% crossing between the
    battery level (inner) and the paper level (outer end of the profile) instead of the strongest step."""
    cap = Capture(req); T = placement_T(placement); g = gray(cap)
    a, b, push = map(lambda v: np.asarray(v, float), (a, b, push))
    ts = np.linspace(trim, 1 - trim, n)
    P = a[None] * (1 - ts[:, None]) + b[None] * ts[:, None]
    uv = cap.project(to_mat(P, T))
    uv2 = cap.project(to_mat(P + push[None], T))
    dpx = uv2 - uv                                  # px per mm of push at each sample
    L = np.linalg.norm(dpx, axis=1); nrm = dpx / L[:, None]
    offs = np.arange(-W, W + 0.01, 0.25)
    res = []
    for p, nv, l in zip(uv, nrm, L):
        q = p[None] + offs[:, None] * nv[None]
        prof = cv2.remap(g, q[:, 0].astype(np.float32)[None], q[:, 1].astype(np.float32)[None], cv2.INTER_LINEAR)[0]
        if sil:
            paper = np.median(prof[-12:]); inner = np.percentile(prof[:len(prof) // 2], 20)
            if paper - inner < 25:
                continue
            thr = inner + frac * (paper - inner)       # frac near 1: the paper's own edge
            below = np.where(prof < thr)[0]
            if len(below) == 0 or below[-1] >= len(prof) - 1:
                continue
            k = below[-1]                              # last dark sample before the paper
            f = (thr - prof[k]) / (prof[k + 1] - prof[k] + 1e-9)
            res.append(((offs[k] + f * 0.25) / l, paper - inner))
            continue
        grad = np.gradient(prof)
        k = int(np.argmax(np.abs(grad)))
        if 2 <= k < len(grad) - 2:
            y0, y1, y2 = np.abs(grad[k - 1:k + 2]); den = y0 - 2 * y1 + y2
            sub = 0.5 * (y0 - y2) / den if abs(den) > 1e-6 else 0
            res.append(((offs[k] + sub * 0.25) / l, abs(grad[k])))
    if not res:
        return None
    r = np.array(res)
    good = r[:, 1] > 0.3 * np.median(r[:, 1])
    mm = r[good, 0]
    med = float(np.median(mm)); mad = float(np.median(np.abs(mm - med)))
    if debug:
        print(f"{req}: samples {good.sum()}/{len(r)} offset {med:+.2f} mm (MAD {mad:.2f}), px/mm {np.median(L):.1f}")
    return med, mad, int(good.sum()), float(np.median(L))
