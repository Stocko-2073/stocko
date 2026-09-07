// Fixed-board PCB scriber, OpenSCAD + BOSL2. Units: mm.
// Two supplied NEMA17 shaft motors, three 150 mm MGN12H guides,
// and a micro-servo lifting a spring-loaded, replaceable scribing cartridge.
// This is a mechanical prototype; copper isolation / cutting force need testing.
// See XYZ2.md. The earlier xyz.scad is independent and unchanged.
include <nema17.scad>
nema17_demo = false;
include <hs65mg.scad>
hs65mg_demo = false;

/* [Display] */
part = "assembly"; // [assembly,base,bridge,saddle,cartridge,plunger,lift_arm,tool_blank,belt_cap,idler_spacer,board_clip,backing,head,carriage,layout,collision_check,head_assembly_check,assembly_access_check,none]
show_board = true;
show_hardware = true;
show_envelope = false;
animate_motion = false;

/* [Motion] */
tool_x = 0; // [-35:1:35]
tool_y = 0; // [-45:1:45]
pen_lift = 0; // [0:0.1:5]

/* [Board] */
board_x = 70;
board_y = 90;
board_z = 1.6;
backing_t = 3;

/* [Scribing cartridge] */
pen_d = 8;
pen_length = 70;
guide_clearance = 0.12;       // diametral allowance: ream / fit the two guides
spring_preload = 2; // [0.5:0.1:4]
spring_free_length = 24;
spring_wire = 0.7;
spring_mean_d = 9.4;
spring_turns = 7;
// Supply a measured spring rate (N/mm) to echo nominal force; 0 = unknown.
spring_rate = 0;

/* [Printing] */
m3_hole = 3.4;
m3_tap = 2.6;
register_clearance = 0.2;
spacer_h = 4; // [1,4]

/* [Hidden] */
$fn=0; $fa=4; $fs=$preview ? 0.8 : 0.4;
eps = 0.02;
frame_col = "#237789";
move_col = "#e4a247";
steel_col = "#c5ced4";
dark_col = "#263440";
rail_length = 150;
rail_width = 12;
rail_height = 8;
block_length = 45.4;
block_width = 27;
block_top = 13;
rail_pattern = [-62.5,-37.5,-12.5,12.5,37.5,62.5];
x_travel = 70;
y_travel = 90;
lift_max = 5;
base_t = 6;
base_x0 = -104;
base_x1 = 110;
base_y0 = -78;
base_y1 = 136;
guide_x = 62;
y_guide_mid = 32;            // tool is 32 mm ahead of the bridge guide face
y_guide_z = 22;
y_block_z = y_guide_z+block_top;
foot_t = 6;
x_guide_z = 58;
x_belt_z = x_guide_z+30;
bridge_back = 8;
pulley_r = 20*2/(2*PI);
belt_thickness = 1.4;
belt_width = 6;
pulley_half = 78;
y_belt_x = guide_x+23;       // outside the right Y rail, clear of its block
y_idler = -64;
y_motor_y = y_guide_mid+pulley_half;
y_motor_face = 51;           // shaft down: its 24 mm shaft reaches z=27
y_belt_z = y_guide_z+9;
board_bottom = base_t+backing_t;
board_top_z = board_bottom+board_z;
clip_x = board_x/2+5;
clip_y = board_y/2-15;
lower_guide = board_top_z+14;
lower_guide_top = lower_guide+8;
collar_base = board_top_z+25;
collar_z = collar_base+spring_preload;
collar_h = 6;
upper_guide = collar_base+collar_h+spring_free_length;
fork_h = 32;
follower_z = collar_z+fork_h;
arm_r = 13;                 // lifting pad beyond both horn screw heads
arm_tip_r = 2.5;
horn_screw_radii = [4,8];   // 4 mm spacing clears the two 3.8 mm screw heads
cam_gap = 0.4;
// Servo stays fixed when preload is changed; the commanded angle compensates.
servo_z = collar_base+2+fork_h-arm_tip_r-arm_r*sin(-20)-cam_gap;
// Keep the printed arm's inner face at X=-10; locate the real bearing boss
// using the drawing's horn stack height. The shaft points +X, case length +Z.
servo_arm_x = -10;
servo_horn_offset = hs65mg_horn_top-hs65mg_boss_z;
servo_axis = [servo_arm_x-servo_horn_offset,-25,servo_z];
servo_case_x = [servo_axis.x-hs65mg_boss_z,servo_axis.x-hs65mg_boss_z+hs65mg_case_h];
servo_case_z0 = servo_z-hs65mg_axis_x-hs65mg_length/2;
servo_case_z1 = servo_case_z0+hs65mg_length;
servo_mount_x = servo_case_x[0]+hs65mg_mount_z;
servo_bracket_t = 4;
servo_mount_zs = [for(s=[-1,1]) (servo_case_z0+servo_case_z1)/2+s*hs65mg_middle_hole_pitch/2];
saddle_screw_y = 16.2;      // recessed M3x6 heads; 2.8 mm of saddle beneath them
tool_datum_z = 62;
dock_front_y = 13;
dock_back_y = 19;
X = animate_motion ? x_travel/2*sin(360*$t) : tool_x;
Y = animate_motion ? y_travel/2*cos(360*$t) : tool_y;
LIFT = animate_motion ? lift_max*(1-cos(720*$t))/2 : pen_lift;

function arm_angle(lift) = asin((follower_z+lift-(lift==0 ? cam_gap : 0)-servo_z-arm_tip_r)/arm_r);
function spring_length(lift) = spring_free_length-spring_preload-lift;
function machine_height() = max(x_belt_z+24,y_motor_face+39,board_top_z+pen_length+lift_max);

assert(board_x==70 && board_y==90, "This frame is laid out for the supplied 70 x 90 mm board.");
assert(board_z>0 && backing_t>0, "Board / backing thickness must be positive.");
assert(abs(X)<=35 && abs(Y)<=45 && LIFT>=0 && LIFT<=lift_max, "Motion outside the working envelope.");
assert(y_travel+block_length+4<=rail_length && x_travel+block_length+4<=rail_length, "Carriage would leave a rail.");
assert(y_belt_x-pulley_r-belt_thickness/2>guide_x+block_width/2+1, "Y belt must clear the outside of the right guide block.");
assert(pen_d>=3 && pen_d<=8, "Cartridge accepts round 3-8 mm shanks; adjust / ream guides to the actual pen.");
assert(spring_mean_d-spring_wire>pen_d+0.3, "Spring rubs the pen shaft.");
assert(spring_length(lift_max)>spring_turns*spring_wire+2, "Spring approaches solid height.");
assert(collar_z>lower_guide_top+3+0.2, "Preload places collar against lower bridge.");
assert(abs(arm_angle(0))<60 && abs(arm_angle(lift_max))<60, "Servo lift exceeds its nominal angular range.");
assert(board_top_z+pen_length>upper_guide+8+3, "Pen too short for both guides.");

module hole(h,d=m3_hole) { down(eps) cyl(d=d,h=h+2*eps,anchor=BOT); }
module xy_pattern(p=20) { for(x=[-p/2,p/2],y=[-p/2,p/2]) translate([x,y,0]) children(); }
module tool_pattern() { for(x=[-16,16],z=[-12,12]) translate([x,0,tool_datum_z+z]) children(); }
module travel_slot(h,d=m3_hole) { hull() for(x=[-3,3]) right(x) hole(h,d); }

module fastener(l=8,dir=DOWN,d=3) {
    color(steel_col) rot(from=UP,to=dir) {
        cyl(d=d,h=l,anchor=BOT);
        difference() {
            cyl(d=d==3 ? 5.5 : 3.8,h=d==3 ? 3 : 2,anchor=TOP);
            down(1) cyl(d=d==3 ? 2.9 : 2,h=2.1,anchor=TOP,$fn=6);
        }
    }
}

module m3_nut() {
    color(steel_col) difference() {
        cyl(d=6.35,h=2.4,anchor=BOT,$fn=6);
        hole(2.4,d=3);
    }
}

module linear_rail() {
    color(steel_col) difference() {
        cuboid([rail_length,12,8],chamfer=0.5,edges="X",anchor=BOT);
        for(x=rail_pattern) right(x) {
            hole(8,d=3.5);
            up(3.5) cyl(d=6,h=4.6,anchor=BOT);
        }
        for(s=[-1,1]) translate([0,s*6,5]) cyl(d=2,h=rail_length+2,orient=RIGHT);
    }
}

module linear_block() {
    color(steel_col) difference() {
        up(3) cuboid([block_length,block_width,10],chamfer=0.5,edges="X",anchor=BOT);
        cuboid([block_length+2,12.4,8.3],anchor=BOT);
        xy_pattern() up(9.5) hole(3.6,d=2.5);
    }
    color(dark_col) for(s=[-1,1]) right(s*(block_length/2-1)) difference() {
        up(3) cuboid([2,block_width+0.2,10],anchor=BOT);
        cuboid([3,12.5,8.4],anchor=BOT);
    }
}

module rail_screws() { for(x=rail_pattern) translate([x,0,3.5]) fastener(8); }

module timing_pulley(idler=false) {
    // Mounting envelopes: verify purchased hub / flange dimensions.
    color(steel_col) difference() {
        union() {
            if(!idler) cyl(d=16,h=5,anchor=BOT);
            up(5) cyl(d=12.22,h=8,anchor=BOT);
            for(z=[4,13]) up(z) cyl(d=18,h=1,anchor=BOT);
        }
        hole(15,d=idler ? 3 : 5);
    }
}

module belt_path(a=-78,b=78,join=0) {
    color(dark_col) up(6) difference() {
        linear_extrude(6) difference() {
            hull() for(x=[a,b]) right(x) circle(r=pulley_r+belt_thickness/2);
            hull() for(x=[a,b]) right(x) circle(r=pulley_r-belt_thickness/2);
        }
        translate([join,-pulley_r,-eps]) cuboid([0.6,3,6+2*eps],anchor=BOT);
    }
}

// Travel +Y; the joined strand and grip are on the outboard (+X) side.
module y_drive_belt(join=Y+y_guide_mid) {
    translate([y_belt_x,0,y_guide_z]) zrot(90) belt_path(y_idler,y_motor_y,join);
}

// Canonical clamp: travel X, clamped strand at Y=-pulley_r, belt centre Z=9.
module grip_body() {
    g=-pulley_r-belt_thickness/2;
    difference() {
        translate([0,g,5]) cuboid([28,8,14],anchor=BOT+BACK);
        for(x=[-8,8]) translate([x,g+eps,15]) cyl(d=m3_tap,h=9,orient=FWD,anchor=BOT);
    }
    for(x=[-12:2:12]) translate([x,g+0.15,9]) cuboid([0.8,0.5,5.6]);
}

module belt_cap() {
    difference() {
        cuboid([28,3,14],rounding=0.8,edges="Y",anchor=BOT+FWD);
        for(x=[-8,8]) translate([x,-eps,10]) cyl(d=m3_hole,h=3+2*eps,orient=BACK,anchor=BOT);
    }
}

module fitted_cap() {
    translate([0,-pulley_r+belt_thickness/2,5]) {
        color(frame_col) belt_cap();
        if(show_hardware) for(x=[-8,8]) translate([x,3,10]) fastener(10,dir=FWD);
    }
}

module idler_spacer(h=4) { difference() { cyl(d=5,h=h,anchor=BOT); hole(h); } }
module idler_hardware(deck=6,axle=25) {
    timing_pulley(true);
    color(frame_col) idler_spacer(4);
    up(14) color(frame_col) idler_spacer(1);
    if(show_hardware) {
        up(15) fastener(axle);
        down(deck+2.4) m3_nut();
    }
}

module base_frame() {
    difference() {
        union() {
            translate([(base_x0+base_x1)/2,(base_y0+base_y1)/2,0])
                cuboid([base_x1-base_x0,base_y1-base_y0,base_t],rounding=4,edges="Z",anchor=BOT);
            for(x=[-guide_x,guide_x]) translate([x,y_guide_mid,base_t-eps])
                cuboid([18,158,y_guide_z-base_t+eps],anchor=BOT);
            // Y motor stands behind the work; the shaft points down into the pulley.
            translate([y_belt_x,y_motor_y,y_motor_face-6]) cuboid([48,48,6],anchor=BOT);
            translate([y_belt_x+21,y_motor_y,base_t-eps])
                cuboid([6,48,y_motor_face-6-base_t+eps],anchor=BOT);
            translate([y_belt_x,y_motor_y+21,base_t-eps])
                cuboid([48,6,y_motor_face-6-base_t+eps],anchor=BOT);
            translate([y_belt_x,y_idler,base_t-eps])
                cuboid([20,20,y_guide_z-base_t+eps],rounding=3,edges="Z",anchor=BOT);
            // Locate the removable backing plate; support the entire copper board.
            for(s=[-1,1]) {
                translate([s*(board_x/2+1.4),0,base_t-eps]) cuboid([2,board_y+4.8,backing_t+eps],anchor=BOT);
                translate([0,s*(board_y/2+1.4),base_t-eps]) cuboid([board_x+4.8,2,backing_t+eps],anchor=BOT);
            }
            for(x=[-clip_x,clip_x],y=[-clip_y,clip_y]) translate([x,y,base_t-eps]) cyl(d=8,h=backing_t+board_z+eps,anchor=BOT);
        }
        for(x=[-guide_x,guide_x],y=rail_pattern) translate([x,y_guide_mid+y,y_guide_z-8]) hole(8,d=m3_tap);
        translate([y_belt_x,y_motor_y,y_motor_face-3]) nema17_mount_mask(6);
        translate([y_belt_x,y_idler,y_guide_z-6]) zrot(90) travel_slot(6);
        // Underside access for idler nut, retained in the 6 mm top deck.
        translate([y_belt_x,y_idler,-eps]) cuboid([10,14,y_guide_z-6+eps],anchor=BOT);
        for(x=[-clip_x,clip_x],y=[-clip_y,clip_y]) translate([x,y,board_top_z-8]) hole(8,d=m3_tap);
    }
}

module backing() { cuboid([board_x+0.4,board_y+0.4,backing_t],anchor=BOT); }
module board_clip() { difference() { cuboid([14,8,3],rounding=1,edges="Z",anchor=BOT); hole(3); } }

module board(anchor=CENTER,spin=0,orient=UP) {
    attachable(anchor,spin,orient,size=[board_x,board_y,board_z]) {
        union() {
            color_this("#746444") cuboid([board_x,board_y,board_z]);
            up(board_z/2-0.035) color_this("#c77e44") cuboid([board_x,board_y,0.035],anchor=BOT);
        }
        children();
    }
}

// Bridge coordinates are machine X / Z; Y=0 is the front rail mounting face.
module bridge() {
    difference() {
        union() {
            translate([-6,4,40]) cuboid([188,8,x_belt_z+24-40],anchor=BOT);
            for(x=[-guide_x,guide_x]) translate([x,0,y_block_z]) cuboid([34,30,foot_t+eps],anchor=BOT);
            // Extend the right foot outward to the belt grip beyond the rail.
            translate([guide_x+10,0,y_block_z]) cuboid([56,30,foot_t+eps],anchor=BOT);
            translate([y_belt_x,0,y_guide_z]) zrot(90) grip_body();
        }
        for(x=[-guide_x,guide_x]) translate([x,0,y_block_z]) xy_pattern() hole(foot_t);
        for(x=rail_pattern) translate([x,-eps,x_guide_z]) cyl(d=m3_tap,h=8+2*eps,orient=BACK,anchor=BOT);
        translate([-pulley_half,4,x_belt_z]) xrot(90) nema17_mount_mask(8);
        translate([pulley_half,-eps,x_belt_z]) xrot(-90) travel_slot(8+2*eps);
    }
}

module saddle() {
    difference() {
        union() {
            translate([0,16,42]) cuboid([44,6,42],anchor=BOT);
            translate([0,y_guide_mid,x_belt_z]) xrot(90) grip_body();
        }
        for(x=[-10,10],z=[-10,10]) translate([x,dock_front_y-eps,x_guide_z+z]) cyl(d=m3_hole,h=6+2*eps,orient=BACK,anchor=BOT);
        for(x=[-10,10],z=[-10,10]) translate([x,dock_front_y-eps,x_guide_z+z])
            cyl(d=6.2,h=saddle_screw_y-dock_front_y+eps,orient=BACK,anchor=BOT);
        tool_pattern() {
            translate([0,dock_front_y-eps,0]) cyl(d=m3_hole,h=6+2*eps,orient=BACK,anchor=BOT);
            translate([0,dock_back_y-3.4,0]) cyl(d=6.6,h=3.4+eps,orient=BACK,anchor=BOT,$fn=6);
        }
        translate([0,dock_front_y-eps,tool_datum_z]) cuboid([12+2*register_clearance,2.2+eps,16+2*register_clearance],anchor=FWD);
    }
}

// Four M3 holes on a 32 x 24 mm pattern, plus a 12 x 16 x 2 mm register.
module tool_blank() {
    difference() {
        union() {
            translate([0,dock_front_y-2.5,tool_datum_z]) cuboid([44,5,40],rounding=1,edges="Y");
            translate([0,dock_front_y-eps,tool_datum_z]) cuboid([12,2+eps,16],anchor=FWD);
        }
        tool_pattern() translate([0,dock_front_y-5-eps,0]) cyl(d=m3_hole,h=5+2*eps,orient=BACK,anchor=BOT);
    }
}

module cartridge() {
    difference() {
        union() {
            tool_blank();
            up(lower_guide) cuboid([24,12,8+eps],anchor=BOT);
            up(lower_guide_top) cuboid([48,12,3+eps],anchor=BOT);
            for(x=[-22,22]) translate([x,0,lower_guide_top+3-eps]) cuboid([4,12,upper_guide-lower_guide_top-3+2*eps],anchor=BOT);
            up(upper_guide) cuboid([48,12,8],anchor=BOT);
            translate([0,4,upper_guide]) cuboid([44,9,8],anchor=BOT+FWD);
            servo_bracket();
        }
        up(lower_guide-eps) cyl(d=pen_d+guide_clearance,h=upper_guide+8-lower_guide+2*eps,anchor=BOT);
        // Open approach from the front for all four dock screws and their driver.
        tool_pattern() translate([0,-35,0]) cyl(d=6.4,h=43+eps,orient=BACK,anchor=BOT);
        tool_pattern() translate([0,8-eps,0]) cyl(d=m3_hole,h=7+2*eps,orient=BACK,anchor=BOT);
    }
}

// Open ear mount. Slide the servo/arm unit in from the front (-Y), seat both ears, then
// fit two M2x6 screws from +X into 4 mm-deep tapped pilots. The case and lead
// have clearance; the two flat pads, not cable ties, locate the servo.
module servo_bracket() {
    difference() {
        union() {
            for(z=servo_mount_zs) translate([servo_mount_x-servo_bracket_t,servo_axis.y-8.5,z-3])
                cuboid([servo_bracket_t,17,6],anchor=BOT+LEFT+FWD);
            translate([servo_mount_x-servo_bracket_t,servo_axis.y+7,servo_mount_zs[0]-3])
                cuboid([servo_bracket_t,4,servo_mount_zs[1]-servo_mount_zs[0]+6],anchor=BOT+LEFT+FWD);
            // Rectangular connection to the upper left guide, clear of the fork.
            translate([servo_mount_x-servo_bracket_t,servo_axis.y+7,upper_guide+2])
                cuboid([7.4,-servo_axis.y-4,6],anchor=BOT+LEFT+FWD);
        }
        // Continue the case opening through the front edges of both pads so
        // the body can slide in without catching their inner corners.
        translate([servo_mount_x-servo_bracket_t-eps,servo_axis.y-10,servo_case_z0-0.4])
            cuboid([servo_bracket_t+2*eps,10+hs65mg_width/2+0.4,hs65mg_length+0.8],anchor=BOT+LEFT+FWD);
        for(z=servo_mount_zs) translate([servo_mount_x-servo_bracket_t-eps,servo_axis.y,z])
            cyl(d=1.6,h=servo_bracket_t+2*eps,orient=RIGHT,anchor=BOT);
    }
}

// Moving collar clamps to the round pen; the elevated fork is lifted by a servo arm.
// Origin is the collar underside, not the tip. Slots make its M3 clamp functional.
module plunger() {
    difference() {
        union() {
            cyl(d=16,h=6,anchor=BOT);
            translate([-4,-6.5,0]) cuboid([28,17,6],anchor=BOT);
            translate([-17,-8.5,5.8]) cuboid([4,3,fork_h+4-5.8+eps],anchor=BOT);
            translate([-9,-10.25,fork_h+4]) cuboid([20,6.5,3],anchor=BOT);
            // Only this narrow pad touches the raised round end of the lift arm.
            translate([-4,-12.25,fork_h]) cuboid([3,6.5,4+eps],anchor=BOT);
        }
        hole(7,d=pen_d+0.15);
        translate([0,-9,-eps]) cuboid([1.2,18,7+2*eps],anchor=BOT);
        translate([-19,-9,3]) cyl(d=m3_hole,h=30,orient=RIGHT,anchor=BOT);
        // Recess the clamp head flush so it clears the fixed guide / servo bracket.
        translate([-18-eps,-9,3]) cyl(d=5.8,h=3+eps,orient=RIGHT,anchor=BOT);
        translate([7.5,-9,3]) cyl(d=6.6,h=3,orient=RIGHT,anchor=BOT,$fn=6);
    }
}

// Print in XY. X=servo axis in assembly; this part fixes to the supplied horn.
module lift_arm() {
    difference() {
        union() {
            linear_extrude(4) hull() { circle(r=5); right(arm_r) circle(r=arm_tip_r); }
            translate([arm_r,0,4-eps]) cyl(r=arm_tip_r,h=3+eps,anchor=BOT);
        }
        hole(4,d=4.2);          // access to the servo horn's centre retaining screw
        for(x=horn_screw_radii) right(x) hole(4,d=2.2);
    }
}

module arm_transform(lift=0) {
    // 2D arm X -> world +Y, 2D arm Y -> world +Z, extrusion -> world +X.
    translate(servo_axis) xrot(arm_angle(lift))
        multmatrix([[0,0,1,servo_horn_offset],[1,0,0,0],[0,1,0,0],[0,0,0,1]]) children();
}

module servo() {
    translate(servo_axis) yrot(90) zrot(180) hs65mg(anchor="shaft",wire_length=8);
}

module servo_mount_fasteners() {
    for(z=servo_mount_zs) translate([servo_mount_x+hs65mg_ear_t,servo_axis.y,z]) fastener(6,dir=LEFT,d=2);
}

module dock_fasteners() {
    for(x=[-10,10],z=[-10,10]) translate([x,saddle_screw_y,x_guide_z+z]) fastener(6,dir=BACK);
    tool_pattern() {
        translate([0,dock_front_y-5,0]) fastener(10,dir=BACK);
        translate([0,dock_back_y-3.4,0]) rot(from=UP,to=BACK) m3_nut();
    }
}

module servo_horn(lift=0) {
    // Stock cross horn with three arms trimmed off and two added pilot holes.
    translate(servo_axis) xrot(arm_angle(lift))
        multmatrix([[0,0,1,0],[1,0,0,0],[0,1,0,0],[0,0,0,1]])
            hs65mg_horn(trimmed=true,drilled=true,screw=show_hardware,drill_radii=horn_screw_radii);
}

module spring(lift=0) {
    color("#7d8993") up(collar_z+lift+collar_h)
        linear_extrude(height=spring_length(lift),twist=360*spring_turns,slices=84)
            right(spring_mean_d/2) circle(d=spring_wire,$fn=8);
}

module pen(lift=0) {
    color("#c1c8c8") up(board_top_z+lift+6) cyl(d=pen_d,h=pen_length-6,anchor=BOT);
    color("#626d74") up(board_top_z+lift) cyl(d1=0.2,d2=pen_d,h=6,anchor=BOT);
}

module head_fixed() { color(frame_col) cartridge(); servo(); if(show_hardware) servo_mount_fasteners(); }
module head_fasteners(lift=0) {
    translate([-15,-9,collar_z+lift+3]) fastener(25,dir=RIGHT);
    translate([7.5,-9,collar_z+lift+3]) rot(from=UP,to=RIGHT) m3_nut();
    arm_transform(lift) for(r=horn_screw_radii) translate([r,0,4]) fastener(6,d=2);
}

module head_moving(lift=0) {
    color(move_col) up(collar_z+lift) plunger();
    color(move_col) arm_transform(lift) lift_arm();
    pen(lift);
    spring(lift);
    // Supplied horn is separate from the printed arm, retained on the servo spline.
    servo_horn(lift);
    if(show_hardware) head_fasteners(lift);
}

module head(lift=0) { head_fixed(); head_moving(lift); }
module carriage(lift=0) {
    color(move_col) saddle();
    head(lift);
    if(show_hardware) dock_fasteners();
}

module fixed_hardware() {
    for(x=[-guide_x,guide_x]) translate([x,y_guide_mid,y_guide_z]) zrot(90) {
        linear_rail();
        if(show_hardware) rail_screws();
    }
    translate([y_belt_x,y_motor_y,y_motor_face]) nema17(orient=DOWN,spin=90);
    translate([y_belt_x,y_motor_y,y_guide_z+18]) xrot(180) timing_pulley();
    translate([y_belt_x,y_idler,y_guide_z]) idler_hardware();
    if(show_hardware) translate([y_belt_x,y_motor_y,y_motor_face-6]) xy_pattern(31) fastener(8,dir=UP);
}

module bridge_hardware(y=0) {
    by=y+y_guide_mid;
    for(x=[-guide_x,guide_x]) {
        translate([x,by,y_guide_z]) zrot(90) linear_block();
        if(show_hardware) translate([x,by,y_block_z+foot_t]) xy_pattern() fastener(8);
    }
    translate([0,by,x_guide_z]) xrot(90) {
        linear_rail();
        if(show_hardware) rail_screws();
    }
    translate([-pulley_half,by+8,x_belt_z]) nema17_pancake(orient=FWD,spin=90);
    translate([-pulley_half,by,x_belt_z]) xrot(90) timing_pulley();
    translate([pulley_half,by,x_belt_z]) xrot(90) idler_hardware(deck=8,axle=30);
    if(show_hardware) translate([-pulley_half,by,x_belt_z]) xrot(90) xy_pattern(31) fastener(10);
    translate([y_belt_x,by,y_guide_z]) zrot(90) fitted_cap();
}

module assembly(x=X,y=Y,lift=LIFT) {
    assert(abs(x)<=35 && abs(y)<=45 && lift>=0 && lift<=5, "Motion outside the working envelope.");
    color(frame_col) base_frame();
    color("#ddd1b4") up(base_t) backing();
    if(show_board) up(board_bottom) board(anchor=BOT);
    for(xx=[-clip_x,clip_x],yy=[-clip_y,clip_y]) translate([xx,yy,board_top_z]) {
        color(move_col) board_clip();
        if(show_hardware) up(3) fastener(8);
    }
    fixed_hardware();
    translate([0,y+y_guide_mid,0]) color(move_col) bridge();
    bridge_hardware(y);
    y_drive_belt(y+y_guide_mid);
    translate([0,y+y_guide_mid,x_belt_z]) xrot(90) belt_path(join=x);
    translate([x,y,0]) {
        translate([0,y_guide_mid,x_guide_z]) xrot(90) linear_block();
        color(move_col) saddle();
        head(lift);
        translate([0,y_guide_mid,x_belt_z]) xrot(90) fitted_cap();
        if(show_hardware) dock_fasteners();
    }
    if(show_envelope) %up(board_top_z) color([0.2,0.8,0.5,0.2]) cuboid([x_travel,y_travel,lift_max],anchor=BOT);
}

// Hardware against every print, including the parts it fastens. Only the two
// intentional M2 tapped pilot engagements are removed from this check.
module head_assembly_check(lift=0) {
    intersection() { saddle(); cartridge(); }
    intersection() {
        arm_transform(lift) translate([horn_screw_radii[0],0,4]) fastener(6,d=2);
        arm_transform(lift) translate([horn_screw_radii[1],0,4]) fastener(6,d=2);
    }
    intersection() {
        union() { saddle(); cartridge(); up(collar_z+lift) plunger(); arm_transform(lift) lift_arm(); }
        union() {
            dock_fasteners();
            head_fasteners(lift);
            difference() {
                servo_mount_fasteners();
                for(z=servo_mount_zs) translate([servo_mount_x-servo_bracket_t-eps,servo_axis.y,z])
                    cyl(d=2+eps,h=servo_bracket_t+2*eps,orient=RIGHT,anchor=BOT);
            }
        }
    }
    // Dock is installed before servo and moving linkage. Check driver access
    // at that assembly stage; the ear screws remain reachable with the linkage.
    intersection() {
        cartridge();
        tool_pattern() translate([0,-40,0]) cyl(d=3,h=45,orient=BACK,anchor=BOT);
    }
    intersection() {
        union() { cartridge(); up(collar_z+lift) plunger(); arm_transform(lift) lift_arm(); servo(); }
        union() {
            for(z=servo_mount_zs) translate([servo_mount_x+hs65mg_ear_t+2+eps,servo_axis.y,z])
                cyl(d=3,h=35,orient=RIGHT,anchor=BOT);
        }
    }
}

// Assembly stages: cartridge, collar, then servo with horn/arm already fitted,
// all approach from the front. Convex hulls are
// deliberately avoided: they would fill the bracket openings and pen bores.
module assembly_access_check() {
    for(offset=[-40:2:-2]) {
        intersection() { saddle(); fwd(-offset) cartridge(); }
        intersection() { cartridge(); fwd(-offset) up(collar_z) plunger(); }
        intersection() {
            union() { cartridge(); up(collar_z) plunger(); }
            fwd(-offset) union() {
                servo(); servo_horn(); arm_transform() lift_arm();
                arm_transform() for(r=horn_screw_radii) translate([r,0,4]) fastener(6,d=2);
            }
        }
    }
    // Install/reach the four recessed saddle screws before fitting the cartridge.
    intersection() {
        saddle();
        for(x=[-10,10],z=[-10,10]) translate([x,-25,x_guide_z+z])
            cyl(d=3,h=saddle_screw_y-3+25,orient=BACK,anchor=BOT);
    }
}

// Excludes intended bearing contact, tapped shafts, spring seats and pen/board contact.
module collision_check() {
    union() {
        head_assembly_check(LIFT);
        // The Y belt must clear the tool, rail blocks and fixed frame.
        // Its toothed grip and pulley contact are intentionally excluded.
        intersection() {
            y_drive_belt();
            union() {
                base_frame();
                translate([X,Y,0]) { saddle(); head(LIFT); }
                for(x=[-guide_x,guide_x]) {
                    translate([x,y_guide_mid,y_guide_z]) zrot(90) linear_rail();
                    translate([x,Y+y_guide_mid,y_guide_z]) zrot(90) linear_block();
                }
            }
        }
        intersection() {
            translate([y_belt_x,Y+y_guide_mid,y_guide_z]) zrot(90) fitted_cap();
            union() { base_frame(); fixed_hardware(); translate([X,Y,0]) head(LIFT); }
        }
        intersection() {
            translate([0,Y+y_guide_mid,0]) bridge();
            union() { base_frame(); fixed_hardware(); }
        }
        intersection() {
            translate([X,Y,0]) union() { saddle(); cartridge(); up(collar_z+LIFT) plunger(); arm_transform(LIFT) lift_arm(); servo(); }
            union() { base_frame(); fixed_hardware(); translate([0,Y+y_guide_mid,0]) bridge(); }
        }
        intersection() {
            union() { cartridge(); saddle(); }
            union() { up(collar_z+LIFT) plunger(); arm_transform(LIFT) lift_arm(); servo_horn(LIFT); servo(); head_fasteners(LIFT); }
        }
        intersection() {
            up(collar_z+LIFT) plunger();
            union() { arm_transform(LIFT) lift_arm(); servo_horn(LIFT); }
        }
        // Check the detailed case, ears and boss against the moving linkage.
        intersection() {
            servo();
            union() { up(collar_z+LIFT) plunger(); arm_transform(LIFT) lift_arm(); servo_horn(LIFT); head_fasteners(LIFT); }
        }
        intersection() {
            translate([X,Y,0]) union() { cartridge(); up(collar_z+LIFT) plunger(); servo(); }
            up(board_bottom) board(anchor=BOT);
        }
        // Check the head against moving guide blocks and drive envelopes as well.
        intersection() {
            translate([X,Y,0]) union() { saddle(); cartridge(); up(collar_z+LIFT) plunger(); servo(); }
            union() {
                for(x=[-guide_x,guide_x]) translate([x,Y+y_guide_mid,y_guide_z]) zrot(90) linear_block();
                translate([X,Y+y_guide_mid,x_guide_z]) xrot(90) linear_block();
                translate([0,Y+y_guide_mid,x_guide_z]) xrot(90) linear_rail();
                translate([-pulley_half,Y+y_guide_mid+8,x_belt_z]) nema17_pancake(orient=FWD,spin=90);
                for(x=[-pulley_half,pulley_half]) translate([x,Y+y_guide_mid,x_belt_z]) xrot(90) timing_pulley(x>0);
            }
        }
    }
}

// Export transforms: each single part sits on Z=0. Some parts need supports.
module print_part(p) {
    if(p=="base") base_frame();
    else if(p=="bridge") translate([0,-y_block_z,15]) xrot(-90) bridge();
    else if(p=="saddle") translate([0,84,-dock_front_y]) xrot(90) saddle();
    else if(p=="cartridge") translate([0,-lower_guide,dock_front_y+2]) xrot(-90) cartridge();
    else if(p=="plunger") plunger();
    else if(p=="lift_arm") lift_arm();
    else if(p=="tool_blank") translate([0,tool_datum_z,5-dock_front_y]) xrot(90) tool_blank();
    else if(p=="belt_cap") xrot(90) belt_cap();
    else if(p=="idler_spacer") idler_spacer(spacer_h);
    else if(p=="board_clip") board_clip();
    else if(p=="backing") backing();
    else assert(false,str("Unknown part: ",p));
}

module layout() {
    parts=["base","bridge","saddle","cartridge","plunger","lift_arm","tool_blank","belt_cap","idler_spacer","board_clip","backing"];
    for(i=[0:len(parts)-1]) translate([(i%4)*240,floor(i/4)*250,0]) print_part(parts[i]);
}

echo(str("XYZ2: fixed ",board_x," x ",board_y," board; XY travel ",x_travel," x ",y_travel,"; pen lift ",lift_max));
echo(str("Envelope: ",base_x1-base_x0," x ",base_y1-base_y0," x ",machine_height()," mm; board top ",board_top_z));
echo(str("GT2 cut lengths, including 20 mm trimming allowance: X ",4*pulley_half+40+20,"; Y ",2*(y_motor_y-y_idler)+40+20));
echo(str("Pen spring installed length: ",spring_length(LIFT)," mm; servo angle: ",arm_angle(LIFT)));
if(spring_rate>0) echo(str("Nominal spring force at contact: ",spring_rate*spring_preload," N (user-supplied spring rate)."));

if(part=="assembly") assembly();
else if(part=="head") head(LIFT);
else if(part=="carriage") carriage(LIFT);
else if(part=="head_assembly_check") head_assembly_check(LIFT);
else if(part=="assembly_access_check") assembly_access_check();
else if(part=="layout") layout();
else if(part=="collision_check") collision_check();
else if(part!="none") print_part(part);
