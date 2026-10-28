"""Score the Blender model against every photo.

For each view: silhouette IoU against the photo mask (the mask includes cast shadows, so this is
a lower bound), and the distance from each point of the model's rendered outline to the nearest
strong edge in the photo, converted to mm at the battery's depth.  Writes out/eval.json.
"""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from common import *
from joint_carve import cams

views = json.load(open(os.path.join(OUT, 'views.json')))
res = {}
for rid, v in views.items():
    rend = cv2.imread(os.path.join(OUT, 'render', rid + '.png'), cv2.IMREAD_UNCHANGED)
    a = rend[..., 3] > 127
    photo = cv2.imread(os.path.join(OUT, 'undist', rid + '.jpg'))
    g = cv2.GaussianBlur(cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    edges = cv2.Canny(g, 30, 80) > 0
    dt = cv2.distanceTransform((~edges).astype(np.uint8), cv2.DIST_L2, 3)
    cnts, _ = cv2.findContours(a.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = np.concatenate([k.reshape(-1, 2) for k in cnts])
    # skip outline points on the image border
    ok = (c[:, 0] > 2) & (c[:, 1] > 2) & (c[:, 0] < a.shape[1] - 3) & (c[:, 1] < a.shape[0] - 3)
    d_px = dt[c[ok, 1], c[ok, 0]]
    depth = np.linalg.norm(np.array(v['t']))            # camera distance to the battery origin (mm)
    mm_per_px = depth / v['K'][0][0]
    d_mm = np.minimum(d_px * mm_per_px, 5.0)
    cam = cams[rid]; K = np.array(cam['K'])
    m = cv2.imread(os.path.join(OUT, 'masks', rid + '.png'), 0)
    mf = cv2.resize(m, (4032, 3024), interpolation=cv2.INTER_NEAREST)
    mu = cv2.undistort(mf, K, np.array([cam['dist'][0], cam['dist'][1], 0, 0, 0]), None, K)
    mu = cv2.resize(mu, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_NEAREST) > 127
    iou = (mu & a).sum() / max(1, (mu | a).sum())
    res[rid] = dict(placement=v['placement'], iou=float(iou), edge_med_mm=float(np.median(d_mm)),
                    edge_p90_mm=float(np.percentile(d_mm, 90)), within_1mm=float((d_mm <= 1.0).mean()))
json.dump(res, open(os.path.join(OUT, 'eval.json'), 'w'), indent=1)
print('%-6s %-3s %6s %9s %9s %9s' % ('view', 'pl', 'IoU', 'edge med', 'edge p90', '<=1mm'))
for rid, r in res.items():
    print('%-6s %-3s %6.3f %8.2fmm %8.2fmm %8.0f%%' % (rid, r['placement'], r['iou'], r['edge_med_mm'], r['edge_p90_mm'], 100 * r['within_1mm']))
allm = np.array([r['edge_med_mm'] for r in res.values()]); allw = np.array([r['within_1mm'] for r in res.values()])
print('ALL views: median outline-to-edge %.2f mm, mean share of outline within 1 mm %.0f%%, mean IoU %.3f'
      % (np.median(allm), 100 * allw.mean(), np.mean([r['iou'] for r in res.values()])))
