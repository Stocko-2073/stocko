// Jobber-style twist drill: plain round shank, two right-hand helical flutes and
// a 118° point. Defaults are the 1/8" bit on the bench: Ø3.175, 60 mm overall,
// 21 mm shank (so 39 mm of flute including the point). Dimensions in mm.
//
//   use <drill_bit.scad>
//   drill_bit();                              // the 1/8" bit
//   drill_bit(d=1, l=38, shank=12);           // a PCB drill
//   drill_bit(helix=false);                   // fast preview, plain rod
//   drill_bit() position("tip") sphere(1);
//   mini_chuck(bit=3.175) position("bit_seat") drill_bit();   // in the chuck
//
// Shank end at BOT, point at TOP. Named anchors: "tip", "flute_start" (where the
// shank ends and the flutes begin).
include <BOSL2/std.scad>
$fn=0;$fa=1;$fs=$preview?0.5:0.25;

db_col_steel = "#c9c9c9";

// d, l, shank as above; point = included point angle; helix = flute helix angle
// to the axis (false for a plain rod); web = core thickness between the flutes
// as a fraction of d; flute = flute cutter radius as a fraction of d/2.
module drill_bit(d=3.175, l=60, shank=21, point=118, helix=30, web=0.16, flute=0.79,
                 anchor=BOT, spin=0, orient=UP) {
    r=d/2; fl=l-shank; ep=0.01;
    tip_h = r/tan(point/2);
    rf = flute*r; c = rf+web*r;                     // flute cutter circles at (0,±c)
    twist = helix==false ? 0 : -fl/(PI*d/tan(helix))*360;   // negative = right hand
    anchors = [
        named_anchor("tip",         [0,0,l/2], UP),
        named_anchor("flute_start", [0,0,shank-l/2], UP),
    ];
    attachable(anchor, spin, orient, d=d, l=l, anchors=anchors) {
        down(l/2) color(db_col_steel) union() {
            cyl(d=d, h=shank+ep, chamfer1=0.3, anchor=BOT);
            up(shank) intersection() {
                // fluted body, then the point cone trims it
                if (helix==false) cyl(d=d, h=fl, anchor=BOT);
                else linear_extrude(fl, twist=twist, slices=ceil(abs(twist)/5), convexity=6)
                    difference() {
                        circle(r=r, $fn=48);
                        for (s=[-1,1]) translate([0,s*c]) circle(r=rf, $fn=48);
                    }
                rotate_extrude(convexity=2)
                    polygon([[0,0],[r+ep,0],[r+ep,fl-tip_h],[0,fl]]);
            }
        }
        children();
    }
}

// demo (skipped when `use`d; files that `include` this set drill_bit_demo=false)
drill_bit_demo = true;
if (drill_bit_demo) {
    drill_bit();
    right(10) drill_bit(d=1, l=38, shank=12);
}
