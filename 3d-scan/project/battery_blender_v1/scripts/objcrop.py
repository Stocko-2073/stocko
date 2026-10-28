"""objcrop.py rid [pad] -- crop full-res image around the object mask, upright; prints crop origin"""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from common import *
rid = sys.argv[1]; pad = int(sys.argv[2]) if len(sys.argv) > 2 else 80
m = cv2.imread(os.path.join(OUT, 'masks', rid + '.png'), 0)
ys, xs = np.nonzero(m); x0, x1, y0, y1 = xs.min() * 2 - pad, xs.max() * 2 + pad, ys.min() * 2 - pad, ys.max() * 2 + pad
im = load_image(rid); x0, y0 = max(0, x0), max(0, y0); c = im[y0:y1, x0:x1]
rot = load_meta(rid)['image']['upright_rotation_cw_deg']
if rot == 270: c = cv2.rotate(c, cv2.ROTATE_90_COUNTERCLOCKWISE)
elif rot == 90: c = cv2.rotate(c, cv2.ROTATE_90_CLOCKWISE)
out = f'/private/tmp/claude-503/-Users-samw3-prj-Make-stocko-3d-scan/9c5addd6-b839-4e81-8b71-1b263a1b3d27/scratchpad/o_{rid}.jpg'
cv2.imwrite(out, c, [cv2.IMWRITE_JPEG_QUALITY, 88]); print(out, 'origin', x0, y0, 'size', c.shape[1], c.shape[0])
