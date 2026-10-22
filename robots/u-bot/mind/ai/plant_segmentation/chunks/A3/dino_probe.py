"""A3 approach 3 — a probe on frozen DINOv2/v3 patch features.

The brief: "a linear or k-NN probe on frozen DINOv2/v3 patch features over a few
dozen hand-labelled patches". Nothing here fine-tunes anything; the backbone is
frozen and only the probe is fitted.

Two feature scales are extracted and concatenated:

* **fine** — the native photograph resized to 3066x4088 (a uniform 3.992x of
  A0's 768x1024 label grid) and tiled into 518x518 windows. One patch is 14
  native-ish px, i.e. **3.5 label px**. This is the scale at which A0 said the
  discriminating evidence lives: "the separation that actually worked by eye was
  texture and cross-section ... and neither survives to 768x1024". The label
  grid caps the *labels*, not the features.
* **coarse** — the whole frame in one pass at 546x728, giving each patch the
  context of the plant it belongs to.

"Hand-labelled patches" are sampled from the A0 ground truth, which stands in
for a human clicking points: a patch is eligible only if its label-grid
footprint is 100 % one class. `--per-class` patches per class are drawn, so the
default is 6 x 7 = **42 patches** — a few dozen, as the brief intends.

Honesty of the split
--------------------
The probe is fitted on those patches and scored on the whole frame, which
includes them. They are 42 patches x ~13 label px = ~0.07 % of the frame, so the
contamination is tiny, but it is not zero and it is not assumed away: every
score is reported twice, once over the whole frame and once with the training
patches' own pixels removed from the ground truth. Five independent draws are
run and the headline is their mean +- sd, because a single draw of 42 points is
itself a lottery.

Approach 3b (an extension, clearly labelled) pools the same frozen features over
the SAM regions of approaches 1-2 and fits the same spatially-blocked-CV
classifier, so the feature source is the only thing that changes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import torch
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import a3_common as A  # noqa: E402
import eval as a0eval  # noqa: E402

from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.neighbors import KNeighborsClassifier  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

FINE_H, FINE_W = 4088, 3066     # 292 x 219 patches of 14 px -> 3.5 label px each
COARSE_H, COARSE_W = 728, 546   # 52 x 39 patches, whole frame in one pass
TILE = 518                      # 37 x 37 patches, DINOv2's own training size
STRIDE = 434                    # 31 patches; a 6-patch overlap, averaged
PATCH = 14
N_DRAWS = 5                     # independent draws of the hand-labelled set
DEFAULT_PER_CLASS = 6           # 6 x 7 classes = 42 patches


def _device():
    return "mps" if torch.backends.mps.is_available() else "cpu"


def load_backbone(name):
    from transformers import AutoModel
    m = AutoModel.from_pretrained(name).eval().to(_device())
    p = getattr(m.config, "patch_size", PATCH)
    return m, int(p)


@torch.no_grad()
def _patch_tokens(model, px, gh, gw):
    out = model(pixel_values=px)
    h = out.last_hidden_state
    n = gh * gw
    h = h[:, -n:, :]                       # drop CLS and any register tokens
    return h.reshape(h.shape[0], gh, gw, h.shape[-1])


def fine_features(model, patch, img: Image.Image, batch=6):
    im = img.resize((FINE_W, FINE_H), Image.LANCZOS)
    arr = np.asarray(im).astype(np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], np.float32)
    std = np.array([0.229, 0.224, 0.225], np.float32)
    arr = (arr - mean) / std
    t = torch.from_numpy(arr).permute(2, 0, 1)

    PH, PW = FINE_H // patch, FINE_W // patch
    ys = list(range(0, FINE_H - TILE + 1, STRIDE))
    xs = list(range(0, FINE_W - TILE + 1, STRIDE))
    if ys[-1] != FINE_H - TILE:
        ys.append(((FINE_H - TILE) // patch) * patch)
    if xs[-1] != FINE_W - TILE:
        xs.append(((FINE_W - TILE) // patch) * patch)

    D = model.config.hidden_size
    acc = np.zeros((PH, PW, D), np.float32)
    cnt = np.zeros((PH, PW, 1), np.float32)
    gh = gw = TILE // patch
    jobs = [(y, x) for y in ys for x in xs]
    for i in range(0, len(jobs), batch):
        chunk = jobs[i:i + batch]
        px = torch.stack([t[:, y:y + TILE, x:x + TILE] for y, x in chunk]
                         ).to(_device())
        f = _patch_tokens(model, px, gh, gw).float().cpu().numpy()
        for k, (y, x) in enumerate(chunk):
            py, pxi = y // patch, x // patch
            acc[py:py + gh, pxi:pxi + gw] += f[k]
            cnt[py:py + gh, pxi:pxi + gw] += 1
    cnt[cnt == 0] = 1
    return acc / cnt, (PH, PW), len(jobs)


def coarse_features(model, patch, img: Image.Image, grid):
    im = img.resize((COARSE_W, COARSE_H), Image.LANCZOS)
    arr = np.asarray(im).astype(np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], np.float32)
    std = np.array([0.229, 0.224, 0.225], np.float32)
    t = torch.from_numpy((arr - mean) / std).permute(2, 0, 1)[None].to(_device())
    gh, gw = COARSE_H // patch, COARSE_W // patch
    f = _patch_tokens(model, t, gh, gw)[0].float().cpu().numpy()
    # resample the coarse patch grid onto the fine patch grid
    PH, PW = grid
    yi = np.clip((np.arange(PH) + 0.5) * gh / PH, 0, gh - 1)
    xi = np.clip((np.arange(PW) + 0.5) * gw / PW, 0, gw - 1)
    y0 = np.floor(yi).astype(int)
    x0 = np.floor(xi).astype(int)
    return f[y0][:, x0]


def l2(a, axis=-1):
    return a / np.maximum(np.linalg.norm(a, axis=axis, keepdims=True), 1e-8)


def patch_gt(grid, gt):
    """Majority GT class and purity per fine patch, over labelled pixels."""
    PH, PW = grid
    yy = np.minimum((np.arange(A.GT_H) * PH // A.GT_H), PH - 1)
    xx = np.minimum((np.arange(A.GT_W) * PW // A.GT_W), PW - 1)
    pid = (yy[:, None] * PW + xx[None, :]).ravel()
    n_cls = len(a0eval.CLASSES)
    counts = np.zeros((PH * PW, n_cls), np.int64)
    np.add.at(counts, (pid, gt.material.ravel()), 1)
    lab = counts[:, 1:].sum(1)
    y = np.zeros(PH * PW, int)
    pur = np.zeros(PH * PW)
    nz = lab > 0
    y[nz] = counts[nz, 1:].argmax(1) + 1
    pur[nz] = counts[nz, 1:].max(1) / lab[nz]
    return y.reshape(PH, PW), pur.reshape(PH, PW), pid.reshape(A.GT_H, A.GT_W)


def upsample_patch_labels(labels, pid_map):
    return labels.ravel()[pid_map].astype(np.uint8)


def patch_height(grid):
    """A2's height, in datum sigma, pooled over each fine patch, plus the
    reliability of the datum beneath it. Two extra columns, so the height
    ablation runs on exactly the winning approach rather than on a proxy."""
    a2 = A.a2_on_gt_grid()
    PH, PW = grid
    yy = np.minimum(np.arange(A.GT_H) * PH // A.GT_H, PH - 1)
    xx = np.minimum(np.arange(A.GT_W) * PW // A.GT_W, PW - 1)
    pid = (yy[:, None] * PW + xx[None, :]).ravel()
    sd = a2["sigma_datum"]
    rel = sd ** 2 / (sd ** 2 + np.nan_to_num(a2["height_sigma"]) ** 2)
    h = np.nan_to_num(a2["h_sigma"]) * a2["valid"]
    n = np.bincount(pid, minlength=PH * PW).astype(float)
    n[n == 0] = 1
    hp = np.bincount(pid, weights=h.ravel(), minlength=PH * PW) / n
    rp = np.bincount(pid, weights=rel.ravel(), minlength=PH * PW) / n
    return np.stack([hp, rp], 1)


def masked_gt(gt, drop: np.ndarray):
    """A copy of the ground truth with `drop` pixels marked `unlabelled`, so a
    score can exclude the pixels the probe was fitted on."""
    import copy
    g2 = copy.copy(gt)
    m = gt.material.copy()
    m[drop] = a0eval.UNLABELLED
    g2.material = m
    g2.meta = dict(gt.meta)
    g2.meta["unlabelled_fraction"] = float((m == 0).mean())
    return g2


def run(model_name, per_class, out_path):
    gt = a0eval.load_gt()
    img = Image.open(os.path.join(A.ROOT, "plants.jpeg")).convert("RGB")

    t0 = time.time()
    model, patch = load_backbone(model_name)
    t_load = time.time() - t0

    t0 = time.time()
    fine, grid, n_tiles = fine_features(model, patch, img)
    t_fine = time.time() - t0
    t0 = time.time()
    coarse = coarse_features(model, patch, img, grid)
    t_coarse = time.time() - t0
    PH, PW = grid
    F = np.concatenate([l2(fine), l2(coarse)], -1).reshape(PH * PW, -1)
    print(f"patch grid {PH}x{PW}, feature dim {F.shape[1]}, "
          f"{n_tiles} tiles, fine {t_fine:.1f}s coarse {t_coarse:.1f}s")

    ygrid, purity, pid_map = patch_gt(grid, gt)
    y = ygrid.ravel()
    pur = purity.ravel()
    H2 = patch_height(grid)
    FH = np.concatenate([F, H2], 1)

    res = {"model": model_name, "patch": patch, "grid": [PH, PW],
           "feature_dim": int(F.shape[1]), "n_tiles": n_tiles,
           "device": _device(),
           "seconds": {"load_backbone": t_load, "fine": t_fine,
                       "coarse": t_coarse},
           "label_px_per_patch": A.GT_H / PH,
           "per_class": per_class, "n_draws": N_DRAWS,
           "draws": [], "probes": {}}

    eligible = {}
    for c in A.PREDICT_CLASSES:
        cid = a0eval.CID[c]
        idx = np.where((y == cid) & (pur >= 1.0))[0]
        eligible[c] = idx
    res["eligible_pure_patches"] = {c: int(len(v)) for c, v in eligible.items()}
    print("eligible pure patches:", res["eligible_pure_patches"])

    # The ceiling of this substrate: every patch given its own majority GT
    # class. Directly comparable to the SAM partitions' 0.82 / 0.92.
    res["patch_grid_ceiling"] = A.summarise(A.score_map(
        upsample_patch_labels(np.where(ygrid > 0, ygrid, a0eval.CID["straw"]),
                              pid_map), gt, "oracle-patchgrid"))
    print(f"patch-grid ceiling: {res['patch_grid_ceiling']['mean_iou']:.4f}")

    probes = {
        "knn1": (lambda: KNeighborsClassifier(n_neighbors=1, metric="cosine"), F),
        "knn3": (lambda: KNeighborsClassifier(n_neighbors=3, metric="cosine"), F),
        "logreg": (lambda: LogisticRegression(max_iter=2000, C=1.0), F),
        # --- the A2 height ablation, on exactly the winning approach
        "logreg_scaled": (lambda: make_pipeline(
            StandardScaler(), LogisticRegression(max_iter=2000, C=1.0)), F),
        "logreg_scaled_height": (lambda: make_pipeline(
            StandardScaler(), LogisticRegression(max_iter=2000, C=1.0)), FH),
        "logreg_height_only": (lambda: make_pipeline(
            StandardScaler(), LogisticRegression(max_iter=2000, C=1.0)), H2),
    }
    acc = {k: {"full": [], "heldout": [], "grass_as_squash": [],
               "per_class": [], "fit_seconds": [], "predict_seconds": []}
           for k in probes}

    for d in range(N_DRAWS):
        rng = np.random.default_rng(1000 + d)
        tr_idx, tr_y = [], []
        for c, idx in eligible.items():
            if len(idx) == 0:
                continue
            take = rng.choice(idx, size=min(per_class, len(idx)), replace=False)
            tr_idx += list(take)
            tr_y += [a0eval.CID[c]] * len(take)
        tr_idx = np.array(tr_idx)
        tr_y = np.array(tr_y)
        train_pixels = np.isin(pid_map, tr_idx)
        gt_held = masked_gt(gt, train_pixels)
        res["draws"].append({"draw": d, "n_patches": int(len(tr_idx)),
                             "train_pixels": int(train_pixels.sum()),
                             "train_pixel_fraction": float(train_pixels.mean())})

        for pname, (mk, FEAT) in probes.items():
            t0 = time.time()
            clf = mk().fit(FEAT[tr_idx], tr_y)
            t_fit = time.time() - t0
            t0 = time.time()
            lab = clf.predict(FEAT).reshape(PH, PW)
            t_pred = time.time() - t0
            m = upsample_patch_labels(lab, pid_map)
            s_full = A.summarise(A.score_map(m, gt, f"dino/{pname}/d{d}"))
            s_held = A.summarise(A.score_map(m, gt_held, f"dino/{pname}/d{d}/held"))
            acc[pname]["full"].append(s_full["mean_iou"])
            acc[pname]["heldout"].append(s_held["mean_iou"])
            acc[pname]["grass_as_squash"].append(s_full["grass_as_squash"])
            acc[pname]["per_class"].append(s_full["per_class_iou"])
            acc[pname]["fit_seconds"].append(t_fit)
            acc[pname]["predict_seconds"].append(t_pred)
            if d == 0:
                A.save_pred(f"approach3_dino_{pname}", m)

    for pname, a in acc.items():
        pc = {}
        for c in a["per_class"][0]:
            v = [d[c] for d in a["per_class"] if d[c] is not None]
            pc[c] = float(np.mean(v)) if v else None
            pc[c + "_sd"] = float(np.std(v)) if v else None
        res["probes"][pname] = {
            "mean_iou": float(np.mean(a["full"])),
            "mean_iou_sd": float(np.std(a["full"])),
            "mean_iou_per_draw": [float(v) for v in a["full"]],
            "mean_iou_heldout": float(np.mean(a["heldout"])),
            "mean_iou_heldout_sd": float(np.std(a["heldout"])),
            "grass_as_squash": float(np.mean(a["grass_as_squash"])),
            "per_class_iou": pc,
            "fit_seconds": float(np.mean(a["fit_seconds"])),
            "predict_seconds": float(np.mean(a["predict_seconds"])),
        }
        print(f"  {pname:7s} mIoU {res['probes'][pname]['mean_iou']:.4f}"
              f" +-{res['probes'][pname]['mean_iou_sd']:.4f}"
              f"  (train pixels excluded: "
              f"{res['probes'][pname]['mean_iou_heldout']:.4f})"
              f"  grass->squash {100*res['probes'][pname]['grass_as_squash']:.1f}%")

    np.save(os.path.join(A.WORK, "dino_fine.npy"), fine.astype(np.float16))
    np.save(os.path.join(A.WORK, "dino_coarse.npy"), coarse.astype(np.float16))
    json.dump(res, open(out_path, "w"), indent=1)
    print("wrote", out_path)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="facebook/dinov2-base")
    ap.add_argument("--per-class", type=int, default=DEFAULT_PER_CLASS)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = a.out or os.path.join(HERE, "results", "dino_probe.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    run(a.model, a.per_class, out)


if __name__ == "__main__":
    main()
