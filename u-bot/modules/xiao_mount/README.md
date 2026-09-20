# Rear-facing XIAO Sense mount

The mount is included in `robot()` in [u-bot.scad](../../u-bot.scad) at the existing 20 mm lid hole. The camera
looks toward `BACK` (+Y), with USB-C accessible from above. The flange bears on
the lid's top face and the hand nut bears on the underside of its 1.5 mm panel.
The 3 mm perimeter lip is unchanged.

## Printed parts

Exported STLs are already oriented on Z=0. Print one of each:

| STL | OpenSCAD export module | Orientation |
| --- | --- | --- |
| [Pedestal](stls/xiao_mount_base.stl) | `xiao_mount_base_print()` | Flange top on bed, stem pointing up |
| [Hand nut](stls/xiao_mount_nut.stl) | `xiao_mount_nut_print()` | Flat, lid-contact face pointing up |
| [Camera shell](stls/xiao_mount_shell.stl) | `xiao_mount_shell_print()` | Camera face on bed, open side up |
| [PCB carrier / cover](stls/xiao_mount_cover.stl) | `xiao_mount_cover_print()` | Outside face on bed, clips up |

Use PETG, a 0.4 mm nozzle, 0.2 mm layers, four walls, and five top/bottom layers
as a starting point. The orientations keep the buttress flanks printable, the
shell open upward, and the snap lips at approximately 45 degrees. The floor's
wire opening has a pointed roof in its print orientation. Start with supports
off; the small transverse M3 pilot holes are the remaining short bridges.
Keep slicer compensation from filling or shrinking the small clips and holes.

The cover's flexible clips favor PETG over brittle filament. Deburr the thread
start, wire exits, and PCB seats before assembly. Fit-test the pedestal and nut
before installing the electronics. These parts have been checked digitally,
but have not been physically printed or fitted.

## Hardware and assembly

- Two M3 × 8 mm countersunk machine screws attach the shell to the pedestal.
- Four M3 × 8 mm socket/button-head machine screws secure the cover.
- One small cable tie provides strain relief through the cover's lower slots.
- The shell has 2.6 mm blind pilots: tap M3 threads before final assembly.
  No heat-set inserts or metal mounting nut are required.

1. Attach the empty shell to the pedestal with the two countersunk screws from
   below. The heads must sit flush with or slightly below the flange underside
   so the flange lies flat on the lid.
2. Solder the wires to the XIAO before installing it. Leave enough slack for
   removing the cover, and route the wires down beside the PCB. Both long pin
   rows have clearance; there is also approximately 4.75 mm behind the main PCB.
3. Put the cover outside-face down. Seat the main PCB in its short-edge cradle,
   USB-C end toward the top, with its camera facing away from the cover. Engage
   one end under the lips, then gently flex the opposite end clips to seat it.
   The pads contact the main PCB's back near its short edges; the side pin rows,
   camera ribbon, and Sense expansion board stay clear of the retainers.
4. Tie the wire bundle to the lower cover slots without pulling on the solder
   joints. Feed the free wire ends through the shell floor and hollow pedestal.
   Insert the board/cover assembly and secure the four cover screws. To remove
   the PCB later, release the end clips rather than pulling on the camera.
5. Pass the stem and wires through the lid hole. From inside the body, feed the
   wire ends through the printed nut and screw it onto the stem. Align the
   camera toward the robot's rear, then hand-tighten to clamp the lid. Connect
   the wires inside the body after fitting the nut.

## Dimensions and adjustments

- Enclosure height above lid: 35 mm; footprint including flange: 40 × 28 mm.
- Stem: 19.2 mm major diameter, 2 mm pitch BOSL2 buttress thread, extending
  10.2 mm below the lid top. The thread clears the 20 mm hole by 0.4 mm radially.
- Wire passage: 10 mm diameter, with flared pedestal entrances. Minimum wall
  at the external thread root is approximately 3 mm.
- Hand nut: 26 mm nominal outside diameter, 6 mm tall. Its radius fits inside
  the underside recess, without reaching the perimeter lip or body wall.
- `xiao_mount_thread_slop=0.15` adds 0.6 mm diametral clearance to the internal
  thread using BOSL2's `4*$slop` convention. Increase this value if a test print
  is too tight. The stem and nut share their thread origin and handedness.
- `body_lid_panel`, `body_lid_hole_y`, and `body_lid_hole_d` define the lid fit.
  The robot passes `body_lid_panel` to the mount as `lid_thickness`; standalone
  calls default to 1.5 mm. `xiao_mount_explode=1` separates the robot assembly.
  Open [preview.scad](preview.scad) to inspect the mount alone or select one of
  its individual print calls. Use `!xiao_mount(explode=1);` for an exploded view.

The PCB seats and lens position are measured from the `xiao_sense.stl` imported
from the sibling `corvid` project, using `xiao_sense(180)`. The lens center in mount coordinates
is `[0,7.66,25.9]`; a flared 12–16 mm camera window surrounds it. Seeed has shipped
different camera versions, so this fit targets that supplied mesh; compare your
actual board/camera with it before printing. See the
[official Seeed hardware documentation](https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/)
for the board revisions and reference drawings.

## Digital checks

- OpenSCAD rendered each printed part as a single closed solid.
- Exported meshes were checked for boundary/nonmanifold edges and Z=0 placement.
- OpenSCAD's interference check found no overlapping pairs among the body,
  lid, pedestal, nut, shell, cover, and supplied XIAO mesh.
- Thread clearance, screw-hole alignment, underside nut clearance, the open
  wire path, and print orientations were reviewed. Physical thread fit and
  clip spring force still need a first-print check.
