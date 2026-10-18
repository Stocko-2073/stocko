include <BOSL2/std.scad>
include <BOSL2/screws.scad>
include <BOSL2/threading.scad>
include <BOSL2/gears.scad>
include <BOSL2/ball_bearings.scad>
include <BOSL2/nema_steppers.scad>
include <../lib/as5600.scad>
include <../lib/globals.scad>
// use <modules/xiao_mount/xiao_mount.scad>
use <modules/caster_as5600_mount/caster_as5600_mount.scad>
use <modules/fpc_camera/fpc_camera.scad>
use <modules/rpsma/rpsma_pigtail.scad>
use <modules/rpsma/rpsma_antenna.scad>
use <modules/battery_mount/battery_mount.scad>

$fn=0;$fa=1;$fs=0.25;ep=0.03;$slop=0.2;
// $fn=0;$fa=1;$fs=2;ep=0.03;$slop=0.2;
// $fn=0;$fa=1;$fs=0.25;ep=0.03;$slop=0.2;
_6902ZZ=ball_bearing_info("6902ZZ");
_6007ZZ=ball_bearing_info("6007ZZ");
echo(_6902ZZ);

wheel_mod=5;
wheel_teeth=40; //72;
drive_teeth=12; //22;
wheel_bearing_spacing=30;
caster_x=50;
caster_d=60;
caster_leg_x=13;
caster_leg_len=90;

body_lid_panel=1.5;
body_lid_hole_y=120;
body_lid_hole_d=10;

board_mount_y_offset=40;

module m3_11(orient=RIGHT,anchor=BOT,spin=0) {
    color("#888") screw("M3,11",head="socket",drive="hex",atype="head",thread="none",orient=orient,anchor=anchor,spin=spin,details=false) children();
}

module m3_8(orient=UP,anchor=TOP,spin=0) {
    color("#888") screw("M3,8",head="socket",drive="hex",atype="threads",thread="none",orient=orient,anchor=anchor,spin=spin,details=false) children();
}

module m3_nut(orient=undef,anchor=undef,spin=undef) {
    color("#888") nut("M3",thread="none",orient=orient,anchor=anchor,spin=spin);
}

module m4_30(orient=RIGHT,anchor=TOP,spin=0) {
    color("#888") screw("M4,30",head="button",drive="hex",atype="head",thread="none",orient=orient,anchor=anchor,spin=spin,details=false) children();
}

module m4_14(orient=RIGHT,anchor=TOP,spin=0) {
    color("#888") screw("M4,14",head="button",drive="hex",atype="threads",thread="none",orient=orient,anchor=anchor,spin=spin,details=false) children();
}

module m4_25(orient=RIGHT,anchor=TOP,spin=0) {
    color("#888") screw("M4,25",head="button",drive="hex",atype="threads",thread="none",orient=orient,anchor=anchor,spin=spin,details=false) children();
}

module m4_nut(orient=undef,anchor=undef,spin=undef) {
    color("#888") nut("M4",thread="none",orient=orient,anchor=anchor,spin=spin);
}

module m5_16(orient=UP,anchor=BOT,spin=0) {
    color("#888") screw("M5,16",head="button",drive="hex",atype="head",thread="none",orient=orient,anchor=anchor,spin=spin,details=false) children();
}

module m5_30(orient=UP,anchor=BOT,spin=0) {
    color("#888") screw("M5,30",head="button",drive="hex",atype="head",thread="none",orient=orient,anchor=anchor,spin=spin,details=false) children();
}

module m5_nut(orient=undef,anchor=undef,spin=undef) {
    color("#888") nut("M5",thread="none",orient=orient,anchor=anchor,spin=spin);
}

module magnet() {
    color("#888") cyl(d=4,l=2,anchor=BOT);
}

module magnet_neg(depth=2) {
    down(ep) {
        d=4+$slop*2;
        difference() {
            union() {
                cyl(d=d,l=depth+0.6+ep,anchor=BOT);
                up(depth+0.6+ep) cyl(d1=d,d2=1,l=0.5,anchor=BOT);
            }
            down(ep) left($slop) cuboid([d,d,0.6],anchor=BOT+RIGHT);
        }
    }
}
// !magnet_neg(1.5);

module wheel() {
    id=208;
    od=218;
    d=_6902ZZ[0]+$slop;
    color("#444") {
        difference() {
            union() {
                intersection() {
                    left(3) hull() {
                        left(10+ep) xcyl(d=195+ep*3,h=10.5,anchor=LEFT,rounding2=2);
                        right(6.25+ep) xcyl(d=147.5,h=14.07,anchor=RIGHT);
                    }
                    right(23.5) bevel_gear(
                        mod=wheel_mod,teeth=wheel_teeth,mate_teeth=drive_teeth,
                        anchor="apex",orient=RIGHT,backing=1,face_width=22,
                        cutter_radius=0,spiral=0,slices=1,spin=-0.025,
                        shaft_diam=10
                    );
                }
                left(20) {
                    zz=10;
                    r=195/2;
                    xcyl(r=r+zz-5,h=14,chamfer=5);
                    xrot(360/40) xrot_copies(n=20) up(r+zz)
                        right(2) cuboid([17,7,zz+2],chamfer=5,edges=[TOP+LEFT,TOP+RIGHT],anchor=TOP+RIGHT);
                    xrot_copies(n=20) hull() {
                        up(r+zz) left(2)
                            cuboid([17,7,zz+1],chamfer=5,edges=[TOP+LEFT,TOP+RIGHT],anchor=TOP+LEFT);
                    }
                    right(7.5) xcyl(d=195,h=22.5,chamfer1=2,anchor=RIGHT);
                }
                right(3+$slop) xcyl(d2=_6902ZZ[0]+6,d1=_6902ZZ[0]+12,h=8.1,anchor=RIGHT);
            }
            right(3+$slop) xcyl(d=d+$slop*3,h=40,anchor=RIGHT,extra=$slop);
            left(36+ep) {
                xcyl(d=160,h=16+ep,chamfer2=16,anchor=LEFT);
                right(7) xrot_copies(n=4) back(55+20) zrot(45) xcyl(d=10,h=30);
            }
        }
        difference() {
            left(20) xcyl(d=d+20,h=15,anchor=RIGHT,chamfer1=2,chamfer2=-2);
            left(20) xcyl(d=d+$slop*3,h=16,anchor=RIGHT);
            up(12) left(27) {
                screw_hole("M5",l=35,head="button",atype="head",counterbore=10,anchor=BOT,$slop=0.2);
                down(23) nut_trap_inline(10,"M5",orient=BOT,$slop=0.5);
            }
        }
    }
    up(12) left(27) children(0); // bolt
}

module axle() {
    recolor("#666") diff() {
        d=_6902ZZ[0]-0.8;
        xx=_6902ZZ[2]/2;
        xxx=wheel_bearing_spacing+$slop*2+23.15;
        
        right(wheel_bearing_spacing+$slop) {
            xcyl(d=_6902ZZ[0]+6,h=3.5-$slop,anchor=LEFT);
            xcyl(d=d,h=xxx+16,chamfer1=2,anchor=RIGHT);
            xrot_copies(n=12) up(d/2) {
                xcyl(d1=0.5,d2=1,h=_6902ZZ[2]+$slop,anchor=RIGHT);
                left(wheel_bearing_spacing-_6902ZZ[2])
                    xcyl(d1=0.5,d2=1.1,h=_6902ZZ[2]+$slop,anchor=RIGHT);
            }
        }
        tag("remove") {
            right(wheel_bearing_spacing+3.5+ep) yrot(-90) magnet_neg(1.25);
            up(12) left(27+3) {
                screw_hole("M5",l=35,head="button",atype="head",counterbore=10,anchor=BOT,$slop=0);
                down(23) nut_trap_inline(10,"M5",orient=BOT,$slop=0.1);
            }
        }
    }
    right(wheel_bearing_spacing/2) xflip_copy() left(wheel_bearing_spacing/2)
        children(0); // axle bearing
    right(wheel_bearing_spacing+3+ep) yrot(-90) children(1); // magnet
}

module motor() {
    nema_stepper_motor(size=17,h=39,shaft_len=30,orient=FWD)
        attach(TOP) up(2+$slop) xflip_copy() yflip_copy() left(15.5) back(15.5) children();
}

module drive_gear() {
    l=22;
    recolor("#f84")
    difference() {
        union() {
            intersection() 
            {
                bevel_gear(
                    mod=wheel_mod,teeth=drive_teeth,mate_teeth=wheel_teeth,
                    anchor="apex",face_width=l,spin=15,
                    cutter_radius=0,spiral=0,slices=1
                );
                down(102) cyl(d=67,h=29,anchor=BOT,chamfer1=10,extra=ep);
            }
        }
        down(82) {
            cyl(d=5+$slop,h=100);
            down(5) zrot_copies(n=3) back(9.5) {
                screw_hole("M3",l=8,head="socket",atype="head",orient=BACK,anchor=BOT,$slop=0,counterbore=18);
                fwd(1.5) yrot(-90) nut_trap_side(30,"M3",orient=FWD,$slop=0.1,thickness=4.5);
            }
        }
    }
}

module axle_mount() {
    yy=20;
    color("#f84") diff() {
        left(3+ep) {
            hull() {
                fwd(yy) cuboid([3-$slop,50+yy*2,61],anchor=LEFT,rounding=4,edges="X");
                fwd(71) cuboid([3-$slop,6,48],rounding=3,edges="X",anchor=LEFT+FWD);
            }
            cuboid([wheel_bearing_spacing+7,34,61],anchor=LEFT,chamfer=1,except=[LEFT]);
            fwd(yy) zflip_copy() up(52/2) {
                back(41/2+yy) {
                    cuboid([6,9,9],anchor=LEFT,rounding=4,edges=[TOP+BACK,BOT+BACK]);
                    right(3-ep) screw_hole("M3",l=13,head="socket",atype="head",orient=LEFT,anchor=BOT,tolerance="tap");
                }
                yflip() back(41/2+yy) {
                    cuboid([6,9,9],anchor=LEFT,rounding=4,edges="X");
                    right(3-ep) screw_hole("M3",l=13,head="socket",atype="head",orient=LEFT,anchor=BOT,tolerance="tap");
                }
            }
        }

        tag("remove") {
            right(wheel_bearing_spacing/2) xflip_copy() left(wheel_bearing_spacing/2){
                right(_6902ZZ[2])
                    xcyl(d=_6902ZZ[1]+$slop,h=_6902ZZ[2]*2,extra=ep,anchor=RIGHT);
            }
            left(3+ep) xcyl(d=_6902ZZ[1]-4,h=50,anchor=LEFT);
            right(wheel_bearing_spacing) 
                as5600_mount_screws();

        }
    }
    children(0); // axle
    right(wheel_bearing_spacing) children(1); // as5600_mount
    fwd(yy) zflip_copy() up(52/2) {
        back(41/2+yy) {
            yrot(180) children(2); // mounting screws
        }
        yflip() back(41/2+yy) {
            yrot(180) children(2); // mounting screws
        }
    }

}

module as5600_mount_screws() {
    zflip_copy() right(4+3+2+$slop*2) up(20) {
        screw_hole("M3",l=15,head="socket",atype="head",orient=RIGHT,anchor=BOT,$slop=0);
        left(7) nut_trap_side(23,"M3",orient=LEFT,$slop=0.1);
    }
}

module as5600_mount_cap() {
    recolor("#f84") diff() {
        right(4+3+$slop*2) {
            cuboid([3,34,50],anchor=LEFT,chamfer=1,except=LEFT);
            tag("remove") cuboid([6+ep,12,20]);
        }
        as5600_mount_screws();
    }
    zflip_copy() right(9+$slop*2) up(20) children(0); // screw
}

module as5600_mount() {
    recolor("#f84") diff() {
        right(4+$slop) {
            difference() {
                ss=24.4;
                cuboid([3,34,50],anchor=LEFT,chamfer=1,edges="X");
                cuboid([6+ep,ss,ss]);
            }
            zflip_copy() yflip_copy() up(8) back(8) {
                xcyl(d=4-$slop*2,h=3,anchor=LEFT);
                down(2) fwd(2) cuboid([1.5,6+$slop,6+$slop],anchor=BOT+FWD+LEFT,rounding=2,edges=[BOT+FWD]);
            }
        }
        as5600_mount_screws();
    }
    right(4) yrot(-90) children(0); // as5600
    children(1); // as5600_mount_cap
}


module leg() {
    zz=56+14;
    recolor("#ccc")
    diff() {
        left(3) {
            fwd(75) {
                yy=34;
                right(3) cuboid([45,30,zz],chamfer=10,edges=[FWD+TOP,FWD+BOT],anchor=LEFT+FWD)
                attach(BACK) cuboid([45,124,zz],orient=FWD,anchor=FWD,chamfer=3,edges=[RIGHT+BACK]) {
                    tag("remove") attach(BACK) up(ep) {
                        cuboid([20+$slop*3,40+$slop*3,zz-10+$slop*3],orient=BACK,anchor=FWD);
                        xrot(90) left(13) fwd(40/2) zflip_copy() up(15) yrot(-90)
                            screw_hole("M5",l=33,head="button",atype="head",counterbore=10,anchor=BOT,$slop=0)
                            down(31) nut_trap_inline(10,"M5",orient=BOT,$slop=0.1);
                    }
                }
            }
        }
        tag("remove") {
            // axel mount cutout
            left(3+ep*2) {
                yy=20;
                cuboid([52.5+ep*2,34+$slop*2,61+$slop*2],anchor=LEFT);
                fwd(yy) zflip_copy() up(52/2) {
                    back(41/2+yy) {
                        cuboid([6,9+$slop*2,9+$slop*2],anchor=LEFT,rounding=4,edges=[TOP+BACK,BOT+BACK]);
                        right(3-ep) screw_hole("M3",l=13,head="socket",atype="head",orient=LEFT,anchor=BOT,tolerance="tap");
                        right(12) xrot(90) nut_trap_side(23,"M3",orient=LEFT,$slop=0.1);
                    }
                    yflip() back(41/2+yy) {
                        cuboid([6,9+$slop*2,9+$slop*2],anchor=LEFT,rounding=4,edges=[TOP+FWD,TOP+BACK]);
                        right(3-ep) screw_hole("M3",l=13,head="socket",atype="head",orient=LEFT,anchor=BOT,tolerance="tap");
                        right(12) xrot(180) nut_trap_side(23,"M3",orient=LEFT,$slop=0.1);
                    }
                }
            }
            // stepper cutout
            fwd(73-2) right(21.35-ep) {
                nema_stepper_motor(size=17,h=50,shaft_len=30,orient=FWD,details=false);
                ycyl(d=22.5,h=10,anchor=BACK);
            }
            // stepper shaft cutout
            fwd(73+ep) right(42.5/2) {
                zz=13.75;
                fwd(2) cuboid([25+ep,4+ep*2,22],anchor=RIGHT+FWD);
                zflip_copy() xflip_copy() left(15.5) up(15.5)
                    screw_hole("M3",l=8,head="socket",atype="head",orient=FWD,anchor=BOT,tolerance="tap");

                back(52) cuboid([30,24,18],anchor=BACK+LEFT);
            }
            // tool pin hole
            right(45/2) back(28) cyl(d=15,h=zz,chamfer=-3,extra=ep);

            right(45+$slop) {
                yy=34;
                wall=2;
                fwd(75) back(154/2+5) zflip_copy() up(zz/2-5) {
                    back(154/2-5-5) {
                        screw_hole("M3",l=12.6+ep,head="socket",atype="shaft",orient=RIGHT,anchor=TOP,tolerance="tap",counterbore=7);
                        left(6) fwd(1.5) xrot(90) yrot(90) nut_trap_side(30,"M3",$slop=0.1);
                    }
                    yflip() back(154/2-5-5) {
                        screw_hole("M3",l=15,head="socket",atype="shaft",orient=RIGHT,anchor=TOP,tolerance="tap",counterbore=7);
                        left(6) fwd(0*1.5) yrot(90) nut_trap_side(30,"M3",$slop=0.1);
                    }
                }
            }
        }
    }
    fwd(73-2) right(21.25) children(0); // motor
    xrot(-90) right(23.5+1.25) left(3.35) children(1); // drive gear
    left(3.35) children(2); // wheel
    children(3); // axle_mount
    right(45+$slop) children(4); // leg cap
}

module leg_cap() {
    zz=56+14;
    yy=34;
    wall=2;
    recolor("#f84") fwd(75) {
        diff() {
            cuboid([10,35,zz],anchor=LEFT+FWD,chamfer=10,edges=[FWD+RIGHT,FWD+TOP,FWD+BOT])
            attach(BACK) cuboid([10,119,zz],orient=FWD,anchor=FWD);

            tag("remove") {
                cuboid([$slop,119+35,zz],anchor=LEFT+FWD);

                difference() {
                    left(ep) back(wall) cuboid([10-wall,35-wall,zz-wall*2],anchor=LEFT+FWD,chamfer=10-wall,edges=[FWD+RIGHT,FWD+TOP,FWD+BOT])
                    attach(BACK) cuboid([10-wall,119+ep,zz-wall*2],orient=FWD,anchor=FWD,chamfer=5,edges=[TOP+BACK]);
                    back(154/2+5) zflip_copy() up(zz/2-5) {
                        back(154/2-5-5) cuboid([20,10,10],rounding=5,edges=[FWD+TOP,FWD+BOT]);
                        yflip() back(154/2-5-5) cuboid([20,10,10],rounding=5,edges="X");
                    }
                }

                right(10) back(154/2+5) zflip_copy() up(zz/2-5) yflip_copy() back(154/2-5-5)
                    screw_hole("M3",l=15,head="socket",atype="head",orient=RIGHT,anchor=TOP,tolerance="tap",counterbore=7);
            }
        }
    }

    fwd(75) right(10-7) back(154/2+5) zflip_copy() up(zz/2-5) yflip_copy() back(154/2-5-5)
        children(0); // screw
}

module front_leg() {
    y=3+26;//54;
    zz=56+14;
    recolor("#ccc")
    diff() {
        left(3) {
            fwd(75) {
                yy=34;
                right(3) cuboid([45,30,zz],chamfer=10,edges=[FWD+TOP,FWD+BOT],anchor=LEFT+FWD)
                attach(BACK) cuboid([45,70+y,zz],orient=FWD,anchor=FWD,chamfer=3,edges=[RIGHT+BACK]) {
                    attach(BACK) {
                        yyy=20;
                        cuboid([20,yyy,zz-10],orient=FWD,anchor=FWD,chamfer=2,edges=[BACK]);
                        xrot(90) left(13) back(yyy/2) zflip_copy() up(15) yrot(-90)
                            screw_hole("M5",l=33,head="button",atype="head",counterbore=10,anchor=BOT,$slop=0)
                            down(31) nut_trap_inline(10,"M5",orient=BOT,$slop=0.1);
                    }
                }
            }
        }
        tag("remove") {
            // axel mount cutout
            left(3+ep*2) {
                yy=20;
                cuboid([52.5+ep*2,34+$slop*2,61+$slop*2],anchor=LEFT);
                fwd(yy) zflip_copy() up(52/2) {
                    back(41/2+yy) {
                        cuboid([6,9+$slop*2,9+$slop*2],anchor=LEFT,rounding=4,edges=[TOP+BACK,BOT+BACK]);
                        right(3-ep) screw_hole("M3",l=13,head="socket",atype="head",orient=LEFT,anchor=BOT,tolerance="tap");
                        right(12) xrot(90) nut_trap_side(23,"M3",orient=LEFT,$slop=0.1);
                    }
                    yflip() back(41/2+yy) {
                        cuboid([6,9+$slop*2,9+$slop*2],anchor=LEFT,rounding=4,edges=[TOP+FWD,TOP+BACK]);
                        right(3-ep) screw_hole("M3",l=13,head="socket",atype="head",orient=LEFT,anchor=BOT,tolerance="tap");
                        right(12) xrot(180) nut_trap_side(23,"M3",orient=LEFT,$slop=0.1);
                    }
                }
            }
            // stepper cutout
            fwd(73-2) right(21.35-ep) {
                nema_stepper_motor(size=17,h=50,shaft_len=30,orient=FWD,details=false);
                ycyl(d=22.5,h=10,anchor=BACK);
            }
            // stepper shaft cutout
            fwd(73+ep) right(42.5/2) {
                zz=13.75;
                fwd(2) cuboid([25+ep,4+ep*2,22],anchor=RIGHT+FWD);
                zflip_copy() xflip_copy() left(15.5) up(15.5)
                    screw_hole("M3",l=8,head="socket",atype="head",orient=FWD,anchor=BOT,tolerance="tap");

                back(52) cuboid([30,24,18],anchor=BACK+LEFT);
            }
            // // tool pin hole
            right(45/2) back(28) cyl(d=15,h=zz,chamfer=-3,extra=ep);

            // screw holes
            right(45+$slop) {
                yy=34;
                wall=2;
                fwd(75) back((100+y)/2+5) zflip_copy() up(zz/2-5) {
                    back((100+y)/2-5-5) {
                        screw_hole("M3",l=12.6+ep,head="socket",atype="shaft",orient=RIGHT,anchor=TOP,tolerance="tap",counterbore=7);
                        left(6) fwd(1.5) xrot(90) yrot(90) nut_trap_side(30,"M3",$slop=0.1);
                    }
                    yflip() back((100+y)/2-5-5) {
                        screw_hole("M3",l=15,head="socket",atype="shaft",orient=RIGHT,anchor=TOP,tolerance="tap",counterbore=7);
                        left(6) fwd(0*1.5) yrot(90) nut_trap_side(30,"M3",$slop=0.1);
                    }
                }
            }
        }
    }
    fwd(73-2) right(21.25) children(0); // motor
    xrot(-90) right(23.5+1.25) left(3.35) children(1); // drive gear
    left(3.35) children(2); // wheel
    children(3); // axle_mount
    right(45+$slop) children(4); // leg cap
}

module front_leg_cap() {
    y=3+26;
    zz=56+14;
    yy=34;
    wall=2;
    recolor("#f84") fwd(75) {
        diff() {
            cuboid([10,35,zz],anchor=LEFT+FWD,chamfer=10,edges=[FWD+RIGHT,FWD+TOP,FWD+BOT])
            attach(BACK) cuboid([10,(65+y),zz],orient=FWD,anchor=FWD);

            tag("remove") {
                cuboid([$slop,(65+y)+35,zz],anchor=LEFT+FWD);

                difference() {
                    left(ep) back(wall) cuboid([10-wall,35-wall,zz-wall*2],anchor=LEFT+FWD,chamfer=10-wall,edges=[FWD+RIGHT,FWD+TOP,FWD+BOT])
                    attach(BACK) cuboid([10-wall,(65+y)+ep,zz-wall*2],orient=FWD,anchor=FWD,chamfer=5,edges=[TOP+BACK]);
                    back((100+y)/2+5) zflip_copy() up(zz/2-5) {
                        back((100+y)/2-5-5) cuboid([20,10,10],rounding=5,edges=[FWD+TOP,FWD+BOT]);
                        yflip() back((100+y)/2-5-5) cuboid([20,10,10],rounding=5,edges="X");
                    }
                }

                right(10) back((100+y)/2+5) zflip_copy() up(zz/2-5) yflip_copy() back((100+y)/2-5-5)
                    screw_hole("M3",l=15,head="socket",atype="head",orient=RIGHT,anchor=TOP,tolerance="tap",counterbore=7);
            }
        }
    }

    fwd(75) right(10-7) back((100+y)/2+5) zflip_copy() up(zz/2-5) yflip_copy() back((100+y)/2-5-5)
        children(0); // screw
}

module board_mount_lid_form(wall=1.5) {
    r=30+wall;
    xx=100+wall*2;
    yy=87+wall;
    zz=58+wall;
    ch=5+wall/2;
    hull() {
        up(zz-r) fwd(r) intersection() {
            xcyl(r=r,h=xx,chamfer=ch);
            cuboid([xx+ep,r,r],anchor=BOT+FWD);
        }
        cuboid([xx,yy/2,zz-r],anchor=BOT+BACK,chamfer=ch,edges=[BACK+LEFT,BACK+RIGHT]);
        fwd(yy/2) cuboid([xx,yy/2,zz],anchor=BOT+BACK,chamfer=ch,edges=[TOP+LEFT,TOP+RIGHT]);
    }
}

module board_mount_lid() {
    wall=3;
    render() color("#f84")
    diff() {
        board_mount_lid_form(wall);
        tag("remove") {
            fwd(wall+ep) board_mount_lid_form(0);
            up(8) back(ep) {
                d=12;
                ycyl(d=d,l=wall+ep*2,anchor=BACK);
                cuboid([d,wall+ep*2,d/2+3],anchor=TOP+BACK);
            }
        }
        fwd(86.25) up(58) tag("remove") {
            back(5) down(2) {
                up(5) screw_hole("M3",l=8,head="socket",atype="threads",anchor=TOP);
                nut_trap_side(10,"M3",$slop=0.1,anchor=TOP,spin=90);
            }
            left(35) back(8.5) {
                d=12;
                cyl(d=d,h=wall,extra=ep,anchor=BOT);
                cuboid([d,d/2+10,wall],anchor=BACK+BOT);
            }
        }
    }
}

module board_mount() {
    d=body_lid_hole_d-$slop*2;
    d2=d-6;
    wall=1.5;
    yy=83;
    zz=55;
    floor=3;
    color("#eee")
    diff() {
        back(33/2) {
            hull() {
                cuboid([100-sqrt(2)*3,yy,ep],anchor=BOT+BACK,chamfer=5,edges=[BACK+LEFT,BACK+RIGHT]);
                up(2) cuboid([100,yy,ep],anchor=TOP+BACK,chamfer=5,edges=[BACK+LEFT,BACK+RIGHT]);
                up(3) cuboid([100,yy,ep],anchor=TOP+BACK,chamfer=5,edges=[BACK+LEFT,BACK+RIGHT]);
            }
            fwd(83) up(3) {
                cuboid([100,3,55],anchor=BOT+FWD,chamfer=5,edges=[TOP+LEFT,TOP+RIGHT]);
                xflip_copy() right(50) {
                    cuboid([3,70,10],anchor=BOT+FWD+RIGHT);
                    up(10) cuboid([6.5,70,2],anchor=TOP+FWD+RIGHT);
                    up(6) cuboid([6.5,70,2],anchor=TOP+FWD+RIGHT);
                }
            }
        }
        back(33/2) fwd(3+body_lid_hole_d/2)
        ycopies([0,-board_mount_y_offset])
        hull() xflip_copy() right(10) {
            h=wall+$slop;
            // cyl(d=body_lid_hole_d-$slop*2,h=ep,anchor=TOP);
            fwd(h)
            cyl(d=body_lid_hole_d-$slop*2,h=ep,anchor=TOP);
            down(h)
            cyl(d=body_lid_hole_d-$slop*2,h=ep,anchor=BOT);
        }
        up(3) back(16.5) {
            zz=6.2;
            cuboid([10,2.5,zz],anchor=BACK+BOT);
            xflip_copy() right(5) hull() {
                cuboid([2,6,ep],anchor=BACK+BOT+LEFT);
                up(zz) cuboid([2,2.5,ep],anchor=BACK+TOP+LEFT);
            }
            up(5) tag("remove") ycyl(d=7.5,h=2.5,extra=ep,anchor=BACK);
        }

        up(1.5) fwd(3) screw_hole("M3",l=8,head="socket",atype="threads",anchor=TOP);

        fwd(yy-16.5) up(zz+3) {
            // screw mount
            back(5) cyl(d=10,h=7,anchor=TOP);
            cuboid([10,5,7],anchor=TOP+FWD);
            tag("remove") back(5) down(2) {
                up(5)screw_hole("M3",l=8,head="socket",atype="threads",anchor=TOP);
                nut_trap_side(10,"M3",$slop=0.1,anchor=TOP,spin=90);
            }

            // antenna mount
            left(35) {
                back(8.5) {
                    cyl(d=14,h=2,anchor=TOP);
                    tag("remove") up(1)
                        cyl(d=6.5+$slop,h=4,anchor=TOP);

                }
                cuboid([14,8.5,2],anchor=TOP+FWD);
                xflip_copy() right(7)
                    cuboid([2,8.5,7],anchor=TOP+FWD+RIGHT,chamfer=3,edges=[BOT+BACK]);
            }

        }

        tag("remove") {
            back(16.5) fwd(3+body_lid_hole_d/2)
            up(3) {
                h=3+wall+$slop;
                hull() xflip_copy() right(10) {
                    fwd(wall) {
                        cyl(d=body_lid_hole_d-wall*2,h=ep,anchor=TOP,extra=ep);
                        down(h)
                            cyl(d=body_lid_hole_d-wall*2,h=ep,anchor=BOT,extra=ep);
                    }
                }
                hull() xflip_copy() right(10) down(h){
                    up(wall) fwd(wall)
                        cyl(d=body_lid_hole_d-wall*2,h=ep,anchor=TOP,extra=ep);
                    ycopies([0,-wall])
                    cyl(d=body_lid_hole_d-wall*2,h=ep,anchor=BOT,extra=ep);
                }
            }
        }
    }
    up(1.5) fwd(3) children(0); // screw
    back(33/2+3+$slop) children(1); // board_mount_lid
    fwd(28) up(10) children(2); // board
}
// !board_mount();

module board() {
    cam_route=["move",15,"arcdown",10,180,"move",10];
    down(2)back(38) fpc_camera(cam_route,orient=BACK);

    panel=2;
    route=["move",15,"arcup",6,90,"move",20];
    up(46) fwd(30) left(35) rpsma_pigtail(route,cable_len=150,panel=panel,threads=true) {
        attach("face",BOT) rpsma_antenna();
    }

    %cuboid([91,71,40],anchor=BOT);
}

module body_back_form() {
    w1=250;
    y1=55;//81;
    w2=250;
    y2=125;
    zz=56+14;
    wall=5;
    color_this("#ccc") diff() {
        // back
        cuboid([w2,y2,zz],chamfer=w2/2,edges=[FWD+LEFT,FWD+RIGHT],anchor=FWD);

        wall_sq2=wall*sqrt(2);
        phi=(1+sqrt(5))/2;
        tag("remove") down(5) back(wall*phi) hull() {
            x3=w2-wall_sq2*4;
            y3=y2-wall_sq2;
            y4=62.55;
            z3=zz-wall*2;
            x4=56;
            up(z3/2) {
                back(y4/2) cuboid([y4-6,ep,z3+wall],anchor=FWD+TOP);
                back(y3-1) cuboid([x3-x4,x4/2-3+wall_sq2,z3+wall],anchor=BACK+TOP);
            }
        }

        back(y2) xflip_copy() right(w2/2-19.5) {
            cuboid([20,35,zz-10],anchor=FWD);
            tag("remove") {
                right(13) back(40/2) zflip_copy() up(15) yrot(90)
                screw_hole("M5",l=33,head="button",atype="head",counterbore=10,anchor=BOT,$slop=0)
                down(31) nut_trap_inline(10,"M5",orient=BOT,$slop=0.1);
            }
        }

        d=_6902ZZ[1]+10;
        up(zz/2) {
            xflip_copy() yflip_copy() fwd(8) left(8) {
                cyl(d=4-$slop*2,h=2.5,anchor=BOT);
                cyl(d=5,h=1,anchor=BOT);
            }
            cyl(d=d-4,h=_6902ZZ[2]+wall,anchor=TOP);
            cuboid([d-4,_6902ZZ[1]/2+2,_6902ZZ[2]+wall],anchor=FWD+TOP)
                attach(BACK) color_this("#ccc") 
                tag("keep") cuboid([d-4,_6902ZZ[2]+wall,3],anchor=BOT,chamfer=-2,edges=[TOP+FWD,TOP+RIGHT,TOP+LEFT]);
            tag("remove") cyl(d=8,h=wall-$slop,anchor=TOP);
        }
        zflip() up(zz/2) {
            cyl(d=d,h=_6902ZZ[2]+wall,anchor=TOP);
            cuboid([d,_6902ZZ[1]/2+2,_6902ZZ[2]+wall],anchor=FWD+TOP)
                attach(BACK) color_this("#ccc") 
                tag("keep") cuboid([d,_6902ZZ[2]+wall,5],anchor=BOT,chamfer=-4,edges=[TOP+FWD]);
        }
        tag("remove") {
            back(19) cuboid([40,19,zz-24],anchor=BACK);
            cyl(d=_6902ZZ[1]+$slop,h=_6007ZZ[1]+$slop*2-2);
            cyl(d=_6902ZZ[1]-4,h=_6007ZZ[1]+$slop*2-1);

            d=_6902ZZ[1]+10;
            up(zz/2+7.8+$slop) back(d-6) down(3) 
                screw_hole("M4",l=26,head="button",atype="head",counterbore=10,orient=TOP,anchor=BOT,$slop=0.1)
                    down(24) nut_trap_side(15,"M4",$slop=0.1,anchor=TOP,spin=90);

        }
    }    
}

module body_back_pivot_encoder_cap() {
    zz=56+14;
    d=_6902ZZ[1]+10;
    dd=d-4+$slop*2;
    wall=5;
    zzz=40;
    color("#f84") up(zz/2+6+$slop) {
        fwd(_6902ZZ[1]/2+wall) cyl(d=6,h=6,anchor=TOP+FWD);
        difference() {
            union() {
                back(d) cyl(d=18,h=6,anchor=TOP+BACK);
                difference() {
                    union() {
                        cuboid([d,_6902ZZ[1]/2+wall,6],anchor=FWD+TOP);
                        cyl(d=d,h=_6902ZZ[2]+wall+6+$slop,anchor=TOP);
                        cuboid([d,_6902ZZ[1]/2+wall-2,_6902ZZ[2]+wall+6+$slop],anchor=FWD+TOP);            
                        back(d/2) cyl(d=d,h=6,anchor=TOP);
                    }
                    down(2) cuboid([dd,_6902ZZ[1]/2+wall,_6902ZZ[2]+wall+6],anchor=FWD+TOP);
                    down(2) back(d/2) cyl(d=dd,h=_6902ZZ[2]+wall+6,anchor=TOP);
                    down(2) cyl(d=dd,h=_6902ZZ[2]+wall+6,anchor=TOP);
                }
                // back(d/2) cyl(d=d,h=wall,anchor=BOT,chamfer2=2);
                // cuboid([d,_6902ZZ[1]/2+wall,wall],anchor=FWD+BOT,chamfer=2,edges=[TOP+LEFT,TOP+RIGHT]);
                // cyl(d=d,h=zzz,anchor=BOT,chamfer2=2);
                down(2) xflip_copy() yflip_copy() fwd(8) left(8) cyl(d=6,h=1.5,anchor=TOP);
            }
            cyl(d=d-4,h=zzz-2,anchor=BOT,chamfer2=2);
            back(d-6) up(3.5)
                screw_hole("M4",l=31,head="button",atype="head",counterbore=45,orient=TOP,anchor=BOT,$slop=0.1);
        }
    }
    up(zz/2+7.8+$slop*2) back(d-6) up(4)
        m4_30(orient=TOP) attach(TOP) down(28-0.3+$slop) m4_nut();
}
// !body_back_pivot_encoder_cap();

module body_back_pivot_cut(slop=0) {
    wall=5;
    zz=56+14;
    yy=_6902ZZ[1]+wall*2;
    xxx=yy+slop*2;
    zzz=_6902ZZ[2]+wall+2;
    color("#ccc") fwd(yy/2+ep) down(zz/2+ep) difference() {
        cuboid([xxx,yy+20+slop,zzz+slop],anchor=BOT+FWD);
        back(yy+10) up(zzz+ep+slop) xflip_copy() right(xxx/2)
            cuboid([wall,wall-slop*2,zzz+slop],anchor=TOP+RIGHT);
    }
}
*!body_back_pivot_cut();

module body_back_pivot_cap() {
    wall=5;
    yy=_6902ZZ[1]+wall*2;
    zz=56+14;
    difference() {
        intersection() {
            body_back_form() {
                skip();
                skip();
            }
            body_back_pivot_cut();
        }
        fwd(yy/2+ep) down(zz/2+ep) back(yy+10) up(9) 
            screw_hole("M4",l=16,head="button",atype="head",counterbore=10,orient=BOT,anchor=BOT,$slop=0.1);
    }
    fwd(yy/2+ep) down(zz/2+ep+$slop) back(yy+10) up(9) 
        children();
}

module body_back(a=0) {
    wall=5;
    w2=250;
    y2=125;
    zrot(-a) difference() {
        body_back_form();
        body_back_pivot_cut($slop*2);
        yy=_6902ZZ[1]+wall*2;
        zz=56+14;
        fwd(yy/2+ep) down(zz/2+ep) back(yy+10) up(9) 
            screw_hole("M4",l=16,head="button",atype="head",counterbore=10,orient=BOT,anchor=BOT,$slop=0.1)
                down(13) nut_trap_side(15,"M4",$slop=0.1,anchor=TOP,spin=90);
    }

    yflip() zrot(a) xflip_copy() fwd(79+y2+$slop) {
        left(w2/2+3) children(0); // leg 
    }

    zz=56+14;
    up(zz/2+$slop) back(y2) {
        battery_mount(anchor=TOP+RIGHT,orient=DOWN,spin=90)
        attach("battery","mount") color("#444") children(1); // battery
    }

    // back payload
    yflip() zrot(a) fwd(79+y2) children(2); // payload
}

module body_front_form() {
    w1=250;
    y1=55;//81;
    w2=250;
    y2=130;
    zz=56+14;
    wall=5;

    color("#ccc") tag_scope("body_front_form") diff() {
        fwd(10) {
            cuboid([w1,y1,zz],anchor=BACK,rounding=y1-20,edges=[BACK+LEFT,BACK+RIGHT]);
            tag("remove") fwd(y1) down(wall) cuboid([166,15+ep,zz],anchor=FWD);
        }

        tag("remove") fwd(y1+10) xflip_copy() left(w1/2-19.5) {
            cuboid([20+$slop,20+$slop,zz-10+$slop],orient=TOP,anchor=FWD,chamfer=2,edges=[BACK]);
            left(13) back(20/2-$slop) zflip_copy() up(15) yrot(-90)
                screw_hole("M5",l=33,head="button",atype="head",counterbore=10,anchor=BOT,$slop=0)
                down(31) nut_trap_side(15,"M5",orient=BOT,$slop=0.1,spin=-90);
        }

        tag("remove") back(ep) {
            hull() {
                ycyl(d=zz*2,h=ep,anchor=FWD);
                fwd(22.5-3) ycyl(d=zz+2,h=ep,anchor=BACK);
            }
            fwd(_6007ZZ[0]/2+wall*2) {
                d=_6007ZZ[1]+$slop*2;
                h=_6007ZZ[2]+$slop*2+ep*2;
                ycyl(d=d,h=h,anchor=BACK);
                
            }
            x3=_6007ZZ[0]+wall*2+2;
            y3=45+wall;
            ycyl(d=x3,h=y3,anchor=BACK);
        }
    }
}

module body_front_pivot_cut(slop=0) {
    w1=250;
    y1=55;//81;
    w2=250;
    y2=130;
    zz=56+14;
    wall=5;
    d=_6007ZZ[1]+$slop*2;
    h=_6007ZZ[2]+$slop*2;
    x3=_6007ZZ[0]+wall*2+2;
    y3=45+wall;
    zzz=zz/2+ep;

    down(slop) {
        fwd(_6007ZZ[0]/2+wall*2+h/2) {
            cuboid([d+slop*2+wall,h+slop,zzz+slop],anchor=BOT);
            up(zzz+slop) cuboid([d+wall*4+slop*2+8,h+wall*3+1+$slop+slop,wall+slop],anchor=TOP);
            cuboid([d+wall*4+slop*2+8,wall+slop*2,zzz+slop],anchor=BOT);
        }
        cuboid([d+slop*2+wall,y3+slop,zzz+slop],anchor=BACK+BOT);
    }
}
// !body_front_pivot_cut();

module body_front_pivot_cap() {
    wall=5;
    zz=56+14;
    h=_6007ZZ[2]+$slop*2;
    yrot(180) diff() {
        intersection() {
            body_front_form();
            body_front_pivot_cut();
        }
        up(zz/2-2.3) fwd(_6007ZZ[0]/2+wall*2+h/2) yflip_copy() back(9) xflip_copy() right(39) 
            screw_hole("M4",l=16,head="button",atype="head",counterbore=10,orient=TOP,anchor=BOT,$slop=0.1);
    }
}
// !body_front_pivot_cap();

module body() {
    w1=250;
    y1=55;//81;
    w2=250;
    y2=130;
    zz=56+14;
    wall=5;
    h=_6007ZZ[2]+$slop*2;

    tag_scope("body") diff() {
        body_front_form();
        tag("remove") yrot(180) body_front_pivot_cut($slop*2);
        yrot(180) up(zz/2-2.3) fwd(_6007ZZ[0]/2+wall*2+h/2) yflip_copy() back(9) xflip_copy() right(39) 
            screw_hole("M4",l=16,head="button",atype="head",counterbore=10,orient=TOP,anchor=BOT,$slop=0.1)
                down(13) nut_trap_side(10,"M4",$slop=0.1,anchor=TOP,spin=180);
    }

    children(0); //body_back
    xflip_copy() fwd(64+y1+$slop) left(w1/2+3) children(1); // front_leg
    yrot(180) up(zz/2-2.3) fwd(_6007ZZ[0]/2+wall*2+h/2) yflip_copy() back(9) xflip_copy() right(39)
        m4_14(orient=TOP)
            attach(TOP) down(11.3) nut("M4",spin=30);

    // front payload
    fwd(y2-5) children(2); // payload
}
*!nop()
xview()
{
    body() {
        body_back();
        skip();
    }
    body_back_pivot_cap();
    body_front_pivot_cap();
    pivot_mid();
    pivot_front();
    pivot_back();
}

module pivot_form() {
    wall=5;
    color("#f84") diff() {
        zz=56+14;
        d=_6007ZZ[0]+wall*2;
        fwd(_6007ZZ[0]/2+_6007ZZ[2]+wall*2+$slop*2) {
            ycyl(d=_6007ZZ[0]+wall*2,h=wall,anchor=BACK);
            ycyl(d=_6007ZZ[0]-$slop,h=_6007ZZ[2]+$slop*2,anchor=FWD);
        } 

        union() {
            hull() {
                fwd(_6007ZZ[0]/2+_6007ZZ[2]+wall*2+$slop) back(_6007ZZ[2]+$slop)
                    ycyl(d=d,h=ep,anchor=FWD);
                cyl(d=_6902ZZ[1],h=d);
            }
            zzz=_6007ZZ[1]-2+ep;
            cyl(d=_6902ZZ[0]-$slop,h=zzz);
            up(zzz/2+4) {
                cyl(d=7,h=4,anchor=TOP);
                tag("remove") up(0.5+$slop) yrot(180) magnet_neg(1.5);
            }
            cyl(d=_6902ZZ[0]+4,h=_6007ZZ[1]-(_6902ZZ[2]+$slop)*2-2);
        }

        tag("remove") {
            back(_6902ZZ[1]/2) ycyl(d=15,h=100,anchor=BACK,extra=ep);
            yrot_copies(n=2) up(13.1) fwd(42+wall) {
                screw_hole("M4",l=32,head="button",atype="head",counterbore=10,orient=FWD,anchor=BOT,$slop=0.1);
                back(22.5) yrot(30) nut_trap_side(30,"M4",$slop=0.1,orient=FWD,anchor=TOP,spin=90);
            }
        }
    }
}

module pivot_front() {
    wall=5;
    zz=56+14;
    // cyl(d=_6902ZZ[1]+5,h=zz+10);
    fwd(_6007ZZ[0]/2+wall*2+$slop) ball_bearing("6007ZZ",orient=FWD,anchor=BOT);
    zflip_copy() up(13.1) fwd(42+wall) m4_30(orient=FWD,anchor=BOT) down(25.3) zrot(30) m4_nut();
}

module pivot_mid() {
    wall=5;
    // zview()
    pivot_form();
}

module pivot_back() {
    zz=56+14;
    // cyl(d=_6902ZZ[1]+5,h=zz+10);
    zflip_copy() up(_6007ZZ[1]/2-1) {
        ball_bearing("6902ZZ",orient=TOP,anchor=TOP);
    }
}

module robot(yaw=0,roll=0) {
    explode=0;// 0..1 
    // up(107.5) 
    body() {
        yrot(roll) body_back(yaw) {
            fwd(explode*40) 
            leg() {
                motor() m3_8();//*4
                drive_gear();
                wheel() skip() m5_30() down(27) m5_nut();
                axle_mount() {
                    axle() {
                        ball_bearing("6902ZZ",orient=RIGHT,anchor=BOT);
                        magnet();
                    }
                    as5600_mount() {
                        as5600();
                        as5600_mount_cap() m3_11() down(11) m3_nut();
                    }
                    m3_11() down(10.5) m3_nut();
                }
                leg_cap() m3_11();
            }
            skip() battery_simplified();
            skip() %cuboid([150,150,100]);
        }
        // nop();// 
        fwd(explode*40) 
        front_leg() {
            motor() m3_8();//*4
            drive_gear();
            wheel() skip() m5_30() down(27) m5_nut();
            axle_mount() {
                axle() {
                    ball_bearing("6902ZZ",orient=RIGHT,anchor=BOT);
                    magnet();
                }
                as5600_mount() {
                    as5600();
                    as5600_mount_cap() m3_11() down(11) m3_nut();
                }
                m3_11() down(10.5) m3_nut();
            }
            front_leg_cap() m3_11();
        }
        skip() %cuboid([150,120,100]);
    }
    yrot(roll) zrot(-yaw) {
        body_back_pivot_cap() {
            m4_14(orient=BOT,anchor=TOP) attach(TOP) down(9.7+$slop) m4_nut();
        }
        body_back_pivot_encoder_cap();
    }
    body_front_pivot_cap();
    yrot(roll) {
        pivot_mid();
        pivot_back();
    }
    pivot_front();
    // pivot encoder
    up(34.5) yrot(180) difference() {
        as5600();
        down(3+ep) cuboid([20,20,10],anchor=TOP);
    }
}

*!nop() {
    //xview(true) 
    body_back(0){
        nop();
        nop();
    }
    pivot_mid();
    pivot_front();
    pivot_back();
}

// !yrot(-90) wheel(); // print
// !axle(); // print
// !up(102) drive_gear(); // print
// !yrot(-90) axle_mount(); // print
// !yrot(-90) as5600_mount_cap(); // print
// !yrot(-90) as5600_mount(); // print

// !yrot(-90) caster_side(); // print
// !yrot(-90) caster_leg_bottom(caster_leg_len); // print
// !xrot(180) caster_leg_top(caster_leg_len); // print
// !yrot(90) caster_cap_right(); // print
// !yrot(-90) caster_cap_left(); // print
// !yrot(-90) caster_spacer(); // print

// !yrot(90) leg(); // print left
// !yrot(-90) xflip() leg(); // print right
// !yrot(90) leg_cap() nop(); // print
// !body(); // print
// !xrot(90) board_mount(); // print
// !board_mount_lid();
// !body_tray();

// zrot($t*360) render()
// zview(true)
//right(128-45/2) up(15) 
// back(154/2-5-5-5)

// yview() fwd(59) left(112.75-15)
// xview()
// zrot(sin($t*360)*45) robot(sin($t*360+90)*45);

// xview()
// zview(true,true)
robot(0,0);

// xview()
// body_lid() board_mount() {
//     m3_8() down(1.5+$slop) m3_nut();
//     board_mount_lid();
//     board();
// }
/*
up(300) {
    measure([-75,50,0],[75,50,0]);
    // measure([-50,-93,0],[50,-93,0]);
    measure([-75,-71,0],[-75,79,0]);
    measure([-128,100,0],[128,100,0]);
}
xrot(90) up(300) {
    measure([-55,0,0],[-55,78,0]);
    measure([-70,0,0],[-70,78+56,0]);
}

// grass
*recolor("#4a4") {
    x=rands(2,4,10);
    left(100) for(i=[0:9]) right(i*20) cuboid([10,10,x[i]*25.4],anchor=BOT);
}
*/

// !wheel();

echo(str("\n",
"sh ./do_mp4.sh u-bot.scad ",
$vpt[0],",",$vpt[1],",",$vpt[2],",",
$vpr[0],",",$vpr[1],",",$vpr[2],",",
$vpd,
"\n"));
