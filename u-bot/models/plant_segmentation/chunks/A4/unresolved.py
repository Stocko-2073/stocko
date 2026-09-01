"""A4 — the unresolved edges.

The roadmap: *"Where the graph cannot connect two fragments because the link is
occluded, record that as an explicit unresolved edge rather than silently
splitting or merging."* Three ways a link can be unresolved, and none of them is
decided:

**1. `ambiguous_boundary`** — the two fragments touch, and the shared boundary is
continuous along part of its length and a step along the rest: `p25 <= tol` but
`p75 > tol`. That is what a leaf lying across another leaf looks like, and what a
petiole emerging from behind one looks like. Merging would join two plants;
splitting would cut one. Recorded.

**2. `occluded_by`** — two plant fragments that do **not** touch, both touching a
third fragment that is *in front of both of them* along their shared boundaries.
The material may or may not continue behind the occluder; one view cannot say.
Note the construction takes no distance: the pair is found by shared adjacency
to an occluder, never by "these two are close enough". Nothing here is a spacing
parameter, and the gap width is *reported*, never thresholded.

**3. `leaves_frame`** — a fragment that touches the image border. Whatever it
connects to outside the frame is unobservable. This is precisely the failure the
roadmap records for ZeroPlantSeg ("corner leaves attach off-frame so their roots
never reach the crown"), so A4 counts it rather than inheriting it silently.

Under **R4** none of these is resolved by extrapolation. They are the list C1
(multi-view re-observation) exists to consume, and the list A5/A7 must read
before treating a component as a whole plant.
"""
from __future__ import annotations

import numpy as np

import a4_common as C
import a4_graph as G


def _boundary_relief(frag, relief, plant):
    """Median relief on each side of every adjacent fragment pair's boundary."""
    keys, rp, rq = [], [], []
    n = int(frag.max())
    for dy, dx in G.DIRECTIONS:
        for (ay, ax) in ((dy, dx), (-dy, -dx)):
            fq = G._shift(frag, ay, ax, 0)
            m = (frag > 0) & (fq > 0) & (frag != fq) & plant \
                & G._shift(plant, ay, ax, False)
            if not m.any():
                continue
            keys.append(frag[m].astype(np.int64) * (n + 1) + fq[m].astype(np.int64))
            rp.append(relief[m])
            rq.append(G._shift(relief, ay, ax, np.nan)[m])
    if not keys:
        return {}
    k = np.concatenate(keys); a = np.concatenate(rp); b = np.concatenate(rq)
    order = np.argsort(k, kind="stable")
    k, a, b = k[order], a[order], b[order]
    uniq, start, cnt = np.unique(k, return_index=True, return_counts=True)
    out = {}
    for u, s, c in zip(uniq, start, cnt):
        out[(int(u // (n + 1)), int(u % (n + 1)))] = (
            float(np.median(a[s:s + c])), float(np.median(b[s:s + c])), int(c))
    return out


def find_unresolved(inp: C.Inputs, frag: np.ndarray, summary, connected,
                    unresolved_mask, comp_of, max_pairs_per_occluder: int = 200):
    """Build the three unresolved-edge lists. Nothing here merges anything."""
    n = int(frag.max())
    sizes = np.bincount(frag.ravel(), minlength=n + 1)
    edges = []

    # 1. ambiguous boundaries -------------------------------------------------
    for i in np.nonzero(unresolved_mask)[0]:
        u, v = int(summary["pairs"][i, 0]), int(summary["pairs"][i, 1])
        edges.append({
            "kind": "ambiguous_boundary", "a": u, "b": v,
            "boundary_px": int(summary["n"][i]),
            "resid_p25_rdu": float(summary["p25"][i]),
            "resid_p50_rdu": float(summary["p50"][i]),
            "resid_p75_rdu": float(summary["p75"][i]),
            "components": [int(comp_of[u]), int(comp_of[v])],
            "already_connected": bool(comp_of[u] == comp_of[v]),
        })

    # 2. occlusion-mediated ---------------------------------------------------
    # every fragment, plant or not, may be an occluder; the test is whether it
    # stands in front of both of its neighbours along their shared boundaries.
    all_key = inp.regions.astype(np.int64) * 16 + inp.material.astype(np.int64)
    occ_lab = np.zeros(frag.shape, np.int32)
    from scipy import ndimage
    nxt = 1
    st = ndimage.generate_binary_structure(2, 2)
    for k in np.unique(all_key):
        m = all_key == k
        cc, cn = ndimage.label(m, structure=st)
        occ_lab[m] = cc[m] + (nxt - 1)
        nxt += cn
    # a joint labelling: plant fragments keep their id, everything else gets a
    # negative id so the two families cannot collide
    joint = np.where(frag > 0, frag.astype(np.int64),
                     -(occ_lab.astype(np.int64) + 1))
    rel = inp.relief.astype(np.float64)
    # (occluder, neighbour) -> boundary length, mean relief of the neighbour,
    # mean relief of the occluder. Accumulated vectorised; `joint` is offset so
    # negative (non-plant) ids index the same table.
    off = int(np.abs(joint).max()) + 1
    ks, rn, ro = [], [], []
    for dy, dx in G.DIRECTIONS:
        for (ay, ax) in ((dy, dx), (-dy, -dx)):
            jq = G._shift(joint, ay, ax, 0)
            m = (joint != 0) & (jq != 0) & (joint != jq)
            if not m.any():
                continue
            # u = neighbour (this pixel), v = occluder candidate (shifted pixel)
            ks.append((jq[m] + off) * (2 * off) + (joint[m] + off))
            rn.append(rel[m])
            ro.append(G._shift(rel, ay, ax, np.nan)[m])
    kk = np.concatenate(ks); an = np.concatenate(rn); ao = np.concatenate(ro)
    uniq, inv = np.unique(kk, return_inverse=True)
    cnt = np.bincount(inv)
    sn = np.bincount(inv, weights=an)
    so = np.bincount(inv, weights=ao)
    v_ids = (uniq // (2 * off)) - off          # occluder
    u_ids = (uniq % (2 * off)) - off           # neighbour
    nbr = {}
    for v, u, c, a_, b_ in zip(v_ids, u_ids, cnt, sn, so):
        nbr.setdefault(int(v), {})[int(u)] = [int(c), float(a_), float(b_)]

    seen = set()
    n_capped = 0
    for occ, ns in nbr.items():
        plants = [(k, v) for k, v in ns.items() if k > 0 and v[0] >= 1]
        # keep the occluder only where it stands in front of the neighbour
        infront = [(k, v) for k, v in plants if v[2] / v[0] > v[1] / v[0]]
        if len(infront) < 2:
            continue
        infront.sort(key=lambda kv: -kv[1][0])
        if len(infront) * (len(infront) - 1) // 2 > max_pairs_per_occluder:
            n_capped += 1
            infront = infront[:int(np.sqrt(2 * max_pairs_per_occluder)) + 1]
        for i in range(len(infront)):
            for j in range(i + 1, len(infront)):
                a, b = sorted((infront[i][0], infront[j][0]))
                if (a, b) in seen:
                    continue
                seen.add((a, b))
                ra = infront[i][1][1] / infront[i][1][0]
                rb = infront[j][1][1] / infront[j][1][0]
                edges.append({
                    "kind": "occluded_by", "a": int(a), "b": int(b),
                    "occluder": int(occ),
                    "occluder_px": int(sizes[occ]) if occ > 0 else None,
                    "relief_a_rdu": ra, "relief_b_rdu": rb,
                    "relief_disagreement_rdu": abs(ra - rb),
                    "components": [int(comp_of[a]), int(comp_of[b])],
                    "already_connected": bool(comp_of[a] == comp_of[b]),
                })

    # 3. frame edges ----------------------------------------------------------
    border = np.zeros(frag.shape, bool)
    border[0, :] = border[-1, :] = border[:, 0] = border[:, -1] = True
    for f in np.unique(frag[border & (frag > 0)]):
        edges.append({"kind": "leaves_frame", "a": int(f), "b": None,
                      "fragment_px": int(sizes[f]),
                      "components": [int(comp_of[f]), None],
                      "already_connected": False})

    counts = {}
    for e in edges:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    unresolved_between_components = sum(
        1 for e in edges if e["kind"] != "leaves_frame" and not e["already_connected"])
    return edges, {
        "n_unresolved_edges": len(edges),
        "by_kind": counts,
        "n_between_distinct_components": unresolved_between_components,
        "occluders_capped_at_max_pairs": n_capped,
        "max_pairs_per_occluder": max_pairs_per_occluder,
        "note": "R4: none of these is resolved by extrapolation. `already_connected` "
                "means the two fragments reached the same component by another "
                "path, so the unresolved link changes nothing; the rest are the "
                "links a second viewpoint (C1) would have to settle.",
    }
