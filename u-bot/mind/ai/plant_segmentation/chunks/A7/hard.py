"""A7 — the hard cases, and the confabulation probe.

The brief asks for the failure mode that matters: seedlings and crop volunteers,
where a wanted plant and a weed look nearly identical. `plants.jpeg` contains no
squash seedling, so the boundary is reached the only honest way available from
one image — by **taking the context away**.

Three probes, all with the shipped framing-A prompt so nothing but the stimulus
changes:

* **context ablation.** The same region rendered at `pad_fraction` 0.00 (the
  region and almost nothing else — a small squash leaf fragment with its vine
  cropped out is visually a broadleaf seedling), the shipped 0.75, and 3.00
  (a lot of surround). This is simultaneously the R1 sensitivity sweep for
  `pad_fraction` and the seedling test: if a label is stable across it, context
  was not doing the work; if it flips, the model was reading the vine, not the
  leaf.
* **null regions.** Regions drawn over material A0 labels as *pure straw*,
  rendered and prompted identically to real ones. There is no plant there. A
  confident `remove` is a confabulation, and this measures the rate.
* **the mixed component.** Component 1 holds 98 % of the ground-truth crop
  **and 83 % of the grass** (A4). Its `mixed` flag across every repeat of every
  condition answers "does the VLM notice a mixed component?"; that one is read
  out of the main run by `score.py`, not re-run here.

Membership of the hard set is a stated rule, fixed before any of it was scored,
not a hand-picked list.
"""
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

import prompts as P
import schema as S
import vlm
from a7_data import ROOT, load_components
from render import Renderer

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
PADS = {"p000": 0.00, "p300": 3.00}
NULL_IDS = range(901, 907)
GT_STRAW = 5
NULL_BOX = 20          # label px; ~78 native px, the size of a small weed
NULL_SEED = 20260901
NULL_REPS = 3


def hard_set(comps):
    """The rule, stated once.  crop fragments / weeds / crop-grass mixtures."""
    small_crop = [c.id for c in comps.values()
                  if c.core and c.truth == "crop" and c.id != 1]
    weeds = [c.id for c in comps.values()
             if c.core and c.truth == "weed"]
    mixed = [c.id for c in comps.values()
             if c.core and c.truth == "grass" and c.crop_fraction >= 0.10]
    return {"small_crop_fragments": sorted(small_crop),
            "weeds": sorted(weeds),
            "grass_with_crop_in_it": sorted(mixed)}


def null_masks():
    """Boxes on material A0 calls straw, and where A4 found no plant at all."""
    gm = np.array(Image.open(os.path.join(ROOT, "groundtruth",
                                          "plants_material.png")))
    _, comps = load_components()
    from a4_api import load_a4
    comp = load_a4(tag="merge").components
    rng = np.random.default_rng(NULL_SEED)
    out, tries = [], 0
    H, W = gm.shape
    while len(out) < len(list(NULL_IDS)) and tries < 200000:
        tries += 1
        y = int(rng.integers(0, H - NULL_BOX))
        x = int(rng.integers(0, W - NULL_BOX))
        sub_m = gm[y:y + NULL_BOX, x:x + NULL_BOX]
        sub_c = comp[y:y + NULL_BOX, x:x + NULL_BOX]
        if (sub_m == GT_STRAW).all() and (sub_c == 0).all():
            m = np.zeros(gm.shape, bool)
            m[y:y + NULL_BOX, x:x + NULL_BOX] = True
            if any((m & o).any() for o in out):
                continue
            out.append(m)
    return out


def run(variant="r2", reps=3, workers=8):
    _, comps = load_components()
    hs = hard_set(comps)
    ids = sorted(set(sum(hs.values(), [])))
    R = Renderer()
    rdir = os.path.join(HERE, "renders", "hard")
    jobs = []          # (key, png_path, cid, condition, rep)

    for name, pad in PADS.items():
        for cid in ids:
            p = R.render_instance(cid, rdir, pad_fraction=pad, tag=f"_{name}")
            n = reps if name == "p000" else 1
            for rep in range(1, n + 1):
                jobs.append((f"H_{name}_{variant}_r{rep}_c{cid:03d}", p, cid,
                             name, rep))

    # Nulls get their own rep count. They are the cheapest probe in the chunk
    # (6 regions) and the only one whose *rate* is the measurement, so they are
    # the last place to economise on repeats.
    nulls = null_masks()
    for i, m in zip(NULL_IDS, nulls):
        p = R.render_synthetic(m, i, rdir, tag="_null")
        for rep in range(1, NULL_REPS + 1):
            jobs.append((f"H_null_{variant}_r{rep}_c{i:03d}", p, i, "null", rep))

    def one(j):
        key, png, cid, cond, rep = j
        files = vlm.stage([png])
        txt, rec = vlm.call(P.prompt_A(cid, variant, files), key)
        try:
            obj = S.validate_label(S.extract_json(txt), expect_id=cid)
        except S.R3Violation as e:
            obj = S.fallback(cid, f"R3 violation: {e}"); obj["r3_violation"] = str(e)
        except Exception as e:
            obj = S.fallback(cid, f"unparseable reply: {e}")
        obj.update(condition=cond, rep=rep, raw=txt)
        return obj

    with ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(one, jobs))

    out = {"variant": variant, "model": vlm.MODEL,
           "cli_version": vlm.cli_version(), "reps": reps,
           "hard_set": hs, "n_hard": len(ids),
           "null_ids": list(NULL_IDS), "null_box_label_px": NULL_BOX,
           "null_seed": NULL_SEED, "pads": PADS,
           "shipped_pad": 0.75,
           "labels": res}
    p = os.path.join(RES, f"hard_{variant}.json")
    json.dump(out, open(p, "w"), indent=1)
    print(f"{len(res)} hard-case calls -> {p}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="r2")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    if a.dry:
        _, comps = load_components()
        hs = hard_set(comps)
        print({k: len(v) for k, v in hs.items()},
              "total", len(set(sum(hs.values(), []))))
        print("nulls found:", len(null_masks()))
    else:
        run(a.variant, a.reps, a.workers)
