# CAD style guide

How the OpenSCAD + BOSL2 models in this repo are written. Follow it for new
files and when editing old ones. Good files to copy from:
`cad-practice/chip_clip.scad`, `cad-practice/header_cutter/header_cutter.scad`,
`WireHandler/WireHandler.scad` and `pet/mx1508.scad`.

The short version: a few knobs at the top, numbers written where they're used,
modules that read the globals, and nothing that only checks or configures the
model.

## A typical file

```openscad
include <BOSL2/std.scad>
$fn=0;$fa=1;$fs=$preview?0.5:0.25;ep=0.01;$slop=0.2;

pcb=[51,70,1.6];
wall=2;

// Bottom face at the origin.
module board() color("#853") cuboid(pcb,anchor=BOT);

module tray() color("#f84") difference() {
    cuboid([pcb.x+wall*2,pcb.y+wall*2,6],rounding=2,edges="Z",anchor=TOP);
    up(ep) cuboid([pcb.x+$slop*2,pcb.y+$slop*2,4+ep],anchor=TOP);
    grid_copies([pcb.x-7,pcb.y-7],n=2) cyl(d=3+$slop,h=20);
}
// !tray(); // print

tray();
down(4) board();
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
- `use <nop.scad>` for a local file of modules. The shared helpers are
  included: `include <../lib/globals.scad>` (`../globals.scad` inside
  `cad-practice`). They provide `nozzle`, the cut-away views `zview()`,
  `xview()` and `yview()`, `nop()` and `skip()`. They also define short globals
  (`x`, `y`, `d1`, `h1`, `z1`), so check your own names don't clash.

## Variables

- At the top, only the knobs someone would change (`pins=40; teeth=30;
  capacity=20;`), then values derived from them (`r=teeth*2.54/(2*PI);`).
  Short ones can share a line: `w=20;l=62;h=3;`.
- Everything else is a number written where it's used:
  `cuboid([inset+overlap,w-inset*2-1,wall],anchor=BOT+RIGHT)`. Don't name a
  dimension that appears once.
- A value a module repeats becomes a local at the top of that module.
- Sizes as vectors, read with `.x`, `.y`, `.z`:
  `size=[24.5,21,1.6]; ... left(size.x/2)`.
- Lowercase snake_case. Short locals (`w`, `l`, `h`, `d`, `r`, `a`); suffixes
  for the rest (`pad_d`, `slot_w`, `wheel_x`, `pivot_offset`).
- No customizer sections (`/* [Feeder] */`) and no `show_*` flags. Hide a part
  with `*`, isolate it with `!`, ghost it with `%`, and edit a knob to pose the
  model.

## Modules

- Modules read the globals. Give a module parameters only when it's called
  with different values (`drive_gear(offset,color,spin)`,
  `screw_with_nut(a=0,l=11)`, `d_shaft(slop=0)`), never to pass the knobs down.
- Build each part with its origin where it's used: a mating face, a mount face,
  the floor. The assembly is then a chain of moves:
  `right(wheel_x) fwd(r) zrot(a) wheel();`. If two rotations cancel out to fix
  a part's orientation, rebuild the part in the right frame instead.
- A part that carries others can place them at the mounting point with
  `children()`: `module sg90() { ...; down(4.5) children(); }`. Label numbered
  slots: `children(1); // stepper`.
- A one-statement module can drop the braces:
  `module pcb() color("#3638") up(ep) cuboid([70,50,1.6-ep*2],anchor=BOT);`
- Use `attachable()` only for parts you `attach()` or anchor, and add a
  `named_anchor` only when something uses it:

  ```openscad
  module rod5(l=100,anchor=CENTER,spin=0,orient=UP) {
      attachable(anchor,spin,orient,d=5,l=l) {
          color_this("#bbb") cyl(d=5,l=l);
          children();
      }
  }
  ```

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
  transparency (`"#3638"`). Use `color_this()` inside attachables. No RGB float
  vectors.

## Comments

- Sparse. One or two lines above a module when its origin or orientation isn't
  obvious ("PCB face at the origin, pins along X, mating ends +Z"), a short
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
- `attachable()` with anchors nothing uses.
- `_private` names, RGB float colours, `$fn` on ordinary round parts.
