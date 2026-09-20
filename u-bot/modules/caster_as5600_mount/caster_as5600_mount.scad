include <BOSL2/std.scad>
include <BOSL2/screws.scad>
include <../../../lib/as5600.scad>

caster_encoder_floor_z=22.1;
caster_encoder_face_z=24.5;
caster_encoder_screw_seat_z=28.5;
caster_encoder_screws=[[15,-10],[-10,15]];
caster_encoder_explode=0; // 0 assembled, 1 exploded
caster_encoder_ep=0.03;

module caster_encoder_tabs(h) {
    for (p=caster_encoder_screws)
        hull() {
            translate([p.x,p.y,0]) cyl(d=7,h=h,anchor=BOT);
            translate([p.x*0.7,p.y*0.7,0]) cyl(d=7,h=h,anchor=BOT);
        }
}

module caster_as5600_mount() {
    seat=caster_encoder_face_z+1.5-caster_encoder_floor_z;
    color("#f84") difference() {
        union() {
            difference() {
                cuboid([28,28,seat+1.5],anchor=BOT,rounding=2,edges="Z");
                down(caster_encoder_ep) cuboid([24.4,24.4,20+caster_encoder_ep],anchor=BOT);
            }
            difference() {
                caster_encoder_tabs(seat+1.5+$slop);
                up(seat) cuboid([24.4,24.4,10],anchor=BOT);
            }
            xflip_copy() yflip_copy() translate([10,10,seat-2])
                cuboid([6.2,6.2,2],anchor=BOT);
            xflip_copy() yflip_copy() translate([8,8,seat])
                cyl(d=4-$slop*2,h=1.5,anchor=BOT);
        }
        for (p=caster_encoder_screws)
            translate([p.x,p.y,-caster_encoder_ep]) cyl(d=3+$slop*2,h=10,anchor=BOT,$fn=32);
        down(caster_encoder_ep) cyl(d=20,h=1+caster_encoder_ep,anchor=BOT);
    }
}

module caster_as5600_mount_cap() {
    // Local bottom is 0.2 mm above the PCB back.
    color("#f84") difference() {
        union() {
            difference() {
                cuboid([28,28,2],anchor=BOT,rounding=2,edges="Z");
                down(caster_encoder_ep) cuboid([20,12,5+caster_encoder_ep],anchor=BOT);
            }
            caster_encoder_tabs(2);
        }
        for (p=caster_encoder_screws) {
            translate([p.x,p.y,-2]) cyl(d=3+$slop*2,h=8,anchor=BOT,$fn=32);
            translate([p.x,p.y,caster_encoder_screw_seat_z-caster_encoder_face_z-3-$slop])
                cyl(d=6,h=5,anchor=BOT);
        }
    }
}

module caster_magnet_holder() {
    lift=0.97;
    color("#f84") difference() {
        union() {
            intersection() {
                cyl(d=19-$slop*2,h=5-$slop,anchor=BOT);
                cuboid([20,5-$slop*2,5-$slop],anchor=BOT);
            }
            up(5-$slop-caster_encoder_ep) cyl(d=7,h=lift+caster_encoder_ep,anchor=BOT);
        }
        up(3-$slop+lift) cyl(d=4+$slop,h=2+caster_encoder_ep,anchor=BOT);
    }
    up(3-$slop+lift) children(); // 4 x 2 magnet
}

module caster_as5600_board() {
    // Direct-wire board: omit the reference mesh's underside headers.
    intersection() {
        as5600();
        down(3) cuboid([30,30,4],anchor=BOT);
    }
}

module caster_encoder() {
    up(caster_encoder_floor_z+28*caster_encoder_explode) caster_as5600_mount();
    up(caster_encoder_face_z+44*caster_encoder_explode) xrot(180) caster_as5600_board();
    up(caster_encoder_face_z+3+$slop+60*caster_encoder_explode) caster_as5600_mount_cap();
    for (p=caster_encoder_screws)
        translate([p.x,p.y,caster_encoder_screw_seat_z+80*caster_encoder_explode])
            color("#888") screw("M3,16",head="button",drive="hex",
                atype="threads",anchor=TOP,thread="none",details=false);
}
