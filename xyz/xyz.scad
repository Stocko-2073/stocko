// xyz.scad -- compact XYZ cartesian table for working on a 90 x 70 mm protoboard.
//
// Layout: a stacked XY table (X stage on the base, Y stage riding on the X
// carriage, work table on the Y carriage) and a Z column at the back whose arm
// carries a dovetail tool mount over the table centre. The board moves under a
// tool that only moves in Z, so tools can be heavy and swapped without touching
// the work. One printed frame and one printed carriage serve all three axes.
// The XY mechanism is turned so both motors point away from the column (X motor
// on the right, Y motor at the front) and only the short end of the Y frame
// faces it; the Y nut runs toward the screw tip just enough that this end stays
// inside the table's sweep, so the column sits as close as the table allows.
//
// Motion: three NEMA 17 steppers with integrated TR8x8 100 mm lead screws
// (nema17_tr8.scad), the shipped Ø22 flange nut bolted to the carriage. Each
// carriage rides on two Ø8 rods with four LM8UU bearings. The lead screw runs
// between the rods and the carriage passes over the motor at the end of travel,
// which is what lets the whole stage be only 153 mm long for 84 mm of travel.
//
// BOM (printed parts aside):
//   3  NEMA 17 + TR8x8 100 mm lead screw motor, with its flange nut
//   6  Ø8 x 150 mm hardened steel rod
//   12 LM8UU linear bearing
//   1  base plate, 200 x 233 x 6 mm (plywood, MDF or acrylic; can be printed)
//   M3 socket screws: 41 x 8, 12 x 10, 4 x 12, 8 x 16 with 8 M3 nuts (see bom())
// Printed: 3 frames, 3 carriages, 1 table, 1 arm, 1 column, 4 board dogs, and
// one tongue per tool. Screws into printed parts thread into 2.6 mm holes.
// Overall 200 x 233 mm on the base plate, 226 mm tall; the arm reaches 75 mm
// from the Z carriage to the tool axis.
//
// Assembly: each frame bolts down through its base with four screws either side
// of the lead screw; slide the carriage to the far end to reach the pair behind
// the motor wall. The board drops into the table pocket and is held by four dogs
// on the long sides. X frame and column foot bolt through the base plate with nuts;
// the Y frame screws into the X carriage, the Z frame into the column, the table
// into the Y carriage, the arm into the Z carriage. Motors go in last, screws
// from inside the frame. Rods are held by an M3 into the top of each end wall.
// Tools carry a 16 mm dovetail tongue (tool_tongue()) that drops into the slot
// on the arm and is pinched by the M3 in the side of the block; the slot floor
// sets the tool height, so tools repeat.
//
// Printing: frame and table flat as modelled, carriage plate down, arm on its
// root plate, column flat on its back (220 x 88 mm, diagonal on a 220 bed).
//
// Tool position: xyz(x, y, z) puts the tool at (x, y) from the board centre,
// z above the board surface. x in ±x_travel/2, y in ±y_travel/2, z in
// -z_below .. z_travel - z_below.
//
// Export one part in print orientation:
//   openscad -o frame.stl    -D 'part="frame"'    xyz.scad
//   part = frame | carriage | table | arm | column | tongue | pen | dog | base
//   (part = none draws nothing, for files that include this one)
//
// Stage-local frame (stage(), stage_frame(), stage_carriage()): travel along +X,
// lead screw on the X axis, the motor's pilot face at the origin and its body
// toward -X, rods at y = ±rod_sp/2 on the screw axis, base underneath.
include <nema17_tr8.scad>
include <BOSL2/screws.scad>
include <BOSL2/linear_bearings.scad>
include <BOSL2/joiners.scad>
nema17_tr8_demo = false;

$fn=0;$fa=1;$fs=$preview?0.5:0.25;
$slop=0.2;
ep=0.01;

part      = "assembly";   // assembly | frame | carriage | table | arm | column | tongue | pen | dog | base
fast      = $preview;     // plain cylinders instead of threads, no screws
hardware  = !fast;        // draw the M3 screws
show_board = true;
show_tool  = true;

// tool position over the board: x, y from the board centre, z above its surface
tool_x = 0;
tool_y = 0;
tool_z = 15;

x_travel=84;
y_travel=66;
z_travel=50;
z_below=3;                // how far below the board surface the tool can reach

board_x=90;
board_y=70;
board_z=1.6;

col_print = "#e8762c";
col_steel = "#c8c8c8";
col_base  = "#c9a66b";
col_screw = "#888";

// -- linear stage -------------------------------------------------------------
rod_d    = 8;
rod_len  = 150;
lm8      = lmXuu_info(8);             // [od, len] = [15, 24]
brg_d    = lm8[0];
brg_len  = lm8[1];
brg_fit  = 0.1;                       // added to the LM8UU bore; tune for your printer
wall     = 5;                         // printed plate thickness
tap_d    = 2.6;                       // M3 thread-forming hole in plastic
thru_d   = 3.4;                       // M3 clearance
mclear   = 0.5;                       // motor body to frame base

mwall_w  = n17_w + 2;                 // motor mount wall, 44 wide, only as tall as the motor
mwall_h  = n17_w/2;
mwall_x  = -n17_pilot_h;              // the motor face sits on the wall's -X side
blk_w    = brg_d + 5;                 // bearing block width, 20
rod_sp   = mwall_w + 2*(2 + blk_w/2); // 68: the blocks pass the motor wall with 2 mm to spare
frame_w  = rod_sp + blk_w;            // 88: blocks flush with the frame sides
frame_x0 = -(n17_pilot_h + n17t_len + 1.3 + wall);   // -47, rear wall behind the motor
frame_x1 = tr8_len - n17_pilot_h + 3 + wall;         // 106, far wall 3 mm past the screw tip
frame_z0 = -(n17_w/2 + mclear + wall);               // -26.5, base underside
ewall_h  = rod_d/2 + 4;               // end walls hold the rods and stop there
rod_x0   = frame_x0 + wall - 3;       // rods sit 3 mm into the rear wall, 4 into the far one

car_len  = 2*brg_len + 4;             // 52: two LM8UU per rod with a 4 mm rib between
blk_z0   = -(brg_d/2 + 2.5);          // -10, bearing block underside
plate_z0 = n17_w/2 + 1.5;             // 22.5, carriage plate clears the motor
plate_t  = 5;
stage_h  = plate_z0 + plate_t - frame_z0;   // 54, base underside to carriage top
boss_t   = 8;                         // nut boss at the +X end of the carriage
boss_w   = 26;
boss_z0  = -13;
pattern  = [30, 80];                  // M3 grid on carriage tops (along travel, across), table, arm
frame_pat = [pattern.y, pattern.x];   // the same grid turned 90 deg on frame bases: a frame always
                                      // sits crosswise on the carriage below it
frame_mount = 51;                     // frame-local x of the base bolt grid, both holes clear of the motor

nut_spec   = tr8_nut_spec("motor");
nut_flange = nut_spec[2] + nut_spec[4];               // 5.5: stub + flange, the carriage face
nut_min    = 1.5;                                     // nut stub to pilot face at end of travel
nut_max    = tr8_len - n17_pilot_h - nut_spec[0] - 2; // 85.5: nut fully on the thread, 2 mm from the tip
screw_travel = nut_max - nut_min;                     // 84

// carriage centre for a nut position; the flange bolts to the -X face of the boss
function car_x(nut_pos) = nut_pos + nut_flange + boss_t - car_len/2;
// nut position for a stage of `travel` at `pos`; bias 0.5 centres the unused
// screw, 1 puts the carriage at the tip end (the Z column uses that)
function stage_nut(travel, pos, bias=0.5) = nut_min + (screw_travel - travel)*bias + pos;
car_mid = car_x(nut_min + screw_travel/2);   // 31: carriage centre at mid travel
mount_off = frame_mount - car_mid;           // 20: a frame's bolt grid sits this far toward the far wall
                                             // from its carriage's mid-travel centre

assert(x_travel <= screw_travel && y_travel <= screw_travel && z_travel <= screw_travel,
       str("travel is limited to ", screw_travel, " mm by the 100 mm lead screw"));
assert(car_x(nut_max) + car_len/2 + 1 <= frame_x1 - wall, "carriage hits the far wall");
assert(car_x(nut_min) - car_len/2 >= frame_x0 + wall + 2, "carriage hits the rear wall");
assert(rod_x0 + rod_len <= frame_x1 - 1, "rods too long for the frame");
assert(frame_mount - frame_pat.x/2 >= mwall_x + wall + 5, "frame bolt heads too close to the motor wall");
assert(frame_mount + frame_pat.x/2 <= frame_x1 - wall - 5, "frame bolt heads too close to the far wall");

module m3(len, orient=UP) {
    color(col_screw) screw(str("M3,",len), head="socket", drive="hex", atype="head",
                           thread="none", anchor=BOT, orient=orient, details=false);
}

// Printed frame: base, a wall behind the motor and one past the screw tip holding
// the rods, and a short wall the motor bolts to. The pilot bore is Ø23 so the nut
// flange screws can run right up to the pilot.
module stage_frame() {
    L = frame_x1 - frame_x0;
    diff() {
        union() {
            translate([frame_x0, 0, frame_z0]) cuboid([L, frame_w, wall], anchor=BOT+LEFT, rounding=2, edges="Z");
            translate([frame_x0, 0, frame_z0]) cuboid([wall, frame_w, ewall_h - frame_z0], anchor=BOT+LEFT);
            translate([frame_x1, 0, frame_z0]) cuboid([wall, frame_w, ewall_h - frame_z0], anchor=BOT+RIGHT);
            translate([mwall_x, 0, frame_z0]) cuboid([wall, mwall_w, mwall_h - frame_z0], anchor=BOT+LEFT);
        }
        tag("remove") {
            translate([mwall_x + wall/2, 0, 0])
                nema17_mount_mask(wall, hole_d=thru_d, pilot_clear=1, cbore=1, cbore_d=6, orient=RIGHT);
            ycopies(rod_sp) {
                translate([rod_x0, 0, 0]) cyl(d=rod_d + $slop, l=rod_len, orient=RIGHT, anchor=BOT);
                for (x = [frame_x0 + wall/2, frame_x1 - wall/2])   // rod clamp screws
                    translate([x, 0, ewall_h + ep]) cyl(d=tap_d, l=ewall_h + 2, anchor=TOP);
            }
            translate([frame_mount, 0, frame_z0 - ep]) grid_copies(spacing=frame_pat) cyl(d=thru_d, l=wall + 2*ep, anchor=BOT);
        }
    }
}

// Printed carriage, centred on the origin: plate over the motor, a bearing block
// hanging over each rod, the nut boss at the +X end. Prints plate down.
module stage_carriage() {
    diff() {
        union() {
            up(plate_z0) cuboid([car_len, frame_w, plate_t], anchor=BOT, rounding=2, edges="Z");
            ycopies(rod_sp) up(blk_z0) cuboid([car_len, blk_w, plate_z0 - blk_z0 + ep], anchor=BOT);
            translate([car_len/2, 0, boss_z0]) cuboid([boss_t, boss_w, plate_z0 - boss_z0 + ep], anchor=BOT+RIGHT);
        }
        tag("remove") {
            ycopies(rod_sp) {
                xcopies(spacing=brg_len + 5, n=2) cyl(d=brg_d + brg_fit, l=brg_len + 1, orient=RIGHT);
                cyl(d=rod_d + 3, l=car_len + 1, orient=RIGHT);
            }
            translate([car_len/2 - boss_t/2, 0, 0])
                tr8_nut_mount_mask(boss_t, "motor", hole_d=tap_d, body_clear=0.6, orient=RIGHT);
            up(plate_z0 + plate_t + ep) grid_copies(spacing=pattern) cyl(d=tap_d, l=10, anchor=TOP);
        }
    }
}

// One axis: frame, motor with nut, rods, carriage with bearings. `pos` is 0..travel.
// mount_len > 0 draws the four screws that hold the frame down through its base.
// Named anchors: "origin" (the pilot face on the screw axis, the default so the
// stage-local frame is kept), "carriage" (top of the carriage plate, moves with
// pos), "mount" (underside of the base at the bolt pattern), "pilot".
module stage(travel, pos=0, bias=0.5, mount_len=0, anchor="origin", spin=0, orient=UP) {
    assert(pos >= -ep && pos <= travel + ep, str("stage pos ", pos, " outside 0..", travel));
    nut_pos = stage_nut(travel, pos, bias);
    xc  = car_x(nut_pos);
    top = plate_z0 + plate_t;
    sz  = [frame_x1 - frame_x0, frame_w, top - frame_z0];
    cp  = [(frame_x0 + frame_x1)/2, 0, (frame_z0 + top)/2];
    anchors = [
        named_anchor("origin",   [0, 0, 0], UP),
        named_anchor("carriage", [xc, 0, top], UP),
        named_anchor("mount",    [frame_mount, 0, frame_z0], DOWN),
        named_anchor("pilot",    [0, 0, 0], RIGHT),
    ];
    attachable(anchor, spin, orient, size=sz, cp=cp, anchors=anchors) {
        union() {
            color(col_print) stage_frame();
            left(n17_pilot_h) nema17_tr8(nut="motor", nut_pos=nut_pos, threads=!fast, orient=RIGHT);
            color(col_steel) ycopies(rod_sp) translate([rod_x0, 0, 0]) cyl(d=rod_d, l=rod_len, orient=RIGHT, anchor=BOT);
            right(xc) {
                color(col_print) stage_carriage();
                ycopies(rod_sp) xcopies(spacing=brg_len + 4, n=2) lmXuu_bearing(8, orient=RIGHT);
            }
            if (hardware) {
                // motor, heads sunk 1 mm into the wall's +X face (M3x8 leaves 4 mm in the motor)
                translate([mwall_x + wall - 1, 0, 0]) grid_copies(spacing=n17_hole_sp, axes="yz") m3(8, orient=RIGHT);
                // nut flange, heads toward the motor
                right(nut_pos + nut_spec[2]) xrot_copies(n=4) up(nut_spec[5]/2) m3(8, orient=LEFT);
                // rod clamps
                ycopies(rod_sp) for (x = [frame_x0 + wall/2, frame_x1 - wall/2]) translate([x, 0, ewall_h]) m3(8);
                if (mount_len > 0)
                    translate([frame_mount, 0, frame_z0 + wall]) grid_copies(spacing=frame_pat) m3(mount_len);
            }
        }
        children();
    }
}

// -- work table -------------------------------------------------------------------
// Bolts to the Y carriage. The board drops into a pocket 0.2 mm deeper than it is
// thick; four dogs on the long sides overlap it so it cannot lift. The front and
// back margins are kept thin because the table's sweep sets the arm length.
tbl_size = [board_x + 16, board_y + 6, 8];    // 106 x 76 x 8
pocket_d = board_z + 0.2;
dog_d    = 10;
dog_t    = 2.5;
dog_off  = 2;                                 // dog screw outside the pocket edge
dog_sp   = [board_x + 2*dog_off, 50];         // two dogs per long side

module table() {
    diff() {
        cuboid(tbl_size, anchor=BOT, rounding=4, edges="Z") tag("remove") position(TOP) {
            up(ep) cuboid([board_x + 2*$slop, board_y + 2*$slop, pocket_d + ep], anchor=TOP);
            grid_copies(spacing=[pattern.y, pattern.x]) {
                up(ep) cyl(d=thru_d, l=tbl_size.z + 2*ep, anchor=TOP);
                down(pocket_d - ep) cyl(d=6.2, l=3 + ep, anchor=TOP);    // heads flush under the board
            }
            grid_copies(spacing=dog_sp) up(ep) cyl(d=tap_d, l=tbl_size.z - 1, anchor=TOP);
        }
    }
}

module board_dog() {
    diff() cyl(d=dog_d, h=dog_t, anchor=BOT, rounding2=0.8)
        tag("remove") cyl(d=thru_d, h=3*dog_t);
}

module board(anchor=CENTER,spin=0,orient=UP) {
    attachable(anchor,spin,orient,size=[board_x,board_y,board_z]) {
        color_this("#853") cuboid([board_x,board_y,board_z]);
        children();
    }
}

// -- Z column, arm and tool mount ---------------------------------------------------
base_t   = 6;
board_top = base_t + 2*stage_h + tbl_size.z - pocket_d + board_z;   // board surface, machine z

tbl_sweep_y = tbl_size.y/2 + y_travel/2;      // how far back the table reaches, 71
// Y nut range: shifted toward the screw tip (bias 0.5 .. 1) just enough that the
// frame's far wall, which faces the column, does not reach past the table
y_bias      = screw_travel > y_travel
              ? constrain(0.5 + (frame_x1 - car_mid - tbl_sweep_y)/(screw_travel - y_travel), 0.5, 1)
              : 0.5;
car_mid_y   = car_x(stage_nut(y_travel, y_travel/2, y_bias));   // Y carriage centre at mid travel
mount_off_y = frame_mount - car_mid_y;        // Y frame bolt grid behind the table centre
yframe_back = frame_x1 - car_mid_y;           // the Y stage's far wall behind the table centre
yframe_front = car_mid_y - frame_x0;          // its motor end in front
col_face_y  = max(tbl_sweep_y, yframe_back) + 4;   // where the Z carriage face goes
arm_reach   = col_face_y;                     // carriage face to the tool axis

arm_w    = 24;                 // beam section
arm_t    = 20;
arm_root = [frame_w, 6, 40];   // plate bolted to the Z carriage [x, y, z]
tm_blk   = [28, 20, 30];       // tool mount block [x, y, z]
tm_stop  = 4;                  // slot floor above the block underside
dt_w     = 16;                 // dovetail: width at the face, depth, tongue height
dt_h     = 5;
dt_slide = 26;
tool_off = 10;                 // dovetail face to the tool axis
tool_reach = 25;               // stop face to the tip of the reference tool
tool_drop  = arm_t/2 - tm_stop + tool_reach;   // carriage centre to tool tip, 31

// Z frame origin (pilot face) height: tool tip on the board at z = 0 with the
// carriage at pos = z_below, using the tip end of the screw (bias 1)
z_frame0 = board_top + tool_drop - car_x(stage_nut(z_travel, z_below, 1));
zframe_bot = z_frame0 + frame_x0;

// Arm: origin at the tool axis (x = y = 0) and the carriage centre height.
// Root plate against the Z carriage, beam forward, tool block with a vertical
// dovetail slot open at the top and a lock screw from the +X side.
module arm() {
    beam_l = col_face_y - arm_root.y - tool_off - tm_blk.y;
    slot_l = tm_blk.z - tm_stop + 8;
    diff() {
        union() {
            translate([0, col_face_y, 0]) cuboid(arm_root, anchor=BACK, rounding=3, edges="X");
            translate([0, col_face_y - arm_root.y + ep, 0]) cuboid([arm_w, beam_l + 2*ep, arm_t], anchor=BACK);
            translate([0, tool_off, -arm_t/2]) cuboid(tm_blk, anchor=BOT+FRONT, rounding=2, edges="Y");
        }
        tag("remove") {
            for (dx=[-pattern.y/2, pattern.y/2], dz=[-pattern.x/2, pattern.x/2])
                translate([dx, col_face_y - arm_root.y/2, dz]) cyl(d=thru_d, l=arm_root.y + 2*ep, orient=BACK);
            translate([0, tool_off, -arm_t/2 + tm_stop + slot_l/2]) xrot(90)
                dovetail("female", width=dt_w, height=dt_h, slide=slot_l, chamfer=0.5);
            translate([tm_blk.x/2 + ep, tool_off + dt_h/2, -arm_t/2 + tm_stop + dt_slide/2])
                cyl(d=tap_d, l=tm_blk.x/2 + 2*ep, orient=LEFT, anchor=BOT);
        }
    }
}

// Male dovetail every tool carries. Origin: bottom of the tongue (the stop face)
// on the dovetail's base face, which faces +Y. The tool axis is at y = -tool_off.
module tool_tongue() {
    cuboid([dt_w + 8, 5, dt_slide], anchor=BACK+BOT, rounding=1, edges="Y");
    up(dt_slide/2) xrot(-90) dovetail("male", width=dt_w, height=dt_h, slide=dt_slide, chamfer=0.5);
}

// Sample tool: a Ø10 pen in a clamp, tip tool_reach below the stop face.
module tool_pen(pen_d=10, with_pen=true) {
    color(col_print) diff() {
        union() {
            tool_tongue();
            translate([0, 0, -(tool_reach - 5)]) cuboid([20, tool_off + 8, tool_reach - 5 + 12], anchor=BOT+BACK, rounding=2, edges="Z");
        }
        tag("remove") {
            translate([0, -tool_off, 0]) cyl(d=pen_d + 2*$slop, l=100);
            translate([10 + ep, -tool_off, -8]) cyl(d=tap_d, l=10, orient=LEFT, anchor=BOT);
        }
    }
    if (with_pen) color("#345") translate([0, -tool_off, 0]) {
        up(-(tool_reach - 5)) cyl(d=pen_d, l=tool_reach - 5 + 50, anchor=BOT);
        down(tool_reach) cyl(d1=1, d2=pen_d, l=5, anchor=BOT);
    }
}

// Column: plate the Z frame bolts to, foot toward the table, a gusset each side.
// Origin: front face of the plate at y = 0, foot underside at z = 0.
col_t      = 8;
col_foot   = 40;
col_gusset = 60;
col_h      = z_frame0 + frame_mount + frame_pat.x/2 + 8 - base_t;
col_foot_holes = [[-36,-12],[36,-12],[-36,-32],[36,-32]];

module column() {
    diff() {
        union() {
            cuboid([frame_w, col_t, col_h], anchor=BOT+FRONT, rounding=3, edges=TOP);
            translate([0, col_t, 0]) cuboid([frame_w, col_foot + col_t, col_t], anchor=BOT+BACK, rounding=3, edges="Z");
            xcopies(frame_w - 4) frame_map(x=BACK, y=UP) linear_extrude(4, center=true)
                polygon([[0, col_t - ep], [-col_foot, col_t - ep], [0, col_gusset]]);
        }
        tag("remove") {
            for (dx=[-frame_pat.y/2, frame_pat.y/2], dz=[-frame_pat.x/2, frame_pat.x/2])
                translate([dx, -ep, z_frame0 + frame_mount + dz - base_t]) cyl(d=tap_d, l=col_t + 2*ep, orient=BACK, anchor=BOT);
            for (p = col_foot_holes) translate([p.x, p.y, -ep]) cyl(d=thru_d, l=col_t + 2*ep, anchor=BOT);
        }
    }
}

// -- base plate ------------------------------------------------------------------------
col_y     = col_face_y + stage_h;   // column front face
base_y0   = -max(yframe_front, tbl_sweep_y) - 8;
base_y1   = col_y + col_t + 6;
base_size = [200, base_y1 - base_y0];
base_cy   = (base_y0 + base_y1)/2;

module base_plate() {
    diff() {
        translate([0, base_cy, 0]) cuboid([base_size.x, base_size.y, base_t], anchor=BOT, rounding=6, edges="Z");
        tag("remove") {
            translate([-mount_off, mount_off_y, 0]) grid_copies(spacing=frame_pat) down(ep) cyl(d=thru_d, l=base_t + 2*ep, anchor=BOT);
            for (p = col_foot_holes) translate([p.x, col_y + p.y, -ep]) cyl(d=thru_d, l=base_t + 2*ep, anchor=BOT);
        }
    }
}

// -- the machine -------------------------------------------------------------------------
module xyz(x=tool_x, y=tool_y, z=tool_z) {
    assert(abs(x) <= x_travel/2 + ep, str("x outside ±", x_travel/2));
    assert(abs(y) <= y_travel/2 + ep, str("y outside ±", y_travel/2));
    assert(z >= -z_below - ep && z <= z_travel - z_below + ep, str("z outside ", -z_below, "..", z_travel - z_below));
    xp = x_travel/2 + x;      // carriage positions: the table moves opposite to the tool,
    yp = y_travel/2 - y;      // and both stages are turned 180 deg
    zp = z + z_below;
    zc = z_frame0 + car_x(stage_nut(z_travel, zp, 1));

    color(col_base) base_plate();
    // X stage on the base, motor to the right. Its carriage's bolt grid must meet the
    // Y frame's, which is mount_off_y behind the table centre, so the X stage sits
    // that far behind the tool axis.
    translate([0, mount_off_y, base_t - frame_z0]) zrot(180) left(car_mid) stage(x_travel, xp, mount_len=16);
    // Y stage on the X carriage, motor to the front
    translate([-x, 0, base_t + stage_h - frame_z0]) zrot(90) left(car_mid_y) stage(y_travel, yp, bias=y_bias, mount_len=10);
    // table and board on the Y carriage
    translate([-x, -y, base_t + 2*stage_h]) {
        color(col_print) table();
        if (show_board) up(tbl_size.z - pocket_d) board(anchor=BOT);
        up(tbl_size.z) grid_copies(spacing=dog_sp) { color(col_print) board_dog(); if (hardware) up(dog_t) m3(8); }
        if (hardware) up(tbl_size.z - pocket_d - 3) grid_copies(spacing=[pattern.y, pattern.x]) m3(10);
    }
    // column and Z stage, motor at the bottom, carriage facing the table
    color(col_print) translate([0, col_y, base_t]) column();
    translate([0, col_face_y + plate_z0 + plate_t, z_frame0]) zrot(90) yrot(-90) stage(z_travel, zp, bias=1, mount_len=12);
    // arm and tool
    up(zc) {
        color(col_print) arm();
        if (hardware) {
            for (dx=[-pattern.y/2, pattern.y/2], dz=[-pattern.x/2, pattern.x/2])
                translate([dx, col_face_y - arm_root.y, dz]) m3(10, orient=FWD);
            translate([tm_blk.x/2, tool_off + dt_h/2, -arm_t/2 + tm_stop + dt_slide/2]) m3(8, orient=RIGHT);
        }
        if (show_tool) translate([0, tool_off, -arm_t/2 + tm_stop]) tool_pen();
    }
}

module bom() {
    echo(str("XYZ table: footprint ", base_size.x, " x ", base_size.y, " mm, ", round(col_h + base_t), " mm tall; ",
             "travel ", x_travel, " x ", y_travel, " x ", z_travel, "; board surface at z=", board_top,
             "; arm reach ", col_face_y, " (Y bias ", y_bias, ")"));
    echo(str("BOM: 3x NEMA17 TR8x8 100 mm lead screw motor with flange nut; 6x rod Ø", rod_d, " x ", rod_len,
             "; 12x LM8UU; base plate ", base_size.x, " x ", base_size.y, " x ", base_t));
    echo("M3 socket screws: 41x M3x8 (12 motor, 12 nut flange, 12 rod clamp, 4 dog, 1 tool lock); 12x M3x10 (4 Y frame, 4 table, 4 arm); 4x M3x12 (Z frame); 8x M3x16 + 8 nuts (X frame and column to the base)");
    echo("Printed: 3x frame, 3x carriage, table, arm, column, 4x dog, one tongue per tool");
}

if (part == "assembly") { bom(); xyz(); }
else if (part == "frame")    up(-frame_z0) stage_frame();
else if (part == "carriage") up(plate_z0 + plate_t) xrot(180) stage_carriage();
else if (part == "table")    table();
else if (part == "arm")      up(col_face_y) xrot(-90) arm();
else if (part == "column")   up(col_t) xrot(-90) column();
else if (part == "tongue")   up(5) xrot(90) tool_tongue();
else if (part == "pen")      up(tool_reach - 5) tool_pen(with_pen=false);
else if (part == "dog")      board_dog();
else if (part == "base")     base_plate();
else if (part == "none")     ;   // for files that include this one
else assert(false, str("unknown part: ", part));
