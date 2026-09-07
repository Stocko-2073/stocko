// NEMA 17 stepper body shared by the motors in this directory, plus the two plain
// Ø5 D-shaft motors: nema17() (39 mm body, JST-XH connector) and nema17_pancake()
// (22.5 mm body, JST-PH connector). Dimensions in mm from the vendor spec sheets.
// Motor axis is Z, shaft points UP, default anchor is the mounting face (TOP) so
// the body hangs below the origin.
//
//   use <nema17.scad>
//   nema17();                                             // 39 mm D-shaft motor
//   nema17_pancake();                                     // 22.5 mm D-shaft motor
//   nema17() position("shaft_tip") sphere(2);
//   nema17() attach("dcut", BOT) cyl(d=12, h=15);         // pulley on the D-cut
//   diff() cuboid([60,60,5]) tag("remove") nema17_mount_mask(5);
//
// Named anchors on both motors: "pilot" (face of the Ø22 boss), "shaft_tip",
// "dcut" (start of the D-cut), "connector" (outer face of the header, facing -Y).
include <BOSL2/std.scad>
include <BOSL2/rounding.scad>
$fn=0;$fa=1;$fs=$preview?0.5:0.25;

// -- body, common to the NEMA 17s ---------------------------------------------
n17_w       = 42;   // □42
n17_chamfer = 5;    // corner chamfer, not on the sheets (typical NEMA 17)
n17_edge_r  = 1;    // rounding on the outer edges of the end caps
n17_pilot_d = 22;   // Ø22 0/-0.05
n17_pilot_h = 2;
n17_hole_sp = 31;   // □31
n17_hole_d  = 3;    // 4-M3
n17_shaft_d = 5;    // Ø5 0/-0.012 D-shaft
n17_dcut    = 4.5;  // 4.5±0.1 across the flat

n17_col_cap     = "#c8c8c8";
n17_col_stator  = "#2a2a2a";
n17_col_steel   = "#d8d8d8";
n17_col_plastic = "#1a1a1a";
n17_col_conn    = "#ece9e1";

// -- 39 mm D-shaft motor ------------------------------------------------------
n17d_len        = 39;
n17d_cap        = 6;      // both end caps, scaled off the drawing
n17d_hole_depth = 5.5;    // sheet says 4.5 MIN
n17d_shaft_len  = 24;     // 24±1 from the mount face
n17d_dcut_len   = 15;     // 15±0.25 from the tip
n17d_conn       = [16, 6.5, 7.2];  // 4-pin JST-XH header [x, protrusion, z]
n17d_conn_pos   = 11;     // rear face to the connector's front edge
n17d_conn_pitch = 2.54;
n17d_conn_pins  = 4;
n17d_lip        = [16, 6.5, 3];    // casing tab beside the connector [x, protrusion, z], flush with the rear face

// -- 22.5 mm pancake D-shaft motor --------------------------------------------
n17p_len        = 22.5;   // 22.5±0.8
n17p_cap_front  = 8.4;    // caps scaled off the drawing; the stator band is only 3 mm
n17p_cap_rear   = 11;
n17p_hole_depth = 3.5;    // sheet says 2.5 MIN
n17p_shaft_len  = 24;     // 24±0.5 from the mount face
n17p_dcut_len   = 22;     // flat runs from the pilot face to the tip
n17p_conn       = [16, 7, 7];      // 6-position JST-PH header (PH-6AW) [x, protrusion, z]
n17p_conn_pos   = 10;     // rear face to the connector's front edge
n17p_conn_pitch = 2.0;
n17p_conn_pins  = 4;      // A+ A- B+ B- populated
n17p_lip        = [16, 4.3, 3];    // casing tab, abuts the connector; protrusion scaled off the drawing

// Body centered on the origin, mount face at +len/2. Building block for the motors.
// rear_lip=[x, protrusion, z] adds a casing tab on the -Y face, flush with the rear
// face, as part of the rear cap so the edge rounding follows it.
module nema17_body(len, cap_front, cap_rear, hole_depth, rear_lip) {
    W=n17_w; ep=0.01;
    profile = rect([W,W], chamfer=n17_chamfer);
    // front end cap with pilot boss and 4-M3 tapped holes
    up(len/2) color(n17_col_cap) difference() {
        union() {
            down(cap_front) offset_sweep(profile, height=cap_front, top=os_circle(r=n17_edge_r));
            cyl(d=n17_pilot_d, h=n17_pilot_h, chamfer2=0.5, anchor=BOT);
        }
        grid_copies(spacing=n17_hole_sp, n=2)
            up(ep) cyl(d=n17_hole_d, h=hole_depth+ep, anchor=TOP);
    }
    // stator laminations
    up(len/2-cap_front) color(n17_col_stator)
        cuboid([W,W,len-cap_front-cap_rear], chamfer=n17_chamfer, edges="Z", anchor=TOP);
    // rear end cap
    down(len/2) color(n17_col_cap)
        if (is_undef(rear_lip)) {
            offset_sweep(profile, height=cap_rear, bottom=os_circle(r=n17_edge_r));
        } else {
            lip = move([0,-W/2+1], rect([rear_lip.x, rear_lip.y+1], anchor=BACK));
            offset_sweep(union([profile, lip]), height=rear_lip.z, bottom=os_circle(r=n17_edge_r));
            up(rear_lip.z) linear_sweep(profile, height=cap_rear-rear_lip.z);
        }
}

// Ø5 D-shaft standing on the origin (the mount face), flat toward BACK (+Y).
module nema17_dshaft(len, dcut_len) {
    ep=0.01;
    color(n17_col_steel) difference() {
        cyl(d=n17_shaft_d, h=len, chamfer2=0.4, anchor=BOT);
        up(len-dcut_len) back(n17_dcut-n17_shaft_d/2)
            cuboid([n17_shaft_d+1, n17_shaft_d, dcut_len+ep], anchor=BOT+FWD);
    }
}

// JST-style header with the socket opening outward (-Y). Origin is at the body
// face (BACK) and the connector's front edge (TOP); it extends toward the rear.
module nema17_connector(size, pitch, pins) {
    c=size; ep=0.01; pin=pitch/4;
    color(n17_col_conn) difference() {
        cuboid(c, anchor=BACK+TOP);
        fwd(c.y+ep) down(0.8) cuboid([c.x-1.6, c.y-1.2, c.z-1.6], anchor=FWD+TOP);
    }
    color(n17_col_steel) fwd(1.2) down(c.z/2)
        xcopies(n=pins, spacing=pitch) cuboid([pin, c.y-2, pin], anchor=BACK);
}

function nema17_anchors(len, shaft_len, dcut_len, conn, conn_pos) =
    let(zc = -len/2+conn_pos) [
        named_anchor("pilot",     [0,0,len/2+n17_pilot_h], UP),
        named_anchor("shaft_tip", [0,0,len/2+shaft_len], UP),
        named_anchor("dcut",      [0,0,len/2+shaft_len-dcut_len], UP),
        named_anchor("connector", [0,-n17_w/2-conn.y,zc-conn.z/2], FWD),
    ];

// 39 mm NEMA 17 with Ø5 D-shaft. The flat faces BACK (+Y); the connector and the
// rear cap's casing tab are on the FWD (-Y) face.
module nema17(anchor=TOP, spin=0, orient=UP) {
    L=n17d_len;
    attachable(anchor, spin, orient, size=[n17_w,n17_w,L],
               anchors=nema17_anchors(L, n17d_shaft_len, n17d_dcut_len, n17d_conn, n17d_conn_pos)) {
        union() {
            nema17_body(L, n17d_cap, n17d_cap, n17d_hole_depth, rear_lip=n17d_lip);
            up(L/2) nema17_dshaft(n17d_shaft_len, n17d_dcut_len);
            down(L/2-n17d_conn_pos) fwd(n17_w/2)
                nema17_connector(n17d_conn, n17d_conn_pitch, n17d_conn_pins);
        }
        children();
    }
}

// 22.5 mm pancake NEMA 17 with Ø5 D-shaft, same layout as nema17().
module nema17_pancake(anchor=TOP, spin=0, orient=UP) {
    L=n17p_len;
    attachable(anchor, spin, orient, size=[n17_w,n17_w,L],
               anchors=nema17_anchors(L, n17p_shaft_len, n17p_dcut_len, n17p_conn, n17p_conn_pos)) {
        union() {
            nema17_body(L, n17p_cap_front, n17p_cap_rear, n17p_hole_depth, rear_lip=n17p_lip);
            up(L/2) nema17_dshaft(n17p_shaft_len, n17p_dcut_len);
            down(L/2-n17p_conn_pos) fwd(n17_w/2)
                nema17_connector(n17p_conn, n17p_conn_pitch, n17p_conn_pins);
        }
        children();
    }
}

// Cutter for a plate the motor bolts to. `depth` is the plate thickness, centered;
// the motor sits against BOT. cbore > 0 sinks the screw heads that far into the
// TOP face (cbore_d fits an M3 button head).
//   diff() cuboid([60,60,5]) tag("remove") nema17_mount_mask(5);
//   diff() cuboid([60,60,6]) tag("remove") nema17_mount_mask(6, cbore=2);
module nema17_mount_mask(depth=5, hole_d=3.4, pilot_clear=0.5, cbore=0, cbore_d=6.4, anchor=CENTER, spin=0, orient=UP) {
    attachable(anchor, spin, orient, size=[n17_w,n17_w,depth]) {
        union() {
            cyl(d=n17_pilot_d+pilot_clear, h=depth+0.02);
            grid_copies(spacing=n17_hole_sp, n=2) {
                cyl(d=hole_d, h=depth+0.02);
                if (cbore > 0) up(depth/2-cbore) cyl(d=cbore_d, h=cbore+0.01, anchor=BOT);
            }
        }
        children();
    }
}

// demo (skipped when `use`d; files that `include` this set nema17_demo=false)
nema17_demo = true;
if (nema17_demo) {
    nema17();
    right(60) nema17_pancake();
}
