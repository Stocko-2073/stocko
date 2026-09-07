// SG15-2RS U-groove track roller (guide wheel): Ø5 bore, Ø17 OD, double-row balls,
// rubber sealed both sides. Dimensions in mm from the vendor spec sheets: outer ring
// 8 wide, inner ring 9.75 wide (stands 0.875 proud per side), groove 5 wide x 1.35
// deep on a 3 mm radius to suit a Ø6 rail. Axis is Z, default anchor is CENTER.
//
//   use <sg15.scad>
//   sg15_2rs();
//   sg15_2rs() position("rail") ycyl(d=6, l=60);           // Ø6 rail in the groove
//   up(sg15_rail_offset(5)) sg15_2rs(orient=RIGHT);        // wheel on a Ø5 rod along Y
//   sg15_2rs() attach(TOP, BOT) cyl(d=5, l=10);            // shaft standing on the inner ring
//   ycyl(d=5, l=100) attach(TOP, "groove") sg15_2rs(spin=90);   // wheel seated on a Ø5 rod
//   ycyl(d=8, l=100) attach(TOP, RIGHT, overlap=sg15_rail_overlap(8)) sg15_2rs(spin=90);
//
// Named anchors, both on +X with the rail running along Y:
//   "rail"   axis of a Ø6 rail resting in the groove
//   "groove" bottom of the groove; attach it to a rail's surface to seat a rail up to Ø6
// sg15_rail_offset(rail_d) is the bearing-axis-to-rail-axis distance for any rail size,
// sg15_rail_overlap(rail_d) the overlap= to seat a rail when attaching by an OD anchor.
include <BOSL2/std.scad>
$fn=0;$fa=1;$fs=$preview?0.5:0.25;

// -- from the spec sheets -----------------------------------------------------
sg15_bore     = 5;
sg15_od       = 17;     // over the groove lips
sg15_outer_w  = 8;      // outer ring width (C)
sg15_inner_w  = 9.75;   // inner ring width (B), the overall width
sg15_groove_w = 5;      // at the OD
sg15_groove_d = 1.35;
sg15_groove_r = 3;      // (2.5^2 + 1.35^2) / (2*1.35) = 2.99
sg15_rail_d   = 6;      // rail the groove is cut for (dw)
sg15_inner_od = 8.6;    // d2

// -- not on the sheets, scaled from photos ------------------------------------
sg15_outer_id    = 12;    // outer ring bore behind the seals
sg15_seal_od     = 13.2;  // seal seat in the outer ring
sg15_seal_t      = 0.6;
sg15_seal_recess = 0.3;   // seal face sits this far below the outer ring face
sg15_chamfer     = 0.3;

sg15_col_steel = "#d8d8d8";
sg15_col_seal  = "#1a1a1a";

// Distance from the bearing axis to the axis of a Ø rail_d rail resting in the groove.
// Rails up to Ø6 sit on the groove bottom; larger ones ride on the two lips.
function sg15_rail_offset(rail_d=sg15_rail_d) =
    let(r = rail_d/2, lip_r = sg15_od/2, bottom_r = lip_r - sg15_groove_d)
    r <= sg15_groove_r ? bottom_r + r
                       : lip_r + sqrt(r*r - sqr(sg15_groove_w/2));

// How far to sink the bearing into a Ø rail_d rail when one of its OD anchors (RIGHT,
// BACK, ...) is attached to the rail's surface, so the rail seats in the groove.
// Equals the groove depth for rails up to Ø6.
function sg15_rail_overlap(rail_d=sg15_rail_d) =
    sg15_od/2 + rail_d/2 - sg15_rail_offset(rail_d);

// spin=90 matches BOSL2's built-in side anchors, so "groove" attaches the same way RIGHT does
sg15_anchors = [
    named_anchor("rail",   [sg15_rail_offset(), 0, 0], RIGHT, 90),
    named_anchor("groove", [sg15_od/2 - sg15_groove_d, 0, 0], RIGHT, 90),
];

module sg15_2rs(anchor=CENTER, spin=0, orient=UP) {
    ep=0.01;
    seat = sg15_seal_recess + sg15_seal_t;
    attachable(anchor, spin, orient, d=sg15_od, l=sg15_inner_w, anchors=sg15_anchors) {
        union() {
            // outer ring: U groove on the OD, bore and seal seats inside
            color(sg15_col_steel) difference() {
                cyl(d=sg15_od, l=sg15_outer_w, chamfer=sg15_chamfer);
                torus(r_maj=sg15_od/2 - sg15_groove_d + sg15_groove_r, r_min=sg15_groove_r);
                cyl(d=sg15_outer_id, l=sg15_outer_w + ep);
                mirror_copy(UP) up(sg15_outer_w/2 - seat)
                    cyl(d=sg15_seal_od, l=seat + ep, anchor=BOT);
            }
            // inner ring
            color(sg15_col_steel)
                tube(od=sg15_inner_od, id=sg15_bore, l=sg15_inner_w,
                     ichamfer=sg15_chamfer, ochamfer=0.2);
            // seals, overlapping both rings slightly so the faces don't z-fight
            color(sg15_col_seal) mirror_copy(UP) up(sg15_outer_w/2 - sg15_seal_recess)
                tube(od=sg15_seal_od + 0.4, id=sg15_inner_od - 0.2, l=sg15_seal_t, anchor=TOP);
        }
        children();
    }
}

// demo (skipped when `use`d; files that `include` this set sg15_demo=false)
sg15_demo = true;
if (sg15_demo) {
    sg15_2rs() position("rail") %ycyl(d=sg15_rail_d, l=40);
}
