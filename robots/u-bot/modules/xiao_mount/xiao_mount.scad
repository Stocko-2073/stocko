include <BOSL2/std.scad>
include <BOSL2/threading.scad>

xiao_mount_thread_d=19.2;
xiao_mount_pitch=2;
xiao_mount_thread_slop=0.15; // BOSL2 adds 4*slop = 0.6 mm diametral clearance
xiao_mount_bore=10;
xiao_mount_explode=0; // 0 assembled, 1 exploded
xiao_mount_ep=0.03;

module xiao_sense(camera_angle=180) {
    camera_offset = [-0.66,-4.1,0.9-1];
    left(0.66) up(2) back(4) xrot(camera_angle) yrot(180) {
        render()
        difference() {
            yrot(-90) fwd(12) up(6.75) left(8.75) import("xiao_sense.stl");
            fwd(6.1) down(3.1) {
                cuboid([15,2,10],anchor=FWD+BOT);
                up(10) cuboid([15,10,2.5],anchor=FWD+TOP);
            }
            fwd(12-7.95+xiao_mount_ep)cuboid([8+xiao_mount_ep,6+xiao_mount_ep,8+xiao_mount_ep],anchor=FWD);
        }
        color("#444") move(camera_offset) xrot(camera_angle) zrot(180) left(4) render() intersection() {
            up(6.75) left(4.75) fwd(7.95) import("xiao_sense.stl");
            cuboid([8,6,8],anchor=LEFT+FWD);
        }
    }
}

// XIAO enclosure coordinates: lid top Z=0, lens toward BACK (+Y).
// See README.md for printing and assembly instructions.
module xiao_mount_board() {
    back(10) up(24) zrot(180) xiao_sense(180);
}

module xiao_mount_thread(internal=false) {
    up(0.3) xrot(180)
        buttress_threaded_rod(d=xiao_mount_thread_d,l=10.5,
            pitch=xiao_mount_pitch,internal=internal,
            bevel1=false,bevel2=0.6,anchor=BOT,
            $slop=internal?xiao_mount_thread_slop:0,$fn=96);
}

module xiao_mount_base() {
    color("#f84") difference() {
        union() {
            cuboid([40,28,3],rounding=4,edges="Z",anchor=BOT);
            xiao_mount_thread();
        }
        down(11) cyl(d=xiao_mount_bore,h=15,anchor=BOT,$fn=64);
        // Flare both wire exits to remove sharp edges.
        up(2) cyl(d1=xiao_mount_bore,d2=xiao_mount_bore+2,h=1+xiao_mount_ep,anchor=BOT);
        down(10.2+xiao_mount_ep) cyl(d1=xiao_mount_bore+2,d2=xiao_mount_bore,h=1+xiao_mount_ep,anchor=BOT);
        // Two M3 x 8 countersunk screws, flush with the lid bearing face.
        xflip_copy() right(16) {
            down(xiao_mount_ep) cyl(d=3.3,h=3+xiao_mount_ep*2,anchor=BOT,$fn=32);
            down(xiao_mount_ep) cyl(d1=6.4,d2=3.3,h=1.55+xiao_mount_ep,anchor=BOT,$fn=48);
        }
    }
}

module xiao_mount_nut(lid_thickness=1.5) {
    color("#f84") difference() {
        down(lid_thickness) cyl(d=26,h=6,anchor=TOP,chamfer1=0.6,$fn=96);
        // Use the same thread origin as the stem, preserving phase and flank direction.
        xiao_mount_thread(internal=true);
        down(lid_thickness+3) zrot_copies(n=12) right(13.8)
            cyl(d=2.6,h=7,$fn=24);
    }
}

module xiao_mount_cover_screws() {
    for (x=[-16,16], z=[7,31]) translate([x,-11,z]) children();
}

module xiao_mount_shell() {
    color("#ccc") difference() {
        union() {
            difference() {
                up(3) cuboid([40,22,32],rounding=2,edges="Y",anchor=BOT);
                // Open front; 2 mm walls and roof, 3 mm floor.
                translate([0,-2,6]) cuboid([36,22,27],anchor=BOT);
            }
            xiao_mount_cover_screws()
                ycyl(d=6,h=20,anchor=FWD,$fn=32);
            xflip_copy() right(16) up(3)
                cyl(d=8,h=7,anchor=BOT,$fn=32);
        }
        // Flared optical window. Lens center is [0,7.66,25.9].
        translate([0,9-xiao_mount_ep,25.9])
            ycyl(d1=12,d2=16,h=2+xiao_mount_ep*2,anchor=FWD,$fn=64);
        // USB-C access is open to the removable cover: no long roof bridge.
        translate([0,-6,32]) cuboid([12,14,4],anchor=BOT);
        // Wire funnel through the floor. Point faces print-up when shell is face-down.
        up(3-xiao_mount_ep) linear_extrude(height=3+xiao_mount_ep*2) hull() {
            circle(d=xiao_mount_bore,$fn=64);
            polygon([[-1,-4],[1,-4],[0,-sqrt(2)*xiao_mount_bore/2]]);
        }
        xflip_copy() right(16) up(3-xiao_mount_ep)
            cyl(d=2.6,h=6+xiao_mount_ep,anchor=BOT,$fn=32);
        xiao_mount_cover_screws() fwd(xiao_mount_ep)
            ycyl(d=2.6,h=8+xiao_mount_ep,anchor=FWD,$fn=32);
    }
}

// A wedge extruded along X; used for support-free clip lead-ins.
module xiao_mount_clip_wedge(x,points) {
    translate([x-0.7,0,0]) rotate([90,0,90])
        linear_extrude(height=1.4) polygon(points);
}

module xiao_mount_cover() {
    color("#f84") difference() {
        union() {
            translate([0,-12,19]) cuboid([40,2,32],rounding=2,edges="Y");
            // Four short-edge seats keep pressure away from the soldered pin rows.
            for (x=[-7.8,7.8]) {
                for (z=[8.8,29.3])
                    translate([x,-8.75-xiao_mount_ep/2,z]) cuboid([1.4,4.5+xiao_mount_ep,1]);
                // Flexible end stops with 45-degree snap-in lips.
                translate([x,-7.25-xiao_mount_ep/2,7.7]) cuboid([1.4,7.5+xiao_mount_ep,1.2+xiao_mount_ep*2]);
                translate([x,-7.25-xiao_mount_ep/2,30.4]) cuboid([1.4,7.5+xiao_mount_ep,1.2+xiao_mount_ep*2]);
                xiao_mount_clip_wedge(x,[[-4.9,8.3-xiao_mount_ep],[-4.2,9],[-3.5,8.3-xiao_mount_ep]]);
                xiao_mount_clip_wedge(x,[[-4.9,29.8+xiao_mount_ep],[-4.2,29.1],[-3.5,29.8+xiao_mount_ep]]);
            }
            // Side stops only at the board ends, leaving both pin rows accessible.
            for (x=[-9.45,9.45], z=[8.9,29.2])
                translate([x,-8.4-xiao_mount_ep/2,z]) cuboid([0.9,5.2+xiao_mount_ep,1.2]);
        }
        xiao_mount_cover_screws() fwd(2+xiao_mount_ep)
            ycyl(d=3.3,h=2+xiao_mount_ep*2,anchor=FWD,$fn=32);
        // Cooling openings, clear of the PCB carrier pads.
        for (x=[-5,0,5]) translate([x,-12,19])
            cuboid([2,4,10],rounding=1,edges="Y");
        // Two slots accept a small cable tie for wire strain relief behind the PCB.
        for (x=[-3,3]) translate([x,-12,6]) cuboid([2,4,3]);
    }
}

module xiao_mount(show_board=true,explode=xiao_mount_explode,lid_thickness=1.5) {
    xiao_mount_base();
    down(14*explode) xiao_mount_nut(lid_thickness=lid_thickness);
    up(16*explode) xiao_mount_shell();
    up(16*explode) fwd(24*explode) xiao_mount_cover();
    if (show_board) up(16*explode) fwd(12*explode) xiao_mount_board();
}

// Print orientations: each part rests on Z=0; nut flanks face opposite the stem.
module xiao_mount_base_print() up(3) xrot(180) xiao_mount_base();
module xiao_mount_nut_print(lid_thickness=1.5)
    up(lid_thickness+6) xiao_mount_nut(lid_thickness=lid_thickness);
module xiao_mount_shell_print() up(11) xrot(-90) xiao_mount_shell();
module xiao_mount_cover_print() up(13) xrot(90) xiao_mount_cover();

xiao_mount();