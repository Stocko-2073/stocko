"""Sparse multi-view stereo with known poses: SIFT matches between the views of one placement,
kept if they satisfy the epipolar geometry, chained into tracks and triangulated from every
view in the track. Points are in that placement's mat frame.

Usage: stereo.py <placement> [...]   -> out/cloud_<placement>.npz (xyz, rgb, nviews, rms_px, desc)
"""
import itertools
import json
import sys

import cv2
import numpy as np

from ac import OUT, PROJECT, Capture

EPI_PX, REPROJ_PX, MIN_VIEWS = 6.0, 5.0, 3      # pose consistency is ~2-3 px at the battery
BOX = np.array([[-46, -72, -1], [46, 72, 78.0]])     # battery frame (object) box for the ROI
c0 = np.array([-3.476, -3.722]); f = np.array([-0.5789, -0.8154]); Xb = np.array([f[1], -f[0]])


def obj_from_battery(p):
    return np.c_[c0 + np.outer(p[:, 0], Xb) + np.outer(p[:, 1], f), p[:, 2]]


def roi_mask(cap, T, shape):
    corners = np.array(list(itertools.product(*BOX.T)))
    pm = obj_from_battery(corners) @ T[:3, :3].T + T[:3, 3]
    uv = cap.project(pm)
    m = np.zeros(shape, np.uint8)
    cv2.fillConvexPoly(m, cv2.convexHull(np.round(uv).astype(np.int32)), 255)
    return m


def P_of(cap):
    T = cap.cam_from_mat
    return cap.K @ T[:3]


def fundamental(ci, cj):
    Ti, Tj = ci.cam_from_mat, cj.cam_from_mat
    T = Tj @ np.linalg.inv(Ti)
    R, t = T[:3, :3], T[:3, 3]
    tx = np.array([[0, -t[2], t[1]], [t[2], 0, -t[0]], [-t[1], t[0], 0]])
    return np.linalg.inv(cj.K).T @ tx @ R @ np.linalg.inv(ci.K)


def view_dir(cap):
    return cap.cam_from_mat[2, :3]      # camera z axis in the mat frame


def triangulate_track(obs, Ps):
    A = []
    for v, (u, w) in obs:
        P = Ps[v]
        A.append(u * P[2] - P[0]); A.append(w * P[2] - P[1])
    _, _, Vt = np.linalg.svd(np.array(A))
    X = Vt[-1]; return X[:3] / X[3]


def run(name, placements, reg):
    reqs = placements[name]["views"].split()
    T = np.eye(4) if name == "up" else np.array(reg[name]["T"])
    caps = [Capture(r) for r in reqs]
    sift = cv2.SIFT_create(nfeatures=40000, contrastThreshold=0.02)
    feats = []
    for c in caps:
        g = cv2.cvtColor(c.image, cv2.COLOR_BGR2GRAY)
        notp = cv2.imread(str(OUT / "mask" / f"{c.req}.png"), 0)
        m = cv2.bitwise_and(roi_mask(c, T, g.shape), notp)
        kp, d = sift.detectAndCompute(g, m)
        d = np.sqrt(d / (d.sum(1, keepdims=True) + 1e-7))     # RootSIFT
        feats.append((np.array([k.pt for k in kp]), d.astype(np.float32)))
        print(f"  {c.req}: {len(kp)} features", flush=True)
    Ps = [P_of(c) for c in caps]
    flann = cv2.FlannBasedMatcher({"algorithm": 1, "trees": 4}, {"checks": 64})
    parent = {}

    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]; a = parent[a]
        return a

    npairs = 0
    for i, j in itertools.combinations(range(len(caps)), 2):
        ang = np.degrees(np.arccos(np.clip(view_dir(caps[i]) @ view_dir(caps[j]), -1, 1)))
        if not 6 <= ang <= 60:
            continue
        (pi, di), (pj, dj) = feats[i], feats[j]
        mt = flann.knnMatch(di, dj, k=2)
        good = [(a.queryIdx, a.trainIdx) for a, b in mt if a.distance < 0.8 * b.distance]
        if len(good) < 20:
            continue
        g = np.array(good)
        F = fundamental(caps[i], caps[j])
        xi = np.c_[pi[g[:, 0]], np.ones(len(g))]; xj = np.c_[pj[g[:, 1]], np.ones(len(g))]
        l = xi @ F.T
        d = np.abs((l * xj).sum(1)) / np.hypot(l[:, 0], l[:, 1])
        g = g[d < EPI_PX]
        for a, b in g:
            ra, rb = find((i, int(a))), find((j, int(b)))
            if ra != rb:
                parent[ra] = rb
        npairs += 1
        print(f"  pair {reqs[i]}-{reqs[j]} ang {ang:4.1f}: {len(good)} matches, {len(g)} epipolar", flush=True)
    tracks = {}
    for key in list(parent):
        tracks.setdefault(find(key), []).append(key)
    xyz, rgb, nv, rms, desc = [], [], [], [], []
    for members in tracks.values():
        views = {}
        for v, k in members:
            views.setdefault(v, []).append(k)
        if len(views) < MIN_VIEWS or any(len(ks) > 1 for ks in views.values()):
            continue                                          # too short, or ambiguous
        obs = [(v, feats[v][0][ks[0]]) for v, ks in views.items()]
        X = triangulate_track(obs, Ps)
        errs = []
        for v, uv in obs:
            p = caps[v].project(X[None])[0]
            errs.append(np.hypot(*(p - uv)))
        if max(errs) > REPROJ_PX:
            continue
        v0, uv0 = obs[0]
        u, w = np.round(uv0).astype(int)
        xyz.append(X); rgb.append(caps[v0].image[w, u][::-1]); nv.append(len(obs)); rms.append(np.sqrt(np.mean(np.square(errs))))
        dsc = np.mean([feats[v][1][ks[0]] for v, ks in views.items()], 0)
        desc.append(dsc / np.linalg.norm(dsc))
    xyz = np.array(xyz)
    np.savez_compressed(OUT / f"cloud_{name}.npz", xyz=xyz, rgb=np.array(rgb), nviews=np.array(nv), rms_px=np.array(rms),
                        desc=np.array(desc, np.float32))
    print(f"{name}: {npairs} pairs, {len(tracks)} tracks, {len(xyz)} points (>= {MIN_VIEWS} views, <= {REPROJ_PX} px)")


if __name__ == "__main__":
    placements = json.loads((PROJECT / "placements.json").read_text())
    reg = json.loads((OUT / "registration.json").read_text())
    for name in sys.argv[1:]:
        run(name, placements, reg)
