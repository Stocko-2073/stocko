"""Segment the (black) battery from the white mat in every capture.

Mask = largest dark blob inside the white paper interior, holes filled.  Saved at
half resolution as out/masks/<rid>.png, plus a debug overlay.
"""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from common import *

cams = json.load(open(os.path.join(OUT, 'cams.json')))
os.makedirs(os.path.join(OUT, 'masks'), exist_ok=True)
os.makedirs(os.path.join(OUT, 'masks_dbg'), exist_ok=True)
S = 0.5


def project_pts(cam, X):
    K = np.array(cam['K']); T = np.linalg.inv(np.array(cam['camera_to_mat']))
    Xc = X @ T[:3, :3].T + T[:3, 3]
    x = Xc[:, :2] / Xc[:, 2:3]
    k1, k2 = cam['dist']; r2 = (x ** 2).sum(1, keepdims=True); x = x * (1 + k1 * r2 + k2 * r2 * r2)
    return np.c_[K[0, 0] * x[:, 0] + K[0, 2], K[1, 1] * x[:, 1] + K[1, 2]]


def segment(rid, thresh=None):
    cam = cams[rid]
    img = load_image(rid)
    small = cv2.resize(img, None, fx=S, fy=S, interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    v = hsv[..., 2].astype(np.float32)
    # interior of the marker ring (a bit inset), as a polygon in the image
    ring = np.array([[-87, -119, 0], [87, -119, 0], [87, 119, 0], [-87, 119, 0]], float)
    poly = (project_pts(cam, ring) + 0.5) * S - 0.5
    roi = np.zeros(v.shape, np.uint8); cv2.fillPoly(roi, [poly.astype(np.int32)], 1)
    # normalise illumination: paper brightness estimated by a big morphological close
    # paper brightness = local max over a window larger than the battery (quarter res for speed)
    vq = cv2.resize(v * roi, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    pq = cv2.dilate(vq, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (121, 121)))
    pq = cv2.GaussianBlur(pq, (0, 0), 15)
    paper = cv2.resize(pq, (v.shape[1], v.shape[0]), interpolation=cv2.INTER_LINEAR)
    rel = v / np.maximum(paper, 1)
    if thresh is None: thresh = 0.65
    dark = ((rel < thresh) & (roi > 0)).astype(np.uint8)
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(dark)
    if n < 2: return None, small, rel
    big = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    m = (lab == big).astype(np.uint8)
    # fill holes
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    filled = np.zeros_like(m); cv2.drawContours(filled, cnts, -1, 1, -1)
    return filled, small, rel


if __name__ == '__main__':
    rids = sys.argv[1:] or list(cams)
    for rid in rids:
        m, small, rel = segment(rid)
        cv2.imwrite(os.path.join(OUT, 'masks', rid + '.png'), m * 255)
        dbg = small.copy()
        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(dbg, cnts, -1, (0, 0, 255), 2)
        cv2.imwrite(os.path.join(OUT, 'masks_dbg', rid + '.jpg'), dbg)
        print(rid, int(m.sum()))
