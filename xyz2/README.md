# Compact XYZ protoboard table

Open [xyz.scad](xyz.scad) in OpenSCAD with BOSL2 installed. It assembles the existing motor models into a moving XY board table and a fixed column carrying the Z tool. The supplied motor files are unchanged.

![XYZ table assembly](preview.png)

| Property | Default |
| --- | --- |
| Protoboard | **70 × 90 × 1.6 mm** |
| Tool travel over board | **70 × 90 × 40 mm**, spanning the board edges |
| Base footprint | **204 × 243 mm** |
| Overall height | **272.3 mm** |
| Board top above bench | 108.6 mm |
| X drive | Existing 39 mm NEMA17, GT2 belt |
| Y drive | Existing 22.5 mm pancake NEMA17, GT2 belt |
| Z drive | Existing NEMA17 with integrated 100 mm TR8×8 screw and shipped flange nut |
| Guides | Three identical 150 mm MGN12H rails, one long carriage each |

This is a printable mechanical prototype for light tools such as a pen, probe or dispenser. Stiffness, backlash, belt tension and tool repeatability require physical testing. There is no claimed machining capacity. The single rail on each axis reduces the purchased parts count; the existing short lead screw is reserved for Z so XY can cover the full board.

## Mechanical BOM

| Qty | Purchased item | Model assumptions |
| ---: | --- | --- |
| 1 | NEMA17, 39 mm body, Ø5 mm D shaft | `nema17()` |
| 1 | NEMA17 pancake, 22.5 mm body, Ø5 mm D shaft | `nema17_pancake()` |
| 1 | NEMA17 with integrated TR8×8, 100 mm screw | `nema17_tr8()`; includes the supplied Ø22 mm, 16 mm PCD nut |
| 3 | MGN12H rail + long carriage, 150 mm | 45.4 × 27 mm block; 13 mm assembled height; 20 × 20 mm M3 block pattern |
| 2 | GT2 20-tooth drive pulley, 2 mm pitch, 6 mm belt, 5 mm bore | Nominal 16 mm hub, 18 mm flange, 14 mm overall height; set screw supplied with pulley |
| 2 | Matching GT2 20-tooth idler, integrated bearings, 3 mm axle | Nominal 18 mm flange, 10 mm overall width; see fit notes |
| ~0.75 m | Open GT2 belt, 2 mm pitch, 6 mm wide | Cut two approximately **364 mm** lengths; trim during assembly |
| 42 | M3 × 8 socket screws | 18 rail, 12 motor, 4 Z carriage, 4 TR8 nut, 4 board clips |
| 4 | M3 × 10 socket screws | Belt clamps |
| 8 | M3 × 16 socket screws | X and Y bearing-to-print connections |
| 8 | M3 × 20 socket screws | Four column foot, four tool plate |
| 2 | M3 × 25 socket screws | Adjustable idler axles |
| 10 | M3 hex nuts | Four column foot, four tool dock, two idler axles |
| Optional: 1 each | M3 × 20 screw and M3 nut | Example pen clamp |

Only M3 fasteners are used. Rail and belt-clamp screws go into **2.6 mm printed pilot holes**, to be tapped M3 after printing. The four dock nuts sit in accessible hexagonal pockets. The TR8 flange uses the supplied nut's M3 holes. Fastener lengths account for the shallow motor and rail-block threads; confirm actual thread depths before tightening.

Control electronics, drivers, power supply, wiring and homing switches are outside this mechanical BOM. The current design assumes manual zeroing. It does not include physical travel stops or a power-off Z brake; the high-lead Z screw can back-drive.

## Printed parts

Select a value of `part` to export a single part. All single-part exports sit on Z=0.

| Qty | `part` | Printing / role |
| ---: | --- | --- |
| 1 | `base` | Deck face down, feet upward; 204 × 243 mm bed area |
| 1 | `y_frame` | Deck face down; integral X riser and belt grip |
| 1 | `tray` | Integral riser, Y belt grip, board ledges and clip posts; supports under raised tray |
| 1 | `column` | Back toward bed; supports under recessed panel and motor shelf |
| 1 | `z_carriage` | Bearing flange toward bed; supports may be needed for nut shelf / dock |
| 1 per tool | `tool_plate` **or** `pen_adapter` | Blank modular plate or example split pen clamp; pen adapter needs support |
| 2 | `belt_clamp` | Flat on bed; both axes use the same cap |
| 2 | `idler_spacer`, `spacer_height=4` | Under the idler's inner bearing race |
| 2 | `idler_spacer`, `spacer_height=1` | Above the idler's inner bearing race |
| 4 | `board_clip` | Edge clamping without drilling the board |

That is **16 printed pieces** with one tool adapter. `print_layout` shows one example of each shape for inspection; it is not a ready-to-print, quantity-correct bed layout. The base requires more than a 220 mm square bed.

Use a stiff print material, sufficient perimeters, and solid regions around fasteners. Check rail-seat flatness after support removal. Fit the Ø3.4 clearance holes, M3 pilot holes, belt teeth and tool register with a small sample before committing to the large prints. A roughly 0.2 mm layer height is a starting point, not a validated print profile.

## Assembly

1. Tap the rail and belt-grip pilot holes. Bolt the X motor under the base, mount its rail, and fit its drive pulley. Fit the idler using a 4 mm lower spacer, 1 mm upper spacer, M3×25 axle and nut beneath the deck. The axle slot provides ±3 mm of belt adjustment.
2. Mount the pancake motor and Y rail on `y_frame`. Fasten that frame onto the X block with four M3×16 screws through the 3 mm counterbores. The 11 mm riser lets the pancake body clear the base. Mount the second pulley and idler.
3. Run each open belt around its pulley and idler, bringing both cut ends together at the moving grip. Engage the printed teeth and clamp with two M3×10 screws **above** the belt. Shift the idler to tension it, then tighten its axle. The model shows smooth belt envelopes and a small split at the clamp.
4. Bolt `tray` to the Y block with four M3×16 screws. Its integral 9 mm riser clears the uncut 24 mm motor shaft. The board rests on side ledges with 3 mm underneath for solder tails. Use the four clips and M3×8 screws to hold the edges. The model preserves the supplied solid `board()` shape; it does not invent a hole pattern.
5. Bolt the column to the base with four M3×20 screws and nuts. Install the Z rail, carriage and arm. Feed the integrated screw through its shelf and nut mount, then fasten the motor from underneath the shelf. The nut stub faces the motor and the flange seats on the **top** of the moving nut shelf; four M3×8 screws enter from below.
6. Seat four M3 nuts in the back of the tool dock. Attach the selected tool plate with four M3×20 screws. Fit and zero the tool before powered movement. The example pen is Ø8 mm; its split clamp adds one M3×20 screw and nut.

Pulley and idler envelopes vary between sellers. The modeled belt center is **9 mm above each rail mounting deck**. Set the drive pulley at that height, and adjust spacer heights to the actual idler bearing faces. Spacers must bear on the inner races so tightening the axle does not lock the wheel. Inspect belt alignment and free rotation before running.

## Tool interface and motion

The tool interface is a **36 × 42 × 5 mm** plate with four Ø3.4 mm holes on a **24 × 28 mm** pattern. A **12 × 20 × 2 mm rectangular register** fits the dock pocket with 0.2 mm clearance per side. This register provides coarse location and prevents rotation; re-zero after a tool swap. The four screws provide retention.

Use `tool_plate()` as the base of a new tool adapter. In its local coordinates, the register is centered at `[0,14,0]` and projects toward +Y. The plate's tool face is at Y=9; the example tool axis is at X=0, Y=0. The tool tip datum is Z=−50. Keep additional tool geometry clear of the moving board and column. To include the file in another design without drawing the table, set `part="none"` after the include.

`tool_x` and `tool_y` refer to the contact point relative to the **board center**. X is −35…35 mm and Y is −45…45 mm. Because the board moves, its displacement is the negative of these values. `tool_z` is the tip height above the board top, from 0…40 mm. `xyz(x,y,z)` also accepts those coordinates directly. `animate_motion=true` uses OpenSCAD's `$t` animation; `show_envelope=true` overlays the usable volume in preview.

The Z nut stays fully on the 100 mm screw throughout the commanded range. The rails retain the whole carriage, with 17.3 mm end clearance on X and 7.3 mm on Y at maximum travel. The rear tray edge stays at least 12 mm from the column panel. The four clip toes each cover a small 2 × 8 mm strip at the board edge: avoid these fixtures in toolpaths and lift Z before traversing them. These are nominal CAD clearances; cable loops and other tools need their own clearance checks.

## Export and verification

```sh
openscad -o tray.stl -D 'part="tray"' xyz.scad
openscad -o tool-plate.stl -D 'part="tool_plate"' xyz.scad
openscad -o spacer-top.stl -D 'part="idler_spacer"' -D 'spacer_height=1' xyz.scad
python3 verify.py
```

`verify.py` renders all ten printable shapes, checks closed meshes, connected bodies and print-bed placement, then checks structural intersections at the center and eight travel corners. It also checks Z motor / carriage screw-head clearance and rejects out-of-range configurations. Contacting hardware such as bearing races, threaded joints and belt teeth is excluded from structural collision tests. These checks do not simulate loads, backlash, thermal effects or manufacturing tolerances.

The design was checked using OpenSCAD 2026.08.27 and local BOSL2 2.0.716. `show_threads=true` enables the existing detailed TR8 screw model; it is off by default for responsive previews.

Rail dimensions follow the MGN12H table in [HIWIN's linear guideway catalog](https://www.hiwin.com/wp-content/uploads/Linear_Guideway-E.pdf). The 20-tooth, 2 mm pitch pulley calculation is consistent with [Grob's GT pulley data](https://grobinc.com/gt/). Hardware in this model represents mounting and clearance envelopes, not manufactured raceway or belt-tooth geometry.
