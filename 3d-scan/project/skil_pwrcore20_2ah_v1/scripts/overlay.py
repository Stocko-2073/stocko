"""Overlay the OpenSCAD model on captures: visible feature edges (red) and silhouette (yellow).

The model is in the battery frame; 'up' views map it with bat_to_obj, other placements also
through out/registration.json. Visibility by a painter's-algorithm face-id buffer.

Usage: overlay.py [--placement up] [--scale 0.5] [--out name] <req> [...]
"""
import argparse
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
import trimesh

from ac import OUT, PROJECT, Capture, bat_to_obj

SCAD = PROJECT / "skil_pwrcore20_2ah.scad"
STL = OUT / "model.stl"


def model_mesh() -> trimesh.Trimesh:
    if not STL.exists() or STL.stat().st_mtime < SCAD.stat().st_mtime:
        subprocess.run(["openscad", "-q", "-o", str(STL), "--export-format", "binstl", str(SCAD)], check=True)
    return trimesh.load(STL, force="mesh")


def feature_edges(mesh: trimesh.Trimesh, deg: float = 25.0):
    ang = mesh.face_adjacency_angles
    sharp = ang > np.radians(deg)
    edges = mesh.face_adjacency_edges[sharp]
    faces = mesh.face_adjacency[sharp]
    return edges, faces


def render(cap: Capture, V_mat: np.ndarray, mesh, scale: float, edges, efaces, img: np.ndarray):
    T = cap.cam_from_mat
    Vc = V_mat @ T[:3, :3].T + T[:3, 3]
    K = cap.K.copy(); K[:2] *= scale
    uv = (Vc @ K.T); uv = uv[:, :2] / uv[:, 2:3]
    H, W = img.shape[:2]
    F = mesh.faces
    depth = Vc[F][:, :, 2].mean(1)
    order = np.argsort(-depth)                       # far to near
    fid = np.full((H, W), -1, np.int32)
    pts = np.round(uv[F] * 16).astype(np.int32)       # 4 bits of subpixel
    for i in order:
        cv2.fillConvexPoly(fid, pts[i], int(i), lineType=cv2.LINE_8, shift=4)
    # face planes in camera coords for depth tests
    n = np.cross(Vc[F[:, 1]] - Vc[F[:, 0]], Vc[F[:, 2]] - Vc[F[:, 0]])
    d = (n * Vc[F[:, 0]]).sum(1)
    Kinv = np.linalg.inv(K)
    out = img.copy()
    # silhouette
    sil = (fid >= 0).astype(np.uint8)
    cnts, _ = cv2.findContours(sil, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(out, cnts, -1, (0, 255, 255), 1)
    # feature edges, sampled
    for (a, b), (f1, f2) in zip(edges, efaces):
        L = np.linalg.norm(uv[a] - uv[b])
        k = max(2, int(L / 1.5))
        t = np.linspace(0, 1, k)[:, None]
        P = Vc[a] * (1 - t) + Vc[b] * t
        q = uv[a] * (1 - t) + uv[b] * t
        qi = np.round(q).astype(int)
        ok = (qi[:, 0] >= 0) & (qi[:, 0] < W) & (qi[:, 1] >= 0) & (qi[:, 1] < H)
        vis = np.zeros(k, bool)
        for j in np.where(ok)[0]:
            f = fid[qi[j, 1], qi[j, 0]]
            if f < 0 or f == f1 or f == f2:
                vis[j] = True
                continue
            ray = Kinv @ np.r_[q[j], 1.0]
            den = n[f] @ ray
            if abs(den) < 1e-12:
                vis[j] = True; continue
            zf = d[f] / den * ray[2]
            vis[j] = P[j, 2] <= zf + 0.3
        for j in range(k - 1):
            if vis[j] and vis[j + 1]:
                cv2.line(out, tuple(np.round(q[j] * 4).astype(int)), tuple(np.round(q[j + 1] * 4).astype(int)),
                         (0, 0, 255), 1, cv2.LINE_AA, shift=2)
    return out, sil


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("reqs", nargs="+")
    ap.add_argument("--placement", default="up")
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--out", default="overlay")
    ap.add_argument("--crop", type=float, default=1.15, help="crop around the model, relative size")
    ap.add_argument("--tile", type=int, default=900)
    ap.add_argument("--box", type=float, nargs=6, default=None, help="battery-frame x0 x1 y0 y1 z0 z1 to crop to")
    a = ap.parse_args()
    mesh = model_mesh()
    edges, efaces = feature_edges(mesh)
    reg = json.loads((OUT / "registration.json").read_text())
    if a.placement == "up":
        V_mat = bat_to_obj(mesh.vertices)
    elif a.placement + "_model" in reg:            # model registered directly (battery frame -> mat)
        T = np.array(reg[a.placement + "_model"]["T"])
        V_mat = mesh.vertices @ T[:3, :3].T + T[:3, 3]
    else:                                          # hull registration (object frame -> mat)
        T = np.array(reg[a.placement]["T"])
        V_mat = bat_to_obj(mesh.vertices) @ T[:3, :3].T + T[:3, 3]
    tiles = []
    for r in a.reqs:
        cap = Capture(r)
        img = cv2.resize(cap.image, None, fx=a.scale, fy=a.scale, interpolation=cv2.INTER_AREA)
        out, sil = render(cap, V_mat, mesh, a.scale, edges, efaces, img)
        if a.box:
            import itertools
            bx = np.array(list(itertools.product(a.box[0:2], a.box[2:4], a.box[4:6])))
            if a.placement == "up":
                pb = bat_to_obj(bx)
            elif a.placement + "_model" in reg:
                pb = bx @ T[:3, :3].T + T[:3, 3]
            else:
                pb = bat_to_obj(bx) @ T[:3, :3].T + T[:3, 3]
            q = cap.project(pb) * a.scale
            (x0, y0), (x1, y1) = q.min(0).astype(int), q.max(0).astype(int)
            crop = out[max(0, y0):y1, max(0, x0):x1]
        else:
            x, y, w, h = cv2.boundingRect(sil)
            cx, cy, s = x + w / 2, y + h / 2, max(w, h) * a.crop / 2
            crop = out[max(0, int(cy - s)):int(cy + s), max(0, int(cx - s)):int(cx + s)]
        f = a.tile / max(crop.shape[:2])
        crop = cv2.resize(crop, None, fx=f, fy=f, interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC)
        t = np.full((a.tile, a.tile, 3), 255, np.uint8); t[:crop.shape[0], :crop.shape[1]] = crop
        cv2.putText(t, r, (6, 28), 0, 0.9, (255, 0, 0), 2)
        tiles.append(t)
    cols = min(3, len(tiles))
    while len(tiles) % cols:
        tiles.append(np.full_like(tiles[0], 255))
    sheet = np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)])
    path = OUT / f"{a.out}.jpg"
    cv2.imwrite(str(path), sheet)
    print(path, f"{len(mesh.faces)} faces, {len(edges)} feature edges")


if __name__ == "__main__":
    main()
