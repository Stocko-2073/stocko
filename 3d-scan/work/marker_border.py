#!/usr/bin/env python3
"""Generate a US Letter page whose border is a ring of 10 mm fiducial markers.

The interior is plain white. Two marker families:
  aruco     DICT_4X4_100         6x6 cells incl. black border (1.67 mm cells)
  apriltag  DICT_APRILTAG_36h11  8x8 cells incl. black border (1.25 mm cells);
            same bit patterns as the official tag36h11, so AprilTag's own
            detector reads it as well as cv2.aruco does.

Marker size is the outer edge of the black border (the OpenCV and AprilTag
convention). Markers sit on a 12.5 mm pitch, leaving 2.5 mm of white between
neighbours, and the ring is centred on the page. IDs run clockwise from the
top-left corner.

Page frame: millimetres, origin at the page's top-left corner, x right, y down,
z = 0 on the paper. make_board() returns the layout as a cv2.aruco.Board, and a
JSON file written next to each PDF lists every marker's corners (TL, TR, BR, BL)
in the same frame. Print at 100% / "Actual size".

Usage: python marker_border.py [aruco|apriltag ...]   (default: both)
"""
import json
import sys
import cv2
import numpy as np
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

# ---- Layout parameters ------------------------------------------------------
MARKER_MM = 10.0                      # marker side, outer edge of black border
PITCH_MM = 12.5                       # marker-to-marker spacing (2.5 mm white gap)
MIN_MARGIN_MM = 6.35                  # keep clear of the printer's unprintable edge
BORDER_BITS = 1
FAMILIES = {                          # family -> (dictionary, name, file tag)
    "aruco": (cv2.aruco.DICT_4X4_100, "DICT_4X4_100", "4x4"),
    "apriltag": (cv2.aruco.DICT_APRILTAG_36h11, "DICT_APRILTAG_36h11", "36h11"),
}

PAGE_W_PT, PAGE_H_PT = letter          # 612 x 792 pt = 215.9 x 279.4 mm
PAGE_W_MM, PAGE_H_MM = PAGE_W_PT / mm, PAGE_H_PT / mm


def ring_count(page_mm):
    """Markers that fit along one side of the page."""
    return int((page_mm - 2 * MIN_MARGIN_MM - MARKER_MM) // PITCH_MM) + 1


NX, NY = ring_count(PAGE_W_MM), ring_count(PAGE_H_MM)          # 16 x 21
X0 = (PAGE_W_MM - ((NX - 1) * PITCH_MM + MARKER_MM)) / 2        # 9.2 mm
Y0 = (PAGE_H_MM - ((NY - 1) * PITCH_MM + MARKER_MM)) / 2        # 9.7 mm


def layout():
    """[(id, x_mm, y_mm)] of each marker's top-left corner, clockwise from top-left."""
    cells = ([(i, 0) for i in range(NX)] +                      # top, left -> right
             [(NX - 1, j) for j in range(1, NY)] +              # right, top -> bottom
             [(i, NY - 1) for i in range(NX - 2, -1, -1)] +     # bottom, right -> left
             [(0, j) for j in range(NY - 2, 0, -1)])            # left, bottom -> top
    return [(mid, X0 + i * PITCH_MM, Y0 + j * PITCH_MM) for mid, (i, j) in enumerate(cells)]


def corners(x, y):
    """TL, TR, BR, BL corners of the marker whose top-left corner is (x, y)."""
    return [(x, y), (x + MARKER_MM, y), (x + MARKER_MM, y + MARKER_MM), (x, y + MARKER_MM)]


def make_board(family):
    d = cv2.aruco.getPredefinedDictionary(FAMILIES[family][0])
    lay = layout()
    obj = [np.array([(cx, cy, 0.0) for cx, cy in corners(x, y)], np.float32)
           for _, x, y in lay]
    return cv2.aruco.Board(obj, d, np.array([mid for mid, _, _ in lay], np.int32))


def draw(c, d):
    """All black cells as one path, so viewers show no seams between cells."""
    n = d.markerSize + 2 * BORDER_BITS
    cell = MARKER_MM / n
    p = c.beginPath()
    for mid, x0, y0 in layout():
        bits = d.generateImageMarker(mid, n, BORDER_BITS) > 0   # True = white
        for r in range(n):
            col = 0
            while col < n:              # merge runs of black bits into one rect
                if bits[r, col]:
                    col += 1
                    continue
                start = col
                while col < n and not bits[r, col]:
                    col += 1
                # page mm (y down) -> PDF pt (y up)
                p.rect((x0 + start * cell) * mm, PAGE_H_PT - (y0 + (r + 1) * cell) * mm,
                       (col - start) * cell * mm, cell * mm)
    c.setFillColorRGB(0, 0, 0)
    c.drawPath(p, stroke=0, fill=1, fillMode=canvas.FILL_NON_ZERO)


def write(family):
    dict_id, dict_name, tag = FAMILIES[family]
    d = cv2.aruco.getPredefinedDictionary(dict_id)
    lay = layout()
    if len(lay) > d.bytesList.shape[0]:
        sys.exit(f"{dict_name} has only {d.bytesList.shape[0]} markers, need {len(lay)}")
    out = f"border_letter_{family}_{tag}_{MARKER_MM:g}mm"

    c = canvas.Canvas(out + ".pdf", pagesize=letter)
    c.setTitle(f"{family} border {MARKER_MM:g}mm {dict_name} - US Letter")
    c.setAuthor("marker_border.py")
    draw(c, d)
    c.showPage()
    c.save()

    with open(out + ".json", "w") as f:
        json.dump({
            "dictionary": dict_name,
            "marker_mm": MARKER_MM,
            "pitch_mm": PITCH_MM,
            "page_mm": [round(PAGE_W_MM, 3), round(PAGE_H_MM, 3)],
            "frame": "mm, origin page top-left, x right, y down; corners TL, TR, BR, BL",
            "markers": [{"id": mid, "corners": [[round(cx, 4), round(cy, 4)]
                                                for cx, cy in corners(x, y)]}
                        for mid, x, y in lay],
        }, f, indent=1)
    print(f"wrote {out}.pdf/.json: {dict_name}, {len(lay)} markers ({NX} x {NY} ring), "
          f"{MARKER_MM:g} mm on {PITCH_MM:g} mm pitch, margins {X0:.2f} / {Y0:.2f} mm")


def main():
    for family in sys.argv[1:] or FAMILIES:
        if family not in FAMILIES:
            sys.exit(f"unknown family {family!r}; choose from {', '.join(FAMILIES)}")
        write(family)


if __name__ == "__main__":
    main()
