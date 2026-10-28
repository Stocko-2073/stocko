// SKIL PWRCORE 20 2.0Ah battery pack (BY519701), modeled from AgentCam photos.
// Frame: +Y toward the terminal end (front), +X to the right looking from the back toward
// the front, +Z up, origin on the table under the middle of the body. Millimeters.
//
// Overall: 74.0 wide, 118.1 long (back face to lug tips), 43.7 to the rail top, 47.9 to the
// latch tab. Measurements and their sources are in README.md.
include <BOSL2/std.scad>

$fn = 40;
eps = 0.01;
details = true;        // surface detail: vents, labels panels, gauge, screws, marks

// ---- lower body: horizontal sections at body_z: half width, back Y, front Y, corner chamfers.
// Side walls are flat from z 5 to 25 (end-on silhouette); the front is cut away underneath,
// and the top corners are faceted where they meet the deck.
body_z      = [0.0,   1.5,   5.0,   8.0,   16.0,  25.0,  27.5];
body_hw     = [33.8,  35.6,  36.9,  37.0,  37.0,  36.9,  35.5];
body_back   = [-54.5, -55.6, -56.2, -56.3, -56.3, -56.1, -54.3];
body_front  = [45.0,  47.5,  52.5,  55.3,  55.5,  55.2,  53.0];
body_bch    = [5.0,   5.6,   6.3,   6.3,   6.3,   7.5,   10.5];
body_fch    = [2.0,   2.5,   3.0,   3.0,   2.5,   4.5,   7.5];
deck_z      = 31.3;    // shoulder deck around the tower
deck_half_w = 29.0;
deck_front  = 49.4;    // front edge of the deck
deck_back   = -50;     // hidden under the rear structures
seam_z      = 16.0;    // parting line between the lower (grey) and upper shells

// ---- front lugs (mirrored): side profile [Y, Z]; plan tapers toward the rounded tip
lug_cx      = [20.65, 20.35];          // center X at the root (Y = 50), near the tip (Y = 60)
lug_w       = [13.7, 8.9];             // width there
lug_front_y = 61.8;
lug_tip_r   = 2.5;
lug_top     = [[46, 31.3], [58.5, 28.7]];
lug_bottom  = [[45, 0.0], [52, 7.5], [61, 9.0]];
lug_screw   = [19.7, 52.8];            // screw in each lug's underside (X mirrored, Y)

// ---- tower (rail block) ----
cap_half_w  = 23.7;    // rail cap outer faces (47.4 across)
cap_y       = [-29.5, 31.3];
cap_z       = [38.3, 43.7];            // lip underside, top
lip_ch      = 0.9;     // chamfer on the lip's lower outer edge
wall_half_w = 22.0;    // tower wall below the lip (rail groove 1.7 deep)
lead_in     = 5;       // ramp on the lip underside at its front end
rail_win_y  = [[-18.0, -10.0], [-8.7, -3.3], [-1.9, 3.45], [4.8, 10.2], [11.4, 16.9], [18.3, 24.0], [25.7, 30.05]];
rail_win_z  = [40.1, 41.75];           // windows in the lip's outer faces
fingers_x   = [15.1, 20.0];            // outer fingers (mirrored) reach further forward
finger_y    = 37.8;
slots_x     = [-13.4, -6.25, 0, 6.5, 13.6];
slots_w     = [2.8, 3.1, 2.7, 3.3, 2.8];
slot_y0     = [15.0, 14.0, 15.0, 14.0, 15.0];
slot_floor  = 33;
contact_slots = [0, 2, 4];             // slots holding spring contacts (+, D, -)
latch_win   = [-15.05, 15.05, -21.6, -12.1];
latch_top   = [43.7, 47.9];            // tab top at its front edge, at its back edge
latch_floor = 38.0;                    // window depth; the tab rises from here
boss        = [0, 3.5, 3.2, 1.8];      // screw counterbore x, y, outer r, hole r
marks       = [[-13.4, "+"], [0, "D"], [13.6, "-"]];
marks_y     = 11.2;

// ---- front deck: vents and keys in front of the tower ----
vent_x      = [-13.7, -8.8, -3.8, 3.8, 8.7, 13.7];
vent_y      = [40.0, 48.2];
vent_w      = 2.6;
keys        = [                         // raised keys on the deck [x0, x1, y0, y1]
    [-10.9, -9.5, 34.6, 39.2],
    [1.2, 5.2, 37.1, 39.1], [2.2, 4.0, 34.2, 37.2],   // the T
    [8.0, 9.8, 34.4, 39.1]];
key_h       = 1.5;
tag_1p      = [-7.3, -1.5, 35.2, 38.6]; // embossed "1P" frame

// ---- back: collar, pillars, release button and charge gauge ----
collar_y    = [-35, -29.5];
collar_half = 29;
collar_z    = 45.5;
pillar_x    = [19.5, 29.5];
pillar_back = [-55.5, 33.5];           // Y, Z where the pillar top meets the back face
button_half = 17.5;
button_y    = [-55.0, -37.0];
button_z    = [35.3, 41.6];            // pad top at its back and front edges
button_ribs = [-49.5, -47.2];          // two grip ribs across the pad (Y)
gauge       = [19.2, 0.8, 14.0, 2.0];  // back-face gauge window: half width, z0, z1, corner chamfer
gauge_btn   = [-15.2, -0.8, 5.0, 11.0];
gauge_leds  = [[2.0, 3.2, 8.0], [5.2, 6.4, 8.8], [8.4, 9.6, 9.4], [11.6, 13.0, 10.2]]; // x0, x1, top z
gauge_led_z0 = 5.6;

// ---- sides: recessed label panel (both sides), outline in (Y, Z) ----
panel       = [[-38.5, 22.8], [41.2, 22.8], [48.4, 17.8], [48.4, 10.8], [43.0, 6.0],
               [15.8, 6.0], [13.8, 9.2], [11.8, 6.0], [-39.6, 6.0], [-45.2, 10.8], [-45.2, 18.0]];
panel_depth = 0.6;

// ---- bottom ----
bot_label   = [-29.5, 29.5, 3.5, 37.5, 3.0];  // recessed label panel x0 x1 y0 y1 chamfer
grip        = [-22.5, 22.5, -14.5, -2.2, 2.5]; // finger channel x0 x1 y0 y1 depth
bot_vents   = [[-15.8, -42.15, 14.5, 3.3], [0, -42.15, 14.5, 3.3], [15.8, -42.15, 14.5, 3.3],
               [-4.85, -51.0, 7.5, 2.4], [4.85, -51.0, 7.5, 2.4]];   // x, y, length, width
bot_screws  = [[-23.9, -52.0], [23.9, -52.0]];
bot_pads    = [[-29.3, 39.4], [29.3, 39.4], [-29.3, -39.5], [29.3, -39.5]];
bot_holes   = [[-32, 16.5], [32, 16.5], [-32, -12.2], [32, -12.2], [-15.2, 43.5], [15.2, 43.5], [0, 0.8]];

module chrect(hw, yb, yf, cb, cf) {
    polygon([[-hw + cb, yb], [hw - cb, yb], [hw, yb + cb], [hw, yf - cf],
             [hw - cf, yf], [-hw + cf, yf], [-hw, yf - cf], [-hw, yb + cb]]);
}

module slab(z) { translate([0, 0, z]) linear_extrude(eps) children(); }

module lower_body(inset = 0) {
    // inset > 0 shrinks the walls (not the top or bottom): used to cut detail to a fixed depth
    hull() {
        for (i = [0 : len(body_z) - 1]) slab(body_z[i])
            chrect(body_hw[i] - inset, body_back[i] + inset, body_front[i] - inset,
                   max(eps, body_bch[i] - inset * 0.4), max(eps, body_fch[i] - inset * 0.4));
        slab(deck_z - eps) chrect(deck_half_w - inset, deck_back, deck_front - inset, 2, 2);
    }
}

// the lower body's skin, depth d: anything intersected with it is cut d deep into the walls
module skin(d) { difference() { lower_body(-1); lower_body(d); } }

module lug() {
    // side profile in (Y, Z), extruded across the lug, then tapered in plan by intersection
    intersection() {
        rotate([90, 0, 90]) translate([0, 0, lug_cx[0] - lug_w[0]]) linear_extrude(2 * lug_w[0])
            polygon(concat([for (p = lug_bottom) p],
                           [[lug_front_y, lug_top[1][1] - 0.2]], [for (i = [len(lug_top) - 1 : -1 : 0]) lug_top[i]]));
        linear_extrude(40)
            hull() {
                translate([lug_cx[0] - lug_w[0]/2, 40]) square([lug_w[0], 10]);
                translate([lug_cx[1] - lug_w[1]/2, 50]) square([lug_w[1], 10]);
                translate([lug_cx[1], lug_front_y - lug_tip_r]) rect([lug_w[1] - 0.4, 2 * lug_tip_r], rounding = lug_tip_r);
            }
    }
}

module rail_cap() {
    hull() {
        translate([-cap_half_w, cap_y[0], cap_z[0] + lip_ch]) cube([2 * cap_half_w, cap_y[1] - cap_y[0] - lead_in, cap_z[1] - cap_z[0] - lip_ch]);
        translate([-cap_half_w + lip_ch, cap_y[0], cap_z[0]]) cube([2 * (cap_half_w - lip_ch), cap_y[1] - cap_y[0] - lead_in, eps]);
        translate([-cap_half_w, cap_y[1] - 1.5, cap_z[1] - 1.4]) cube([2 * cap_half_w, 1.5, 1.4]);
        translate([-wall_half_w, cap_y[0], cap_z[0]]) cube([2 * wall_half_w, cap_y[1] - cap_y[0], cap_z[1] - cap_z[0]]);
    }
}

module tower() {
    difference() {
        union() {
            translate([-wall_half_w, cap_y[0], deck_z - eps]) cube([2 * wall_half_w, cap_y[1] - cap_y[0], cap_z[0] - deck_z + eps]);
            rail_cap();
            for (s = [-1, 1]) mirror([s < 0 ? 1 : 0, 0, 0])
                translate([fingers_x[0], cap_y[1] - 2, deck_z - eps])
                    cuboid([fingers_x[1] - fingers_x[0], finger_y - cap_y[1] + 2, cap_z[1] - deck_z + eps],
                           rounding = 1.5, edges = [BACK + LEFT, BACK + RIGHT], anchor = BOTTOM + LEFT + FRONT);
        }
        for (i = [0 : len(slots_x) - 1])
            translate([slots_x[i] - slots_w[i]/2, slot_y0[i], slot_floor]) cube([slots_w[i], 40, 20]);
        translate([latch_win[0], latch_win[2], latch_floor]) cube([latch_win[1] - latch_win[0], latch_win[3] - latch_win[2], 10]);
        if (details) {
            for (s = [-1, 1]) for (w = rail_win_y)
                translate([s * cap_half_w - 1.2, w[0], rail_win_z[0]])
                    cube([2.4, w[1] - w[0], rail_win_z[1] - rail_win_z[0]]);
            // screw counterbore and hole
            translate([boss[0], boss[1], cap_z[1] - 0.6]) cyl(r = boss[2], h = 1.2, anchor = BOTTOM);
            translate([boss[0], boss[1], cap_z[1] - 4]) cyl(r = boss[3], h = 5, anchor = BOTTOM);
            // terminal marks: a ring with the polarity sign, 0.25 deep
            for (m = marks) translate([m[0], marks_y, cap_z[1] - 0.25]) {
                tube(or = 2.5, ir = 2.1, h = 0.5, anchor = BOTTOM);
                linear_extrude(0.5) text(m[1], size = 2.4, halign = "center", valign = "center",
                                         font = "Liberation Sans:style=Bold");
            }
        }
    }
    // latch tab: a wedge rising toward the back, with a vertical catch face
    hull() {
        translate([latch_win[0] + 0.6, latch_win[3] - 0.8, latch_floor - eps]) cube([latch_win[1] - latch_win[0] - 1.2, eps, latch_top[0] - latch_floor]);
        translate([latch_win[0] + 0.6, latch_win[2] + 0.6, latch_floor - eps]) cube([latch_win[1] - latch_win[0] - 1.2, 0.8, latch_top[1] - latch_floor]);
    }
    // spring contacts: two crossed blades in each live slot
    if (details) for (i = contact_slots) for (s = [-1, 1])
        translate([slots_x[i], 23, slot_floor + 4])
            rotate([0, 0, s * 8]) cube([0.3, 14, 8.2], center = true);
}

module rear() {
    // collar behind the tower: front corners flare out from the cap width
    hull() {
        translate([-cap_half_w, collar_y[1] - eps, deck_z - eps]) cube([2 * cap_half_w, eps, collar_z - deck_z]);
        translate([-collar_half, collar_y[1] - (collar_half - cap_half_w), deck_z - eps]) cube([2 * collar_half, eps, collar_z - deck_z]);
        translate([-collar_half, collar_y[0], deck_z - eps]) cube([2 * collar_half, eps, collar_z - deck_z]);
    }
    // pillars either side of the button, sloping down to the back face
    for (s = [-1, 1]) mirror([s < 0 ? 1 : 0, 0, 0])
        hull() {
            translate([pillar_x[0], collar_y[0], deck_z - 8]) cube([pillar_x[1] - pillar_x[0], eps, collar_z - deck_z + 8]);
            translate([pillar_x[0], pillar_back[0], deck_z - 8]) cube([pillar_x[1] - pillar_x[0] - 4, eps, pillar_back[1] - deck_z + 8]);
        }
    // button pad, sloped, dropping to the back face; two grip ribs across it
    hull() {
        translate([-button_half, button_y[1] - eps, gauge[2]]) cube([2 * button_half, eps, button_z[1] - gauge[2]]);
        translate([-button_half, button_y[0], gauge[2]]) cube([2 * button_half, eps, button_z[0] - gauge[2]]);
        translate([-button_half, pillar_back[0], gauge[2]]) cube([2 * button_half, eps, button_z[0] - 1 - gauge[2]]);
    }
    if (details) for (y = button_ribs) {
        z = button_z[0] + (y - button_y[0]) / (button_y[1] - button_y[0]) * (button_z[1] - button_z[0]);
        translate([0, y, z]) cuboid([22, 0.8, 0.8], rounding = 0.35, edges = "X");
    }
    // fill between pillars and button
    hull() {
        translate([-pillar_x[0] - eps, collar_y[0], deck_z - 8]) cube([2 * pillar_x[0] + 2 * eps, eps, button_z[1] - 1 - deck_z + 8]);
        translate([-pillar_x[0] - eps, pillar_back[0], deck_z - 8]) cube([2 * pillar_x[0] + 2 * eps, eps, button_z[0] - 3 - deck_z + 8]);
    }
}

module deck_details() {
    for (k = keys) translate([k[0], k[2], deck_z - eps]) cube([k[1] - k[0], k[3] - k[2], key_h]);
    // "1P" in a frame, raised 0.3
    translate([tag_1p[0], tag_1p[2], deck_z - eps]) linear_extrude(0.3 + eps) {
        difference() { square([tag_1p[1] - tag_1p[0], tag_1p[3] - tag_1p[2]]);
                       offset(delta = -0.3) square([tag_1p[1] - tag_1p[0], tag_1p[3] - tag_1p[2]]); }
        translate([(tag_1p[1] - tag_1p[0]) / 2, (tag_1p[3] - tag_1p[2]) / 2])
            text("1P", size = 2.2, halign = "center", valign = "center", font = "Liberation Sans:style=Bold");
    }
}

module vent_cuts() {
    // six perforated vent slots: a 1 mm recess with 2 x 5 holes through
    for (x = vent_x) {
        translate([x, (vent_y[0] + vent_y[1]) / 2, deck_z - 1])
            linear_extrude(2) rect([vent_w, vent_y[1] - vent_y[0]], rounding = vent_w / 2 - eps);
        for (dx = [-0.6, 0.6]) for (i = [0 : 4])
            translate([x + dx, vent_y[0] + 1.3 + i * 1.4, deck_z - 4]) cylinder(d = 0.8, h = 5, $fn = 12);
    }
}

module side_panel_cuts() {
    intersection() {
        skin(panel_depth);
        rotate([90, 0, 90]) linear_extrude(100, center = true) polygon(panel);
    }
}

// prism along Y through the back face, from a 2D shape in (X, Z)
module back_prism() { translate([0, -40, 0]) rotate([90, 0, 0]) linear_extrude(40, center = true) children(); }

module gauge_outline() {
    polygon([[-gauge[0], gauge[2]], [gauge[0], gauge[2]], [gauge[0], gauge[1] + gauge[3]],
             [gauge[0] - gauge[3], gauge[1]], [-gauge[0] + gauge[3], gauge[1]], [-gauge[0], gauge[1] + gauge[3]]]);
}

module gauge_cuts() {
    // window recessed 0.4 behind a 0.5 wide frame groove, with LED slots
    intersection() {
        skin(0.4);
        back_prism() gauge_outline();
    }
    intersection() {
        skin(0.8);
        back_prism() difference() { gauge_outline(); offset(delta = -0.5) gauge_outline(); }
    }
    intersection() {
        skin(0.9);
        back_prism() for (l = gauge_leds) translate([l[0], gauge_led_z0]) square([l[1] - l[0], l[2] - gauge_led_z0]);
    }
}

module gauge_button() {
    // the gauge's push button stands 0.4 proud of the window
    intersection() {
        difference() { lower_body(-0.4); lower_body(0.4); }
        back_prism() translate([(gauge_btn[0] + gauge_btn[1]) / 2, (gauge_btn[2] + gauge_btn[3]) / 2])
            rect([gauge_btn[1] - gauge_btn[0], gauge_btn[3] - gauge_btn[2]], rounding = 1.5);
    }
}

module bottom_cuts() {
    // label panel, 0.3 deep
    translate([0, 0, -1]) linear_extrude(1.3)
        translate([bot_label[0], bot_label[2]])
            chrect_ll(bot_label[1] - bot_label[0], bot_label[3] - bot_label[2], bot_label[4]);
    // finger channel: steep front wall, 45 degree back wall
    hull() {
        translate([grip[0], grip[2] + grip[4], -1]) cube([grip[1] - grip[0], grip[3] - grip[2] - grip[4], grip[4] + 1]);
        translate([grip[0], grip[2], -1]) cube([grip[1] - grip[0], grip[3] - grip[2], 1 + eps]);
    }
    for (v = bot_vents) translate([v[0], v[1], -1]) linear_extrude(2.5) rect([v[2], v[3]], rounding = v[3] / 2 - eps);
    for (p = bot_screws) translate([p[0], p[1], -1]) { cylinder(d = 4.6, h = 4); cylinder(d = 2, h = 9); }
    for (p = bot_pads) translate([p[0], p[1], -1]) difference() { cylinder(r = 2.6, h = 1.3); cylinder(r = 2.2, h = 3, center = true); }
    for (p = bot_holes) translate([p[0], p[1], -1]) cylinder(d = 1.3, h = 4, $fn = 16);
    // screws up into the lugs' undersides
    for (s = [-1, 1]) translate([s * lug_screw[0], lug_screw[1], 6.6]) { cylinder(d = 4.6, h = 4); cylinder(d = 2, h = 9); }
}

module chrect_ll(w, h, c) {  // chamfered rectangle from the origin corner
    polygon([[c, 0], [w - c, 0], [w, c], [w, h - c], [w - c, h], [c, h], [0, h - c], [0, c]]);
}

module battery() {
    difference() {
        union() {
            lower_body();
            for (s = [-1, 1]) mirror([s < 0 ? 1 : 0, 0, 0]) lug();
            tower();
            rear();
            if (details) { deck_details(); gauge_button(); }
        }
        if (details) {
            // parting line groove, 0.4 wide and 0.4 deep, all round
            intersection() { skin(0.4); translate([0, 0, seam_z]) cube([200, 200, 0.4], center = true); }
            vent_cuts();
            side_panel_cuts();
            gauge_cuts();
            bottom_cuts();
        }
    }
}

// render(): the detail cuts are too many for the F5 preview's CSG normalization (it gives up
// and shows nothing), so compute the mesh once and preview that.
render(convexity = 10) battery();
