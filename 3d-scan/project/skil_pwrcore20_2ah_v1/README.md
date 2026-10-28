# SKIL PWRCORE 20 2.0Ah battery (BY519701), v1

OpenSCAD + BOSL2 model built from 41 AgentCam photos (requests r0069–r0109) in four placements:
upright, lying on its side, standing on its back end, and upside down.

- `skil_pwrcore20_2ah.scad`: the model. Set `details = false` for the plain envelope.
- `skil_pwrcore20_2ah.stl`: export (watertight).

## Frame

+Y points to the terminal end (front), +X to the right when looking from the back toward the
front, and +Z up. The origin is on the table, under the middle of the body.

## Main dimensions (mm)

| | value | how it was measured | confidence |
|---|---|---|---|
| Width across side walls | 74.0 | End-on silhouette (standing, r0102); silhouette fit over 20 upright views | ±0.5 |
| Length, back face to front face | 111.8 (−56.3 … 55.5) | Silhouette fit over 20 upright views | ±0.7 |
| Length to lug tips | 118.1 (lug tips at Y 61.8) | Side-lying silhouette (61.7); top-down views | ±0.5 |
| Rail top | 43.7 | Stereo against the mat (upright), face-on side view (43.65), end view (44.0) | ±0.4 |
| Latch tab peak | 47.9 | Side-lying silhouette | ±0.5 |
| Rear collar top | 45.5 | Plane sweep, 11 views | ±0.5 |
| Rail cap width | 47.4 | Top-down edge probe (r0083) plus two obliques | ±0.5 |
| Rail lip underside | 38.3 | Face-on side view, intensity edges | ±0.5 |
| Rail windows | 7 per side, z 40.1–41.75, Y list in the file | Face-on side view plus upright obliques, averaged | ±0.4 |
| Shoulder deck | 31.3 | Plane sweep (vents 32.0), SIFT cloud | ±0.5 |
| Release button pad | 41.6 (front edge) → 35.3 (back) | Plane sweeps at Y −40 and −52 | ±0.5 |
| Parting line | z 16 | Upright rectified side and end faces | ±0.7 |

Top-face features were measured in top-down rectified images (`scripts/ortho.py`) at their own
heights. These include the terminal slots, latch window, screw boss, polarity marks, front vents,
keys and "1P". They are good to about ±0.3 mm in X/Y.

The side label panels come from the upright side views and match both sides. The back-face
gauge (window, button, 4 LEDs) comes from r0079 rectified onto the back face.

Bottom features were measured in two independent placements, which agree to within about
0.5 mm. These are the label recess, finger channel, 5 vents, screws, corner pads and small holes.

## What limits accuracy

- The mat's pose is good to about 0.5 mm per photo, but the other placements are registered to the
  model by silhouette. That adds about 1 mm and ~1° per placement, so detail from those
  views was cross-checked against a second view wherever possible.
- Vertical faces seen from 55° couple height with depth: 0.5 mm of depth error moves a feature
  about 0.7 mm in height. Heights come from horizontal plane sweeps and face-on views instead.
- Silhouettes against the paper pick up the contact shadow at the base, which reads about 1.5 mm
  wide per side. The body width is from the end-on view instead.
- Not modeled: the label artwork, the curve of the deck's front edge (about 0.7 mm), and the
  spring contacts' exact shape (two crossed blades stand in for them).

## Reproducing the checks

Captures are in `../../captures/`. Run the scripts with `../../.venv/bin/python` from `scripts/`:

- `overlay.py [--placement up|side|end|flipped] [--box x0 x1 y0 y1 z0 z1] r0083 …`: draws the
  model's feature edges (red) and silhouette (yellow) on photos → `out/<name>.jpg`.
- `silcmp.py r0083 …`: marks the model over bare paper (red) and battery the model misses (blue).
- `ortho.py` / `ortho_p.py`: rectifies a photo onto a battery-frame plane, with a mm grid.
- `facesweep.py`: sweeps a textured flat patch through several views to find its height or depth.
- `edgeprobe.py`: finds how far a real straight edge sits from the model's, in mm.
- `modelreg.py`, `planereg.py`: register the model into a placement's views
  (→ `out/registration.json`).
- `fitparams.py body|top`: coordinate-descent fit of SCAD parameters to the upright silhouettes.
- `masks.py`, `hull.py`, `register.py`, `stereo.py`: the first pass, which built a visual hull and
  a SIFT point cloud and roughly registered the placements.
