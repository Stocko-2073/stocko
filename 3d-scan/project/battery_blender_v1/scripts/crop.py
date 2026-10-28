"""crop.py rid x0 y0 x1 y1 [out] -- crop full-res (sensor grid) image, rotate upright, save."""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from common import *
rid = sys.argv[1]
im = load_image(rid)
x0, y0, x1, y1 = map(int, sys.argv[2:6])
c = im[y0:y1, x0:x1]
rot = load_meta(rid)['image']['upright_rotation_cw_deg']
if rot == 90: c = cv2.rotate(c, cv2.ROTATE_90_CLOCKWISE)
elif rot == 270: c = cv2.rotate(c, cv2.ROTATE_90_COUNTERCLOCKWISE)
elif rot == 180: c = cv2.rotate(c, cv2.ROTATE_180)
out = sys.argv[6] if len(sys.argv) > 6 else '/private/tmp/claude-503/-Users-samw3-prj-Make-stocko-3d-scan/9c5addd6-b839-4e81-8b71-1b263a1b3d27/scratchpad/crop.jpg'
cv2.imwrite(out, c, [cv2.IMWRITE_JPEG_QUALITY, 90])
print(out, c.shape)
