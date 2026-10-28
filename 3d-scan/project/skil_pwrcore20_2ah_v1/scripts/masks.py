"""Where each capture certainly sees bare paper, for carving the visual hull.

Carving is only as good as its "not battery" evidence, so this marks open paper (bright,
inside the mat, off the markers, connected to the big inner field) and leaves everything
else (battery, markers, desk, highlights enclosed by the battery) as "maybe battery".
Contact shadows stay "maybe", which inflates the hull slightly at the base.

Usage: masks.py r0070 r0071 ...   -> out/mask/<req>.png (255 = maybe battery)
"""
import sys

import cv2
import numpy as np

from ac import OUT, Capture

RING_IN = (88.75 - 1.0, 120.0 - 1.0)      # inner edge of the marker ring, less a margin (mm)


def not_paper(c: Capture) -> tuple[np.ndarray, float]:
    v = cv2.cvtColor(c.image, cv2.COLOR_BGR2HSV)[..., 2]
    field = np.zeros(v.shape, np.uint8)
    w, h = RING_IN
    poly = c.project(np.array([[-w, -h, 0], [w, -h, 0], [w, h, 0], [-w, h, 0]]))
    cv2.fillPoly(field, [np.round(poly).astype(np.int32)], 255)
    _, corners = c.detections()
    for q in corners:
        ctr = q.mean(0)
        cv2.fillPoly(field, [np.round(ctr + 1.25 * (q - ctr)).astype(np.int32)], 0)
    roi = v[field > 0]
    thr, _ = cv2.threshold(roi.reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bright = ((v >= thr) & (field > 0)).astype(np.uint8)
    bright = cv2.morphologyEx(bright, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(bright, 4)
    if n <= 1:
        return np.full(v.shape, 255, np.uint8), thr
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    paper = lab == big
    # Keep a 2 px safety band: edge pixels are mixed.
    paper = cv2.erode(paper.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    return np.where(paper, 0, 255).astype(np.uint8), thr


if __name__ == "__main__":
    (OUT / "mask").mkdir(parents=True, exist_ok=True)
    for r in sys.argv[1:]:
        c = Capture(r)
        m, thr = not_paper(c)
        cv2.imwrite(str(OUT / "mask" / f"{r}.png"), m)
        print(r, "otsu thr", int(thr))
