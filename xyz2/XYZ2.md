# XYZ2: fixed-board copper scriber

Open [xyz2.scad](xyz2.scad) in OpenSCAD with BOSL2 installed. This is a new mechanical prototype for a spring-loaded scribing pen; the earlier `xyz.scad` and its motor models are unchanged.

![Scribing table](xyz2-preview.png)

| Property | Original `xyz.scad` | New `xyz2.scad` |
| --- | --- | --- |
| Nominal envelope, W × D × H | 204 × 243 × 272.3 mm | **214 × 214 × 112 mm** |
| Board | Moving in XY | **Stationary, fully backed** |
| Board top above bench | 108.6 mm | **10.6 mm** |
| XY travel | 70 × 90 mm | **70 × 90 mm** |
| Z function | 40 mm screw-driven travel | **5 mm servo lift, spring-loaded contact** |
| Guide rails | Three, stacked X/Y/Z | Three: two Y, one X |
| Actuators | Three NEMA17 motors | Two supplied NEMA17 shaft motors + one micro servo |

The bounding box is about **59% shorter and 8% smaller in footprint**. Most of the saving comes from removing the stacked table and long Z motor/screw. The 100 mm TR8 motor is not used in this version. The low board and short pen overhang also shorten the path through which cutting forces reach the frame.

## How it works

The standard NEMA17 drives a single Y belt outside the right linear rail, away from the board and tool travel. Its pulley and idler centres are at X=85 mm, 23 mm outboard of the rail centre. The bridge foot extends outward to grip the outer belt strand; the motor stand's side wall is also outboard. The base is 214 mm wide to support the relocated drive. A rigid printed bridge rides on two MGN12H blocks, one at each side of the board. The pancake NEMA17 rides on that bridge and drives X. The board rests on a removable, fully supported 3 mm backing plate and is secured by four edge clips.

The tool cartridge guides a round **8 mm scribe shank** through two short printed bores. A compression spring pushes a split collar, clamped to the shank, downward. A servo arm lifts a fork on the collar to retract the pen. Its raised circular contact pad clears the arm body and stock servo horn. At the cutting position the arm has a nominal **0.4 mm gap**, leaving the spring to apply the load.

![Tool carriage, including saddle and mounting screws, shown with 5 mm lift](xyz2-head.png)

The servo mounts on two flat ear seats with M2 screws. The saddle's four bearing screws are recessed below its front face, and the cartridge has open channels for its dock screws. The 13 mm lift arm places its contact pad beyond the two horn screw heads. Install the saddle and empty cartridge before the servo and moving linkage so the dock screws remain accessible during assembly.

`pen_lift` is nominal lift above the board, **not a commanded copper cutting depth**. The drawing assumes the tip is supported by the board at zero lift. With no board under it the spring can lower the pen until the lift arm catches the fork; zero the mechanism with stock installed. Repeated cutting passes require the same XY path; use 5 mm lift for traverses over the clips.

The collar position sets spring preload. Default preload is 2 mm, adjustable in the model from 0.5 to 4 mm. The servo angle is calculated from the collar position and requested lift. This gives approximate load `spring rate × preload`; friction and actual spring rate must be measured. `spring_rate=0` deliberately leaves force unspecified. Enter a measured rate in N/mm to have the console echo the nominal contact force.

## BOM

Purchased items:

| Qty | Item | Notes |
| ---: | --- | --- |
| 1 | Existing NEMA17, 39 mm body, 5 mm shaft | Y motor, shaft down |
| 1 | Existing pancake NEMA17, 22.5 mm body, 5 mm shaft | X motor, shaft forward |
| 3 | MGN12H rail and long block, **150 mm** | 45.4 × 27 mm block, 13 mm assembled height, 20 × 20 mm M3 pattern |
| 2 | 20T GT2 pulley, 2 mm pitch, 6 mm belt, 5 mm bore | Hub/flange envelopes must match the model or be adjusted |
| 2 | Matching 20T GT2 idler, integrated bearings, 3 mm bore | Model: 18 mm flange, 10 mm overall width |
| ~0.8 m | Open GT2 belt, 6 mm wide | Approximate cuts: **372 mm X, 408 mm Y**, including 20 mm trimming allowance each |
| 1 | Hitec **HS-65MG** with supplied plastic cross horn and retaining screw | Separate dimensioned model in `hs65mg.scad`; trim/drill the horn as below |
| 1 | Compression spring | Nominal free length 24 mm, mean diameter 9.4 mm, wire 0.7 mm; about 10.1 mm OD / 8.7 mm ID. **Select/calibrate the rate experimentally.** |
| 1 | Round-shank scribing pen | Default 8 mm diameter, 70 mm tip-to-end length; carbide/diamond tip selected by experiment |
| 1 | 70.4 × 90.4 × 3 mm backing plate | Can be printed using `part="backing"` or cut from flat sacrificial material |

Fasteners:

| Qty | Item | Use |
| ---: | --- | --- |
| 34 | M3 × 8 socket screws | 18 rails, 4 Y motor, 8 Y blocks, 4 board clips |
| 4 | M3 × 6 socket screws | Recessed X saddle-to-block screws |
| 12 | M3 × 10 socket screws | 4 X motor, 4 tool dock, 4 belt caps |
| 2 | M3 × 25 socket screws | Y idler axle and recessed pen collar clamp |
| 1 | M3 × 30 socket screw | X idler axle |
| 7 | M3 hex nuts | 2 idlers, 4 tool dock, 1 collar |
| 4 | M2 × 6 socket screws | Two servo ear mounts, two lift-arm-to-horn screws; confirm actual horn thickness |

Pulley set screws and the servo horn's centre retaining screw are assumed to come with those components. Electronics, motor drivers, servo power and limit switches are not modeled or included in this mechanical BOM. The preview includes a short section of servo leads; the full wiring route requires space beyond the quoted envelope.

The rail and belt-grip holes are 2.6 mm pilots for M3 tapping. Through holes are 3.4 mm. Tap the servo bracket's two 1.6 mm pilots M2; each screw passes through a 2 mm ear into 4 mm of plastic. The X saddle screws seat 3.2 mm into 6.2 mm counterbores, leaving 2.8 mm of plastic beneath each head and 3.2 mm nominal block engagement. Tool-dock nuts sit 3.4 mm into the saddle so the M3×10 screws do not project into the X bearing block. Do not substitute longer screws without checking clearance.

## Printed parts and assembly

| Qty | `part` | Role / print notes |
| ---: | --- | --- |
| 1 | `base` | Board bed, Y rail seats, motor stand and front idler support. Print flat; support under the motor shelf. |
| 1 | `bridge` | Both Y feet, X rail/motor mounts and Y belt grip. Back toward bed; support the raised panel. |
| 1 | `saddle` | X bearing adapter, X belt grip and modular dock. Front face down. |
| 1 | `cartridge` | Pen guides, spring seat, modular plate and servo ear bracket. Export places its back on the bed; use supports. |
| 1 | `plunger` | Split pen collar and lift fork. Collar on bed; support beneath the small fork crossbar. |
| 1 | `lift_arm` | Attaches to the supplied servo horn. Flat on bed. |
| 2 | `belt_cap` | Identical clamps for X and Y. Flat on bed. |
| 2 + 2 | `idler_spacer` | Two 4 mm lower and two 1 mm upper spacers; change `spacer_h`. |
| 4 | `board_clip` | Edge clamps, flat on bed. |
| Optional 1 | `backing` | Replaces the cut backing plate. |
| Optional per tool | `tool_blank` | Starting plate for another cartridge; replaces the scribing cartridge. |

That is **16 printed pieces**, plus the optional printed backing. `layout` shows one example of every selectable shape for inspection, not a quantity-correct printer plate. Each individual export has its lowest surface at Z=0. Both large frame pieces fit within a nominal 220 mm square bed; allow extra space if using a brim.

Use a stiff material and adequate perimeters around rail seats and fasteners. PETG is a possible starting material, but the design does not include a validated slicer profile or load rating. Print the cartridge, plunger and lift arm first to test the sliding fit and lifting action before committing to the frame.

Suggested assembly order:

1. Clean up the prints and tap M3 pilots. Check that rail seats and backing are flat. Install both Y rails and the rear Y motor; its connector faces sideways to stay clear of the bridge.
2. Slide on the Y blocks and fasten the bridge with eight M3×8 screws. Install the X rail, pancake motor, pulley and idler. The X motor mounts against the **back of the 8 mm panel** and uses M3×10 screws.
3. Install the Y pulley and front idler outside the right Y rail. Route both Y belt strands on that side of the rail, with the cut ends joining at the outboard bridge grip. Put a 4 mm spacer below each idler and a 1 mm spacer above it. Spacers must contact the **inner bearing races**. Slide idler axles in their ±3 mm slots to tension the belts, then tighten the nuts. Confirm free wheel rotation.
4. Bring each open belt's cut ends together at its moving grip. Engage the printed teeth and install a cap with two M3×10 screws. The preview has a small split at each clamp and uses smooth belt envelopes. When converting an assembled machine from the inboard Y drive, reverse the controller's Y motor direction because the bridge now grips the opposite belt strand.
5. Place four nuts in the back of the X saddle, then attach it to the X block with four **M3×6** screws in the counterbores. Verify the heads sit below the front face. Mount the **empty cartridge** with four M3×10 screws through the front access channels. The tool pattern is **32 × 24 mm**, with a **12 × 16 × 2 mm register**; it differs from the first design.
6. Before fitting the servo, slide the collar/fork into the cartridge from the front. Feed the pen through the lower guide, collar, spring and upper guide. Rest the tip on the installed board, set the spring compression by sliding the collar, and tighten the recessed M3×25 clamp. Refit or ream the guide bores until the pen moves smoothly without obvious sideways play.
7. Assemble the horn and arm on the servo **before mounting the servo**: trim three arms from the supplied cross horn, retaining one arm extending at least 10 mm from the shaft centre. Drill 1.6 mm pilots and tap M2 at radii **4 and 8 mm**, then attach the printed lift arm with two M2×6 screws. Install the horn and stock centre screw on the servo, setting the arm to the contact orientation (−20° at default preload). Slide the complete servo/arm assembly into the open bracket from the front (−Y), with its shaft pointing toward the pen and its wire exit upward. The raised pad slides below the fork with the contact gap. Seat the ear undersides against the two pads and install two M2×6 screws into the tapped bracket, using the middle hole in each ear. For removal, undo the ear screws and withdraw the servo/arm assembly toward the front; the fork blocks pulling the horn straight off the shaft while the servo is mounted. Remove the servo assembly before accessing the upper-left dock screw.
8. With the arm disengaged, verify spring loading and tip contact. Calibrate servo positions for contact clearance and 5 mm lift. Check all corners slowly and verify belt tracking before trying repeated scribing passes.

The servo is modeled directly in [hs65mg.scad](hs65mg.scad), using native OpenSCAD solids and the dimensioned drawing in [Hitec's HS-65MG specification v2.2](https://www.hiteccs.com/public/uploads/data_sheet/HCS_HS-65MG_Specsheetv2.2_10-1729888021.pdf). No imported mesh or STEP file is required. The case is 23.6 × 11.6 mm, the ears span 32.3 mm, and all six mounting holes are Ø2 mm. The middle holes are 28.6 mm apart; the outer pairs are 27 mm apart with 6 mm between rows. The output axis is 5.7 mm from the longitudinal centre, derived from the symmetric mounting pattern.

The specification's table lists a 24 mm height, but its drawing calls out a **20 mm case roof, 26 mm boss face and 3.1 mm exposed spline**, measured from the case bottom. This model follows those explicit drawing dimensions. The ear underside is at 17 mm, the ears are 2 mm thick, and the horn's upper face is at 30.4 mm. Check these heights against the purchased unit before printing the bracket. The bracket seats the ears and allows 0.4 mm clearance around the case opening. The horn stack locates the printed arm at X=−10 mm; the servo axis is at Y=−25 mm to accommodate the longer arm.

Molded contours, seams, the horn outline and factory horn holes, spline tooth form, label and strain relief are approximations of undimensioned details in the drawing. The shaft uses the specified Ø5 mm / 25-tooth envelope; it is not a printable mating-spline specification. The standalone preview shows the stock cross horn; the assembly shows the trimmed and drilled horn. Only a short portion of the specified 160 mm cable is displayed.

![HS-65MG servo model](hs65mg-preview.png)

Open `hs65mg.scad` to inspect the servo alone. In another BOSL2 design, put `include <BOSL2/std.scad>` before `use <hs65mg.scad>`, then call `hs65mg()` for the bare servo or `hs65mg(horn=true)` for the stock horn. Named anchors `mount`, `shaft` and `horn_face` locate its ear underside, output boss and horn upper face. `xyz2.scad` includes the file and disables its standalone demo with `hs65mg_demo=false`.

Guide bores are printed at `pen_d + guide_clearance`, default 8.12 mm. The cartridge relies on those fitted bores for lateral stiffness. It does not have precision linear bushings or a Z rail. Printed fit, friction and wear are therefore important prototype checks, especially for repeat-pass copper isolation.

## Controls and validation

`tool_x` and `tool_y` move the tip relative to the stationary board centre: X = −35…35 and Y = −45…45 mm. `pen_lift` ranges from 0 to 5 mm. `animate_motion=true` uses `$t` to animate XY and the lift linkage. `part="head"` isolates the cartridge; `part="carriage"` also includes the saddle and all dock fasteners for inspection. `part="none"` permits including this file in other designs without drawing its assembly.

```sh
openscad -o cartridge.stl -D 'part="cartridge"' xyz2.scad
openscad -o plunger.stl -D 'part="plunger"' xyz2.scad
openscad -o spacer-top.stl -D 'part="idler_spacer"' -D 'spacer_h=1' xyz2.scad
python3 verify_xyz2.py
```

The verifier checks all eleven printable shapes for closed meshes, connected bodies and print-bed placement. It checks XY corners, intermediate lift positions, preload limits, and collisions with the fixed frame and guide/drive envelopes, including Y belt clearance from the tool and guides and Y cap clearance from the fixed drive. Head checks include all dock, collar, horn and servo mounting fasteners against the printed parts they attach to, cartridge/saddle overlap, and interference between the two horn screw heads. Only the intended M2 pilot engagement is masked in the servo bracket. Driver access is checked at the assembly stages above, along with cartridge, collar and complete servo/arm insertion sampled every 2 mm. It rejects out-of-range motion. The script imports the unchanged mesh-inspection helper from `verify.py`.

These are nominal geometry checks, not a cutting test or a structural analysis. They exclude intentional spring, threaded-fastener, bearing-seat and tool/board contact. The four clip toes each cover roughly 2 × 8 mm of the board edge; avoid them in cutting paths and retract before crossing them. The current prototype has no end-stop switches or force feedback. A one-sided Y drive also needs a physical check for bridge twisting under scribing load.

For direct copper isolation, first scribe test shapes on scrap, inspect the groove and burrs, and measure resistance between the separated regions. A visible scratch alone does not establish electrical isolation. Use those trials to choose tip geometry, preload and pass count before attempting a circuit.

References: [Hitec HS-65MG specification](https://www.hiteccs.com/actuators/product-details/HS-65MG), [HIWIN MGN guideway catalog](https://www.hiwin.com/wp-content/uploads/Linear_Guideway-E.pdf), and [2L's spring-loaded drag-engraving description](https://www.2linc.com/diamond-drag-engraving-spring-loaded-tool/). They inform component envelopes and the mechanism concept; they do not validate this prototype for PCB isolation.
