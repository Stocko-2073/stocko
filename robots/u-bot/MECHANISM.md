# U-bot mechanism

U-bot is an outdoor utility robot base intended to carry interchangeable tools.
The current [CAD model](u-bot.scad) defines the mobile base: two independently
driven wheels, two passive swivel casters, and a rigid U-shaped chassis with a
battery compartment across the rear. The opening between the side housings is
available for tools; no working tool is included yet. The intended environment
is grass and rough concrete, as described in [README.md](README.md).

This document records the mechanism and its apparent design intent. Dimensions
are nominal millimetres from the CAD, not measurements of a finished robot.
Where a feature's purpose is inferred or unfinished, that is stated explicitly.
Electrical control, calibration and bench results belong in
[firmware/DRIVE_MECHANISM.md](firmware/DRIVE_MECHANISM.md).

## Layout and motion

In the assembled model, X runs across the robot, Y runs along it, and Z is up.
The drive wheel axes lie along X at approximately Y = 0, Z = 0. This document
calls the open end of the U the front (negative Y), and the battery body the
rear (positive Y). These names describe the mechanical layout, not a verified
firmware direction convention. The model origin is at axle height; the
commented `up(107.5)` would raise it approximately onto a Z = 0 ground plane.

Each drive motor turns one wheel through a right-angle bevel gear pair. Equal
wheel ground speeds produce straight travel; different speeds turn the robot;
opposite speeds allow it to turn about the midpoint of the drive axle. The
rear casters swivel to follow the resulting motion. There is no steering motor,
steering linkage, differential gearbox, or suspension joint in this model.

The chassis consists of a rear `body()` and two mirrored `leg()` housings. Here
“leg” means a rigid side housing, not an articulated walking limb. Each houses
a motor, wheel bearing carrier and encoder, with a removable inner cover.
Rectangular tongues on the body fit sockets in the legs, with two transverse
M5 fastening positions per joint. Wire slots lead through the body near these
connections. The model provides holes and nut traps for these joints but does
not instantiate every assembly screw.

## Drive wheel assemblies

There is one complete drive assembly on each side:

```text
NEMA 17 motor -> 12-tooth bevel pinion -> 40-tooth wheel gear and tread
                                                    |
                                             bolted rotating axle
                                                    |
                                             magnet -> AS5600

Wheel loads -> axle -> two bearings -> axle mount -> leg -> rear body
```

The motor shaft runs fore-and-aft, perpendicular to the wheel axle. The model
uses a NEMA 17 motor envelope with a 39 mm body and 30 mm shaft; the housing
cutout allows a 50 mm motor body. Four M3 positions fasten the motor face to
the leg. These envelopes do not specify a motor torque or electrical rating.

`drive_gear()` has a round nominal 5 mm shaft bore with clearance and three
radial M3 screw positions, each with a captive-nut pocket. These screws appear
intended to secure the pinion to the shaft. A keyed or D-shaped bore is not
modeled. Both gears are straight bevel gears (`spiral=0`), module 5, with a
22 mm requested face width; intersections trim their final shapes.

The 12:40 pair gives a 40/12 = 3⅓:1 speed reduction. One motor revolution
turns the wheel 0.3 revolutions. Ideal output torque is multiplied by 3⅓ before
losses. The motor and bearing carrier have fixed mounting positions; no
explicit gear-mesh adjustment mechanism is modeled.

`wheel()` integrates the large bevel gear, wheel structure, tread and axle
hub into one part. It has two staggered circumferential rows of 20 lugs each.
Their nominal radial placement gives approximately 215 mm tread diameter;
this is the nominal rolling diameter used in the firmware mechanism notes.
The local `id=208` and `od=218` variables are unused and do not define the
wheel size. Effective rolling diameter on soil or grass depends on penetration
and slip. There is no separate tire part or specified tread material.

The wheel fits over a separate rotating `axle()`. An M5 transverse bolt and
captured nut couple the wheel hub to the axle. The axle has a shoulder at its
inboard end and small longitudinal crush ribs at the bearing fits. Two 6902ZZ
bearings support it in `axle_mount()`, with corresponding bearing locations
30 mm apart. The installed BOSL2 bearing definition is 15 mm bore, 28 mm outer
diameter and 7 mm width. The outer races sit in the stationary carrier; the
inner races turn with the axle.

This separates the wheel's primary support from the motor shaft. Gear forces
still act on both shafts, including thrust from the bevel mesh. Shoulders,
seats, fitted parts and the wheel bolt provide the apparent locating scheme;
the source does not specify an axial preload or endplay target. The carrier
fits into a matching opening in the leg and is secured at four M3 positions.

## Wheel angle sensing

Each axle carries a modeled 4 mm diameter × 2 mm magnet at its inboard end.
A stationary AS5600 board faces it along the axle axis. `as5600_mount()`
locates the board with a square opening and four small locating features;
`as5600_mount_cap()` retains it. Two M3 through-fastening positions and nut
traps join the sensor mount/cap to the bearing carrier.

The encoder therefore measures output axle angle, after the gearing, rather
than inferring wheel motion from commanded motor steps. With the wheel bolt
secure, this is also wheel angle. It cannot by itself measure wheel slip
against the ground. Magnet magnetization, installed sensor gap and acceptable
alignment are not specified in the CAD. The imported AS5600 STL represents
the board geometry; it is not a complete electrical specification.

## Rear casters

There are two identical passive caster assemblies beneath the rear body, with
vertical swivel axes approximately at X = ±104.75, Y = 161.25. Each has a
nominal 60 mm rolling diameter and 50 mm overall transverse width. The
`caster_leg_len=90` parameter locates the wheel axis relative to the top of
the stem; it is not the caster's overall height.

Each caster has two separate rounded `caster_side()` rollers, one on either
side of a 13 mm thick central leg. Each roller runs on its own 6902ZZ bearing,
so the two sides can rotate independently. This should reduce scrubbing as
the caster changes heading. Printed axle caps pass through the roller
bearings and central leg; spacers locate the inner assembly, and an M4 bolt
and nut hold the transverse stack together. Crush ribs appear at the bearing
fits. The intended stationary structure is the leg/caps/inner races, with the
rollers turning on the outer races.

The central leg rises into an offset vertical swivel stem. Two more 6902ZZ
bearings, seated in the body, support that stem. The wheel axis is offset
19 mm horizontally from the swivel axis, providing caster trail. The
displayed 180° orientation places the wheel axis toward the front of the
robot relative to its swivel axis; this is an assembly pose, not a steering
constraint. A free caster can reverse its heading when travel reverses.

The stem is divided into `caster_leg_bottom()` and `caster_leg_top()` near
the upper bearing. There is a small clearance at the split, an axial M3 screw
passage with a nut trap, and a slot across the top. A removable top appears
intended to permit assembly and retention through the body bearings. The top
slot now locates a separate magnet holder. The axial screw is not shown in
`caster()` even though its accommodation is modeled.

The body also contains two features labeled “caster encoder screw holes” per
caster. The designer confirms that these are for magnetic encoders measuring
passive caster swivel angle. **The caster encoders are still in progress.**
The intended arrangement has a magnet at the top of each caster stem turning
with the caster, while the encoder remains fixed to the body. This measures
caster heading, not roller rotation, and does not actuate the caster. It is
not yet a completed or verified feedback system.

The CAD now includes three custom parts per caster:

- `caster_as5600_mount()` seats the 24 mm square board in a 24.4 mm opening,
  with four locating pins and corner supports, following the drive encoder
  mount's arrangement. Its two ears match the existing body holes at local
  (15, −10) and (−10, 15) relative to the swivel axis.
- `caster_as5600_mount_cap()` retains the board from above. Two M3 × 16 button
  head screws pass through the cap and mount into the existing body fastening
  positions and captive-nut pockets. The cap's central opening provides access
  to the wire connections. The opposite caster uses mirrored mount/cap parts.
- `caster_magnet_holder()` has an 18.6 mm long, 4.6 mm wide, 4.8 mm high tongue
  with rounded ends that fits the existing 5 mm wide stem slot. A central
  7 mm diameter boss raises the magnet pocket by 0.97 mm, making the overall
  height 5.77 mm while preserving the fit in the stem. A 4.2 mm
  diameter, 2 mm deep pocket holds the same nominal 4 × 2 mm magnet used at
  the drive axles. The slot keys the insert to the rotating stem. These are
  clearance fits, not snap fits: bond the magnet in its pocket and secure the
  insert in the slot after checking alignment and sensor response.

The stationary `caster_encoder()` assembly is attached to the body, while
the magnet holder belongs to `caster()`, so only the holder follows swivel
motion. The magnet's top is at Z = 23.5 and the downward-facing
sensor package face at Z = 24.5, leaving a nominal 1 mm physical gap. The
mount has a 20 mm diameter underside relief around the 19 mm stem top, allowing
the stem and holder to turn without contacting the stationary mount. This gap
and the printed fits still need physical validation; CAD alignment alone does
not establish encoder performance.

The caster boards use **direct-soldered wires without header pins**, confirmed
by the designer. `caster_as5600_board()` removes the underside header geometry
from the reference mesh for this configuration. The cap top is at Z = 29.7;
the button heads also fit below the closed lid's underside at Z = 32.2. Tall
headers from the original reference mesh would intersect the lid. Wire bends
and solder joints are not modeled, so keep them within the available space.

`caster_encoder_explode` separates the holder, magnet, mount, board, cap and
screws vertically for inspection. Set it to 1 for the exploded view or 0 for
the assembled arrangement; it is currently set to 0.

The model has four bearings per caster, plus two per drive wheel:
**12 × 6902ZZ bearings for the complete base**.

The caster wheel centres are at Z = −77.5. With a 30 mm caster radius, their
bottoms align with the nominal drive-wheel ground plane at Z = −107.5. The
body underside at Z = −35 is consequently about 72.5 mm above that plane;
this is body clearance, not clearance under every part. All four wheel
supports are rigidly attached, so uneven-ground contact relies on terrain,
part compliance and chassis attitude rather than modeled suspension travel.

## Body, battery and access

The rear body's main envelope is 250 mm wide, 140 mm long and 70 mm high,
with rounded rear corners and nominal 3 mm walls in the pocket construction.
It bridges the two side housings and carries the caster bearing seats.

`robot()` includes a 150 × 94 × 65 mm cuboid labeled battery. This establishes
a packaging envelope, not battery chemistry, voltage, capacity or mass.
`body_tray()` is a shallow insert with a cutout around the battery footprint;
it appears to locate the battery near the floor. No separate battery strap,
clamp or connector is modeled.

`body_lid()` fits a recessed lip and has two M3 fastening positions. A 20 mm
hole is cut near its rear centre; its intended function is unspecified.
Each `leg_cap()` closes the inner side of a drive housing and has four M3
fastening positions, giving access to the motor and internal space. The CAD
does not define a sealed enclosure, cable glands, electronics mounting
arrangement or complete wire routing.

## Tool interface

The model has four vertical nominal 15 mm through-holes explicitly labeled
“tool pin hole”: one in each leg and two in the rear body. Their centres form
approximately a 211 mm wide × 71 mm long rectangle (X = ±105.5, Y ≈ 27.8
and 98.8). The openings have chamfered mouths.

These holes locate and mount interchangeable tools around the open working
area. The intended retention, confirmed by the designer, is a bolt through
each used mounting hole with a nut underneath. The mating tool structure and
retaining bolts/nuts are not yet modeled; bolt size and any locating sleeves
or shoulders remain unspecified. No tool actuator or service connector is
included. Tool load capacity, reach and allowable centre of gravity are also
unspecified; they cannot be inferred from the hole diameter alone.

## Parts and assembly intent

The custom parts are organized as separately printable modules. A useful
inventory of the instantiated base is:

| Group | Custom parts |
| --- | --- |
| Rear chassis, one set | `body`, `body_tray`, `body_lid` |
| Each drive side, two sets | `leg`, `leg_cap`, `wheel`, `drive_gear`, `axle`, `axle_mount`, `as5600_mount`, `as5600_mount_cap` |
| Each caster, two sets | Two `caster_side`, `caster_leg_bottom`, `caster_leg_top`, `caster_cap_right`, `caster_cap_left`, two `caster_spacer` |
| Each caster encoder, two sets | `caster_as5600_mount`, `caster_as5600_mount_cap`, `caster_magnet_holder` |

Purchased components shown are two NEMA 17 motors, four AS5600 boards, four
magnets, twelve bearings, the battery envelope and assorted M3/M4/M5
fasteners. This is not a verified purchasing list: some screws exist only as
holes, and helper names do not always match geometry. In particular,
`m3_8()` actually instantiates an M3 × 11 screw, while the motor mounting
holes request length 8. Check actual stacks before selecting screw lengths.

An inferred assembly sequence is to fit the drive bearings and axles, secure
the wheels, mount the motors and pinions, install the bearing carriers and
encoder boards, then close the leg covers. Assemble each caster's rollers,
caps and spacers around the central leg, fit its swivel bearings into the
body, and retain the split stem. Fit each caster magnet holder, solder the
encoder wires, seat the board sensor-side down on its mount, and secure the
cap/mount through the existing body holes. Join the legs to the body, route wiring, and
install the battery insert, battery and lid. Access to captive nuts and gear
fasteners may require adjusting this sequence; it has not been build-tested
for this document.

The source's commented “print” calls provide suggested part orientations,
including mirroring for the opposite leg. The final active call is
`robot()`, an assembly view, not a single printable object. BOSL2 and the
sibling `../lib` files, including the AS5600 mesh, are required. Global
`$slop=0.2` and local overrides provide fit allowances, with crush ribs used
for several bearing interfaces. These values do not establish tolerances for
every printer or material. Colors distinguish parts visually; materials,
infill and structural ratings are not specified.

## Intent still to confirm

The tool mounting and passive caster sensing intent are confirmed. The new
caster encoder mount and separate magnet insert make that interface concrete
in the CAD; printed fit, fastening and sensor operation remain to be checked
on the physical robot.

Other details can remain open without obscuring how the base moves: the lid
hole's purpose, battery retention, final electronics packaging, gear-mesh
and bearing-fit targets, print materials, and operating load/terrain limits.
These are unfinished specifications rather than mechanisms supplied by the
current model. Update this document as those decisions become concrete, and
keep the source focused on geometry and concise implementation comments.
