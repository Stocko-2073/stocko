// NEMA 17 stepper with integrated TR8x8 lead screw (100 mm) and Ø22 flange nuts.
// Dimensions from the vendor spec sheet, in mm. The body comes from nema17.scad:
// motor axis is Z, screw points UP, default anchor is the mounting face (TOP).
//
//   use <nema17_tr8.scad>
//   nema17_tr8();                                         // motor + screw + shipped nut
//   nema17_tr8(nut="brass", nut_pos=30);                  // generic 22x15 brass nut instead
//   nema17_tr8(nut=false, threads=false);                 // fast preview
//   nema17_tr8() position("screw_tip") sphere(2);
//   nema17_tr8(nut_pos=30) attach("nut_flange", BOT) cuboid([30,30,8]);
//   nema17_tr8() position("pilot") up(60) tr8_flange_nut("brass");   // an extra nut
//   tr8_flange_nut("brass");                              // a nut on its own
//
// `include` this file (and set nema17_tr8_demo=false) when you need its variables
// and tr8_nut_spec(); `use` it when the modules are enough.
//
// Named anchors on nema17_tr8(): "pilot" (face of the Ø22 boss), "screw_tip", and
// when a nut is fitted, "nut_flange" (carriage side of the flange) and "nut_end".
include <nema17.scad>
include <BOSL2/threading.scad>
nema17_demo = false;

// -- lead screw motor body ----------------------------------------------------
n17t_len        = 38.7;    // 38.7±0.8, mount face to rear face
n17t_cap_front  = 7.8;     // end cap thicknesses, scaled off the drawing
n17t_cap_rear   = 8.6;
n17t_hole_depth = 4.5;     // sheet says 3.5 MIN
n17t_wire_exit  = 5.4;     // lead exit, distance from rear face
n17t_wire_block = [8,3,4]; // placeholder rectangle for the leads [x, protrusion, z]

// -- TR8x8 lead screw ---------------------------------------------------------
tr8_d      = 8;
tr8_len    = 100;   // 100±1 from the mount face
tr8_pitch  = 2;     // P=2.0
tr8_starts = 4;     // lead 8 = 4 starts × 2 mm pitch

// -- Ø22 flange nuts: [len, body_d, stub, flange_d, flange_t, pcd, hole_d] ------
// The stub is the short end of the body; it faces the motor.
tr8nut_specs = [
    ["motor", [10.5, 10,   2,   22, 3.5, 16, 3  ]],  // nut shipped on the motor, 4-M3
    ["brass", [15,   10.2, 1.5, 22, 3.5, 16, 3.5]],  // generic brass Tr8 nut, 22x15, 4-Ø3.5
];
tr8nut_bore_d = 8.5;  // internal thread major dia (Tr8 D4)
n17_col_brass = "#c49a3c";

function tr8_nut_spec(type) =
    let(found=[for (s=tr8nut_specs) if (s[0]==type) s[1]])
    assert(len(found)==1, str("unknown Tr8 nut type: ", type))
    found[0];

// nut = "motor" | "brass" | false; nut_pos = pilot face to the nut's stub end,
// so 0 is the nut resting on the pilot boss
module nema17_tr8(nut="motor", nut_pos=0, nut_spin=0, threads=true, anchor=TOP, spin=0, orient=UP) {
    L=n17t_len; W=n17_w;
    zp = L/2+n17_pilot_h;  // pilot face
    nut_type = nut==true ? "motor" : nut;
    ns = nut==false ? undef : tr8_nut_spec(nut_type);
    anchors = concat(
        [
            named_anchor("pilot",     [0,0,zp], UP),
            named_anchor("screw_tip", [0,0,L/2+tr8_len], UP),
        ],
        is_undef(ns) ? [] : [
            named_anchor("nut_flange", [0,0,zp+nut_pos+ns[2]+ns[4]], UP),
            named_anchor("nut_end",    [0,0,zp+nut_pos+ns[0]], UP),
        ]
    );
    attachable(anchor, spin, orient, size=[W,W,L], anchors=anchors) {
        union() {
            nema17_body(L, n17t_cap_front, n17t_cap_rear, n17t_hole_depth);
            // lead exit placeholder, bottom of the rear cap
            down(L/2-n17t_wire_exit) fwd(W/2) color(n17_col_plastic)
                cuboid(n17t_wire_block, anchor=BACK);
            // lead screw
            up(L/2) color(n17_col_steel)
                if (threads)
                    trapezoidal_threaded_rod(d=tr8_d, l=tr8_len, pitch=tr8_pitch,
                        starts=tr8_starts, bevel2=true, anchor=BOT);
                else
                    cyl(d=tr8_d, h=tr8_len, chamfer2=0.5, anchor=BOT);
            if (!is_undef(ns)) up(zp+nut_pos) zrot(nut_spin) tr8_flange_nut(nut_type);
        }
        children();
    }
}

// Ø22 flange nut for TR8x8, type="motor" or "brass" (see tr8nut_specs).
// BOT is the short stub (motor side), TOP the long body.
// Named anchors: "flange_bot" (motor side face), "flange_top" (carriage side face).
module tr8_flange_nut(type="motor", bore=true, anchor=BOT, spin=0, orient=UP) {
    s=tr8_nut_spec(type);
    L=s[0]; body_d=s[1]; stub=s[2]; flange_d=s[3]; flange_t=s[4]; pcd=s[5]; hole_d=s[6];
    ep=0.01;
    zf = -L/2+stub;  // motor-side face of the flange
    anchors = [
        named_anchor("flange_bot", [0,0,zf], DOWN),
        named_anchor("flange_top", [0,0,zf+flange_t], UP),
    ];
    attachable(anchor, spin, orient, d=body_d, l=L, anchors=anchors) {
        color(n17_col_brass) difference() {
            union() {
                cyl(d=body_d, h=L, chamfer=0.3);
                up(zf) cyl(d=flange_d, h=flange_t, chamfer=0.3, anchor=BOT);
            }
            if (bore) cyl(d=tr8nut_bore_d, h=L+2*ep);
            up(zf-ep) zrot_copies(n=4) right(pcd/2)
                cyl(d=hole_d, h=flange_t+2*ep, anchor=BOT);
        }
        children();
    }
}

// Cutter for a carriage the nut flange bolts to. `depth` is the plate thickness, centered:
//   diff() cuboid([36,36,8]) tag("remove") tr8_nut_mount_mask(8, "brass");
module tr8_nut_mount_mask(depth=5, type="motor", hole_d=3.4, body_clear=0.4, anchor=CENTER, spin=0, orient=UP) {
    s=tr8_nut_spec(type);
    attachable(anchor, spin, orient, d=s[3], l=depth) {
        union() {
            cyl(d=s[1]+body_clear, h=depth+0.02);
            zrot_copies(n=4) right(s[5]/2) cyl(d=hole_d, h=depth+0.02);
        }
        children();
    }
}

// demo (skipped when `use`d; files that `include` this set nema17_tr8_demo=false)
nema17_tr8_demo = true;
if (nema17_tr8_demo) {
    nema17_tr8(nut_pos=25);
    right(40) tr8_flange_nut("brass");
}
