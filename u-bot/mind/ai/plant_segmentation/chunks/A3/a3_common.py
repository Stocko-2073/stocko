"""A3 — shared substrate: partitions, region features, honest CV, scoring.

Nothing in this module classifies anything by itself. It provides:

* `build_partition`  — overlapping SAM proposals -> a non-overlapping cover,
  the same construction A0 used (`MIN_REGION` = 25 px, the registered (a)
  constant), so the two partitions are comparable.
* `RegionFeatures`   — per-region descriptors in four named groups:
    SHAPE   the roadmap's approach 1 (elongation, solidity, boundary
            complexity, plus width-constancy and ribbon-ness)
    SIZE    log area and mean width **in pixels** — kept separate because a
            pixel size is *not* scale-free: it encodes how far the camera was
            from the bed. Reported with and without, see FINDINGS.
    HEIGHT  A2's `height_in_sigma`, weighted by `height_sigma` (approach 2)
    COLOUR  chromaticity / excess-green (an extension beyond the brief)
    TEXTURE native-resolution gradient and orientation-coherence statistics
            (an extension; A0 found texture is the cue that separates grass
            from squash by eye, and that it does not survive the 768x1024
            label grid — but the *features* need not be computed there)
* `blocked_folds`    — spatially blocked group CV. Regions are contiguous, so
  a random split would put a region's own neighbourhood in the training set.
* `assemble`         — region labels -> a label map on the GT grid.
* `score_map`        — thin wrapper over `chunks/A0/eval.py`.

Every array is on A0's 768x1024 label grid unless stated.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
WORK = os.path.join(HERE, "work")
sys.path.insert(0, os.path.join(ROOT, "chunks", "A0"))
sys.path.insert(0, os.path.join(ROOT, "chunks", "A2"))

import eval as a0eval  # noqa: E402

GT_H, GT_W = 1024, 768

# --- constants ---------------------------------------------------------------
MIN_REGION = 25          # (a) A0's registered minimum reviewable region, reused
                         #     unchanged so the two partitions are comparable
CV_BLOCKS = (4, 4)       # (c) spatial CV block grid, see blocked_folds
N_FOLDS = 4              # (c) convention

# The label space A3 predicts. `soil` is excluded because the ground truth has
# zero soil pixels (A0: bare soil is not visible in a mulched bed), so it can be
# neither learnt nor scored; predicting it could only steal pixels from classes
# that do exist. `other` (554 px, one feather) is kept because it is labelled.
PREDICT_CLASSES = ["squash_leaf", "squash_petiole", "grass",
                   "broadleaf_weed", "straw", "fruit", "other"]
PREDICT_IDS = np.array([a0eval.CID[c] for c in PREDICT_CLASSES])

# Roadmap class -> A0 class. A0 is finer: it splits the roadmap's `broadleaf`
# into crop leaf and weed leaf. A3 predicts A0's classes and reports on A0's
# eight-class table; this mapping is documentation, not code that runs.
ROADMAP_TO_A0 = {
    "broadleaf": ["squash_leaf", "broadleaf_weed"],
    "grass": ["grass"],
    "stem_petiole": ["squash_petiole"],
    "straw": ["straw"],
    "soil": ["soil"],
    "fruit": ["fruit"],
    # A0's `other` has no roadmap class; it is one feather, 554 px.
}

FEATURE_GROUPS = ["SHAPE", "SIZE", "HEIGHT", "COLOUR", "TEXTURE"]


# ---------------------------------------------------------------- partition --
def load_masks(prefix: str = "a3_") -> np.ndarray:
    shape = tuple(np.load(os.path.join(WORK, f"{prefix}sam_masks_shape.npy")))
    packed = np.load(os.path.join(WORK, f"{prefix}sam_masks.npy"))
    return np.unpackbits(packed, axis=-1)[:, :, : shape[2]].astype(bool)


def build_partition(masks: np.ndarray, min_region: int = MIN_REGION) -> np.ndarray:
    """Overlapping proposals -> a non-overlapping cover of every pixel.

    Identical construction to A0's `build_partition.py`: paint largest-area
    first so the finest mask covering a pixel wins, split disconnected pieces,
    then fold sub-`min_region` fragments and uncovered pixels into the nearest
    surviving region. Region identity carries no class.
    """
    n, h, w = masks.shape
    areas = masks.reshape(n, -1).sum(1)
    order = np.argsort(-areas)
    lab = np.zeros((h, w), np.int32)
    for rank, i in enumerate(order, start=1):
        lab[masks[i]] = rank

    out = np.zeros((h, w), np.int32)
    nxt = 1
    for v in np.unique(lab):
        cc, k = ndimage.label(lab == v)
        for j in range(1, k + 1):
            out[cc == j] = nxt
            nxt += 1

    sizes = np.bincount(out.ravel(), minlength=nxt)
    keep = sizes >= min_region
    keep[0] = False
    good = keep[out]
    if not good.any():
        raise RuntimeError("no region survived the minimum-size filter")
    _, (iy, ix) = ndimage.distance_transform_edt(~good, return_indices=True)
    filled = out[iy, ix]

    ids = np.unique(filled)
    remap = np.zeros(filled.max() + 1, np.int32)
    remap[ids] = np.arange(1, len(ids) + 1)
    return remap[filled].astype(np.int32)


# ----------------------------------------------------------------- features --
def _rgb_gt() -> np.ndarray:
    p = os.path.join(WORK, "rgb_gtgrid.png")
    if not os.path.exists(p):
        im = Image.open(os.path.join(ROOT, "plants.jpeg")).resize(
            (GT_W, GT_H), Image.LANCZOS)
        im.save(p)
    return np.asarray(Image.open(p).convert("RGB")).astype(np.float32)


def _native_gray() -> np.ndarray:
    im = Image.open(os.path.join(ROOT, "plants.jpeg")).convert("L")
    return np.asarray(im).astype(np.float32)


def a2_on_gt_grid():
    """A2's height products, bilinearly resampled onto the 768x1024 label grid.

    A2 lives on the 1344x1008 A1 depth grid. Heights are a continuous field, so
    bilinear is correct here; the validity and coverage *labels* are nearest.
    """
    from a2_api import load_a2
    a2 = load_a2()

    def rs(a, nearest=False):
        im = Image.fromarray(np.asarray(a).astype(np.float32))
        return np.asarray(im.resize((GT_W, GT_H),
                                    Image.NEAREST if nearest else Image.BILINEAR))

    return {
        "h_sigma": rs(a2.height_in_sigma()),
        "height_sigma": rs(a2.height_sigma),
        "valid": rs(a2.valid.astype(np.float32), nearest=True) > 0.5,
        "observed": rs((a2.coverage == 0).astype(np.float32), nearest=True) > 0.5,
        "sigma_datum": a2.sigma_datum,
        "datum": a2.datum,
        "scale_confidence": a2.scale_confidence,
    }


def _shape_one(mask_bb: np.ndarray, ys: np.ndarray, xs: np.ndarray) -> dict:
    """Shape descriptors for one region. `mask_bb` is the region inside its
    bounding box; ys/xs are pixel coordinates in full-image space."""
    area = float(mask_bb.sum())
    # second central moments -> elongation, eccentricity
    cy, cx = ys.mean(), xs.mean()
    dy, dx = ys - cy, xs - cx
    cov = np.array([[np.mean(dy * dy), np.mean(dy * dx)],
                    [np.mean(dy * dx), np.mean(dx * dx)]])
    ev = np.linalg.eigvalsh(cov)
    l2, l1 = max(ev[0], 1e-9), max(ev[1], 1e-9)   # l1 >= l2
    elong = float(np.sqrt(l1 / l2))
    ecc = float(np.sqrt(max(0.0, 1.0 - l2 / l1)))

    # crack perimeter: pixel edges with no in-region 4-neighbour
    p = np.pad(mask_bb, 1)
    per = float((p[1:-1, 1:-1] & ~p[:-2, 1:-1]).sum()
                + (p[1:-1, 1:-1] & ~p[2:, 1:-1]).sum()
                + (p[1:-1, 1:-1] & ~p[1:-1, :-2]).sum()
                + (p[1:-1, 1:-1] & ~p[1:-1, 2:]).sum())
    per = max(per, 1.0)
    # boundary complexity: isoperimetric quotient, 1 for a disc, larger for lobed
    bcomplex = float(per ** 2 / (4 * np.pi * area))

    # solidity against the convex hull
    try:
        from scipy.spatial import ConvexHull, QhullError
        pts = np.stack([xs, ys], 1).astype(float)
        try:
            hull = ConvexHull(pts)
            solidity = float(area / max(hull.volume, 1e-9))
        except QhullError:
            solidity = 1.0
    except Exception:
        solidity = 1.0
    solidity = float(np.clip(solidity, 0.0, 1.0))

    # width from the distance transform: mean/max half-width and its spread
    dt = ndimage.distance_transform_edt(np.pad(mask_bb, 1))[1:-1, 1:-1]
    dv = dt[mask_bb]
    mean_w = float(2 * dv.mean())
    max_w = float(2 * dv.max())
    width_cv = float(dv.std() / max(dv.mean(), 1e-9))
    # ribbon-ness: 1.0 for a long constant-width ribbon, 0.5 for a disc
    ribbon = float(area / max(per * max(dv.max(), 1e-9), 1e-9))

    h_bb, w_bb = mask_bb.shape
    extent = float(area / (h_bb * w_bb))
    return dict(area=area, elongation=elong, eccentricity=ecc,
                solidity=solidity, boundary_complexity=bcomplex,
                width_cv=width_cv, ribbonness=ribbon, extent=extent,
                mean_width=mean_w, max_width=max_w,
                aspect_len_over_width=float(area / max(mean_w, 1e-9) / max(mean_w, 1e-9)),
                cy=float(cy), cx=float(cx))


@dataclass
class RegionFeatures:
    ids: np.ndarray                     # (R,) region ids, 1..R
    X: np.ndarray                       # (R, F)
    names: list                         # F feature names
    group_of: dict                      # name -> group
    area: np.ndarray                    # (R,) pixels
    centroid: np.ndarray                # (R, 2) as (y, x)
    meta: dict = field(default_factory=dict)

    def cols(self, groups) -> np.ndarray:
        sel = [i for i, n in enumerate(self.names) if self.group_of[n] in groups]
        if not sel:
            raise ValueError(f"no features in groups {groups}")
        return np.asarray(sel, int)

    def subset(self, groups):
        c = self.cols(groups)
        return self.X[:, c], [self.names[i] for i in c]


def compute_features(regions: np.ndarray, a2: dict | None = None,
                     with_texture: bool = True) -> RegionFeatures:
    rgb = _rgb_gt()
    R = int(regions.max())
    objs = ndimage.find_objects(regions)

    # --- colour channels on the GT grid
    s = rgb.sum(2) + 1e-6
    chrom = rgb / s[..., None]
    exg = (2 * rgb[..., 1] - rgb[..., 0] - rgb[..., 2]) / s
    val = rgb.max(2) / 255.0
    sat = (rgb.max(2) - rgb.min(2)) / np.maximum(rgb.max(2), 1e-6)

    # --- texture on the NATIVE 3000x4000 grid, pooled per region
    if with_texture:
        g = _native_gray()
        gy = ndimage.sobel(g, 0) / 8.0
        gx = ndimage.sobel(g, 1) / 8.0
        gmag = np.hypot(gx, gy)
        # structure tensor over a 9 px native window (~2.3 label px)
        Jxx = ndimage.uniform_filter(gx * gx, 9)
        Jyy = ndimage.uniform_filter(gy * gy, 9)
        Jxy = ndimage.uniform_filter(gx * gy, 9)
        coh = np.sqrt((Jxx - Jyy) ** 2 + 4 * Jxy ** 2) / (Jxx + Jyy + 1e-6)
        loc_std = np.sqrt(np.maximum(
            ndimage.uniform_filter(g * g, 9) - ndimage.uniform_filter(g, 9) ** 2, 0))
        # region map at native resolution (nearest, exact 3.90625x)
        nat = np.asarray(Image.fromarray(regions).resize(
            (g.shape[1], g.shape[0]), Image.NEAREST))
        idx = nat.ravel()
        cnt = np.bincount(idx, minlength=R + 1).astype(np.float64)
        cnt[cnt == 0] = 1

        def npool(a):
            return np.bincount(idx, weights=a.ravel(), minlength=R + 1) / cnt

        t_gmag = npool(gmag)
        t_gmag2 = npool(gmag ** 2)
        t_coh = npool(coh)
        t_std = npool(loc_std)
        t_gmag_sd = np.sqrt(np.maximum(t_gmag2 - t_gmag ** 2, 0))

    rows, ids, areas, cents = [], [], [], []
    for r in range(1, R + 1):
        sl = objs[r - 1]
        if sl is None:
            continue
        sub = regions[sl] == r
        ys, xs = np.nonzero(sub)
        ys = ys + sl[0].start
        xs = xs + sl[1].start
        sh = _shape_one(sub, ys, xs)

        f = {}
        for k in ("elongation", "eccentricity", "solidity", "boundary_complexity",
                  "width_cv", "ribbonness", "extent"):
            f[k] = sh[k]
        f["log_area"] = float(np.log10(sh["area"]))
        f["mean_width"] = sh["mean_width"]
        f["max_width"] = sh["max_width"]

        m = (regions == r) if False else None  # avoid a full-image mask per region
        f["chrom_r"] = float(chrom[ys, xs, 0].mean())
        f["chrom_g"] = float(chrom[ys, xs, 1].mean())
        f["exg_mean"] = float(exg[ys, xs].mean())
        f["exg_std"] = float(exg[ys, xs].std())
        f["value_mean"] = float(val[ys, xs].mean())
        f["value_std"] = float(val[ys, xs].std())
        f["sat_mean"] = float(sat[ys, xs].mean())

        if with_texture:
            f["tex_grad_mean"] = float(t_gmag[r])
            f["tex_grad_std"] = float(t_gmag_sd[r])
            f["tex_coherence"] = float(t_coh[r])
            f["tex_local_std"] = float(t_std[r])

        if a2 is not None:
            hs = a2["h_sigma"][ys, xs]
            sg = a2["height_sigma"][ys, xs]
            ok = a2["valid"][ys, xs] & np.isfinite(hs)
            if ok.sum() < 3:
                f.update(h_mean=0.0, h_med=0.0, h_p10=0.0, h_p90=0.0,
                         h_std=0.0, h_wmean=0.0, h_unc=1.0, h_obs_frac=0.0)
            else:
                v = hs[ok]
                # weight each pixel by the reliability of the datum under it:
                # w = sd^2 / (sd^2 + sigma_local^2), in datum-sigma units.
                sd = a2["sigma_datum"]
                w = sd ** 2 / (sd ** 2 + np.nan_to_num(sg[ok]) ** 2)
                f["h_mean"] = float(v.mean())
                f["h_med"] = float(np.median(v))
                f["h_p10"] = float(np.percentile(v, 10))
                f["h_p90"] = float(np.percentile(v, 90))
                f["h_std"] = float(v.std())
                f["h_wmean"] = float((v * w).sum() / max(w.sum(), 1e-9))
                f["h_unc"] = float(np.median(np.nan_to_num(sg[ok])) / sd)
                f["h_obs_frac"] = float(a2["observed"][ys, xs].mean())

        rows.append(f)
        ids.append(r)
        areas.append(sh["area"])
        cents.append((sh["cy"], sh["cx"]))

    names = list(rows[0].keys())
    X = np.array([[row[n] for n in names] for row in rows], np.float64)
    group_of = {}
    for n in names:
        if n in ("log_area", "mean_width", "max_width"):
            group_of[n] = "SIZE"
        elif n.startswith("h_"):
            group_of[n] = "HEIGHT"
        elif n.startswith("tex_"):
            group_of[n] = "TEXTURE"
        elif n.startswith(("chrom", "exg", "value", "sat")):
            group_of[n] = "COLOUR"
        else:
            group_of[n] = "SHAPE"
    return RegionFeatures(np.array(ids, int), X, names, group_of,
                          np.array(areas, float), np.array(cents, float))


# ----------------------------------------------------------- labels and CV ---
def region_gt_labels(regions: np.ndarray, gt) -> tuple:
    """Majority ground-truth class per region, over labelled pixels only.

    Returns (y, purity, labelled_frac) aligned to region ids 1..R.
    `y` is -1 where a region has too few labelled pixels to call.
    """
    R = int(regions.max())
    n_cls = len(a0eval.CLASSES)
    counts = np.zeros((R + 1, n_cls), np.int64)
    np.add.at(counts, (regions.ravel(), gt.material.ravel()), 1)
    tot = counts.sum(1)
    lab = counts[:, 1:].sum(1)                       # excluding `unlabelled`
    y = np.full(R + 1, -1, int)
    nz = lab > 0
    y[nz] = counts[nz, 1:].argmax(1) + 1
    purity = np.zeros(R + 1)
    purity[nz] = counts[nz, 1:].max(1) / lab[nz]
    lfrac = np.zeros(R + 1)
    lfrac[tot > 0] = lab[tot > 0] / tot[tot > 0]
    y[lfrac < 0.5] = -1                               # mostly-unlabelled: no call
    return y[1:], purity[1:], lfrac[1:]


def blocked_folds(centroid: np.ndarray, n_folds: int = N_FOLDS,
                  blocks: tuple = CV_BLOCKS, seed: int = 0) -> np.ndarray:
    """Spatially blocked CV assignment, one fold id per region.

    Regions are contiguous, so a random region split leaves a region's own
    neighbours (same leaf, same tussock, same lighting) in the training set and
    the score is optimistic. The frame is cut into `blocks` tiles, and whole
    tiles are dealt to folds, so a held-out region's neighbourhood is held out
    with it.
    """
    by = np.clip((centroid[:, 0] / GT_H * blocks[0]).astype(int), 0, blocks[0] - 1)
    bx = np.clip((centroid[:, 1] / GT_W * blocks[1]).astype(int), 0, blocks[1] - 1)
    bid = by * blocks[1] + bx
    rng = np.random.default_rng(seed)
    perm = rng.permutation(blocks[0] * blocks[1])
    fold_of_block = np.zeros(blocks[0] * blocks[1], int)
    for i, b in enumerate(perm):
        fold_of_block[b] = i % n_folds
    return fold_of_block[bid]


def assemble(regions: np.ndarray, region_ids: np.ndarray,
             y: np.ndarray) -> np.ndarray:
    """Region class ids -> a per-pixel label map on the GT grid."""
    lut = np.zeros(int(regions.max()) + 1, np.uint8)
    lut[region_ids] = np.asarray(y, np.uint8)
    return lut[regions]


# ------------------------------------------------------------------ scoring --
def score_map(pred_material: np.ndarray, gt=None, name="pred") -> dict:
    gt = gt or a0eval.load_gt()
    pred = a0eval.load_prediction(material=pred_material.astype(np.uint8),
                                  name=name, gt=gt)
    return a0eval.score(pred, gt)


def confusion_rows(res: dict) -> np.ndarray:
    return np.array(res["confusion"], np.int64)


def grass_squash_confusion(res: dict) -> dict:
    """The failure this chunk exists to fix, as a table.

    `grass_as_squash` — fraction of ground-truth grass pixels predicted as
    squash material (leaf, petiole or fruit). The A0-scored baseline's
    equivalent number, on instances rather than classes, is 53.0 %.
    """
    m = confusion_rows(res)
    C = a0eval.CID
    squash = [C["squash_leaf"], C["squash_petiole"], C["fruit"]]
    g = C["grass"]
    grass_tot = m[g].sum()
    sq_tot = m[squash].sum()
    return {
        "gt_grass_px": int(grass_tot),
        "grass_as_squash_px": int(m[g][squash].sum()),
        "grass_as_squash": float(m[g][squash].sum() / max(grass_tot, 1)),
        "grass_as_squash_leaf": float(m[g][C["squash_leaf"]] / max(grass_tot, 1)),
        "grass_as_grass": float(m[g][g] / max(grass_tot, 1)),
        "grass_as_straw": float(m[g][C["straw"]] / max(grass_tot, 1)),
        "gt_squash_px": int(sq_tot),
        "squash_as_grass": float(m[squash][:, g].sum() / max(sq_tot, 1)),
    }


def summarise(res: dict) -> dict:
    per = {c: v["iou"] for c, v in res["per_class_iou"].items()}
    out = {"mean_iou": res["mean_iou"], "per_class_iou": per}
    out.update(grass_squash_confusion(res))
    return out


def save_pred(name: str, material: np.ndarray):
    d = os.path.join(HERE, "preds")
    os.makedirs(d, exist_ok=True)
    Image.fromarray(material.astype(np.uint8)).save(os.path.join(d, f"{name}.png"))


def load_json(p, default=None):
    return json.load(open(p)) if os.path.exists(p) else default
