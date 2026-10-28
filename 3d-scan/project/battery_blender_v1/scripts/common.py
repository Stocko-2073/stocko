"""Shared helpers: load captures, mat layout, camera poses."""
import json, glob, os
import numpy as np
import cv2

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
CAP = os.path.join(ROOT, 'captures')
PROJ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
OUT = os.path.join(PROJ, 'out')

# Which placement of the battery each capture shows (worked out from capture times:
# the phone took some angled shots before the battery had been moved).
PLACEMENTS = {
    'A': ['r0069', 'r0070', 'r0071', 'r0072', 'r0073', 'r0074', 'r0075', 'r0076', 'r0077',
          'r0078', 'r0079', 'r0080', 'r0081', 'r0082', 'r0083', 'r0084', 'r0085', 'r0087',
          'r0088', 'r0089', 'r0091', 'r0092', 'r0093', 'r0095', 'r0096', 'r0097'],
    'B1': ['r0086'],
    'C1': ['r0090'],
    'D1': ['r0094'],
    'B2': ['r0098', 'r0099', 'r0100', 'r0101'],
    'C2': ['r0102', 'r0103', 'r0104'],
    'D2': ['r0106', 'r0107', 'r0108', 'r0109'],
}


def capdir(rid):
    return glob.glob(os.path.join(CAP, rid, '*'))[0]


def load_meta(rid):
    return json.load(open(os.path.join(capdir(rid), 'meta.json')))


def load_image(rid):
    return cv2.imread(os.path.join(capdir(rid), 'image.jpg'))


def mat_layout():
    return json.load(open(os.path.join(CAP, 'mat_layout.json')))


def marker_corners_3d():
    lay = mat_layout()
    return {m['id']: np.array([[c[0], c[1], 0.0] for c in m['corners']]) for m in lay['markers']}
