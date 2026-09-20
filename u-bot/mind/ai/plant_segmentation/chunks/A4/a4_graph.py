"""A4 — the connectivity graph. This is the chunk.

    fragments  ->  boundary-wise depth-continuity test  ->  connected components

Nodes are mask fragments. An edge asserts that two fragments are *the same
physical surface*: adjacent in image space (8-connected, A1's registered
adjacency) **and** continuous in depth, within A1's measured local-planarity
floor at the scale the link spans.

What is deliberately absent
---------------------------
There is no `eps`, no radius, no "plants are about this far apart", no maximum
gap, no minimum plant size, no distance of any kind between two fragments that
do not touch. Two fragments are linked or not linked by whether the material is
*contiguous*, which is a question about the instrument's ability to resolve a
step in a surface, not a question about how a garden is arranged. Fragments that
do not touch are never linked, at any separation — the only thing that can be
said about them is recorded as an **unresolved edge**.

The continuity test
-------------------
For a pixel `p` and its 8-neighbour `q`:

1. Work on **relief** = A2's `soil_surface_depth` minus A1's depth, both in rdu.
   Subtracting the datum first is A2's instruction: a bed that slopes is a bed
   whose fragments must not be split by the slope.
2. Fit a least-squares plane to the relief over the 5x5 window around `p`,
   using **only pixels of p's own fragment**. Extrapolate it one pixel to `q`.
   The residual `|relief(q) - plane_p(q)|` is the evidence that `q` is not on
   `p`'s surface.
3. Do it the other way too, and take the **smaller** of the two: if either
   surface continues into the other, the material is contiguous. (A leaf and its
   petiole meet at a curvature the leaf's own plane cannot follow; the petiole's
   can.)
4. Aggregate over the whole shared boundary of the two fragments and judge the
   boundary by its **quartiles**, not by any single pixel:

       p75(residual) <= tol   -> connected
       p25(residual) >  tol   -> separated
       otherwise              -> UNRESOLVED, recorded, not decided

   That last case is a boundary that is continuous along part of its length and
   a step along the rest — which is what a leaf lying across another leaf looks
   like. Under R2 and R4 it is reported, not guessed.

`tol` is `local_planarity_p10` at win9 = 1.29e-4 rdu, A1's (a) instrument
constant, read at the window the 5x5-fit-plus-one-step stencil spans. It is
swept over 0.25x..100x in `sweeps.py`; the answer is stable over two decades,
against the 1.3x window the ZeroPlantSeg `eps` survived.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

import a4_common as C

# The four unordered directions of an 8-neighbourhood.
DIRECTIONS = [(0, 1), (1, 0), (1, 1), (1, -1)]


def _shift(a: np.ndarray, dy: int, dx: int, fill):
    """a[y+dy, x+dx], padded with `fill`."""
    out = np.full_like(a, fill)
    ys_dst = slice(max(0, -dy), a.shape[0] - max(0, dy))
    ys_src = slice(max(0, dy), a.shape[0] - max(0, -dy))
    xs_dst = slice(max(0, -dx), a.shape[1] - max(0, dx))
    xs_src = slice(max(0, dx), a.shape[1] - max(0, -dx))
    out[ys_dst, xs_dst] = a[ys_src, xs_src]
    return out


# ---------------------------------------------------------------- fragments --
def build_fragments(inp: C.Inputs, min_px: int = C.MIN_FRAGMENT_PX,
                    use_class: bool = False):
    """Mask fragments: 8-connected pieces uniform in SAM region *and* material.

    Two hypotheses are being crossed here, and neither is trusted:

    * SAM says where the boundaries in the picture are.
    * A3 says what material each piece is.

    A fragment is a piece both agree on. Every boundary between two fragments —
    including every boundary A3 drew between grass and squash — is then handed
    to the depth to adjudicate. Nothing about the *class* of a fragment is used
    to decide whether an edge exists; the class only decides where a candidate
    boundary is placed.

    Fragments smaller than the plane fit's own 5x5 support carry no surface, so
    they are merged into the neighbour they share the longest boundary with —
    A0's and A3's registered `min region` rule, reused unchanged.

    Returns (frag, info) with `frag` 0 outside plant material.
    """
    H, W = inp.material.shape
    key = inp.regions.astype(np.int64) * 16
    if use_class:
        key = key + inp.material.astype(np.int64)
    struct = ndimage.generate_binary_structure(2, 2)  # 8-connected

    lab = np.zeros((H, W), np.int32)
    nxt = 1
    for k in np.unique(key):
        m = key == k
        cc, n = ndimage.label(m, structure=struct)
        lab[m] = cc[m] + (nxt - 1)
        nxt += n

    plant_lab = np.where(inp.plant, lab, 0).astype(np.int32)
    plant_lab, remap = _compact(plant_lab)
    n_before = int(plant_lab.max())

    merged_px = 0
    n_merged = 0
    for _ in range(8):  # a few passes; each pass only grows fragments
        sizes = np.bincount(plant_lab.ravel())
        small = np.nonzero(sizes[1:] < min_px)[0] + 1
        if small.size == 0:
            break
        target = _longest_boundary_neighbour(plant_lab, small)
        changed = False
        for s in small:
            t = target.get(int(s))
            if t:
                merged_px += int(sizes[s])
                n_merged += 1
                plant_lab[plant_lab == s] = t
                changed = True
        if not changed:
            break
    plant_lab, _ = _compact(plant_lab)

    sizes = np.bincount(plant_lab.ravel())
    info = {
        "n_fragments": int(plant_lab.max()),
        "n_fragments_before_min_merge": n_before,
        "n_merged_below_min": n_merged,
        "px_merged_below_min": merged_px,
        "min_fragment_px": min_px,
        "plant_px": int(inp.plant.sum()),
        "fragment_px_p50": float(np.median(sizes[1:])) if plant_lab.max() else 0.0,
        "fragment_px_p95": float(np.percentile(sizes[1:], 95)) if plant_lab.max() else 0.0,
        "n_still_below_min": int((sizes[1:] < min_px).sum()),
        "note": "fragments still below the minimum have no plant neighbour to "
                "merge into; they are kept, and their edges are decided by the "
                "other side's surface fit alone.",
    }
    return plant_lab, info


def _compact(lab):
    ids = np.unique(lab)
    remap = np.zeros(int(ids.max()) + 1, np.int32)
    remap[ids] = np.arange(len(ids), dtype=np.int32)
    if ids[0] != 0:                       # keep 0 as background
        remap[ids] = np.arange(1, len(ids) + 1, dtype=np.int32)
    return remap[lab], remap


def _longest_boundary_neighbour(lab, subset):
    """For each label in `subset`, the neighbouring label sharing the most
    boundary pixels. Purely geometric; no class, no depth, no distance."""
    want = set(int(s) for s in subset)
    counts = {}
    for dy, dx in DIRECTIONS:
        a = lab
        b = _shift(lab, dy, dx, 0)
        m = (a > 0) & (b > 0) & (a != b)
        for u, v in ((a[m], b[m]), (b[m], a[m])):
            sel = np.isin(u, list(want)) if want else np.zeros(u.shape, bool)
            if not sel.any():
                continue
            uu, vv = u[sel].astype(np.int64), v[sel].astype(np.int64)
            k, c = np.unique(uu * (lab.max() + 1) + vv, return_counts=True)
            for kk, cc in zip(k, c):
                s, t = int(kk // (lab.max() + 1)), int(kk % (lab.max() + 1))
                counts[(s, t)] = counts.get((s, t), 0) + int(cc)
    best = {}
    for (s, t), c in counts.items():
        if s not in best or c > best[s][1]:
            best[s] = (t, c)
    # never merge a small fragment into another fragment that is itself small
    sizes = np.bincount(lab.ravel())
    return {s: t for s, (t, _) in best.items() if s not in want or t not in want
            or sizes[t] >= sizes[s]}


# ------------------------------------------------------------ surface fits ---
def plane_fits(relief: np.ndarray, frag: np.ndarray, valid: np.ndarray,
               win: int = C.FIT_WINDOW):
    """Per-pixel least-squares plane of `relief`, fitted **within the pixel's own
    fragment** over a `win` x `win` window.

    Returns (a, b, c, ok): relief ~ a + b*dx + c*dy about the pixel, and a
    boolean saying the fit is determined. A fragment with fewer than 3
    non-collinear pixels in the window gets ok=False and contributes no
    one-sided residual — it is never given a fabricated surface.
    """
    r = np.where(valid, relief, 0.0).astype(np.float64)
    k = win // 2
    S0 = np.zeros(relief.shape); Sx = np.zeros_like(S0); Sy = np.zeros_like(S0)
    Sxx = np.zeros_like(S0); Sxy = np.zeros_like(S0); Syy = np.zeros_like(S0)
    Sr = np.zeros_like(S0); Srx = np.zeros_like(S0); Sry = np.zeros_like(S0)
    for dy in range(-k, k + 1):
        for dx in range(-k, k + 1):
            same = (_shift(frag, dy, dx, 0) == frag) & (frag > 0) \
                & _shift(valid, dy, dx, False) & valid
            w = same.astype(np.float64)
            rv = _shift(r, dy, dx, 0.0) * w
            S0 += w; Sx += w * dx; Sy += w * dy
            Sxx += w * dx * dx; Sxy += w * dx * dy; Syy += w * dy * dy
            Sr += rv; Srx += rv * dx; Sry += rv * dy
    A = np.empty(relief.shape + (3, 3))
    A[..., 0, 0] = S0; A[..., 0, 1] = Sx;  A[..., 0, 2] = Sy
    A[..., 1, 0] = Sx; A[..., 1, 1] = Sxx; A[..., 1, 2] = Sxy
    A[..., 2, 0] = Sy; A[..., 2, 1] = Sxy; A[..., 2, 2] = Syy
    B = np.stack([Sr, Srx, Sry], -1)
    det = np.linalg.det(A)
    ok = (S0 >= 3) & (np.abs(det) > 1e-12) & (frag > 0)
    A = np.where(ok[..., None, None], A, np.eye(3))
    B = np.where(ok[..., None], B, 0.0)
    sol = np.linalg.solve(A, B[..., None])[..., 0]
    return (sol[..., 0].astype(np.float32), sol[..., 1].astype(np.float32),
            sol[..., 2].astype(np.float32), ok)


# --------------------------------------------------------------- boundaries --
def _secdiff_residual(r, frag, valid, dy, dx):
    """Directional second difference: extrapolate the line through `p` and its
    in-fragment predecessor `p-d` to `q`, and vice versa. Slope-free by
    construction (a tilted flat surface gives exactly zero), needs no matrix
    inverse, and is the same quantity A1's depth-resolution floor was estimated
    with. Returns (e, defined)."""
    rq = _shift(r, dy, dx, np.nan)
    back = _shift(r, -dy, -dx, np.nan)
    back_ok = (_shift(frag, -dy, -dx, 0) == frag) & _shift(valid, -dy, -dx, False)
    fwd = _shift(r, 2 * dy, 2 * dx, np.nan)
    fwd_ok = (_shift(frag, 2 * dy, 2 * dx, 0) == _shift(frag, dy, dx, 0)) \
        & _shift(valid, 2 * dy, 2 * dx, False)
    e_p = np.where(back_ok, np.abs(rq - (2 * r - back)), np.inf)
    e_q = np.where(fwd_ok, np.abs(r - (2 * rq - fwd)), np.inf)
    e = np.minimum(e_p, e_q)
    return e, np.isfinite(e)


def boundary_residuals(inp: C.Inputs, frag: np.ndarray, fits=None,
                       intra: bool = False, statistic: str = "plane5"):
    """Per-boundary-pixel continuity residual, for every adjacent fragment pair.

    `intra=True` instead returns residuals for pairs **inside** one fragment —
    the control distribution, i.e. what a boundary looks like when the material
    really is continuous.

    Returns dict with `pair` (M,2 int64, sorted ids), `resid` (M,) float32.
    """
    r = inp.relief.astype(np.float64)
    if statistic == "plane5":
        a, b, c, ok = fits if fits is not None else plane_fits(
            inp.relief, frag, inp.plant)
    pair_a, pair_b, res = [], [], []
    for dy, dx in DIRECTIONS:
        fq = _shift(frag, dy, dx, 0)
        m = (frag > 0) & (fq > 0)
        m &= (frag == fq) if intra else (frag != fq)
        if not m.any():
            continue
        if statistic == "secdiff":
            e, _ = _secdiff_residual(r, frag, inp.plant, dy, dx)
        elif statistic == "step":
            e = np.abs(_shift(r, dy, dx, np.nan) - r)
        elif statistic == "plane5":
            rq = _shift(r, dy, dx, np.nan)
            okq = _shift(ok, dy, dx, False)
            pred_pq = a + b * dx + c * dy                  # p's plane at q
            pred_qp = _shift(a, dy, dx, np.nan) + _shift(b, dy, dx, np.nan) * (-dx) \
                + _shift(c, dy, dx, np.nan) * (-dy)        # q's plane at p
            e = np.minimum(np.where(ok, np.abs(rq - pred_pq), np.inf),
                           np.where(okq, np.abs(r - pred_qp), np.inf))
        else:
            raise ValueError(statistic)
        sel = m & np.isfinite(e)
        pa, pb = frag[sel].astype(np.int64), fq[sel].astype(np.int64)
        lo, hi = np.minimum(pa, pb), np.maximum(pa, pb)
        pair_a.append(lo); pair_b.append(hi); res.append(e[sel])
    if not pair_a:
        return {"pair": np.zeros((0, 2), np.int64), "resid": np.zeros(0, np.float32)}
    return {"pair": np.stack([np.concatenate(pair_a), np.concatenate(pair_b)], 1),
            "resid": np.concatenate(res).astype(np.float32)}


def summarise_boundaries(bnd, n_frag):
    """Group per-pixel residuals into one row per adjacent fragment pair."""
    if bnd["pair"].shape[0] == 0:
        return {"pairs": np.zeros((0, 2), np.int64), "n": np.zeros(0, np.int64),
                "p25": np.zeros(0), "p50": np.zeros(0), "p75": np.zeros(0)}
    key = bnd["pair"][:, 0] * (n_frag + 1) + bnd["pair"][:, 1]
    order = np.lexsort((bnd["resid"], key))
    key, res = key[order], bnd["resid"][order]
    uniq, start, cnt = np.unique(key, return_index=True, return_counts=True)

    def q(p):
        # nearest-rank percentile inside each contiguous run
        idx = start + np.minimum((cnt - 1), np.floor(cnt * p / 100.0).astype(np.int64))
        return res[idx]

    return {"pairs": np.stack([uniq // (n_frag + 1), uniq % (n_frag + 1)], 1),
            "n": cnt, "p25": q(C.LINK_QUANTILE_LO), "p50": q(50.0),
            "p75": q(C.LINK_QUANTILE_HI)}


# -------------------------------------------------------------- the verdict --
def classify_edges(summary, tol: float = C.CONTINUITY_TOL_RDU):
    """connected / separated / unresolved, per adjacent fragment pair."""
    p25, p75 = summary["p25"], summary["p75"]
    connected = p75 <= tol
    separated = p25 > tol
    unresolved = ~connected & ~separated
    return connected, separated, unresolved


def components(n_frag: int, pairs, connected):
    """Union-find over the accepted edges. Connected components are plants."""
    parent = np.arange(n_frag + 1)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (u, v) in pairs[connected]:
        ru, rv = find(int(u)), find(int(v))
        if ru != rv:
            parent[max(ru, rv)] = min(ru, rv)
    root = np.array([find(i) for i in range(n_frag + 1)])
    root[0] = 0
    ids = {r: i for i, r in enumerate(sorted(set(root[1:].tolist())), start=1)}
    comp_of = np.zeros(n_frag + 1, np.int32)
    for f in range(1, n_frag + 1):
        comp_of[f] = ids[root[f]]
    return comp_of
