"""Prepare per-view camera data (battery frame) + undistorted photos for Blender overlay renders.

usage: prep_views.py [scale] [rid ...]
Writes out/views.json: {rid: {K, R_cam_to_batt (opencv), t, w, h}} and out/undist/<rid>.jpg
"""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from common import *
from joint_carve import pose_mat, cams

scale = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
rids = sys.argv[2:] or list(cams)
poses = {k: np.array(v) for k, v in json.load(open(os.path.join(OUT, 'poses.json'))).items()}
os.makedirs(os.path.join(OUT, 'undist'), exist_ok=True)
views = {}
vpath = os.path.join(OUT, 'views.json')
if os.path.exists(vpath): views = json.load(open(vpath))
for rid in rids:
    cam = cams[rid]
    pl = next(p for p, v in PLACEMENTS.items() if rid in v)
    Tbm = pose_mat(poses[pl])                    # battery -> mat
    Tcm = np.array(cam['camera_to_mat'])         # camera -> mat
    Tcb = np.linalg.inv(Tbm) @ Tcm               # camera -> battery
    K = np.array(cam['K'])
    w, h = int(round(4032 * scale)), int(round(3024 * scale))
    Ks = K.copy(); Ks[:2] *= scale; Ks[0, 2] = (K[0, 2] + 0.5) * scale - 0.5; Ks[1, 2] = (K[1, 2] + 0.5) * scale - 0.5
    img = load_image(rid)
    k1, k2 = cam['dist']
    und = cv2.undistort(img, K, np.array([k1, k2, 0, 0, 0]), None, K)
    und = cv2.resize(und, (w, h), interpolation=cv2.INTER_AREA)
    cv2.imwrite(os.path.join(OUT, 'undist', rid + '.jpg'), und, [cv2.IMWRITE_JPEG_QUALITY, 92])
    views[rid] = dict(K=Ks.tolist(), R=Tcb[:3, :3].tolist(), t=Tcb[:3, 3].tolist(), w=w, h=h,
                      mat_to_batt=np.linalg.inv(Tbm).tolist(),
                      upright=load_meta(rid)['image']['upright_rotation_cw_deg'], placement=pl)
json.dump(views, open(vpath, 'w'), indent=1)
print('views', len(views))
