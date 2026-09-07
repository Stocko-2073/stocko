# XYZ3 T-bot scribing platform

Open `xyz3.scad` in OpenSCAD with BOSL2 installed. Keep `xyz2.scad`, `nema17.scad`, and `hs65mg.scad` alongside it: the existing scribing cartridge and board fixtures are reused. Earlier models are unchanged.

![T-bot assembly](xyz3-preview.png)

The fixed cross rail carries an X carriage. An inverted Y rail slides through a second block on that carriage, carrying the fore/aft arm and tool. Both NEMA17 motors remain on the base. One open GT2 belt runs around both motors, four corner idlers on the X carriage, and two larger end idlers on the arm. Its cut ends meet under the arm's left belt clamp. This follows the differential, single-belt T-bot family illustrated by [Bart Dring's midTbot](https://github.com/bdring/midTbot_esp32).

| Property | Model |
| --- | --- |
| Working travel | 70 × 90 mm; tool coordinates relative to board center |
| Board | Fixed 70 × 90 × 1.6 mm, on 3 mm backing |
| Pen lift | Existing spring cartridge and HS-65MG servo, 0–5 mm |
| Guide rails | Two 150 mm MGN12H rails with one block each |
| Motors | Existing 39 mm NEMA17 and 22.5 mm pancake NEMA17 |
| Base print | 246 × 208 × 86 mm |
| Arm print | 228 mm long; exceeds a 220 mm bed in this orientation |
| Belt | 6 mm GT2, approximately 813.9 mm pitch-path length |
| Pulleys | Two 20T motor pulleys; four matching corner idlers |
| Arm end idlers | Two larger idlers: 35.27 mm pitch diameter, 33.87 mm modeled running OD, 40.47 mm flange OD, 10 mm width |

The arm projects behind the base and sweeps to Y=283 mm; allow additional room for wiring and the end pulley flange. This configuration reduces moving motor mass but increases the required space behind the board. The large end idlers are explicit design envelopes, **not a verified catalog selection**. Select suitable bearing idlers and adjust `c`/`R` to their effective belt radius before fabrication. The four small idlers and two end idlers use M3 axles with race spacers. The model shows smooth belt envelopes, not individual belt teeth.

## Controls and exports

Use `tool_x`, `tool_y`, and `pen_lift`, or enable `animate_motion`. `show_envelope` overlays the working area. `part="belt"` isolates the full belt route. Select `base`, `cross_carriage`, `arm`, or `belt_clamp` for the new prints. The cartridge, plunger, lift arm, board clips, and backing can also be exported through their existing part names. The inherited cartridge uses the default dimensions from XYZ2; see [XYZ2.md](XYZ2.md) for its spring, servo and assembly details.

```sh
openscad -o xyz3-arm.stl -D 'part="arm"' xyz3.scad
python3 verify_xyz3.py
```

The relative motor belt distances are A=X+Y and B=X−Y with a suitable choice of motor signs. A 20T GT2 pulley moves 40 mm per revolution. Configure differential motion in the controller and verify motor direction at low speed before using the tool. The model echoes these distances; it does not generate firmware or step signals.

The horizontal belt runs exchange length as X moves. The front and rear vertical runs exchange length as Y moves. Their sum and the pulley wrap lengths stay constant. The Y block is offset 30 mm behind the X block so their mounting screws are accessible from opposite sides without sharing screw axes. At full travel the rail end margins are 17.3 mm on X and 7.3 mm on Y.

## Assembly notes and limits

Mount the X block to the cross carriage with four recessed M3×6 screws from above. Mount the inverted Y block with four recessed M3×6 screws from below, before installing the carriage on the X rail. Bolt the Y rail underneath the arm through its six clearance holes. Rail-seat pilot holes and idler posts are intended for M3 tapping; check the purchased hardware's thread engagement. Install the tool-dock nuts before attaching the cartridge. The base motor shelves and arm dock require print supports.

Start with about 850 mm of open belt and trim after routing. Pull the ends taut at the left-arm clamp, then tighten its two transverse screws. This first version has a smooth friction clamp and manual tension setting; belt retention and tension must be proven physically. Use inner-race spacers so axle tightening does not lock an idler. Most mounting screws are omitted from the assembly view for clarity.

`verify_xyz3.py` checks the four new prints for closed, connected meshes and bed placement, checks primary frame intersections at center and four XY corners, and compiles all eight XY/lift corners without warnings. These checks exclude the complete hardware and belt contact audit. This is a mechanical prototype, not a validated fabrication package or a demonstrated copper-cutting machine; arm stiffness, belt retention, idler selection and scribing repeatability remain to be tested.
