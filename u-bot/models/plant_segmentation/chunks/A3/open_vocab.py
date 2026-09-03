"""A3 approach 4 — an open-vocabulary classifier over the same SAM regions.

What the brief asks for: replace OVSeg's 2022-era mask-tuned CLIP with either
Alpha-CLIP (an alpha channel marks the region, instead of crop-and-fill
destroying the surround) or SigLIP 2, and separately test the cheap
prompt-ensembling trick (OVSeg uses a single `f'a photo of {name}'`).

Alpha-CLIP: see `alpha_clip_check.py` and FINDINGS. SigLIP 2 is the shipped
choice, with `openai/clip-vit-large-patch14` run alongside as the "before" — a
2022-era CLIP on the identical crops and prompts, so the model upgrade is
isolated from everything else.

Three ways of telling the model *which* region it is looking at, all cropped
from the **native 3000x4000** photograph, not the label grid:

* `crop_fill`    — OVSeg's protocol: tight crop, everything outside the mask
                   replaced by the encoder's mean colour. Destroys the surround.
* `crop_context` — bbox plus a margin, nothing masked. Keeps the surround but
                   never says which pixels are the region.
* `blend`        — bbox plus a margin, outside the mask blended halfway to the
                   mean colour. A stand-in for Alpha-CLIP's alpha channel that
                   needs no new weights: the region is marked, the surround
                   survives at reduced contrast.

Selection honesty
-----------------
A zero-shot classifier is fitted on nothing, so the whole frame is legitimately
test data. The one thing that can be over-fitted is the *configuration*, so the
headline config is fixed in advance — `crop_fill` (OVSeg's own protocol, so the
comparison isolates the model), descriptive prompts, prompt ensemble — and the
full 2x2x3 grid is reported as sensitivity underneath, with the best cell
flagged as chosen after seeing the scores.
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

NATIVE_SCALE = 3.90625        # (a) A0's label grid -> native, exact in x and y
CROP_PAD = 0.30               # (c) context margin as a fraction of the bbox
MIN_CROP_NATIVE = 96          # (a) a crop smaller than this carries no texture
                              #     at the encoder's own input resolution

# The single template OVSeg uses, and the ensemble it is being compared against.
SINGLE = ["a photo of {}"]
ENSEMBLE = [
    "a photo of {}", "a close-up photo of {}", "a cropped photo of {}",
    "a macro photo of {}", "a bright photo of {}", "a dark photo of {}",
    "a blurry photo of {}", "a photo of the {}", "an image of {}",
    "a photo of one {}", "a close-up of {} outdoors",
    "a photograph of {} in a garden bed",
]

# Prompt vocabularies. `plain` is the bare class name; `descriptive` paraphrases
# A0's SCHEMA.md wording for each class. Both are fixed before scoring.
VOCAB = {
    "plain": {
        "squash_leaf": "a squash leaf",
        "squash_petiole": "a plant stem",
        "grass": "a grass blade",
        "broadleaf_weed": "a weed leaf",
        "straw": "straw",
        "fruit": "a squash",
        "other": "an animal",
    },
    "descriptive": {
        "squash_leaf": "a large lobed green squash leaf blade",
        "squash_petiole": "a thick green plant stem or vine",
        "grass": "long narrow blades of green grass",
        "broadleaf_weed": "a small low-growing broadleaf weed",
        "straw": "dry brown straw mulch",
        "fruit": "a round green squash fruit",
        "other": "a bird feather on the ground",
    },
}

HEADLINE = ("crop_fill", "descriptive", "ensemble")


def _device():
    return "mps" if torch.backends.mps.is_available() else "cpu"


def load_model(name):
    from transformers import AutoModel, AutoProcessor
    proc = AutoProcessor.from_pretrained(name)
    model = AutoModel.from_pretrained(name).eval().to(_device())
    return model, proc


def _feat(out):
    """transformers 5.x returns a BaseModelOutputWithPooling from
    `get_*_features` for SigLIP; older versions and CLIP return a bare tensor."""
    return out if isinstance(out, torch.Tensor) else out.pooler_output


def _image_mean(proc):
    ip = getattr(proc, "image_processor", proc)
    m = getattr(ip, "image_mean", [0.5, 0.5, 0.5])
    return np.array([int(round(255 * v)) for v in m], np.uint8)


def region_crops(regions, native, variant, proc):
    """One PIL crop per region, from the native photograph."""
    from scipy import ndimage
    fill = _image_mean(proc)
    H, W = native.shape[:2]
    objs = ndimage.find_objects(regions)
    out, ids = [], []
    for r in range(1, int(regions.max()) + 1):
        sl = objs[r - 1]
        if sl is None:
            continue
        y0, y1 = sl[0].start, sl[0].stop
        x0, x1 = sl[1].start, sl[1].stop
        ny0, ny1 = y0 * NATIVE_SCALE, y1 * NATIVE_SCALE
        nx0, nx1 = x0 * NATIVE_SCALE, x1 * NATIVE_SCALE
        if variant != "crop_fill":
            ph, pw = (ny1 - ny0) * CROP_PAD, (nx1 - nx0) * CROP_PAD
            ny0, ny1, nx0, nx1 = ny0 - ph, ny1 + ph, nx0 - pw, nx1 + pw
        cy, cx = (ny0 + ny1) / 2, (nx0 + nx1) / 2
        hh = max(ny1 - ny0, MIN_CROP_NATIVE) / 2
        ww = max(nx1 - nx0, MIN_CROP_NATIVE) / 2
        ay0 = int(np.clip(cy - hh, 0, H - 1)); ay1 = int(np.clip(cy + hh, 1, H))
        ax0 = int(np.clip(cx - ww, 0, W - 1)); ax1 = int(np.clip(cx + ww, 1, W))
        sub = native[ay0:ay1, ax0:ax1].copy()
        if variant in ("crop_fill", "blend"):
            m = np.asarray(Image.fromarray((regions == r).astype(np.uint8) * 255)
                           .resize((W, H), Image.NEAREST))[ay0:ay1, ax0:ax1] > 0
            if variant == "crop_fill":
                sub[~m] = fill
            else:
                sub[~m] = (0.5 * sub[~m] + 0.5 * fill).astype(np.uint8)
        out.append(Image.fromarray(sub))
        ids.append(r)
    return out, np.array(ids, int)


@torch.no_grad()
def text_embeddings(model, proc, vocab, templates):
    embs = []
    for c in A.PREDICT_CLASSES:
        name = vocab[c]
        txt = [t.format(name) for t in templates]
        tk = proc(text=txt, return_tensors="pt", padding="max_length",
                  truncation=True).to(_device())
        e = _feat(model.get_text_features(**tk)).float()
        e = e / e.norm(dim=-1, keepdim=True)
        e = e.mean(0)
        embs.append((e / e.norm()).cpu().numpy())
    return np.stack(embs)


@torch.no_grad()
def image_embeddings(model, proc, crops, batch=16):
    out = []
    for i in range(0, len(crops), batch):
        px = proc(images=crops[i:i + batch], return_tensors="pt").to(_device())
        e = _feat(model.get_image_features(**px)).float()
        out.append((e / e.norm(dim=-1, keepdim=True)).cpu().numpy())
    return np.concatenate(out)


def run(model_name, partition, out_path):
    gt = a0eval.load_gt()
    regions = np.load(os.path.join(A.WORK, f"regions_{partition}.npy")) \
        if partition != "a0" else np.load(
            os.path.join(A.ROOT, "chunks/A0/work/regions.npy"))
    native = np.asarray(Image.open(os.path.join(A.ROOT, "plants.jpeg"))
                        .convert("RGB"))

    t0 = time.time()
    model, proc = load_model(model_name)
    t_load = time.time() - t0

    res = {"model": model_name, "partition": partition,
           "n_regions": int(regions.max()), "device": _device(),
           "headline_config": list(HEADLINE), "seconds": {"load": t_load},
           "grid": {}, "prompt_templates": {"single": SINGLE,
                                            "ensemble": ENSEMBLE},
           "vocab": VOCAB}

    img_emb, t_img = {}, {}
    for variant in ("crop_fill", "crop_context", "blend"):
        t0 = time.time()
        crops, ids = region_crops(regions, native, variant, proc)
        t_crop = time.time() - t0
        t0 = time.time()
        img_emb[variant] = image_embeddings(model, proc, crops)
        t_img[variant] = time.time() - t0
        print(f"{variant}: {len(crops)} crops in {t_crop:.1f}s, "
              f"encoded in {t_img[variant]:.1f}s")
    res["seconds"]["image_encode"] = t_img

    for vname, vocab in VOCAB.items():
        for tname, templates in (("single", SINGLE), ("ensemble", ENSEMBLE)):
            t0 = time.time()
            T = text_embeddings(model, proc, vocab, templates)
            t_txt = time.time() - t0
            for variant in img_emb:
                lab = np.array(A.PREDICT_IDS)[(img_emb[variant] @ T.T).argmax(1)]
                m = A.assemble(regions, ids, lab)
                key = f"{variant}|{vname}|{tname}"
                s = A.summarise(A.score_map(m, gt, key))
                s["seconds_text"] = t_txt
                s["seconds_image"] = t_img[variant]
                res["grid"][key] = s
                if (variant, vname, tname) == HEADLINE:
                    A.save_pred(f"approach4_openvocab_{model_name.split('/')[-1]}", m)
                    res["headline"] = s
                print(f"  {key:34s} mIoU {s['mean_iou']:.4f}  "
                      f"grass->squash {100*s['grass_as_squash']:.1f}%")

    best = max(res["grid"], key=lambda k: res["grid"][k]["mean_iou"])
    res["best_config_selected_on_gt"] = {"config": best, **res["grid"][best]}
    # prompt-ensembling effect, isolated: same variant and vocabulary
    eff = {}
    for variant in img_emb:
        for vname in VOCAB:
            a = res["grid"][f"{variant}|{vname}|single"]["mean_iou"]
            b = res["grid"][f"{variant}|{vname}|ensemble"]["mean_iou"]
            eff[f"{variant}|{vname}"] = {"single": a, "ensemble": b,
                                         "delta": b - a}
    res["prompt_ensembling_effect"] = eff
    res["prompt_ensembling_mean_delta"] = float(
        np.mean([v["delta"] for v in eff.values()]))
    print("prompt ensembling, mean delta over 6 (variant, vocab) cells: "
          f"{res['prompt_ensembling_mean_delta']:+.4f}")

    json.dump(res, open(out_path, "w"), indent=1)
    print("wrote", out_path)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="google/siglip2-base-patch16-384")
    ap.add_argument("--partition", default="a3f")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    tag = a.model.split("/")[-1]
    out = a.out or os.path.join(HERE, "results", f"open_vocab_{tag}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    run(a.model, a.partition, out)


if __name__ == "__main__":
    main()
