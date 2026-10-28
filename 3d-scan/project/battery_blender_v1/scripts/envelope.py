"""Fast silhouette model of the battery's main volumes, for fitting dimensions and poses.

The envelope is a union of convex pieces (chamfered housing, latch block, tongue base and
plate, two feet), each built from half-spaces.  Silhouettes are rasterised per view with
cv2.fillPoly on projected convex hulls, so a full 39-view evaluation takes ~0.1 s.

Cost per view: model silhouette contour should sit on strong photo edges (chamfer distance
to Canny edges, capped) + a mask XOR term with the photo silhouette.
"""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from common import *
from joint_carve import pose_mat, cams
from segment import project_pts
from scipy.spatial import ConvexHull, HalfspaceIntersection
from scipy.spatial.transform import Rotation as Rot

QS = 0.25  # quarter resolution

DEFAULT = dict(
    x_back=-59.5, x_front=53.5, half_w=37.5, deck_z=30.0, bot_ch=2.5, side_top_ch=5.0,
    front_top_ch=4.0, back_top_ch=4.0, corner_ch_back=8.0, corner_ch_front=4.5,
    lb_x1=-31.0, lb_hw=27.0, lb_z1=46.5, lb_back_ch=6.0, lb_side_ch=4.0,
    t_x1=35.0, t_plate_x1=29.0, t_plate_hw=24.5, t_plate_z1=44.0, t_base_hw=23.5,
    foot_y0=13.5, foot_y1=29.0, foot_x1=60.5, foot_top_back=29.0, foot_top_front=26.0,
)


def halfspaces_to_verts(H, interior):
    hs = HalfspaceIntersection(np.asarray(H, float), np.asarray(interior, float))
    return hs.intersections


def hs_box(x0, x1, y0, y1, z0, z1):
    return [[-1, 0, 0, x0], [1, 0, 0, -x1], [0, -1, 0, y0], [0, 1, 0, -y1], [0, 0, -1, z0], [0, 0, 1, -z1]]


def hs_chamfer(ay, az, py, pz):
    """half-space cutting the edge: keep points with ay*y + az*z <= ay*py + az*pz (normal (0, ay, az))"""
    n = np.array([ay, az]); n = n / np.linalg.norm(n)
    return n, n[0] * py + n[1] * pz


def plane(nx, ny, nz, px, py, pz):
    n = np.array([nx, ny, nz], float); n /= np.linalg.norm(n)
    return [n[0], n[1], n[2], -(n @ np.array([px, py, pz]))]


def pieces(p):
    """list of vertex arrays (convex pieces) in the battery frame"""
    out = []
    xb, xf, hw, zt = p['x_back'], p['x_front'], p['half_w'], p['deck_z']
    b, s, f, k, cb, cf = p['bot_ch'], p['side_top_ch'], p['front_top_ch'], p['back_top_ch'], p['corner_ch_back'], p['corner_ch_front']
    H = hs_box(xb, xf, -hw, hw, 0, zt)
    for sy in (1, -1):
        H.append(plane(0, sy, -1, 0, sy * (hw - b), 0))            # bottom long edges
        H.append(plane(0, sy, 1, 0, sy * hw, zt - s))              # top long edges
        H.append(plane(-1, sy, 0, xb + cb, sy * hw, 0))            # back vertical corners
        H.append(plane(1, sy, 0, xf - cf, sy * hw, 0))             # front vertical corners
    H.append(plane(-1, 0, -1, xb + b, 0, 0)); H.append(plane(1, 0, -1, xf - b, 0, 0))
    H.append(plane(-1, 0, 1, xb, 0, zt - k)); H.append(plane(1, 0, 1, xf, 0, zt - f))
    out.append(halfspaces_to_verts(H, [0, 0, zt / 2]))
    # latch block
    x1, lhw, lz, bc, sc = p['lb_x1'], p['lb_hw'], p['lb_z1'], p['lb_back_ch'], p['lb_side_ch']
    H = hs_box(xb, x1, -lhw, lhw, zt - 1, lz)
    for sy in (1, -1): H.append(plane(0, sy, 1, 0, sy * lhw, lz - sc))
    H.append(plane(-1, 0, 1, xb, 0, lz - bc))
    out.append(halfspaces_to_verts(H, [(xb + x1) / 2, 0, (zt + lz) / 2]))
    # tongue base (to the shelf front) and plate
    out.append(halfspaces_to_verts(hs_box(x1, p['t_x1'], -p['t_base_hw'], p['t_base_hw'], zt - 1, 40.5), [(x1 + p['t_x1']) / 2, 0, zt + 3]))
    out.append(halfspaces_to_verts(hs_box(x1, p['t_plate_x1'], -p['t_plate_hw'], p['t_plate_hw'], 40.4, p['t_plate_z1']),
                                   [(x1 + p['t_plate_x1']) / 2, 0, 42]))
    # feet
    for sy in (1, -1):
        y0, y1 = sorted((sy * p['foot_y0'], sy * p['foot_y1']))
        fx0 = xf - 4
        H = hs_box(fx0, p['foot_x1'], y0, y1, 0, p['foot_top_back'])
        H.append(plane(p['foot_top_back'] - p['foot_top_front'], 0, p['foot_x1'] - fx0, fx0, 0, p['foot_top_back']))
        H.append(plane(1, 0, -1, p['foot_x1'] - 2, 0, 0))
        out.append(halfspaces_to_verts(H, [(fx0 + p['foot_x1']) / 2, (y0 + y1) / 2, 5]))
    return out


def silhouette(verts_list, rid, T_bm, shape):
    img = np.zeros(shape, np.uint8)
    cam = cams[rid]
    for V in verts_list:
        Xm = V @ T_bm[:3, :3].T + T_bm[:3, 3]
        uv = (project_pts(cam, Xm) + 0.5) * QS - 0.5
        hull = ConvexHull(uv)
        poly = np.round(uv[hull.vertices] * 8).astype(np.int32)
        cv2.fillPoly(img, [poly], 1, shift=3)
    return img


class Data:
    def __init__(self, rids):
        self.rids = rids; self.mask = {}; self.edt = {}; self.pcont = {}
        for rid in rids:
            m = cv2.imread(os.path.join(OUT, 'masks', rid + '.png'), 0)
            m = cv2.resize(m, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA) > 127
            self.mask[rid] = m
            img = cv2.resize(load_image(rid), None, fx=QS, fy=QS, interpolation=cv2.INTER_AREA)
            g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (3, 3), 0)
            e = cv2.Canny(g, 40, 100)
            # only edges near the photo silhouette matter
            near = cv2.dilate(m.astype(np.uint8), np.ones((25, 25), np.uint8)) > 0
            e[~near] = 0
            self.edt[rid] = cv2.distanceTransform((e == 0).astype(np.uint8), cv2.DIST_L2, 3)
            cn, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            self.pcont[rid] = np.concatenate([k.reshape(-1, 2) for k in cn])


def view_cost(sil, rid, D, cap=6.0):
    cnts, _ = cv2.findContours(sil, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts: return 1e3
    c = np.concatenate([k.reshape(-1, 2) for k in cnts])
    # model contour -> nearest strong photo edge
    d1 = np.minimum(D.edt[rid][c[:, 1], c[:, 0]], cap).mean()
    # photo silhouette contour -> model contour (capped, so shadow stretches stop pulling)
    edge = np.zeros(sil.shape, np.uint8); edge[c[:, 1], c[:, 0]] = 1
    dt = cv2.distanceTransform(1 - edge, cv2.DIST_L2, 3)
    pc = D.pcont[rid]
    d2 = np.minimum(dt[pc[:, 1], pc[:, 0]], cap).mean()
    return d1 + d2


def rest_penalty(V, T):
    """the battery lies on the mat: its lowest point must be at z = 0"""
    z = min((Vi @ T[:3, :3].T + T[:3, 3])[:, 2].min() for Vi in V)
    return (z / 0.5) ** 2


def total_cost(p, poses, D, rids=None, detail=False):
    V = pieces(p)
    costs = {}
    rids = rids or D.rids
    for rid in rids:
        pl = next(k for k, v in PLACEMENTS.items() if rid in v)
        sil = silhouette(V, rid, pose_mat(poses[pl]), D.mask[rid].shape)
        costs[rid] = view_cost(sil, rid, D)
    if detail: return costs
    pls = {next(k for k, v in PLACEMENTS.items() if r in v) for r in rids}
    rest = sum(rest_penalty(V, pose_mat(poses[pl])) for pl in pls if pl != 'A')
    return float(np.mean(list(costs.values()))) + 0.1 * rest
