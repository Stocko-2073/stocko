"""A0 step 4 — a crude first *proposal* of a class per region.

This is NOT ground truth. It exists only so the review overlay starts from
something better than a blank canvas; every region is then looked at by eye at
4x zoom and corrected in `corrections.py`. The heuristic below is deliberately
simple and is documented so it is obvious it encodes no scene knowledge.

Writes work/proposal.npy (per-region class id) and work/region_feats.npz.
"""
import os

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "work")

CLASSES = ["unlabelled", "squash_leaf", "squash_petiole", "grass",
           "broadleaf_weed", "straw", "soil", "fruit", "other"]
CID = {c: i for i, c in enumerate(CLASSES)}


def main():
    rgb = np.asarray(Image.open(os.path.join(OUT, "rgb_gtgrid.png")).convert("RGB"), float)
    lab = np.load(os.path.join(OUT, "regions.npy"))
    n = lab.max()
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    s = np.maximum(R + G + B, 1)
    exg = 2 * (G / s) - (R / s) - (B / s)     # excess green, chromaticity-normalised
    val = rgb.max(-1)
    sat = (rgb.max(-1) - rgb.min(-1)) / np.maximum(rgb.max(-1), 1)

    idx = np.arange(1, n + 1)
    area = np.bincount(lab.ravel(), minlength=n + 1)[1:]
    m_exg = ndimage.mean(exg, lab, idx)
    m_val = ndimage.mean(val, lab, idx)
    m_sat = ndimage.mean(sat, lab, idx)
    m_r = ndimage.mean(R, lab, idx)
    m_g = ndimage.mean(G, lab, idx)
    m_b = ndimage.mean(B, lab, idx)

    elong = np.zeros(n)
    fill = np.zeros(n)
    cy = np.zeros(n); cx = np.zeros(n)
    objs = ndimage.find_objects(lab)
    for i, sl in enumerate(objs):
        if sl is None:
            continue
        m = lab[sl] == i + 1
        ys, xs = np.nonzero(m)
        cy[i] = ys.mean() + sl[0].start
        cx[i] = xs.mean() + sl[1].start
        p = np.stack([ys - ys.mean(), xs - xs.mean()])
        ev = np.linalg.eigvalsh(np.cov(p) + np.eye(2) * 1e-6)
        elong[i] = np.sqrt(max(ev[1], 1e-6) / max(ev[0], 1e-6))
        fill[i] = m.sum() / m.size

    # Rules chosen after looking at the image, not fitted to anything. They only
    # have to be close enough that the review overlay is quick to correct.
    #  - living foliage is strongly excess-green, or moderately so when sunlit;
    #  - grass blades are long and thin, squash leaf blades are large and blobby;
    #  - everything else here is dry plant litter (straw), which is the mulch.
    prop = np.zeros(n, np.uint8)
    green = (m_exg > 0.22) | ((m_exg > 0.12) & (m_val > 105))
    for i in range(n):
        if green[i]:
            if elong[i] > 3.5:
                prop[i] = CID["grass"]
            elif area[i] > 1500:
                prop[i] = CID["squash_leaf"]
            else:
                prop[i] = CID["grass"] if elong[i] > 2.2 else CID["squash_leaf"]
        else:
            prop[i] = CID["straw"]

    np.save(os.path.join(OUT, "proposal.npy"), prop)
    np.savez(os.path.join(OUT, "region_feats.npz"), area=area, exg=m_exg, val=m_val,
             sat=m_sat, r=m_r, g=m_g, b=m_b, elong=elong, fill=fill, cy=cy, cx=cx)
    for c in CLASSES:
        k = (prop == CID[c])
        print(f"{c:16s} regions={k.sum():4d} px%={100*area[k].sum()/area.sum():5.1f}")


if __name__ == "__main__":
    main()
