# XYZ mechanism

These notes describe the assembly, load paths, coordinate frames, and drilling demo in `xyz.scad`. Dimensions are in millimeters unless stated otherwise.

## XY stage and work surface

The table carries the work under the spindle. The X and Y carriages hook over their rails, with the Y carriage carrying the X motor mount. The X motor face is set back by `mb` from the carriage's drawing reference.

The base plate is the surface the Y carriage rides on. It shares the tower's origin, starts at the tower's front face, and extends under the table. The board sits on the X carriage's pocket floor; its placement is drawn in the carriage's frame before rotation.

The four M3×8 screws in `tr8_nut_screws()` fasten a part to the supplied lead-screw nut. Their heads sit beneath the flange and they thread upward into the part resting on it. In the `nut_flange` frame, the holes are rotated 45° to match `nut_spin=45`.

`x_carriage()` includes its own nut-body clearance and four M3 mounting holes. `y_carriage()` includes the Y nut clearance and mounting holes, along with the X motor's body clearance, pilot clearance, mounting holes, and counterbores. The Y carriage's origin is the X motor mount face. Its Y nut cutter is transformed back from the Y nut flange frame through the inverse of the assembly's X motor placement.

## Exporting printable parts

Each printable module (`x_carriage`, `y_carriage`, `tower`, `base_plate`, and `z_carriage`) contains all of its cuts and only the plastic part. Screws, nuts, motors, and the protoboard are added by the assembly.

Run `./export.sh` to export all five parts into `stl/` beside the script, or `./export.sh /path/to/output` to choose another directory. The script passes each part name through OpenSCAD's `-D 'print="part_name"'` option. The printing section of `xyz.scad` selects and orients that part for export. Leave `print` undefined to view the complete mechanism.

## Tower and base plate joint

The tower combines the Y motor housing, Z motor saddle, and guide fins in one print. Its origin is the Y motor mount face, attached to the motor's `TOP`, with the motor inside the housing. The base plate butts against the housing's front face.

The lower housing's rear face is aligned with the saddle and guide fins to form a common print-bed plane. Its depth is derived from the saddle geometry; with the current dimensions this plane is at local z = −46.49, trimming 1.01 from the lower housing's previous rear face.

In the tower's frame, +Y is up and +Z runs along the plate. The plate spans x = −13…86 and y = −22…−13: it is 9 thick, with the floor at −22. It starts at z = `hf`.

The tower has a foot extending forward along the floor beneath the plate's end. A recess in the plate's underside fits over the foot. Two M3×13 screws pass upward through the foot to nuts on the plate's top; the nuts and screw ends stand about 7 above the bed. The screw heads are counterbored just beneath the floor.

The Y carriage's nut mount runs along the plate within 12 of the Y screw axis and reaches the housing face. Nothing may project above the bed within x = ±12. Both joint screws therefore sit to the right of this region, and the foot extends beyond the housing to support them.

The foot spans x = −7…60, starting 6 inward from the plate's edge and extending 35 past the housing's side. It is 5 thick and extends 20 forward of the housing face. The screws are at x = 22 and 50, both 12 forward of that face. A 45° gusset supports the overhang beside the housing so the tower can print with its back face down without support. The tower is printed on its side so the fins' layer lines run along the slide.

The Y motor screws are flush with the housing face so the plate can overlap the front two. There is `hf - 3` of material under their heads; M3×6 screws engage 4 into the motor.

## Z motor saddle and guide fins

The saddle sits on top of the Y motor housing, flush with its left and back faces. Its geometry is drawn in the Z motor's frame: the mount face is the origin and the screw points along +Z.

The assembly places the Z motor at global (8.5, 62, 47), with `spin=180`. The tower attaches to the Y motor facing `FWD`; the corresponding local mapping is `(x - 17, z + 17, 35.5 + hf - y)`, with the Z screw along +Y and the motor's +X pointing left.

The saddle's side walls continue upward as guide fins, reaching approximately to the screw tip. Each fin has an inward stiffening flange along its back edge. The flanges stay clear of the motor as it slides into the saddle from behind. A slot through the saddle's back edge provides clearance for the motor's pilot boss, and the motor pocket cuts just into the housing top.

M3×8 screws pass down through the saddle top, engaging 4 into the motor through the `mp_under`-thick top plate.

## Z carriage and spindle

The Z carriage rests on the supplied nut's flange, with the nut beneath it. Its weight seats it on the flange rather than hanging from screws threaded down into the block. The carriage wraps the saddle's two guide fins, much as the X and Y carriages hook over their rails, and carries a cantilever arm out to the spindle motor.

The spindle's weight pitches the carriage nose-down: the top pushes toward the table and the bottom moves away. The nut holds the bottom. A hook wall behind the fins' back edges wraps their flanges and holds the top, leaving the fin channels open toward the table.

Sliding contact is confined to narrow vertical ribs, with `$slop` clearance to the fins. The rest of each channel wall stands `relief` clear. Each fin has four narrow contact strips: front and back on the outer face, and just ahead of the flange and at the front on the inner face. Their spacing, rather than their area, constrains twist. The hook wall also bears only on the fin's own back edge, with relief beside it around the flange. Channel geometry is drawn from the hook wall's face.

The carriage's `BOT` anchor is the nut flange face and attaches to `nut_flange`. Its named `spindle` anchor is the motor mount face over the table, facing down. The arm has a top plate and a web on each side tapering from the block to the motor pad. Only the body receives the carriage color, preserving the screws' own color.

Spindle screw heads are counterbored flush into the pad's underside. The screws enter upward from inside the skirt. The pancake motor's holes are only 3.5 deep, so M3×6 screws provide 3 of engagement with 3 of pad beneath the heads.

The pancake motor carries a mini chuck on its Ø5 shaft, inserted into the chuck's 12-deep bore. The chuck holds a 1/8-inch × 60 drill, with the shank pushed to the bit seat.

## Protoboard and drilling demo

The 7 × 9 cm phenolic protoboard sits pads-up on the table's pocket floor. The preview uses pads with dark dots for the grid holes, avoiding roughly 800 Boolean hole cuts. The `protoboard()` module's `drilled` argument supplies board-coordinate `[x,y]` positions where actual holes are cut.

The animation follows a G81-style cycle: start at the safe height above a hole, rapid down to the retract plane just above the work, feed to depth, dwell, rapid back to the safe height, then travel to the next hole. The last rapid returns above the first hole to close the loop. Rapids ease in and out; the plunge uses a steady feed.

Hole positions are table travel, corresponding to X and Y nut positions over ranges 0…84 and 0…70. Heights refer to the drill tip. The stage's 84 × 70 travel is centered on the 90 × 70 pocket, so `bit_on_board(xy)` maps table travel to centered board coordinates as `[42 - xy.x, xy.y - 35]`.

The work top is the pocket floor height of 29 plus the board thickness. Drilling depth adds 1 beyond the board thickness for the drill point to leave a full-size hole underneath. `tip_to_nut=21` relates the tip height to Z `nut_pos`; the stack comprises the flange 5.5 above the pilot at 49, the 51.5-high carriage, a shaft extending 24 downward, a chuck inserted 12 onto it, a bit seat 13 inward, and the 60-long bit.

Move records contain duration, endpoint `[x,y,tipz]`, and an easing flag. Times are in seconds. The lead screws turn with their nuts, as modeled in `nema17_tr8.scad`, and the spindle runs throughout. Holes appear as the bit bottoms out at each location. The spindle's nominal 180 rpm is slow enough to follow at 60 fps and is rounded to a whole number of turns per cycle for a seamless loop.

The final echo prints a `do_mp4.sh` command with the current camera and the frame count for one cycle at 60 fps. `explode` separates the base plate from the tower to inspect the joint; `show_stage` controls visibility of the XY stage.
