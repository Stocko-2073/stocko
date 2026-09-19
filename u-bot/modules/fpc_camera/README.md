# 24-pin FPC camera

[fpc_camera.scad](fpc_camera.scad) models the CV-JH640G2V1-T140 style camera in
[camera_design.jpg](../../camera_design.jpg): an M7 120° lens in a 9 × 9 mm
holder, a 6 mm × 0.12 mm flex ribbon, and a 12.5 × 4.5 mm 24-pin 0.5 mm pitch
connector tab, 75 mm overall. It is a reference model for designing mounts, not
a printable part.

Open [preview.scad](preview.scad) to see it with an example folded route. The
commented calls at the bottom show the straight camera, the head alone, and a
cable of arbitrary length.

## Coordinates

The optical axis is +Z and the lens looks toward +Z. Z=0 is the back face of
the holder, where the flex leaves the head; the lens front is at
`fpc_camera_depth` (10.4 mm). The flex ribbon lies just behind Z=0 and runs
along −Y from the holder edge at y=−4.5.

## Attaching

`fpc_camera()` and `fpc_camera_head()` are BOSL2 attachables. The attachable
volume is the 9 × 9 holder from the flex pad's back face to the lens front, so
`anchor=BOT` puts the back of the head on Z=0 and the barrel overhangs the
sides by 0.5 mm. The default anchor `"origin"` keeps the coordinates above.
Named anchors:

- `"lens"`: lens front centre, pointing +Z.
- `"base"`: top of the 1.9 mm holder base, pointing +Z, for clamps that grip the base.
- `"flex"`: ribbon exit at the holder edge, pointing −Y.
- `"connector"` (on `fpc_camera()` only): centre of the connector tab's contact
  face, pointing away from the lens side, so `attach("connector")` places a
  mating connector footprint on the contacts wherever the route ends.

## Routing the flex

`fpc_camera(route)` and `fpc_camera_flex(route)` take a BOSL2 `turtle3d`
command list for the free cable. The turtle starts at the holder edge heading
away from the head (−Y) with its "up" toward the lens (+Z), so:

- `"move", d` runs straight,
- `"arcup", r, a` / `"arcdown", r, a` fold the ribbon toward / away from the lens,
- `"arcleft"` / `"arcright"` curve it sideways in the ribbon's plane.

Use the arc forms rather than `"up"`/`"left"` so the sweep stays clean, and
keep radii above about 1 mm. A bare number is a straight run of that length.
The connector tab is placed at the end of the route with its contacts on the
side away from the lens, matching the drawing.

The nominal free cable is `fpc_camera_flex_len` (61.5 mm). The module echoes a
note when a route differs from that by more than 0.5 mm, and
`fpc_camera_flex_path(route)` returns the centerline so you can check it with
`path_length()`. `fpc_camera_flex_end(route)` returns the frame at the connector
root (local +X along the cable, +Z toward the lens side) for positioning a
mating connector.

## Dimensions taken from the drawing

Only the overall depth (10.5), holder (9 × 9), barrel (Ø10), ribbon (6 wide,
0.12 thick), overall length (75), tab (12.5 × 4.5, 0.35 thick) and contact
pitch (24 × 0.5, 0.3 wide, 11.5 span) are labelled. The barrel, step, thread
and boss depths along the axis were scaled from the side view and are
approximate to about ±0.2 mm.
