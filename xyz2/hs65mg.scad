// Hitec HS-65MG micro servo. Native, editable OpenSCAD geometry; units: mm.
// Source: Hitec General Specification, v2.2 (drawing on page 1), accessed 2026-09-05:
// https://www.hiteccs.com/public/uploads/data_sheet/HCS_HS-65MG_Specsheetv2.2_10-1729888021.pdf
// The table says 24 mm high, but the dimensioned drawing explicitly shows a
// 20 mm case roof, 26 mm bearing boss and 3.1 mm exposed spline. This model uses
// those drawing datums, not the conflicting catalog bounding box.
//
// Local X is case length, Y is width, Z is the output direction. The output is
// toward +X. Default BOT is the case bottom; named anchors: "mount" (ear
// underside), "shaft" (boss face on the output axis), "horn_face" (arm seat).
//
//   include <BOSL2/std.scad>
//   use <hs65mg.scad>
//   hs65mg();
//   hs65mg(horn=true, horn_angle=30, wire_length=20);
//   hs65mg(anchor="shaft", orient=RIGHT);
// Include instead of use to share dimensions; set hs65mg_demo=false afterward.
include <BOSL2/std.scad>
$fn=0; $fa=3; $fs=$preview ? 0.5 : 0.25;

// Dimensioned geometry. Heights are measured from the bottom of the case.
hs65mg_length = 23.6;
hs65mg_width = 11.6;
hs65mg_case_h = 20;
hs65mg_ear_span = 32.3;
hs65mg_mount_z = 17;
hs65mg_ear_t = 2;
hs65mg_boss_z = 26;
hs65mg_spline_h = 3.1;
hs65mg_spline_d = 5;
hs65mg_spline_teeth = 25;
hs65mg_horn_top = hs65mg_boss_z+4.4;
hs65mg_horn_bottom = hs65mg_mount_z+hs65mg_ear_t+9.6;
hs65mg_horn_t = hs65mg_horn_top-hs65mg_horn_bottom;
hs65mg_hole_d = 2;
hs65mg_outer_hole_pitch = 19.2+7.8;
hs65mg_middle_hole_pitch = 20+8.6;
hs65mg_hole_row_pitch = 6;
hs65mg_axis_x = hs65mg_middle_hole_pitch/2-8.6; // 5.7 from case centre

// Undimensioned details estimated from the drawing: molded corner radii,
// cover seams, gear-cover contours, spline tooth form, horn outline/hole radii,
// case screws and strain relief. These are visual details, not tooling data.
hs65mg_corner_r = 0.8;
hs65mg_boss_d = 9.8;
hs65mg_gear_d = 11.2;
hs65mg_wire_z = 2.8;
hs65mg_case_col = "#292b2e";
hs65mg_cover_col = "#36383b";
hs65mg_horn_col = "#242629";

function hs65mg_mount_points() = [
    for(s=[-1,1]) each [
        [s*hs65mg_middle_hole_pitch/2,0],
        [s*hs65mg_outer_hole_pitch/2,-hs65mg_hole_row_pitch/2],
        [s*hs65mg_outer_hole_pitch/2, hs65mg_hole_row_pitch/2]
    ]
];

// All geometry in this helper uses the physical case bottom as Z=0.
module hs65mg_case(details=true) {
    ep=0.01;
    color(hs65mg_case_col) difference() {
        cuboid([hs65mg_length,hs65mg_width,hs65mg_case_h],
               rounding=hs65mg_corner_r,edges="Z",anchor=BOT);
        if(details) for(z=[2.8,14]) up(z) difference() {
            cuboid([hs65mg_length+1,hs65mg_width+1,0.16]);
            cuboid([hs65mg_length-0.25,hs65mg_width-0.25,0.3],
                   rounding=hs65mg_corner_r,edges="Z");
        }
    }
    color(hs65mg_cover_col) {
        // Two full-width ears, each with three holes (not open mounting slots).
        difference() {
            up(hs65mg_mount_z) cuboid([hs65mg_ear_span,hs65mg_width,hs65mg_ear_t],
                                      rounding=1.3,edges="Z",anchor=BOT);
            for(p=hs65mg_mount_points()) translate([p.x,p.y,hs65mg_mount_z-ep])
                cyl(d=hs65mg_hole_d,h=hs65mg_ear_t+2*ep,anchor=BOT);
        }
        // Offset circular output housing and the smaller adjoining gear lobe.
        up(hs65mg_case_h-ep) linear_extrude(4+ep) hull() {
            right(hs65mg_axis_x) circle(d=hs65mg_gear_d);
            right(hs65mg_axis_x-5.5) circle(d=6.6);
        }
        hull() {
            translate([hs65mg_axis_x,0,hs65mg_case_h+4-ep])
                cyl(d=hs65mg_gear_d,h=ep,anchor=BOT);
            translate([hs65mg_axis_x,0,hs65mg_boss_z-ep])
                cyl(d=hs65mg_boss_d,h=ep,anchor=BOT);
        }
    }
    if(details) {
        // Four recessed case screw heads, visible from the bottom.
        color("#888b8e") for(x=[-9.8,9.8],y=[-3.8,3.8])
            translate([x,y,0]) difference() {
                cyl(d=2.2,h=0.08,anchor=BOT);
                cuboid([1.5,0.35,0.2],anchor=BOT);
                cuboid([0.35,1.5,0.2],anchor=BOT);
            }
        // Small roof label, clear of the gear housing.
        translate([-6.5,0,hs65mg_case_h]) {
            color("#deded9") cuboid([8.5,9.4,0.03],anchor=BOT);
            color("#b42729") translate([-3.1,0,0.03]) cuboid([1.5,9.4,0.02],anchor=BOT);
            color("#202123") up(0.04) zrot(90) linear_extrude(0.02) {
                back(1) text("Hitec",size=2,halign="center",valign="center");
                fwd(1.7) text("HS-65MG",size=1.25,halign="center",valign="center");
            }
        }
    }
}

module hs65mg_spline() {
    // 25 teeth on the documented Ø5 envelope. Tooth root/form is illustrative.
    color("#b3a17a") difference() {
        linear_extrude(hs65mg_spline_h) polygon([
            for(i=[0:hs65mg_spline_teeth*4-1])
                let(a=360*i/(hs65mg_spline_teeth*4),
                    r=hs65mg_spline_d/2-(i%4<2 ? 0.18 : 0))
                    [r*cos(a),r*sin(a)]
        ]);
        down(0.01) cyl(d=1.6,h=hs65mg_spline_h+0.02,anchor=BOT);
    }
}

// Short, straight lead preview; the specified full cable is 160 mm of 28 AWG.
// Length=0 hides the free wires, retaining the molded exit at the shaft end.
module hs65mg_lead(length=12) {
    translate([hs65mg_length/2-0.1,0,hs65mg_wire_z]) {
        color("#1e2022") cuboid([1.5,4,3.5],rounding=0.6,anchor=LEFT);
        if(length>0) for(i=[0:2]) color(["#222222","#b52726","#e6bf22"][i])
            translate([1,(i-1)*1.1,0]) cyl(d=1,h=length,orient=RIGHT,anchor=BOT);
    }
}

// Origin is the bearing-boss face, on the output axis. Full stock cross is the
// default. trimmed=true represents three arms cut off for the XYZ2 linkage;
// drilled=true adds Ø1.6 pilots at drill_radii (default 4.5 and 8 mm).
module hs65mg_horn(trimmed=false,drilled=false,screw=true,drill_radii=[4.5,8]) {
    z0=hs65mg_horn_bottom-hs65mg_boss_z;
    color(hs65mg_horn_col) difference() {
        union() {
            up(0.15) cyl(d=6.8,h=z0+hs65mg_horn_t-0.15,anchor=BOT);
            up(z0) linear_extrude(hs65mg_horn_t) {
                circle(d=7.8);
                for(a=trimmed ? [0] : [0,90,180,270]) rotate(a) hull() {
                    circle(d=6.2);
                    right(9.2) circle(d=4.6);
                }
            }
        }
        down(0.01) cyl(d=hs65mg_spline_d+0.1,h=hs65mg_spline_h+0.02,anchor=BOT);
        cyl(d=2,h=6,anchor=BOT);
        for(a=trimmed ? [0] : [0,90,180,270]) zrot(a)
            for(r=drilled ? drill_radii : [6.5,9]) translate([r,0,z0-0.01])
                cyl(d=drilled ? 1.6 : 1,h=hs65mg_horn_t+0.02,anchor=BOT);
    }
    if(screw) color("#696c70") up(hs65mg_horn_top-hs65mg_boss_z) difference() {
        cyl(d=3.5,h=0.9,chamfer2=0.2,anchor=BOT);
        up(0.6) cuboid([2.4,0.55,0.5],anchor=BOT);
        up(0.6) cuboid([0.55,2.4,0.5],anchor=BOT);
    }
}

module hs65mg(horn=false,horn_angle=0,wire_length=12,details=true,
              anchor=BOT,spin=0,orient=UP) {
    anchors=[
        named_anchor("mount",[0,0,hs65mg_mount_z-hs65mg_case_h/2],DOWN),
        named_anchor("shaft",[hs65mg_axis_x,0,hs65mg_boss_z-hs65mg_case_h/2],UP),
        named_anchor("horn_face",[hs65mg_axis_x,0,hs65mg_horn_top-hs65mg_case_h/2],UP)
    ];
    attachable(anchor,spin,orient,size=[hs65mg_length,hs65mg_width,hs65mg_case_h],anchors=anchors) {
        down(hs65mg_case_h/2) union() {
            hs65mg_case(details);
            hs65mg_lead(wire_length);
            translate([hs65mg_axis_x,0,hs65mg_boss_z]) {
                hs65mg_spline();
                if(horn) zrot(horn_angle) hs65mg_horn();
            }
        }
        children();
    }
}

hs65mg_demo=true;
if(hs65mg_demo) hs65mg(horn=true);
