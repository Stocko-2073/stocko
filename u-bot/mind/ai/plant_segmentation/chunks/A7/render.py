"""A7 — rendering.  The only place image geometry is turned into pixels.

Two products:

* **`render_instance(cid)`** — framing A's stimulus.  One PNG, three panels:
  `CONTEXT` (whole frame, region marked), `MARKED` (a zoomed crop with the
  region outlined and tinted) and `PLAIN` (the identical crop, untouched).  The
  plain panel exists because A3 measured that OVSeg-style crop-and-fill destroys
  the surround; here the surround is kept and the marking is additive, so the
  model can always see the material as it really is.
* **`render_montage()`** — framing B's stimulus.  The frame tiled into a grid,
  every `core` region outlined and stamped with its ID, plus a whole-frame
  overview.  One global look, all IDs at once.

Rendering constants are in `RENDER` below and registered in BOOKKEEPING §2.
No coordinate produced here ever reaches the model as text; IDs are the only
handle it is given (R3).
"""
from __future__ import annotations

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from a7_data import HERE, ROOT, NATIVE_PER_LABEL_PX, load_components

RENDER = dict(
    # Context margin around a region's bounding box, as a fraction of its own
    # larger extent.  Scale-relative, so it encodes no belief about how far
    # apart plants grow (R1).  (c) convention — swept in sweep_margin.py.
    pad_fraction=0.75,
    # A crop smaller than this cannot fill the detail panel without upsampling
    # more than 3x past the sensor.  A property of the render, not the garden.
    min_crop_native=256,
    detail_px=760,      # side of each detail panel in the emitted PNG
    context_px=620,     # width of the context panel
    tile_native=1000,   # montage tile side, native px  (3x4 tiles = the frame)
    tile_px=900,
)

MARK = (255, 0, 255)          # magenta: no plant, soil or straw in this scene
MARK_ALPHA = 0.22
OUTLINE_W = 4                 # native px


def _font(size):
    for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
              "/System/Library/Fonts/Helvetica.ttc"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _boundary(mask):
    """8-connected morphological gradient — the outline of a boolean mask."""
    p = np.pad(mask, 1)
    acc = np.zeros_like(mask, dtype=bool)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            acc |= ~p[dy:dy + mask.shape[0], dx:dx + mask.shape[1]]
    return mask & acc


class Renderer:
    def __init__(self, tag="merge"):
        self.a4, self.comps = load_components(tag)
        self.rgb = Image.open(os.path.join(ROOT, "plants.jpeg")).convert("RGB")
        self.W, self.H = self.rgb.size
        self.comp = self.a4.components                       # 1024 x 768
        # component map lifted to native by nearest neighbour (never the RGB
        # down to the label grid — the detail panels must show real texture)
        gy = (np.arange(self.H) / NATIVE_PER_LABEL_PX).astype(int)
        gx = (np.arange(self.W) / NATIVE_PER_LABEL_PX).astype(int)
        gy = np.clip(gy, 0, self.comp.shape[0] - 1)
        gx = np.clip(gx, 0, self.comp.shape[1] - 1)
        self.comp_native = self.comp[np.ix_(gy, gx)]
        self.rgb_np = np.asarray(self.rgb)
        self._gy, self._gx = gy, gx
        self._override = None          # set by render_synthetic()
        self._override_bbox = None

    # -- geometry ---------------------------------------------------------
    def native_bbox(self, cid, pad=True):
        x0, y0, x1, y1 = (self._override_bbox if self._override_bbox
                          else self.comps[cid].bbox)
        s = NATIVE_PER_LABEL_PX
        X0, Y0, X1, Y1 = x0 * s, y0 * s, (x1 + 1) * s, (y1 + 1) * s
        if pad:
            ext = max(X1 - X0, Y1 - Y0)
            p = RENDER["pad_fraction"] * ext
            X0, Y0, X1, Y1 = X0 - p, Y0 - p, X1 + p, Y1 + p
        cx, cy = (X0 + X1) / 2, (Y0 + Y1) / 2
        side = max(X1 - X0, Y1 - Y0, RENDER["min_crop_native"])
        X0, X1 = cx - side / 2, cx + side / 2
        Y0, Y1 = cy - side / 2, cy + side / 2
        # slide (never shrink) back inside the frame
        if X0 < 0: X0, X1 = 0, side
        if Y0 < 0: Y0, Y1 = 0, side
        if X1 > self.W: X0, X1 = self.W - side, self.W
        if Y1 > self.H: Y0, Y1 = self.H - side, self.H
        return (int(max(0, X0)), int(max(0, Y0)),
                int(min(self.W, X1)), int(min(self.H, Y1)))

    # -- panels -----------------------------------------------------------
    def _native_mask(self, cid):
        """Boolean native-resolution mask for a component, or an override."""
        if self._override is not None:
            return self._override
        return self.comp_native == cid

    def _marked_crop(self, cid, box, out_px):
        X0, Y0, X1, Y1 = box
        sub = self.rgb_np[Y0:Y1, X0:X1].astype(np.float32).copy()
        m = self._native_mask(cid)[Y0:Y1, X0:X1]
        sub[m] = sub[m] * (1 - MARK_ALPHA) + np.array(MARK, np.float32) * MARK_ALPHA
        b = _boundary(m)
        if b.any():
            im = Image.fromarray(sub.astype(np.uint8))
            d = ImageDraw.Draw(im)
            ys, xs = np.nonzero(b)
            for y, x in zip(ys, xs):
                d.ellipse([x - OUTLINE_W, y - OUTLINE_W,
                           x + OUTLINE_W, y + OUTLINE_W], fill=MARK)
            sub = np.asarray(im).astype(np.float32)
        return Image.fromarray(sub.astype(np.uint8)).resize(
            (out_px, out_px), Image.LANCZOS)

    def _context(self, cid, box, width):
        h = int(width * self.H / self.W)
        im = self.rgb.resize((width, h), Image.LANCZOS).convert("RGB")
        arr = np.asarray(im).astype(np.float32)
        gy = (np.arange(h) * self.comp.shape[0] / h).astype(int)
        gx = (np.arange(width) * self.comp.shape[1] / width).astype(int)
        nm = self._native_mask(cid)
        ny = (np.arange(h) * self.H / h).astype(int)
        nx = (np.arange(width) * self.W / width).astype(int)
        m = nm[np.ix_(np.clip(ny, 0, self.H - 1), np.clip(nx, 0, self.W - 1))]
        arr[m] = arr[m] * 0.45 + np.array(MARK, np.float32) * 0.55
        im = Image.fromarray(arr.astype(np.uint8))
        d = ImageDraw.Draw(im)
        sx, sy = width / self.W, h / self.H
        d.rectangle([box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy],
                    outline=MARK, width=3)
        return im

    def render_instance(self, cid, out_dir, pad_fraction=None, tag=""):
        """Framing A stimulus for one component."""
        old = RENDER["pad_fraction"]
        if pad_fraction is not None:
            RENDER["pad_fraction"] = pad_fraction
        try:
            box = self.native_bbox(cid)
        finally:
            RENDER["pad_fraction"] = old
        D, Cw = RENDER["detail_px"], RENDER["context_px"]
        ctx = self._context(cid, box, Cw)
        marked = self._marked_crop(cid, box, D)
        plain = Image.fromarray(
            self.rgb_np[box[1]:box[3], box[0]:box[2]]).resize(
            (D, D), Image.LANCZOS)
        cap = 34
        Hc = max(ctx.height, D) + cap
        canvas = Image.new("RGB", (Cw + 2 * D + 24, Hc), (16, 16, 16))
        canvas.paste(ctx, (0, cap))
        canvas.paste(marked, (Cw + 12, cap))
        canvas.paste(plain, (Cw + D + 24, cap))
        d = ImageDraw.Draw(canvas)
        f = _font(24)
        for x, t in ((6, "A: WHOLE SCENE (region in magenta)"),
                     (Cw + 18, "B: ZOOM, region outlined + tinted magenta"),
                     (Cw + D + 30, "C: SAME ZOOM, nothing drawn on it")):
            d.text((x, 6), t, font=f, fill=(255, 255, 255))
        os.makedirs(out_dir, exist_ok=True)
        p = os.path.join(out_dir, f"region_{cid:03d}{tag}.png")
        canvas.save(p, optimize=True)
        return p

    def render_synthetic(self, label_mask, fake_id, out_dir, pad_fraction=None,
                         tag=""):
        """Render an arbitrary label-grid mask exactly as if it were a component.

        Used only by `hard.py`'s null-region probe: a region drawn over material
        the ground truth says is pure straw, presented with the same framing and
        the same prompt as a real one. If the model invents a plant for it, that
        is confabulation, and it is measurable rather than anecdotal.
        """
        ys, xs = np.nonzero(label_mask)
        self._override_bbox = (int(xs.min()), int(ys.min()),
                               int(xs.max()), int(ys.max()))
        self._override = label_mask[np.ix_(self._gy, self._gx)]
        try:
            return self.render_instance(fake_id, out_dir,
                                        pad_fraction=pad_fraction, tag=tag)
        finally:
            self._override = None
            self._override_bbox = None

    # -- framing B --------------------------------------------------------
    def render_montage(self, out_dir):
        """Whole-frame overview + numbered tiles.  One global look."""
        os.makedirs(out_dir, exist_ok=True)
        ids = [c.id for c in self.comps.values() if c.core]
        paths = []
        # overview
        ov_w = 900
        ov_h = int(ov_w * self.H / self.W)
        ov = self.rgb.resize((ov_w, ov_h), Image.LANCZOS)
        d = ImageDraw.Draw(ov)
        d.text((8, 8), "OVERVIEW — the whole garden bed, nothing drawn on it",
               font=_font(20), fill=(255, 255, 0))
        p = os.path.join(out_dir, "montage_00_overview.png")
        ov.save(p, optimize=True)
        paths.append(p)
        ov2 = self.rgb.resize((ov_w, ov_h), Image.LANCZOS)
        ImageDraw.Draw(ov2).text(
            (8, 8), "OVERVIEW — the whole garden bed", font=_font(20),
            fill=(255, 255, 0))
        ov2.save(os.path.join(out_dir, "plain_00_overview.png"), optimize=True)

        T = RENDER["tile_native"]
        ncols = int(np.ceil(self.W / T))
        nrows = int(np.ceil(self.H / T))
        n = 0
        for r in range(nrows):
            for c in range(ncols):
                X0, Y0 = c * T, r * T
                X1, Y1 = min(self.W, X0 + T), min(self.H, Y0 + T)
                sub = self.rgb_np[Y0:Y1, X0:X1].astype(np.float32).copy()
                cm = self.comp_native[Y0:Y1, X0:X1]
                n += 1
                pl = Image.fromarray(sub.astype(np.uint8)).resize(
                    (RENDER["tile_px"],
                     int(RENDER["tile_px"] * (Y1 - Y0) / (X1 - X0))),
                    Image.LANCZOS)
                dp = ImageDraw.Draw(pl)
                dp.rectangle([0, 0, pl.width, 30], fill=(0, 0, 0))
                dp.text((6, 4), f"TILE {n} of {nrows * ncols}  "
                                f"(row {r + 1}, col {c + 1})",
                        font=_font(20), fill=(255, 255, 0))
                pl.save(os.path.join(out_dir, f"plain_{n:02d}.png"),
                        optimize=True)
                im = Image.fromarray(sub.astype(np.uint8))
                dr = ImageDraw.Draw(im)
                for cid in ids:
                    m = cm == cid
                    if m.sum() < 40:      # not enough of it in this tile to mark
                        continue
                    b = _boundary(m)
                    ys, xs = np.nonzero(b)
                    for y, x in zip(ys[::3], xs[::3]):
                        dr.ellipse([x - 2, y - 2, x + 2, y + 2], fill=MARK)
                    ys, xs = np.nonzero(m)
                    ty, tx = int(np.median(ys)), int(np.median(xs))
                    if not m[ty, tx]:
                        k = np.argmax(m.sum(1)); ty = int(k)
                        tx = int(np.median(np.nonzero(m[ty])[0]))
                    txt = str(cid)
                    f = _font(46)
                    bb = dr.textbbox((tx, ty), txt, font=f, anchor="mm")
                    dr.rectangle([bb[0] - 6, bb[1] - 4, bb[2] + 6, bb[3] + 4],
                                 fill=(0, 0, 0))
                    dr.text((tx, ty), txt, font=f, fill=(255, 255, 0),
                            anchor="mm")
                im = im.resize((RENDER["tile_px"],
                                int(RENDER["tile_px"] * (Y1 - Y0) / (X1 - X0))),
                               Image.LANCZOS)
                dr = ImageDraw.Draw(im)
                dr.rectangle([0, 0, im.width, 30], fill=(0, 0, 0))
                dr.text((6, 4), f"TILE {n} of {nrows * ncols}  "
                                f"(row {r + 1}, col {c + 1})",
                        font=_font(20), fill=(255, 255, 0))
                p = os.path.join(out_dir, f"montage_{n:02d}.png")
                im.save(p, optimize=True)
                paths.append(p)
        return paths


if __name__ == "__main__":
    import sys
    R = Renderer()
    out = os.path.join(HERE, "renders", "A")
    ids = [c.id for c in R.comps.values() if c.core]
    if "--montage" in sys.argv:
        ps = R.render_montage(os.path.join(HERE, "renders", "B"))
        print(f"{len(ps)} montage panels")
    else:
        for i, cid in enumerate(ids):
            R.render_instance(cid, out)
            if i % 20 == 0:
                print(i, cid, flush=True)
        print(f"rendered {len(ids)} regions -> {out}")
