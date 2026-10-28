"""dbg_sheet.py out.jpg rid... -- montage of mask debug overlays cropped around the object."""
import sys
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from common import *
out = sys.argv[1]; tiles = []
for rid in sys.argv[2:]:
    d = cv2.imread(os.path.join(OUT, 'masks_dbg', rid + '.jpg'))
    m = cv2.imread(os.path.join(OUT, 'masks', rid + '.png'), 0)
    ys, xs = np.nonzero(m)
    if len(xs) == 0: x0, y0, x1, y1 = 0, 0, d.shape[1], d.shape[0]
    else: x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    pad = 120; x0 = max(0, x0 - pad); y0 = max(0, y0 - pad); x1 = min(d.shape[1], x1 + pad); y1 = min(d.shape[0], y1 + pad)
    t = d[y0:y1, x0:x1]; sc = 600 / max(t.shape[:2]); t = cv2.resize(t, None, fx=sc, fy=sc)
    canvas = np.full((600, 600, 3), 255, np.uint8); canvas[:t.shape[0], :t.shape[1]] = t
    cv2.putText(canvas, rid, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 200, 255), 2)
    tiles.append(canvas)
rows = [np.hstack(tiles[i:i + 4] + [np.full((600, 600, 3), 255, np.uint8)] * (4 - len(tiles[i:i + 4]))) for i in range(0, len(tiles), 4)]
cv2.imwrite(out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
