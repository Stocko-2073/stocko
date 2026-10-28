"""Overlay model renders on the undistorted photos.

usage: overlay.py out.jpg rid [rid ...] [--full] [--tile N]
Silhouette in yellow, internal shading edges in cyan; cropped to the object, upright.
Also prints silhouette IoU against the photo mask.
"""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from common import *

args = [a for a in sys.argv[1:] if not a.startswith('--')]
opts = [a for a in sys.argv[1:] if a.startswith('--')]
out = args[0]; rids = args[1:]
TILE = 900
for o in opts:
    if o.startswith('--tile='): TILE = int(o.split('=')[1])
sub = 'render'
for o in opts:
    if o.startswith('--sub='): sub = o.split('=')[1]
views = json.load(open(os.path.join(OUT, 'views.json')))


def overlay(rid):
    photo = cv2.imread(os.path.join(OUT, 'undist', rid + '.jpg'))
    rend = cv2.imread(os.path.join(OUT, sub, rid + '.png'), cv2.IMREAD_UNCHANGED)
    a = rend[..., 3] > 127
    g = cv2.cvtColor(rend[..., :3], cv2.COLOR_BGR2GRAY)
    e = cv2.Canny(g, 12, 30) > 0
    e &= cv2.erode(a.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    sil = a.astype(np.uint8)
    edge_s = (cv2.dilate(sil, np.ones((3, 3), np.uint8)) - sil) > 0
    img = photo.copy()
    img[e] = (255, 255, 0)
    img[edge_s] = (0, 255, 255)
    # IoU with the photo mask (mask lives in the distorted grid; undistort it the same way)
    m = cv2.imread(os.path.join(OUT, 'masks', rid + '.png'), 0)
    iou = None
    if m is not None:
        from joint_carve import cams
        cam = cams[rid]; K = np.array(cam['K'])
        mf = cv2.resize(m, (4032, 3024), interpolation=cv2.INTER_NEAREST)
        mu = cv2.undistort(mf, K, np.array([cam['dist'][0], cam['dist'][1], 0, 0, 0]), None, K)
        mu = cv2.resize(mu, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_NEAREST) > 127
        iou = (mu & a).sum() / max(1, (mu | a).sum())
    ys, xs = np.nonzero(a | (m is not None and False))
    pad = 60
    x0, x1, y0, y1 = max(0, xs.min() - pad), min(a.shape[1], xs.max() + pad), max(0, ys.min() - pad), min(a.shape[0], ys.max() + pad)
    c = img[y0:y1, x0:x1]
    rot = views[rid]['upright']
    if rot == 270: c = cv2.rotate(c, cv2.ROTATE_90_COUNTERCLOCKWISE)
    elif rot == 90: c = cv2.rotate(c, cv2.ROTATE_90_CLOCKWISE)
    sc = TILE / max(c.shape[:2]); c = cv2.resize(c, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
    canvas = np.full((TILE, TILE, 3), 255, np.uint8); canvas[:c.shape[0], :c.shape[1]] = c
    cv2.putText(canvas, '%s IoU %.3f' % (rid, iou if iou is not None else -1), (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
    return canvas, iou


tiles = []
for rid in rids:
    t, iou = overlay(rid); tiles.append(t)
    print(rid, 'IoU %.4f' % iou if iou is not None else '')
cols = 2 if len(tiles) > 1 else 1
rows = []
for i in range(0, len(tiles), cols):
    r = tiles[i:i + cols]
    while len(r) < cols: r.append(np.full_like(tiles[0], 255))
    rows.append(np.hstack(r))
cv2.imwrite(out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])
