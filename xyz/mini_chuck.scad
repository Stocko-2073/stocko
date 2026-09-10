// Mini self-tightening drill chuck, 0.3-3.4 mm capacity, Ø5 shaft bore. The
// brass arbor (knurled Ø10 body + M8x0.75 shank) screws into a black aluminium
// collet nut; three steel jaws sit in the nut's nose cone and are pushed by the
// shank face as the nut is tightened. Dimensions in mm: Ø10 body, Ø5 bore and
// M8x0.75 / 23.5 mm shank from the listings, the rest scaled off the photos.
//
//   use <mini_chuck.scad>
//   mini_chuck();                          // assembled, jaws set for a 1 mm bit
//   mini_chuck(bit=3.4, show_bit=true);    // jaws swallowed, with a stand-in bit
//   mini_chuck(threads=false);             // fast preview
//   mini_chuck() position("jaw_tip") sphere(1);
//   mini_chuck(bit=3.175) position("bit_seat") drill_bit();   // holding a real bit (drill_bit.scad)
//   chuck_body(); chuck_nut(); chuck_jaw(); chuck_set_screw(); chuck_hex_key();
//   nema17() position("shaft_tip") down(mc_bore_depth) mini_chuck();  // on a Ø5 motor shaft
//
// Every part stands on its own base (anchor=BOT) with the axis on Z:
//   chuck_body   base (motor side) at BOT, shank tip at TOP.
//                anchors "shoulder" (top of the knurl), "shank_tip", "bore_bottom",
//                "set_screw" (outer face of the +X screw hole, facing RIGHT)
//   chuck_nut    open threaded end at BOT, nose at TOP. anchor "tip"
//   chuck_jaw    one jaw, rear face at BOT, tip at TOP, gripping pad on the axis,
//                jaw body toward +X
//   chuck_jaws   the three jaws arranged for a bit of diameter `bit`
//   mini_chuck   body base at BOT; anchors "shoulder", "shank_tip", "bore_bottom",
//                "nose" (nut tip face), "jaw_tip", "bit_seat" (where a bit's shank
//                end sits when pushed all the way in, 1 mm clear of the motor shaft)
include <BOSL2/std.scad>
include <BOSL2/threading.scad>
include <BOSL2/screws.scad>
$fn=0;$fa=1;$fs=$preview?0.5:0.25;

// -- colours ------------------------------------------------------------------
mc_col_brass = "#c49a3c";
mc_col_nut   = "#444";
mc_col_steel = "#c8c8c8";
mc_col_screw = "#444";

// -- brass arbor --------------------------------------------------------------
mc_body_d      = 10;     // knurled body Ø
mc_body_h      = 12.5;   // knurled body length
mc_body_teeth  = 40;     // straight knurl ridges
mc_body_kdepth = 0.35;   // knurl depth
mc_bore_d      = 5;      // motor shaft bore
mc_bore_depth  = 12;
mc_thru_d      = 4;      // bit pass-through bore, full length
mc_neck_d      = 7.2;    // relief between knurl and thread
mc_neck_h      = 1;
mc_thread_d    = 8;      // M8x0.75
mc_pitch       = 0.75;
mc_thread_h    = 8.5;
mc_tip_d       = 7.6;    // plain end past the thread
mc_tip_h       = 1.5;
mc_body_len    = mc_body_h+mc_neck_h+mc_thread_h+mc_tip_h;  // 23.5
mc_set_screw_z = 4;      // base to the set screw axis
mc_set_screw_d = 3;      // 2x M3 grub screws, 180° apart
mc_set_screw_l = 3;
mc_bit_seat    = mc_bore_depth+1;  // deepest a bit shank goes: just clear of the motor shaft

// -- collet nut ---------------------------------------------------------------
mc_nut_d        = 13.5;  // knurled Ø
mc_nut_h        = 17.5;
mc_nut_knurl_h  = 9;     // knurled section, three bands split by two grooves
mc_nut_base_h   = 0.8;   // smooth band under the first knurl band
mc_nut_groove_z = [3, 6];
mc_nut_groove   = [0.6, 0.5];   // [width, depth]
mc_nut_teeth    = 48;
mc_nut_kdepth   = 0.4;
mc_nut_tip_d    = 7.4;   // flat ring at the nose
mc_nut_hole_d   = 6.0;   // jaw opening in the nose
mc_nut_thread_h = 6.5;   // internal M8x0.75
mc_nut_pocket_d = 9.5;   // clearance for the jaw heads at full opening
mc_alpha        = 20;    // nose cone half-angle, inside (outer cone is 19.7°)
mc_nut_cone_h   = (mc_nut_pocket_d-mc_nut_hole_d)/2/tan(mc_alpha);  // 4.75
mc_nut_cone_z   = mc_nut_h-mc_nut_cone_h;                            // 12.75

// -- jaws (dimensions with the three pads meeting on the axis) ----------------
mc_jaw_tip_d  = 4.6;   // OD of the jaw set at the tip
mc_jaw_head_h = 2;     // conical seating length
mc_jaw_neck_d = 4.6;   // OD of the jaw set behind the head
mc_jaw_len    = 8;
mc_jaw_gap    = 0.5;   // slot between neighbouring jaws
mc_jaw_chamf  = 0.3;
mc_bit_min    = 0.3;
mc_bit_max    = 3.4;

// How far the jaw tips stand out of the nose for a bit of diameter `bit`
// (negative = recessed). The jaws slide down the cone as they open.
function mc_jaw_protrusion(bit) = (mc_nut_hole_d-mc_jaw_tip_d-bit)/2/tan(mc_alpha);
// Nut base above the body base when clamping `bit`; the knurl shoulder is the stop.
function mc_nut_z(bit) = max(mc_body_h, mc_body_len+mc_jaw_len-mc_nut_h-mc_jaw_protrusion(bit));
function mc_total_len(bit) = mc_nut_z(bit)+mc_nut_h;

// -- knurls -------------------------------------------------------------------
// Straight knurl: V ridges along Z, standing on the origin.
module mc_knurl_straight(d, h, n, depth) {
    linear_extrude(h, convexity=10) star(n=n, r=d/2, ir=d/2-depth);
}

// Diamond knurl: two counter-rotating twisted stars intersected, standing on
// the origin. `helix` is the angle of each ridge set to the axis.
module mc_knurl_diamond(d, h, n, depth, helix=30) {
    r=d/2;
    twist = h*tan(helix)/r*180/PI;
    slices = max(8, ceil(h/0.2));
    intersection() {
        linear_extrude(h, twist=twist,  slices=slices, convexity=10) star(n=n, r=r, ir=r-depth);
        linear_extrude(h, twist=-twist, slices=slices, convexity=10) star(n=n, r=r, ir=r-depth);
    }
}

// -- brass arbor --------------------------------------------------------------
module chuck_body(threads=true, anchor=BOT, spin=0, orient=UP) {
    L=mc_body_len; ep=0.01;
    anchors = [
        named_anchor("shoulder",    [0,0,mc_body_h-L/2], UP),
        named_anchor("shank_tip",   [0,0,L/2], UP),
        named_anchor("bore_bottom", [0,0,mc_bore_depth-L/2], UP),
        named_anchor("set_screw",   [mc_body_d/2,0,mc_set_screw_z-L/2], RIGHT),
    ];
    attachable(anchor, spin, orient, d=mc_body_d, l=L, anchors=anchors) {
        down(L/2) color(mc_col_brass) difference() {
            union() {
                intersection() {
                    mc_knurl_straight(mc_body_d, mc_body_h, mc_body_teeth, mc_body_kdepth);
                    cyl(d=mc_body_d, h=mc_body_h, chamfer1=0.5, chamfer2=0.3, anchor=BOT);
                }
                up(mc_body_h-ep) cyl(d=mc_neck_d, h=mc_neck_h+2*ep, anchor=BOT);
                up(mc_body_h+mc_neck_h)
                    if (threads) threaded_rod(d=mc_thread_d, pitch=mc_pitch, l=mc_thread_h, anchor=BOT);
                    else cyl(d=mc_thread_d, h=mc_thread_h, anchor=BOT);
                up(L-mc_tip_h-ep) cyl(d=mc_tip_d, h=mc_tip_h+ep, chamfer2=0.5, anchor=BOT);
            }
            down(ep) cyl(d=mc_bore_d, h=mc_bore_depth+ep, anchor=BOT);
            down(ep) cyl(d1=mc_bore_d+1, d2=mc_bore_d, h=0.5+ep, anchor=BOT);
            cyl(d=mc_thru_d, h=L+2*ep);
            up(mc_set_screw_z) xcyl(d=mc_set_screw_d, h=mc_body_d+2*ep);
        }
        children();
    }
}

// -- collet nut ---------------------------------------------------------------
module chuck_nut(threads=true, anchor=BOT, spin=0, orient=UP) {
    H=mc_nut_h; ep=0.01;
    anchors = [named_anchor("tip", [0,0,H/2], UP)];
    attachable(anchor, spin, orient, d=mc_nut_d, l=H, anchors=anchors) {
        down(H/2) color(mc_col_nut) difference() {
            union() {
                cyl(d=mc_nut_d, h=mc_nut_base_h+ep, chamfer1=0.5, anchor=BOT);
                up(mc_nut_base_h)
                    mc_knurl_diamond(mc_nut_d, mc_nut_knurl_h-mc_nut_base_h, mc_nut_teeth, mc_nut_kdepth);
                up(mc_nut_knurl_h-ep)
                    cyl(d1=mc_nut_d, d2=mc_nut_tip_d, h=H-mc_nut_knurl_h+ep, rounding2=0.3, anchor=BOT);
            }
            // grooves between the knurl bands
            for (z=mc_nut_groove_z) up(z)
                tube(od=mc_nut_d+1, id=mc_nut_d-2*mc_nut_groove[1], h=mc_nut_groove[0]);
            // internal thread, jaw pocket and nose cone
            down(ep)
                if (threads) threaded_rod(d=mc_thread_d, pitch=mc_pitch, l=mc_nut_thread_h+2*ep, internal=true, anchor=BOT);
                else cyl(d=mc_thread_d, h=mc_nut_thread_h+2*ep, anchor=BOT);
            down(ep) cyl(d1=mc_thread_d+1.2, d2=mc_thread_d, h=0.6+ep, anchor=BOT);
            up(mc_nut_thread_h) cyl(d=mc_nut_pocket_d, h=mc_nut_cone_z-mc_nut_thread_h+ep, anchor=BOT);
            up(mc_nut_cone_z) cyl(d1=mc_nut_pocket_d, d2=mc_nut_hole_d, h=mc_nut_cone_h+ep, anchor=BOT);
        }
        children();
    }
}

// -- jaws ---------------------------------------------------------------------
// One jaw: a 120° sector of the jaw set (cone head + cylindrical neck) with a
// flat gripping pad on the axis and half a slot on each side. Rear face at BOT.
module chuck_jaw(anchor=BOT, spin=0, orient=UP) {
    L=mc_jaw_len; rt=mc_jaw_tip_d/2; rn=mc_jaw_neck_d/2; c=mc_jaw_chamf;
    rh = rt+mc_jaw_head_h*tan(mc_alpha);   // head radius at its rear
    g=mc_jaw_gap; B=rh+1;
    profile = [
        [0,0], [rn,0], [rn,L-mc_jaw_head_h], [rh,L-mc_jaw_head_h],
        [rt,L-c], [rt-c,L], [0,L],
    ];
    xa = g/2/sin(60);                  // slot planes meet here in front of the pad
    yb = (B*sin(60)-g/2)/cos(60);
    attachable(anchor, spin, orient, d=2*rh, l=L) {
        down(L/2) color(mc_col_steel) intersection() {
            rotate_extrude(convexity=4) polygon(profile);
            linear_extrude(L) polygon([[xa,0],[B,yb],[B,-yb]]);
        }
        children();
    }
}

// The three jaws spread for a bit of diameter `bit`, rear faces on the origin.
module chuck_jaws(bit=1) {
    zrot_copies(n=3) right(bit/2) chuck_jaw();
}

// -- small parts --------------------------------------------------------------
// M3 hex socket grub screw; TOP is the socket end.
module chuck_set_screw(anchor=TOP, spin=0, orient=UP) {
    color_this(mc_col_screw)
        screw(str("M3,", mc_set_screw_l), head="none", drive="hex", anchor=anchor, spin=spin, orient=orient);
}

// 1.5 mm L key lying in the XY plane: long arm along +X, short arm along +Y,
// bend at the origin.
module chuck_hex_key(long=40, short=12, af=1.5, bend_r=2) {
    path = round_corners([[long,0],[0,0],[0,short]], radius=bend_r, closed=false);
    color(mc_col_steel) path_sweep(hexagon(id=af), path);
}

// -- assembly -----------------------------------------------------------------
// bit = diameter the jaws are set to (0..3.4); show_bit draws a bit_len rod of
// that diameter standing in the jaws.
module mini_chuck(bit=1, jaws=true, screws=true, threads=true, show_bit=false, bit_len=30,
                  anchor=BOT, spin=0, orient=UP) {
    assert(bit>=0 && bit<=mc_bit_max, str("bit must be 0..", mc_bit_max));
    zn=mc_nut_z(bit); L=zn+mc_nut_h; zj=mc_body_len+mc_jaw_len;  // jaw tips
    anchors = [
        named_anchor("shoulder",    [0,0,mc_body_h-L/2], UP),
        named_anchor("shank_tip",   [0,0,mc_body_len-L/2], UP),
        named_anchor("bore_bottom", [0,0,mc_bore_depth-L/2], UP),
        named_anchor("nose",        [0,0,L/2], UP),
        named_anchor("jaw_tip",     [0,0,zj-L/2], UP),
        named_anchor("bit_seat",    [0,0,mc_bit_seat-L/2], UP),
    ];
    attachable(anchor, spin, orient, d=mc_nut_d, l=L, anchors=anchors) {
        down(L/2) {
            chuck_body(threads=threads);
            up(zn) chuck_nut(threads=threads);
            if (jaws) up(mc_body_len) chuck_jaws(bit);
            if (screws) up(mc_set_screw_z) xflip_copy() right(mc_body_d/2) chuck_set_screw(orient=RIGHT);
            if (show_bit && bit>0) color("#707070") up(zj-bit_len/3) cyl(d=bit, h=bit_len, chamfer2=bit/4, anchor=BOT);
        }
        children();
    }
}

// demo (skipped when `use`d; files that `include` this set mini_chuck_demo=false)
mini_chuck_demo = true;
if (mini_chuck_demo) {
    mini_chuck(bit=1);
    right(25) back_half(s=100) mini_chuck(bit=1);          // cutaway
    right(50) chuck_body();
    right(70) chuck_nut();
    right(90) zrot_copies(n=3) right(4) chuck_jaw();       // jaws spread out
    right(105) xcopies(n=2, spacing=6) chuck_set_screw(anchor=BOT);
    right(115) chuck_hex_key();
}
