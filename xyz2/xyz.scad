// Compact moving-board XYZ table. Dimensions are mm.
// X: 39 mm NEMA17 + GT2; Y: pancake NEMA17 + GT2; Z: integrated TR8x8.
// Three identical 150 mm MGN12H rails. Read README.md for BOM and assembly.
include <nema17_tr8.scad>
nema17_demo = false;
nema17_tr8_demo = false;

/* [View] */
part = "assembly"; // [assembly,base,y_frame,tray,column,z_carriage,tool_plate,pen_adapter,belt_clamp,idler_spacer,board_clip,print_layout,travel_envelope,collision_check,none]
show_board = true;
show_tool = true;
show_hardware = true;
show_envelope = false;
show_threads = false;
animate_motion = false;

/* [Board and motion] */
board_x = 70;
board_y = 90;
board_z = 1.6;
x_travel = 70;
y_travel = 90;
z_travel = 40;
// Tool coordinates relative to board centre / top surface.
tool_x = 0; // [-35:1:35]
tool_y = 0; // [-45:1:45]
tool_z = 15; // [0:1:40]

/* [Fit] */
slide_clearance = 0.2;
m3_clearance = 3.4;
m3_pilot = 2.6;
tool_diameter = 8;
spacer_height = 4; // [1,4]

/* [Hidden] */
$fn=0; $fa=4; $fs=$preview ? 0.8 : 0.4;
$slop=0.2;
ep=0.02;
printed = "#247c8e";
moving = "#e8a348";
dark = "#253344";
steel = "#b8c4ce";

// MGN12H nominal envelope; vendor drawing links in README.md.
rail_l = 150;
rail_w = 12;
rail_h = 8;
block_l = 45.4;
block_w = 27;
block_h = 13;                 // rail underside to carriage top
rail_holes = [-62.5,-37.5,-12.5,12.5,37.5,62.5];
block_pitch = 20;

deck_t = 6;
base_z = 42;                  // room underneath for the 39 mm X motor
base_top = base_z+deck_t;
belt_offset = -28;            // canonical belt stage: rail along X, belt at -Y
pulley_c = 76;
pulley_r = 20*2/(2*PI);       // GT2, 2 mm pitch, 20 teeth
belt_t = 1.4;
belt_w = 6;
belt_z = 9;                  // relative to rail underside
grip_y = belt_offset+pulley_r;
idler_adjust = 3;

// The unmodified pancake shaft projects 18 mm above its 6 mm mounting deck.
// Clearance is provided by the tray's integral central riser.
y_frame_z = base_top+block_h+11;
y_rail_z = y_frame_z+deck_t;
tray_mount_z = y_rail_z+block_h;
tray_riser = 9;
tray_t = 4;
board_lift = 3;
board_bottom = tray_mount_z+tray_riser+tray_t+board_lift;
board_top = board_bottom+board_z;
tray_size = [board_x+24,board_y+12];
clip_x = board_x/2+5;
clip_y = board_y/2-15;

column_front = max(board_y/2+y_travel/2+6, pulley_c+10)+12;
column_t = 8;
tool_reach = 50;              // dock datum above example tool tip
z_mid = board_top+tool_reach+z_travel/2;
z_rail_mid = z_mid;
z_motor_face = z_mid+z_travel/2+27+8;
column_top = max(z_rail_mid+rail_l/2+4,z_motor_face);
z_screw_x = 34;
z_screw_y = column_front-26;
z_carriage_back = column_front-block_h;
dock_y = 20;
dock_front = dock_y-6;
base_front = -103;
base_back = column_front+32;
base_w = 204;
base_d = base_back-base_front;

X = animate_motion ? x_travel/2*sin(360*$t) : tool_x;
Y = animate_motion ? y_travel/2*cos(360*$t) : tool_y;
Z = animate_motion ? z_travel*(1-cos(720*$t))/2 : tool_z;

// Stage motion is opposite to tool coordinates on the workpiece.
function z_height(z) = board_top+tool_reach+z;
function z_nut_pos(z) = z_motor_face-z_height(z)-7.5;
function belt_cut_length() = ceil(4*pulley_c+2*PI*pulley_r+20);

assert(board_x>40 && board_y>50 && board_z>0, "Board dimensions too small for this tray hardware.");
assert(x_travel>=board_x && y_travel>=board_y, "Travel must cover the entire board.");
assert(max(x_travel,y_travel,z_travel)+block_l+4<=rail_l, "Carriage runs off a rail.");
assert(abs(X)<=x_travel/2 && abs(Y)<=y_travel/2 && Z>=0 && Z<=z_travel, "Tool position outside travel.");
assert(z_nut_pos(z_travel)>=deck_t+2, "Z nut hits motor bracket.");
assert(z_nut_pos(0)+2+10.5+2<=100, "Z nut runs off the 100 mm screw.");
assert(y_frame_z-n17p_len>=base_top+1, "Pancake motor hits the base.");
assert(tray_mount_z+tray_riser>=y_frame_z+24+2, "Tray hits the uncut Y motor shaft.");
assert(column_front-(board_y/2+y_travel/2+6)>=12, "Tray sweep hits column.");
assert(tool_diameter>=3 && tool_diameter<=12, "Pen adapter supports tool diameters from 3 to 12 mm.");

// Through-hole with optional head counterbore, measured up from z=0.
module clearance(h, cbore=0, d=m3_clearance) {
    down(ep) cyl(d=d,h=h+2*ep,anchor=BOT);
    if (cbore>0) up(h-cbore) cyl(d=6.4,h=cbore+ep,anchor=BOT);
}

module block_pattern() {
    for (x=[-1,1],y=[-1,1]) translate([x*block_pitch/2,y*block_pitch/2,0]) children();
}

module slot(d=3.4,l=6,h=10) {
    hull() for (x=[-l/2,l/2]) right(x) cyl(d=d,h=h,anchor=BOT);
}

// Hardware envelopes, not replacement manufacturing models.
module bolt(l=8,orient=DOWN) {
    color(steel) rot(from=UP,to=orient) {
        cyl(d=3,h=l,anchor=BOT);
        difference() {
            cyl(d=5.5,h=3,anchor=TOP);
            down(1.5) cyl(d=2.9,h=2,anchor=TOP,$fn=6);
        }
    }
}

module hex_nut() {
    color(steel) difference() {
        cyl(d=6.35,h=2.4,anchor=BOT,$fn=6);
        cyl(d=3,h=2.4+2*ep,anchor=BOT);
    }
}

module guide_rail() {
    color(steel) difference() {
        cuboid([rail_l,rail_w,rail_h],chamfer=0.5,edges="X",anchor=BOT);
        for (x=rail_holes) right(x) clearance(rail_h,4.5,d=3.5);
        for (s=[-1,1]) translate([0,s*rail_w/2,5])
            cyl(d=2,h=rail_l+2,orient=RIGHT);
    }
}

module guide_block() {
    color(steel) difference() {
        up(3) cuboid([block_l,block_w,block_h-3],chamfer=0.6,edges="X",anchor=BOT);
        down(ep) cuboid([block_l+2,rail_w+0.4,rail_h+0.3+ep],anchor=BOT);
        block_pattern() up(block_h-3.5) cyl(d=2.5,h=3.6,anchor=BOT);
    }
    color(dark) for (s=[-1,1]) right(s*(block_l/2-1)) difference() {
        up(3) cuboid([2,block_w+0.4,block_h-3],anchor=BOT);
        cuboid([3,rail_w+0.5,rail_h+0.4],anchor=BOT);
    }
}

// Pulley / idler teeth are intentionally represented by pitch envelopes.
module pulley(idler=false) {
    color(steel) difference() {
        union() {
            if (!idler) cyl(d=16,h=5,anchor=BOT);
            up(5) cyl(d=12.22,h=8,anchor=BOT);
            for (z=[4,13]) up(z) cyl(d=18,h=1,anchor=BOT);
        }
        down(ep) cyl(d=idler ? 3 : 5,h=15,anchor=BOT);
    }
}

module belt_loop(pos=0) {
    color(dark) up(belt_z-belt_w/2) difference() {
        linear_extrude(belt_w) difference() {
            hull() for (s=[-1,1]) translate([s*pulley_c,belt_offset]) circle(r=pulley_r+belt_t/2);
            hull() for (s=[-1,1]) translate([s*pulley_c,belt_offset]) circle(r=pulley_r-belt_t/2);
        }
        // Open ends meet at the moving clamp; this is not an endless belt.
        translate([pos,grip_y,0]) cuboid([0.6,belt_t+1,belt_w+2],anchor=BOT);
    }
}

module belt_hardware(pos=0,pancake=false) {
    guide_rail();
    right(pos) guide_block();
    translate([-pulley_c,belt_offset,-deck_t])
        if (pancake) nema17_pancake(spin=180); else nema17(spin=180);
    translate([-pulley_c,belt_offset,0]) pulley();
    translate([pulley_c,belt_offset,0]) {
        pulley(idler=true);
        color(printed) idler_spacer();
        up(14) color(printed) idler_spacer(h=1);
        if (show_hardware) {
            up(15) bolt(25);
            down(deck_t+2.4) hex_nut();
        }
    }
    belt_loop(pos);
    if (show_hardware) {
        for (x=rail_holes) translate([x,0,rail_h-4.5]) bolt(8);
        translate([-pulley_c,belt_offset,0]) grid_copies(spacing=31,n=2) bolt(8);
    }
}

module stage_deck_holes() {
    for (x=rail_holes) right(x) clearance(deck_t,d=m3_pilot);
    translate([-pulley_c,belt_offset,deck_t/2]) nema17_mount_mask(depth=deck_t);
    translate([pulley_c,belt_offset,-ep]) slot(l=2*idler_adjust,h=deck_t+2*ep);
}

// All printed assemblies have mating holes. M3 pilot holes are tapped after printing.
module base() {
    difference() {
        union() {
            translate([0,(base_front+base_back)/2,base_z])
                cuboid([base_w,base_d,deck_t],rounding=5,edges="Z",anchor=BOT);
            // Integral corner feet leave the X motor and fasteners accessible.
            for (x=[-base_w/2+10,base_w/2-10],y=[base_front+10,base_back-10])
                translate([x,y,0]) cuboid([18,18,base_z+ep],rounding=3,edges="Z",anchor=BOT);
        }
        up(base_z) stage_deck_holes();
        // Four through-bolts hold the column foot, with nuts accessible underneath.
        for (x=[-44,44],y=[column_front+14,column_front+24]) translate([x,y,base_z]) clearance(deck_t);
        // Slots for a bench strap; they also provide wire routing.
        for (x=[-base_w/2+14,base_w/2-14]) translate([x,38,base_z-ep])
            cuboid([5,24,deck_t+2*ep],rounding=2,edges="Z",anchor=BOT);
    }
}

// Canonical clamp: belt along X, teeth facing +Y, two screws ABOVE the belt.
module belt_grip(top=24) {
    difference() {
        translate([0,grip_y+belt_t/2,5])
            cuboid([28,8,top-5],anchor=BOT+FWD);
        for (x=[-8,8]) translate([x,grip_y-1,belt_z+6])
            cyl(d=m3_pilot,h=12,orient=BACK,anchor=BOT);
    }
    // Printed teeth engage both cut belt ends; leave a 0.6 mm split in the preview.
    for (x=[-12:2:12]) translate([x,grip_y+belt_t/2-0.15,belt_z])
        cuboid([0.8,0.5,belt_w-0.4]);
}

module belt_clamp() {
    difference() {
        cuboid([28,3,14],rounding=1,edges="Y",anchor=BOT+BACK);
        for (x=[-8,8]) translate([x,ep,10])
            cyl(d=m3_clearance,h=3+2*ep,orient=FWD,anchor=BOT);
    }
}

module fitted_belt_clamp() {
    translate([0,grip_y-belt_t/2,belt_z-4]) {
        color(moving) belt_clamp();
        if (show_hardware) for (x=[-8,8]) translate([x,-3,10]) bolt(10,orient=BACK);
    }
}

module idler_spacer(h=4) {
    difference() {
        cyl(d=5,h=h,anchor=BOT);
        down(ep) cyl(d=m3_clearance,h=h+2*ep,anchor=BOT);
    }
}

// One print combines the X carriage riser, X belt grip and complete Y deck.
// Origin is the X bearing top; the Y rail runs along world Y.
module y_frame() {
    difference() {
        union() {
            cuboid([34,34,11+ep],anchor=BOT);
            up(11) zrot(90) translate([-4,-15,0])
                cuboid([194,74,deck_t],rounding=4,edges="Z",anchor=BOT);
            down(block_h) belt_grip(top=block_h+11+ep);
        }
        up(11) zrot(90) stage_deck_holes();
        block_pattern() clearance(11+deck_t,cbore=3);
    }
}

module tray() {
    difference() {
        union() {
            cuboid([34,34,tray_riser+ep],anchor=BOT);
            up(tray_riser) cuboid([tray_size.x,tray_size.y,tray_t],rounding=3,edges="Z",anchor=BOT);
            // Edge support gives solder tails 3 mm of space beneath the board.
            for (s=[-1,1]) translate([s*(board_x/2-2.5),0,tray_riser+tray_t-ep])
                cuboid([5,board_y,board_lift+ep],anchor=BOT);
            for (s=[-1,1]) translate([0,s*(board_y/2+1+slide_clearance),tray_riser+tray_t-ep])
                cuboid([board_x,2,board_lift+board_z+ep],anchor=BOT);
            for (x=[-clip_x,clip_x],y=[-clip_y,clip_y]) translate([x,y,tray_riser+tray_t-ep])
                cyl(d=8,h=board_lift+board_z+ep,anchor=BOT);
            down(block_h) zrot(90) belt_grip(top=block_h+tray_riser+tray_t);
        }
        block_pattern() clearance(tray_riser+tray_t);
        for (x=[-clip_x,clip_x],y=[-clip_y,clip_y]) translate([x,y,tray_riser-ep])
            clearance(tray_t+board_lift+board_z+ep,d=m3_pilot);
    }
}

module board_clip() {
    difference() {
        cuboid([14,8,3],rounding=1,edges="Z",anchor=BOT);
        clearance(3);
    }
}

// Local rail X -> world Z; rail top faces the front (-Y).
module z_rail_transform() {
    multmatrix([[0,-1,0,0],[0,0,-1,column_front],[1,0,0,z_rail_mid],[0,0,0,1]]) children();
}

module column() {
    difference() {
        union() {
            translate([0,column_front,base_top])
                cuboid([116,column_t,column_top-base_top],anchor=BOT+FWD);
            translate([0,column_front,base_top])
                cuboid([116,30,8],rounding=2,edges="Z",anchor=BOT+FWD);
            // Two integral back ribs triangulate the column to its foot.
            for (x=[-52,52]) hull() {
                translate([x,column_front+column_t,base_top]) cuboid([10,22,8],anchor=BOT+FWD);
                translate([x,column_front+column_t,base_top+85]) cuboid([10,2,4],anchor=BOT+FWD);
            }
            translate([z_screw_x,column_front-50,z_motor_face-deck_t])
                cuboid([48,50+column_t,deck_t],anchor=BOT+FWD);
            // Shelf ribs stay outside the moving carriage's 36 mm flange.
            for (x=[22,z_screw_x+23]) hull() {
                translate([x,column_front-48,z_motor_face-deck_t]) cuboid([3,48,2],anchor=BOT+FWD);
                translate([x,column_front,z_motor_face-28]) cuboid([3,4,2],anchor=BOT+FWD);
            }
        }
        for (x=[-44,44],y=[column_front+14,column_front+24]) translate([x,y,base_top]) clearance(8);
        z_rail_transform() for (x=rail_holes) translate([x,0,-column_t]) clearance(column_t,d=m3_pilot);
        translate([z_screw_x,z_screw_y,z_motor_face-deck_t/2]) nema17_mount_mask(depth=deck_t);
        // Screw-head and driver access through the shelf ribs from below.
        translate([z_screw_x,z_screw_y,z_motor_face-deck_t-30]) grid_copies(spacing=31,n=2)
            cyl(d=6.4,h=30+ep,anchor=BOT);
    }
}

// Z tool arm: rail flange, two vertical webs, nut shelf, and standardized dock.
// Origin is the tool dock datum. The tool tip is tool_reach below it.
module z_carriage() {
    difference() {
        union() {
            translate([0,z_carriage_back-3,0]) cuboid([36,6,54]);
            translate([0,(dock_y+z_carriage_back)/2,-3])
                cuboid([36,z_carriage_back-dock_y+ep,6]);
            for (x=[-15,15]) hull() {
                translate([x,z_carriage_back-6,-4]) cuboid([6,2,44]);
                translate([x,dock_y+5,-3]) cuboid([6,2,6]);
            }
            translate([z_screw_x,z_screw_y,-6]) cuboid([40,26,6],anchor=BOT);
            translate([0,dock_y,0]) cuboid([36,12,42],rounding=2,edges="Y");
        }
        // Bearing mounting screws enter from the front of the vertical flange.
        for (x=[-10,10],z=[-10,10]) translate([x,z_carriage_back-6-ep,z])
            cyl(d=m3_clearance,h=6+2*ep,orient=BACK,anchor=BOT);
        for (x=[-10,10],z=[-10,10]) translate([x,dock_y+10,z])
            cyl(d=6.4,h=z_carriage_back-6-(dock_y+10)+ep,orient=BACK,anchor=BOT);
        translate([z_screw_x,z_screw_y,-3]) tr8_nut_mount_mask(depth=6,type="motor");
        // Rectangular registration pocket constrains rotation; screws supply clamp load.
        translate([0,dock_front-ep,0]) cuboid([12+2*slide_clearance,2.2+ep,20+2*slide_clearance],anchor=FWD);
        tool_pattern() {
            translate([0,dock_front-ep,0]) cyl(d=m3_clearance,h=12+2*ep,orient=BACK,anchor=BOT);
            translate([0,dock_y+6-2.5,0]) cyl(d=6.6,h=2.5+ep,orient=BACK,anchor=BOT,$fn=6);
        }
    }
}

module tool_pattern() {
    for (x=[-12,12],z=[-14,14]) translate([x,0,z]) children();
}

// Reusable module for new tools; origin is the dock datum, flat back at dock_front.
module tool_plate() {
    difference() {
        union() {
            translate([0,dock_front-2.5,0]) cuboid([36,5,42],rounding=2,edges="Y");
            translate([0,dock_front-ep,0]) cuboid([12,2+ep,20],anchor=FWD);
        }
        tool_pattern() translate([0,dock_front-5-ep,0])
            cyl(d=m3_clearance,h=5+2*ep,orient=BACK,anchor=BOT);
    }
}

module pen_adapter() {
    difference() {
        union() {
            tool_plate();
            cyl(d=20,h=20);
            translate([0,-9,0]) cuboid([20,8,12],rounding=1,edges="Z");
        }
        cyl(d=tool_diameter+0.3,h=24);
        translate([0,-9,0]) cuboid([1.4,18,24]);
        translate([-11,-9,0]) cyl(d=m3_clearance,h=22,orient=RIGHT,anchor=BOT);
        translate([10-2.5,-9,0]) cyl(d=6.6,h=3,orient=RIGHT,anchor=BOT,$fn=6);
    }
}

module example_tool() {
    color("#f2eee5") up(9-tool_reach/2) cyl(d=tool_diameter,h=tool_reach+2);
    color("#444b56") down(tool_reach) cyl(d1=0.6,d2=tool_diameter,h=8,anchor=BOT);
}

// Preserve the supplied board's BOSL2 attachable interface.
module board(anchor=CENTER,spin=0,orient=UP) {
    attachable(anchor,spin,orient,size=[board_x,board_y,board_z]) {
        color_this("#885533") cuboid([board_x,board_y,board_z]);
        children();
    }
}

module board_assembly() {
    color(moving) tray();
    if (show_board) up(tray_riser+tray_t+board_lift) board(anchor=BOT);
    for (x=[-clip_x,clip_x],y=[-clip_y,clip_y]) translate([x,y,tray_riser+tray_t+board_lift+board_z]) {
        color(printed) board_clip();
        if (show_hardware) up(3) bolt(8);
    }
    if (show_hardware) block_pattern() up(tray_riser+tray_t) bolt(16);
    down(block_h) zrot(90) fitted_belt_clamp();
}

module xy_moving(x=0,y=0) {
    translate([-x,0,base_top+block_h]) color(moving) y_frame();
    translate([-x,0,base_top]) fitted_belt_clamp();
    translate([-x,0,y_rail_z]) zrot(90) belt_hardware(pos=-y,pancake=true);
    translate([-x,-y,tray_mount_z]) board_assembly();
    if (show_hardware) translate([-x,0,y_frame_z+deck_t-3]) block_pattern() bolt(16);
}

module z_moving(z=15) {
    z_rail_transform() right(z_height(z)-z_rail_mid) guide_block();
    up(z_height(z)) {
        color(moving) z_carriage();
        if (show_tool) {
            color(printed) pen_adapter();
            example_tool();
            if (show_hardware) {
                translate([-10,-9,0]) bolt(20,orient=RIGHT);
                translate([7.5,-9,0]) rot(from=UP,to=RIGHT) hex_nut();
            }
        } else color(printed) tool_plate();
        if (show_hardware) {
            for (x=[-10,10],zz=[-10,10]) translate([x,z_carriage_back-6,zz]) bolt(8,orient=BACK);
            tool_pattern() {
                translate([0,dock_front-5,0]) bolt(20,orient=BACK);
                translate([0,dock_y+6-2.5,0]) rot(from=UP,to=BACK) hex_nut();
            }
            translate([z_screw_x,z_screw_y,-6]) zrot_copies(n=4) right(8) bolt(8,orient=UP);
        }
    }
}

module fixed_assembly(x=X,z=Z) {
    color(printed) base();
    color(printed) column();
    up(base_top) belt_hardware(pos=-x);
    z_rail_transform() guide_rail();
    translate([z_screw_x,z_screw_y,z_motor_face])
        nema17_tr8(nut="motor",nut_pos=z_nut_pos(z),threads=show_threads,orient=DOWN,spin=180);
    if (show_hardware) {
        for (x=[-44,44],y=[column_front+14,column_front+24]) {
            translate([x,y,base_top+8]) bolt(20);
            translate([x,y,base_z-2.4]) hex_nut();
        }
        z_rail_transform() for (x=rail_holes) translate([x,0,rail_h-4.5]) bolt(8);
        translate([z_screw_x,z_screw_y,z_motor_face-deck_t]) grid_copies(spacing=31,n=2) bolt(8,orient=UP);
    }
}

module travel_envelope(x=X,y=Y) {
    translate([-x,-y,board_top]) color([0.2,0.8,0.5,0.15]) cuboid([x_travel,y_travel,z_travel],anchor=BOT);
}

module xyz(x=tool_x,y=tool_y,z=tool_z) {
    assert(abs(x)<=x_travel/2 && abs(y)<=y_travel/2 && z>=0 && z<=z_travel, "Tool position outside travel.");
    fixed_assembly(x,z);
    xy_moving(x,y);
    z_moving(z);
    if (show_envelope) %travel_envelope(x,y);
}

// Collision diagnostic deliberately excludes contacting hardware (rails, nuts,
// belts and screw joints). Positive volume means unrelated structural parts clash.
module collision_check() {
    union() {
        intersection() {
            translate([-X,0,base_top+block_h]) y_frame();
            union() { base(); column(); }
        }
        intersection() {
            translate([-X,-Y,tray_mount_z]) tray();
            union() {
                column();
                translate([-X,0,y_rail_z]) zrot(90)
                    translate([-pulley_c,belt_offset,-deck_t]) nema17_pancake();
            }
        }
        intersection() {
            up(z_height(Z)) z_carriage();
            column();
        }
        intersection() {
            translate([-X,-Y,board_bottom]) board(anchor=BOT);
            up(z_height(Z)) z_carriage();
        }
        // Check the Z screw heads, excluding intentional contact / tapped shafts.
        intersection() {
            column();
            translate([z_screw_x,z_screw_y,z_motor_face-deck_t]) grid_copies(spacing=31,n=2)
                cyl(d=5.5,h=3,anchor=TOP);
        }
        intersection() {
            z_carriage();
            for (x=[-10,10],z=[-10,10]) translate([x,z_carriage_back-6,z])
                cyl(d=5.5,h=3,anchor=BOT,orient=FWD);
        }
    }
}

// Print transforms put each named part on z=0; see README.md for supports.
module print_part(name) {
    if (name=="base") translate([0,0,base_top]) xrot(180) base();
    else if (name=="y_frame") translate([0,0,17]) xrot(180) y_frame();
    else if (name=="tray") up(block_h-5) tray();
    else if (name=="column") translate([0,-base_top,column_front+30]) xrot(-90) column();
    else if (name=="z_carriage") translate([0,0,z_carriage_back]) xrot(-90) z_carriage();
    else if (name=="tool_plate") translate([0,0,5-dock_front]) xrot(90) tool_plate();
    else if (name=="pen_adapter") up(21) pen_adapter();
    else if (name=="belt_clamp") xrot(-90) belt_clamp();
    else if (name=="idler_spacer") idler_spacer(h=spacer_height);
    else if (name=="board_clip") board_clip();
    else assert(false,str("Unknown printable part: ",name));
}

module print_layout() {
    // Inspection layout, intentionally larger than one printer bed.
    names=["base","y_frame","tray","column","z_carriage","tool_plate","pen_adapter","belt_clamp","idler_spacer","board_clip"];
    for (i=[0:len(names)-1]) translate([(i%4)*260,floor(i/4)*290,0]) print_part(names[i]);
}

echo(str("XYZ travel: ",x_travel," x ",y_travel," x ",z_travel," mm; board: ",board_x," x ",board_y," x ",board_z));
echo(str("Base: ",base_w," x ",base_d," mm; height: ",z_motor_face+n17t_len," mm; board top: ",board_top));
echo(str("2 GT2 belts: cut approximately ",belt_cut_length()," mm each, trim at clamp; 3 MGN12H rails: 150 mm."));

if (part=="assembly") xyz(X,Y,Z);
else if (part=="travel_envelope") travel_envelope();
else if (part=="collision_check") collision_check();
else if (part=="print_layout") print_layout();
else if (part!="none") print_part(part);
