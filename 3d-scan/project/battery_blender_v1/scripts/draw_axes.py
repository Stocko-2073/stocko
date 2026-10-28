"""Draw the fitted battery frame (X red = front, Y green, Z blue = top) on views."""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from joint_carve import *
poses = json.load(open(os.path.join(OUT, sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith('.json') else 'poses.json')))
rids = [a for a in sys.argv[1:] if a.startswith('r')]
tiles = []
for rid in rids:
    pl = next(p for p, v in PLACEMENTS.items() if rid in v)
    T = pose_mat(np.array(poses[pl]))
    pts = np.array([[0, 0, 0], [60, 0, 0], [0, 38, 0], [0, 0, 46], [60, 38, 0], [60, -38, 0], [-60, 38, 0], [-60, -38, 0]], float)
    Xm = pts @ T[:3, :3].T + T[:3, 3]
    uv = project_pts(cams[rid], Xm)
    img = load_image(rid)
    o = tuple(uv[0].astype(int))
    for k, col in ((1, (0, 0, 255)), (2, (0, 255, 0)), (3, (255, 0, 0))):
        cv2.arrowedLine(img, o, tuple(uv[k].astype(int)), col, 12, tipLength=0.15)
    box = uv[[4, 5, 7, 6]].astype(np.int32)
    cv2.polylines(img, [box], True, (0, 255, 255), 6)
    rot = load_meta(rid)['image']['upright_rotation_cw_deg']
    if rot == 270: img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    elif rot == 90: img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    sc = 700 / max(img.shape[:2]); img = cv2.resize(img, None, fx=sc, fy=sc)
    canvas = np.full((700, 700, 3), 255, np.uint8); canvas[:img.shape[0], :img.shape[1]] = img; img = canvas
    cv2.putText(img, rid + ' ' + pl, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 200, 255), 3)
    tiles.append(img)
h = max(t.shape[0] for t in tiles)
tiles = [cv2.copyMakeBorder(t, 0, h - t.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255)) for t in tiles]
rows = [np.hstack(tiles[i:i + 3]) if len(tiles[i:i + 3]) == 3 else np.hstack(tiles[i:i + 3] + [np.full_like(tiles[0], 255)] * (3 - len(tiles[i:i + 3]))) for i in range(0, len(tiles), 3)]
cv2.imwrite('/private/tmp/claude-503/-Users-samw3-prj-Make-stocko-3d-scan/9c5addd6-b839-4e81-8b71-1b263a1b3d27/scratchpad/axes.jpg', np.vstack(rows))
