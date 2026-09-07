// T-bot XY platform. Units mm. See XYZ3.md for routing and prototype limits.
include <nema17.scad>
nema17_demo=false;
use <xyz2.scad> // Existing board fixtures and complete servo/spring cartridge.

/* [Display] */
part="assembly"; // [assembly,base,cross_carriage,arm,belt_clamp,head,cartridge,plunger,lift_arm,board_clip,backing,belt,collision_check,none]
show_board=true;
show_hardware=true;
show_envelope=false;
animate_motion=false;
/* [Motion] */
tool_x=0; // [-35:1:35]
tool_y=0; // [-45:1:45]
pen_lift=0; // [0:0.1:5]
/* [Hidden] */
$fa=5; $fs=0.6;
r=20/PI;                 // 20T GT2 pitch radius
c=24;                   // corner idler offset from arm center
R=c-r;                  // end idler pitch radius, tangent to both vertical runs
axis_y=110;
motor_x=95;
belt_z=95;
front_end=30;
rear_end=225;
X=animate_motion?35*sin(360*$t):tool_x;
Y=animate_motion?45*cos(360*$t):tool_y;
L=animate_motion?2.5*(1-cos(720*$t)):pen_lift;
frame_color="#237789";
moving_color="#e4a247";
function belt_length()=4*(motor_x-c)+2*(rear_end-front_end-4*r)+4*PI*r+2*PI*R;
function motor_a(x,y)=x+y;
function motor_b(x,y)=x-y;
assert(abs(X)<=35 && abs(Y)<=45 && L>=0 && L<=5,"Motion outside 70 x 90 x 5 mm travel");
assert(45+45.4/2<75,"Y block must remain fully on its 150 mm rail");
assert(front_end+45<axis_y-2*r && rear_end-45>axis_y+2*r,"End idlers hit crossover pulleys");

module bore(h,d=3.4) { translate([0,0,-0.02]) cylinder(d=d,h=h+0.04); }
module plate(size) { translate([-size.x/2,-size.y/2,0]) cube(size); }
module pattern() { for(x=[-10,10],y=[-10,10]) translate([x,y,0]) children(); }
module base3() {
    difference() {
        union() {
            translate([0,49,0]) plate([246,208,6]);
            for(x=[-40,40],y=[-30,30]) translate([x,y,6]) cylinder(d=8,h=4.6);
            translate([0,axis_y,6]) plate([156,28,24]);
            for(s=[-1,1]) {
                translate([s*119,axis_y,6]) plate([8,54,80]);
                translate([s*motor_x,axis_y,80]) plate([56,54,6]);
            }
        }
        for(x=[-62.5:25:62.5]) translate([x,axis_y,20]) bore(10,2.6);
        for(s=[-1,1]) translate([s*motor_x,axis_y,80]) {
            bore(6,22.5);
            for(x=[-15.5,15.5],y=[-15.5,15.5]) translate([x,y,0]) bore(6);
        }
        for(x=[-40,40],y=[-30,30]) translate([x,y,0]) bore(10.6,2.6);
    }
}
// X block top at 43. Y block is inverted, mounting face at 49.
module cross3() {
    difference() {
        union() {
            translate([0,axis_y+15,43]) plate([62,84,6]);
            for(s=[-1,1],t=[-1,1]) translate([s*c,axis_y+t*2*r,49]) cylinder(d=9,h=37);
        }
        translate([0,axis_y,43]) pattern() { bore(6); translate([0,0,3]) bore(3,6.4); }
        translate([0,axis_y+30,43]) pattern() { bore(6); bore(3,6.4); }
        for(s=[-1,1],t=[-1,1]) translate([s*c,axis_y+t*2*r,76]) bore(10,2.6);
    }
}
// Inverted moving Y rail bolts underneath this arm. Front dock matches XYZ2.
module arm3() {
    difference() {
        union() {
            translate([0,124,62]) plate([29,228,6]);
            translate([0,16,42]) plate([44,6,26]);
            for(y=[front_end,rear_end]) translate([0,y,68]) cylinder(d=12,h=18);
            translate([-R+3,60,68]) plate([6,24,38]);
            translate([-R+6,60,62]) plate([12,24,6]);
        }
        for(y=[77.5:25:202.5]) translate([0,y,62]) bore(6);
        for(y=[front_end,rear_end]) translate([0,y,62]) bore(24,2.6);
        for(x=[-16,16],z=[50,74]) translate([x,12.9,z]) rotate([-90,0,0]) bore(6.2);
        // Dock ears extend above the arm; completed in docked_arm().
        for(y=[52,68]) translate([-R-0.1,y,101]) rotate([0,90,0]) bore(7,2.6);
        translate([0,12.98,62]) cube([12.4,2.22,16.4],center=true);
    }
}
module docked_arm() {
    difference() {
        union() {
            arm3();
            translate([0,16,62]) plate([44,6,22]);
        }
        for(x=[-16,16],z=[50,74]) translate([x,12.9,z]) rotate([-90,0,0]) {
            bore(6.2);
            translate([0,0,2.7]) cylinder(d=6.6,h=3.5,$fn=6);
        }
        translate([0,14,62]) cube([12.4,2.4,16.4],center=true);
    }
}
module clamp3() {
    difference() {
        plate([3,24,15]);
        for(y=[-8,8]) translate([-1.6,y,12]) rotate([0,90,0]) bore(3.2);
    }
}
module wheel(radius=r) {
    color("#c5ced4") difference() {
        union() {
            cylinder(r=radius-0.7,h=8,center=true);
            for(z=[-4.5,4.5]) translate([0,0,z]) cylinder(r=radius+2.6,h=1,center=true);
        }
        cylinder(d=3.4,h=12,center=true);
    }
}
module idler_at(p,radius=r) {
    translate([p.x,p.y,belt_z]) {
        wheel(radius);
        color(frame_color) translate([0,0,-9]) difference() { cylinder(d=5,h=4); bore(4); }
        color(frame_color) translate([0,0,5]) difference() { cylinder(d=5,h=1); bore(1); }
        if(show_hardware) translate([0,0,6]) fastener(25);
    }
}
module line2(a,b) { hull() { translate(a) circle(r=0.7); translate(b) circle(r=0.7); } }
module arc2(p,rad,a,b) {
    for(i=[0:ceil((b-a)/5)-1]) let(n=ceil((b-a)/5))
        line2(p+rad*[cos(a+(b-a)*i/n),sin(a+(b-a)*i/n)],p+rad*[cos(a+(b-a)*(i+1)/n),sin(a+(b-a)*(i+1)/n)]);
}
// One planar, constant-length belt; each segment meets its pulley tangentially.
module belt3(x=X,y=Y) {
    color("#25313d") translate([0,0,belt_z-3]) linear_extrude(6) difference() { union() {
        for(s=[-1,1]) {
            line2([-motor_x,axis_y+s*r],[x-c,axis_y+s*r]);
            line2([x+c,axis_y+s*r],[motor_x,axis_y+s*r]);
            line2([x+s*R,front_end+y],[x+s*R,axis_y-2*r]);
            line2([x+s*R,axis_y+2*r],[x+s*R,rear_end+y]);
        }
        arc2([-motor_x,axis_y],r,90,270);
        arc2([motor_x,axis_y],r,270,450);
        arc2([x-c,axis_y-2*r],r,0,90);
        arc2([x+c,axis_y-2*r],r,90,180);
        arc2([x-c,axis_y+2*r],r,270,360);
        arc2([x+c,axis_y+2*r],r,180,270);
        arc2([x,front_end+y],R,180,360);
        arc2([x,rear_end+y],R,0,180);
        }
        translate([x-R,y+60]) square([2,0.6],center=true);
    }
}
module collision3() {
    intersection() {
        base3();
        union() { translate([X,0,0]) cross3(); translate([X,Y,0]) { docked_arm(); head(L); } }
    }
    intersection() { translate([X,0,0]) cross3(); translate([X,Y,0]) docked_arm(); }
}
module assembly3() {
    color(frame_color) base3();
    translate([0,axis_y,30]) linear_rail();
    translate([X,axis_y,30]) linear_block();
    translate([X,0,0]) color(moving_color) cross3();
    translate([X,Y+140,62]) rotate([0,180,90]) linear_rail();
    translate([X,axis_y+30,62]) rotate([0,180,90]) linear_block();
    translate([X,Y,0]) {
        color(moving_color) docked_arm();
        head(L);
        if(show_hardware) dock_fasteners();
        translate([-R-2.2,60,89]) color(frame_color) clamp3();
        for(y=[front_end,rear_end]) idler_at([0,y],R);
    }
    for(s=[-1,1],t=[-1,1]) idler_at([X+s*c,axis_y+t*2*r]);
    translate([-motor_x,axis_y,80]) nema17(spin=90);
    translate([motor_x,axis_y,80]) nema17_pancake(spin=-90);
    for(s=[-1,1]) translate([s*motor_x,axis_y,86]) timing_pulley();
    belt3();
    color("#a9a49a") translate([0,0,6]) backing();
    if(show_board) translate([0,0,9]) board(anchor=BOT);
    for(x=[-40,40],y=[-30,30]) translate([x,y,10.6]) {
        color(moving_color) board_clip();
        if(show_hardware) translate([0,0,3]) fastener(8);
    }
    if(show_envelope) %translate([0,0,10.6]) plate([70,90,5]);
}
echo(str("XYZ3 T-bot: 70 x 90 mm XY; 5 mm servo lift; belt pitch length = ",belt_length()," mm"));
echo(str("Relative motor belt travel A=X+Y: ",motor_a(X,Y)," mm, B=X-Y: ",motor_b(X,Y)," mm (verify wiring signs)"));
if(part=="assembly") assembly3();
else if(part=="base") base3();
else if(part=="cross_carriage") translate([0,-axis_y,-43]) cross3();
else if(part=="arm") translate([0,0,22]) rotate([0,90,0]) docked_arm();
else if(part=="belt_clamp") clamp3();
else if(part=="belt") belt3();
else if(part=="collision_check") collision3();
else if(part=="head") head(L);
else if(part!="none") print_part(part);
