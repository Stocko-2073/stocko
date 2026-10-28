# SKIL PWRCore 20 2Ah battery (BY519701) — Blender model

Built in Blender 5.2 from the AgentCam photos already on disk (captures r0069–r0109). No
new photos were taken. The model is scripted: every dimension is a named parameter in
`scripts/build_battery.py`, and the same script rebuilds the whole solid.

## Files

| File | What |
|---|---|
| `battery.blend` | Blender scene: geometry (`Battery`, `Battery_LatchButton`, `Battery_LatchPawl`), dressing collection (labels, gauge, contacts, screws, sticker), lights and cameras |
| `skil_pwrcore20_2ah.stl` | Geometry only, millimetres, watertight (3 bodies: housing, latch button, latch pawl) |
| `skil_pwrcore20_2ah.glb` | Geometry, materials and label artwork (glTF, metres, Y up) |
| `out/compare_1.jpg`, `out/compare_2.jpg` | Photo, then a Blender render from the same calibrated camera, then the model's edges drawn on the photo |
| `out/beauty_sheet.jpg`, `out/pretty/beauty_*.png` | Studio renders |
| `out/eval.json` | Per-photo accuracy scores |
| `scripts/` | The whole pipeline (below) |

Rebuild inside Blender:
`runpy.run_path('scripts/build_battery.py')['build']()`, then
`runpy.run_path('scripts/dress_battery.py')['dress'](P)`.

## Frame

Origin at the centre of the footprint on the bottom face. +X points to the terminal (front)
end, +Z up through the rails, and +Y to the left when you look from the latch end.

## Main dimensions (mm)

| | |
|---|---|
| Overall | 117.7 × 74.0 × 47.0 (back face incl. gauge button to foot tips × width × pawl top) |
| Lower housing | x −59.0 … +52.0, width 74.0, deck at z 31.0; chamfers: bottom 2.8, long top edges 4.3, front top 5.5, back top 6.0, vertical corners 9.5 (back) and 5.0 (front) |
| Parting line | z 16.0, all round |
| Side label recess | x −47 … +45, z 3.5 … 21.5, 0.6 deep, 5 mm corner chamfers |
| Feet | y ±13.8 … ±27.3, reach x +57.8, top 30 → 28 sloping forward, 3.5 plan chamfer, 4.5 bottom-front chamfer, screw on the underside at (52.5, ±19.75) |
| Tongue | x −32 … +34.5, width 46.6; rail groove width 42.0 between z 37.5 and 41.3; top plate z 43.6; 7 rail windows per side, z 38.7 … 41.3, from x −22 … +26 |
| Terminal slots | y 0, ±6.9, ±13.7, 2.5 wide, from x 7.5 out through the front |
| Latch housing | full deck width (±32.5) at the back, narrowing to ±26 at x −34; inclined top from z 31.5 at the back face to 46.0 at x −41, flat to x −32 |
| Latch button | x −56.5 … −42, width 34, 0.8 below the housing surface, 2 grooves |
| Latch pawl | window x −25 … −16, width 30; ramp rising to z 47.0 at the back edge |
| Front vents | 6 stadium pockets at y ±3.9, ±9.0, ±14.0, x 36.5 … 45, each with 2 × 5 holes |
| Bottom | finger slot x −14 … −5, width 45.5, 3 deep; back screws at (−54.5, ±23.25) in counterbores; 5 vent slots; 4 pad rings; pin marks |
| Charge gauge | back face, width 34, z 3 … 10.5; button on the +Y side, 4 LED windows on the −Y side |

## Accuracy

The model is rendered from each of the 39 calibrated photo cameras and its outline is compared
with the photo (`scripts/eval_model.py`):

- The median distance from the model outline to the nearest photo edge is **0.39 mm**, and
  **81 %** of outline points fall within 1 mm.
- Silhouette IoU averages 0.90. The photo masks include cast shadows, so this figure
  understates the real match. The lowest IoUs, 0.70–0.73, are the shadow-heavy oblique shots
  of the end-standing and flipped placements, and their edges still line up.
- The scale comes from the printed mat. The cameras refined against the mat sit 0.6 %
  (σ 0.15 %) farther away than ARKit's own estimate, so absolute size carries about ±0.5 %
  (±0.6 mm over the length).

## How it was measured

1. **Camera calibration** (`detect_calib.py`): the mat markers are re-detected in every photo.
   One joint fit then solves each photo's pose plus a shared focal-length scale and radial
   distortion (k1, k2), with bad marker detections dropped. Reprojection error is about 3 px,
   roughly 0.3 mm at the mat.
2. **Placements**: capture timestamps show that some of the "on its side / on end / upside
   down" requests were shot before the battery was moved. The photos therefore fall into 7
   placements: upright (26 photos), side ×2, end ×2 and flipped ×2.
3. **Silhouettes** (`segment.py`): dark object against locally-normalised paper brightness.
4. **Joint visual hull** (`joint_carve.py`, `fit_poses*.py`, `final_carve.py`): carves one
   volume from all placements together, with each placement's pose found by silhouette
   consistency. The upright photos alone left a false roof about 20 mm tall. The
   side-lying and end-standing photos remove it.
5. **Envelope fit** (`envelope.py`, `fit_envelope.py`): a fast convex-piece silhouette model
   of the main volumes. It fits dimensions and placement poses together against all 39 views,
   using a two-way edge-distance cost that is robust to shadows. Poses are constrained to rest
   on the mat.
6. **Plane rectification and plane-sweep stereo** (`rectify.py`, `plane_sweep.py`): photos are
   flattened onto a chosen plane at true scale for reading feature positions. The plane's
   height is checked by whether two different views agree on it.
7. **Review loop** (`render_views.py`, `overlay.py`): Blender renders the model from each
   photo's exact camera, and the model edges are drawn on the undistorted photo. This was
   repeated for the latch housing, the tongue front, the feet and the bottom details.

## Simplifications / known gaps

- The label artwork uses Blender's built-in font, not the real condensed typeface. The
  bottom rating sticker is only a plain panel with the SKIL logo.
- The springs inside the terminal slots are simple X-shaped strips.
- The front vent holes and bottom vent slots are approximate: plain holes and slots, not
  the real grille pattern.
- The rail groove depth (width 42.0) and the lower-tongue width could only be seen at an
  angle, so they are less certain, probably ±0.5 mm.
- The parting-line groove depth and width are guessed (0.5 × 0.6).
