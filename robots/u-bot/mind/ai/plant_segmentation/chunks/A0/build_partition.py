"""A0 step 2 — turn overlapping SAM proposals into a non-overlapping region map.

Paint proposals largest-area-first so the finest mask covering a pixel wins.
Pixels no proposal covers, and fragments below MIN_REGION px, are folded into
the nearest labelled region so the partition is a true cover. Region identity
carries no class; classes are assigned by visual review in classify.py.
"""
import json
import os

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "work")
MIN_REGION = 25  # px on the 768x1024 grid; below this a fragment is not
                 # independently reviewable, so it is merged into a neighbour.


def load_masks():
    shape = tuple(np.load(os.path.join(OUT, "sam_masks_shape.npy")))
    packed = np.load(os.path.join(OUT, "sam_masks.npy"))
    return np.unpackbits(packed, axis=-1)[:, :, : shape[2]].astype(bool)


def main():
    masks = load_masks()
    meta = json.load(open(os.path.join(OUT, "sam_meta.json")))
    n, h, w = masks.shape
    order = np.argsort([-m["area"] for m in meta])  # large first, small paints over
    lab = np.zeros((h, w), np.int32)
    for rank, i in enumerate(order, start=1):
        lab[masks[i]] = rank

    # split disconnected pieces of the same id
    out = np.zeros((h, w), np.int32)
    nxt = 1
    for v in np.unique(lab):
        m = lab == v
        cc, k = ndimage.label(m)
        for j in range(1, k + 1):
            out[cc == j] = nxt
            nxt += 1

    # fold tiny regions / uncovered pixels into nearest surviving region
    sizes = np.bincount(out.ravel())
    keep = np.zeros(nxt, bool)
    keep[np.where(sizes >= MIN_REGION)[0]] = True
    keep[0] = False
    good = keep[out]
    _, (iy, ix) = ndimage.distance_transform_edt(~good, return_indices=True)
    filled = out[iy, ix]

    ids = np.unique(filled)
    remap = np.zeros(filled.max() + 1, np.int32)
    remap[ids] = np.arange(1, len(ids) + 1)
    filled = remap[filled]
    np.save(os.path.join(OUT, "regions.npy"), filled)

    sz = np.bincount(filled.ravel())[1:]
    print(f"{len(ids)} regions; area min/med/max = {sz.min()}/{int(np.median(sz))}/{sz.max()}")
    print(f"top-50 regions cover {100*np.sort(sz)[::-1][:50].sum()/sz.sum():.1f}% of pixels")
    print(f"top-150 regions cover {100*np.sort(sz)[::-1][:150].sum()/sz.sum():.1f}%")


if __name__ == "__main__":
    main()
