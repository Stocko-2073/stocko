# CAD style guide

How the OpenSCAD + BOSL2 models in this repo are written. Follow it for new
files and when editing old ones. Good files to copy from:
`cad-practice/chip_clip.scad`, `cad-practice/header_cutter/header_cutter.scad`,
`WireHandler/WireHandler.scad` and `pet/mx1508.scad`.

The short version: a few knobs at the top, numbers written where they're used,
BOSL2 attachable modules, and nothing that only checks or configures the model.

## A typical file

```openscad
include <BOSL2/std.scad>
$fn=0;$fa=1;$fs=$preview?0.5:0.25;ep=0.01;$slop=0.2;

pcb=[51,70,1.6];
wall=2;

module board(anchor=BOT,spin=0,orient=UP) {
    attachable(anchor,spin,orient,size=pcb) {
        color("#853") cuboid(pcb);
        children();
    }
}

module tray(anchor=TOP,spin=0,orient=UP) {
    size=[pcb.x+wall*2,pcb.y+wall*2,6];
    attachable(anchor,spin,orient,size=size) {
        color("#f84") difference() {
            cuboid(size,rounding=2,edges="Z");
            up(3+ep) cuboid([pcb.x+$slop*2,pcb.y+$slop*2,4+ep],anchor=TOP);
            grid_copies([pcb.x-7,pcb.y-7],n=2) cyl(d=3+$slop,h=20);
        }
        children();
    }
}
// !tray(); // print

tray() position(TOP) down(4) board();
```

In order: includes, the settings line, the knobs, values derived from them,
vitamins (bought parts), printed parts each followed by its print line, and the
assembly at the bottom.

## Header

- `include <BOSL2/std.scad>` first, plus the BOSL2 files the model needs
  (`screws.scad`, `gears.scad`, `threading.scad`, `nema_steppers.scad`,
  `ball_bearings.scad`).
- Then the settings on one line, as is:
  `$fn=0;$fa=1;$fs=$preview?0.5:0.25;ep=0.01;$slop=0.2;`

## Variables

- At the top, only the knobs someone would change (`pins=40; teeth=30;
  capacity=20;`), then global values derived from them (`r=teeth*2.54/(2*PI);`).
  Short ones can share a line: `w=20;l=62;h=3;`.
- Don't make variables for an expression that appears once, just write in the
  number, but if it's used in a few places a short variable helps keep it DRY
  `cuboid([inset+overlap,w-inset*2-1,wall],anchor=BOT+RIGHT)`.
- A value a module repeats becomes a local at the top of that module.
- Sizes as vectors, read with `.x`, `.y`, `.z`:
  `size=[24.5,21,1.6]; ... left(size.x/2)`.
- Lowercase snake_case. Short locals (`w`, `l`, `h`, `d`, `r`, `a`); suffixes
  for the rest (`pad_d`, `slot_w`, `wheel_x`, `pivot_offset`).
- No customizer sections (`/* [Feeder] */`) and no `show_*` flags. Hide a part
  with `*`, isolate it with `!`, ghost it with `%`, and edit a knob to pose the
  model.

## Modules

- Make modules BOSL2 attachables: take `anchor`, `spin` and `orient`, wrap the
  geometry in `attachable()` and pass `children()` through, so a part can be
  anchored, oriented and attached like BOSL2's own shapes. Size the box to the
  part, or to its main body the way BOSL2 does for motors and gears. If the
  geometry isn't centred on the origin, give `cp=` instead of moving it.
- Build each part around the origin where it's used (a mating face, a mount
  face, the floor) and make that the default anchor: a box anchor when it is
  one (`nema17_pancake(anchor=TOP)` is the mount face), otherwise a
  `named_anchor` (`pin_header(anchor="pcb")`). Add other named anchors only
  when something uses them.

  ```openscad
  module pin_header(anchor="pcb",spin=0,orient=UP) {
      anchors=[named_anchor("pcb",[0,0,0],DOWN)];
      attachable(anchor,spin,orient,size=[l,2.54,11.64],cp=[0,0,2.82],anchors=anchors) {
          union() {
              color("#222") up(1.27) cuboid([l,2.54,2.54]);
              color("#da3") down(3) xcopies(2.54,n=pins) cuboid([0.64,0.64,11.64],anchor=BOT);
          }
          children();
      }
  }
  ```

- Mount parts on each other through anchors and moves:
  `tray() position(TOP) down(4) board();`. If two rotations cancel out to fix a
  part's orientation, rebuild the part in the right frame instead.
- Modules read the globals. Besides `anchor`, `spin` and `orient`, give a
  module parameters only when it's called with different values
  (`nema17_pancake(a=0)`, `screw_with_nut(a=0,l=11)`, `d_shaft(slop=0)`), never
  to pass the knobs down.
- 2D profiles and other helpers used inside a part (`d_shaft()`,
  `pin_pocket()`) stay plain modules. One that is a single statement can drop
  its braces: `module d_shaft(slop=0) difference() {`.

## Formatting

- 4-space indent, no tabs.
- No spaces around `=` or after commas in calls: `cyl(d=pad_d,h=1,anchor=BOT)`.
  A space after `for` and `if`: `for (i=[0:24])`, `if (fed>0)`.
- Chain transforms on one line, outermost first:
  `back(pivot_offset) up(pivot_z) xcyl(d=pivot_d,h=w);`

## BOSL2 habits

- Move with `up`, `down`, `left`, `right`, `fwd`, `back`; turn with `xrot`,
  `yrot`, `zrot`.
- Shapes: `cuboid`, `cyl`, `xcyl`, `ycyl`, `tube`, `rect`, placed with
  `anchor=` rather than offsets of half a size; edges with `chamfer=` or
  `rounding=` plus `edges=` or `except=`.
- Repeats and symmetry: `xcopies`, `ycopies`, `zcopies` (also with a list:
  `xcopies([-13.5,0,13.5])`), `grid_copies`, `zrot_copies`, `xflip_copy()`,
  `yflip_copy()`.
- Cuts: `difference()`, or `diff()` with `tag("remove")` and `tag("keep")`
  when the cuts sit next to the parts they cut.
- Use BOSL2's hardware where it fits: `screw()`, `screw_hole()`, `nut()`,
  `nut_trap_inline()`, `nema_stepper_motor()`, `nema_mount_mask()`,
  `spur_gear()`.

## Clearance, overlap and facets

- Fits use `$slop`: `cyl(d=5+$slop,...)` for a bore,
  `cuboid([29+$slop*2,...])` for a pocket.
- Cuts overshoot by `ep`: `up(ep) cyl(d=2,h=1.6+ep*2,anchor=TOP)`. No other
  tiny padding terms.
- Facets come from `$fa` and `$fs` in the header. Set `$fn` only for a
  deliberate polygon, such as `$fn=6` for a hex.
- Thin printed walls in nozzle widths: `wall=nozzle*2`.

## Vitamins

- Model bought parts (motors, boards, batteries, headers) with a few
  primitives: enough to check the fit and see the assembly. Put the datasheet
  link above the module.
- Imported meshes go behind `%` or a `color()`: `%import("AS5600.stl")`.

## Colours

- Hex strings, usually three digits: `color("#848")`, grey like `"#888"` for
  metal, a colour of its own for each printed part. Four or eight digits add
  transparency (`"#3638"`). Inside `attachable()`, colour the geometry, not
  `children()`. No RGB float vectors.

## Comments

- Sparse. One or two lines above a module when its anchor or orientation isn't
  obvious ("Anchored at the PCB face, pins along X, mating ends +Z"), a short
  label after a line (`// gate`, `// M3, 3 deep`), and a sentence for any maths
  that isn't obvious.

## Printing and animation

- Each printed part is followed by a commented line that isolates it in print
  orientation: `// !xrot(180) wheel(); // print`. `*!part();` keeps a quick
  isolate handy while working.
- Animate with `$t` directly: `zrot($t*360)`, `travel=$t*2*l;`.

## Don't

- `assert()` or any other input checking.
- Customizer sections and `show_*` toggles.
- Long parameter lists passed down through modules.
- Helper functions for simple derivations. To get a wheel with whole teeth,
  pick `teeth` and derive the radius, not the other way round.
- Named anchors nothing uses.
- `_private` names, RGB float colours, `$fn` on ordinary round parts.
