# RP-SMA pigtail and stubby antenna

[rpsma_pigtail.scad](rpsma_pigtail.scad) models an RP-SMA female bulkhead to
MHF4 pigtail (1/4-36 UNS thread, 8 mm hex, 0.81 mm cable) with its lock
washer, spring washer and hex nut. [rpsma_antenna.scad](rpsma_antenna.scad)
models the 28.4 mm stubby RP-SMA male antenna that screws onto it. Both are
reference models for designing mounts, not printable parts.

Open [preview.scad](preview.scad) to see the pigtail through a panel with the
antenna mated, an example cable route, and an MHF4 receptacle stand-in on the
plug. The commented calls at the bottom show the straight pigtail and each
part alone.

## Pigtail coordinates

The connector axis is +Z. Z=0 is the front face of the hex flange, which is
the panel's rear surface. The threads run to `rpsma_thread_len` (11 mm), where
the mating face is. Behind the flange are the crimp ferrule and heat shrink;
the free cable starts at `rpsma_cable_z` (−14.5 mm) heading −Z.

`rpsma_pigtail(route, cable_len, panel, hardware, threads)`:

- `cable_len` is the overall length from the hex back face to the MHF4 tip
  (the vendor's "±5" dimension). Default 150 mm.
- `panel` is the panel thickness the washers and nut stack behind (default
  1.5). `hardware=false` omits them. The stack is `rpsma_stack_h` (3.25 mm).
- `threads=true` models the 1/4-36 thread on the barrel and nut; the default
  plain cylinders are faster.

## Routing the cable

`route` is a BOSL2 `turtle3d` command list for the free cable, or a number
for a straight run. The turtle starts at the end of the heat shrink heading
away from the connector (−Z) with "up" toward +Y, so `"arcup"`/`"arcdown"`
bend toward +Y/−Y and `"arcleft"`/`"arcright"` toward −X/+X. Use the arc
forms and keep radii above a few millimetres. The MHF4 plug lands at the end
of the route with its mating face toward the cable's "down" side.

`rpsma_route_len(cable_len)` gives the free cable length for a pigtail
(134.5 mm for 150), the module echoes a note when a route differs by more than
1 mm, and `rpsma_cable_path(route)` returns the centerline for `path_length()`.

## Attaching

Both `rpsma_pigtail()` and `rpsma_body()` are attachables whose volume is the
threaded barrel: `BOT` is the panel plane, `TOP` the mating face, and the
sides the thread. Named anchors:

- `"face"`: mating face, pointing +Z.
- `"hex"`: back of the hex flange, pointing −Z.
- `"cable"`: cable start at the end of the heat shrink, pointing −Z.
- `"hardware"`: top of the nut stack for the given panel, pointing +Z.
- `"terminal"` (pigtail only): the MHF4 plug's mating face, so
  `attach("terminal",BOT)` puts a board receptacle on it wherever the route ends.

`rpsma_antenna()` is an attachable whose volume is the body from the mating
plane (Z=0, the bottom of the coupling nut's bore) to the tip, so
`attach("face",BOT) rpsma_antenna()` on a pigtail mates it, with the nut
wrapping the exposed thread. The nut's open end hangs 6 mm below Z=0 and
clears the panel nut stack with the default 1.5 mm panel. Named anchors are
`"tip"` (+Z) and `"nut"` (open end of the coupling nut, −Z).

## Dimensions

The receptacle thread length, hex, washers and nut come from the pigtail
drawing; the ferrule, heat shrink and bore were scaled from its side view and
the photo. The MHF4 plug is a 2 mm round head with a 1.2 mm crimp sleeve. The
antenna's overall, body and nut dimensions come from its drawing; the bore
depth and end rounding are estimates.
