include <BOSL2/std.scad>
include <BOSL2/screws.scad>
include <BOSL2/gears.scad>
include <BOSL2/ball_bearings.scad>
include <BOSL2/nema_steppers.scad>
include <../lib/as5600.scad>
include <../lib/globals.scad>

$fn=0;$fa=1;$fs=$preview?2:0.25;ep=0.03;$slop=0.2;
// $fn=0;$fa=1;$fs=2;ep=0.03;$slop=0.2;
// $fn=0;$fa=1;$fs=0.25;ep=0.03;$slop=0.2;
_6902ZZ=ball_bearing_info("6902ZZ");
echo(_6902ZZ);

wheel_mod=5;
wheel_teeth=40; //72;
drive_teeth=12; //22;
wheel_bearing_spacing=30;
caster_x=50;
caster_d=60;
caster_leg_x=13;
caster_leg_len=90;


module m3_11() {
    color("#888") screw("M3,11",head="socket",drive="hex",atype="head",thread="none",orient=RIGHT,anchor=BOT,details=false) children();
}

module m3_8(orient=UP) {
    color("#888") screw("M3,11",head="socket",drive="hex",atype="threads",thread="none",orient=orient,anchor=TOP,details=false) children();
}

module m3_nut() {
    color("#888") nut("M3",thread="none");
}

module m4_30() {
    color("#888") screw("M4,30",head="button",drive="hex",atype="shaft",thread="none",orient=RIGHT,anchor=TOP,details=false) children();
}

module m4_nut() {
    color("#888") nut("M4",thread="none");
}

module m5_16(orient=UP,anchor=BOT) {
    color("#888") screw("M5,16",head="button",drive="hex",atype="head",thread="none",orient=orient,anchor=anchor,details=false) children();
}

module m5_30(orient=UP,anchor=BOT) {
    color("#888") screw("M5,30",head="button",drive="hex",atype="head",thread="none",orient=orient,anchor=anchor,details=false) children();
}

module m5_nut(orient=undef,anchor=undef) {
    color("#888") nut("M5",orient=orient,anchor=anchor,thread="none");
}

module magnet() {
    color("#888") %cyl(d=4,l=2,anchor=BOT);
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



module caster_side() {
    xx=(caster_x-caster_leg_x)/2-$slop;
    recolor("#444") diff() {
        xcyl(d=caster_d,h=xx,rounding2=12,anchor=LEFT);
        tag("remove") xcyl(d=_6902ZZ[1]-4,h=xx,extra=ep);
        right(xx) {
            d=_6902ZZ[1]+0.75+$slop;
            tag("remove") 
            xcyl(d=d,h=_6902ZZ[2]+3,anchor=RIGHT,extra=ep);
            // crush ribs
            tag("keep") xrot_copies(n=12) left(3) back(d/2)
                xcyl(d2=0.5,d1=1,h=_6902ZZ[2],anchor=RIGHT,extra=ep);
        }
    }

    right(xx-3+ep) children(0); // bearing
}

module caster_leg(l) {
    diff() {
        d=caster_d-4;
        dd=_6902ZZ[0]+3;
        ll=d/2+17.5-3;
        zz=3+_6902ZZ[2]/2;
        xcyl(d=d,h=caster_leg_x);
        cuboid([caster_leg_x,(d-dd)/2,d/2],anchor=BOT+BACK,chamfer=caster_leg_x/3,edges=[FWD+LEFT,FWD+RIGHT]);
        fwd((d-dd)/2) intersection() {
            union() {
                r=(_6902ZZ[0]-0.75)/2;
                cyl(r=r,h=l,anchor=BOT);
                up(ll) zrot_copies(n=14) fwd(r) cyl(d2=0.5,d1=1,h=_6902ZZ[2],anchor=BOT,extra=ep);
                up(l-_6902ZZ[2]/2) {
                    zrot_copies(n=14) fwd(r) cyl(d1=0.75,d2=1,h=_6902ZZ[2]/2,anchor=BOT,extra=ep);
                    zrot_copies(n=14) fwd(r) cyl(d2=0.75,d1=1,h=_6902ZZ[2]/2,anchor=TOP,extra=ep);
                }
            }
            cuboid([caster_leg_x,_6902ZZ[0]-$slop,l],anchor=BOT);
        }
        fwd((d-dd)/2) intersection() {
            cyl(d=dd,h=ll,anchor=BOT);
            cuboid([caster_leg_x,dd,ll],anchor=BOT);
        }
        fwd((d-dd)/2) up(l) difference() {
            cyl(d=_6902ZZ[0]+4,h=10,anchor=BOT);
        }
        tag("remove") {
            xcyl(d=_6902ZZ[0]-1+$slop,h=caster_leg_x+1+ep);
            fwd((d-dd)/2) {
                up(l+10+ep) {
                    cuboid([20,5,5],anchor=TOP);
                }
                up(l-zz+3) {
                    // #cyl(d=30,h=ep,anchor=BOT,extra=ep);
                    up(3) {
                        cyl(d=9,h=zz+10,anchor=BOT,extra=ep);
                        screw_hole("M3",l=13,head="socket",atype="threads",anchor=TOP,tolerance="tap",counterbore=zz)
                        down(5.5) nut_trap_side(23,"M3",$slop=0.1);
                    }
                }
            }
        }
    }

    xflip_copy() right(caster_leg_x/2+$slop) children(0); // caster
    children(1); // caster_cap_right
    children(2); // caster_cap_left
    right(11.75) children(3); // bolt
}

module caster_leg_top(l) {
    recolor("#777") 
    intersection() {
        up(l-(_6902ZZ[2]-$slop)/2) cuboid([100,100,200],anchor=BOT);
        caster_leg(l){
            nop();
            nop();
            nop();
            nop();
        }
    }
}

module caster_leg_bottom(l) {
    recolor("#666") 
    intersection() {
        up(l-(_6902ZZ[2]+$slop)/2) cuboid([100,100,200],anchor=TOP);
        caster_leg(l) {
            children(0);
            children(1);
            children(2);
            children(3);
        }
    }
}

module caster_cap() {
    right($slop/2) {
        xcyl(d=_6902ZZ[0]-1,h=caster_x/2-3,anchor=LEFT);
        right(caster_x/2-3) {
            xcyl(d=_6902ZZ[0]+4,h=3-$slop/2,anchor=LEFT);
            // crush ribs
            tag("keep") xrot_copies(n=12) up((_6902ZZ[0]-0.75)/2)
                xcyl(d1=0.5,d2=1,h=_6902ZZ[2],anchor=RIGHT,extra=ep);
        }
    }

    right(caster_leg_x/2+$slop) children(0); // caster_cap
}

module caster_cap_right() recolor("#666") diff() { 
    caster_cap() children(); 
    caster_screw_hole();
}

module caster_cap_left() recolor("#666") diff() {
    xflip() caster_cap() children();
    caster_screw_hole();
}

module caster_spacer() recolor("#333") difference() {
    xx=(caster_x-caster_leg_x)/2-$slop*2-_6902ZZ[2]-2.5;
    xcyl(d1=_6902ZZ[0]+8,d2=_6902ZZ[0]+4,h=xx,anchor=LEFT);
    xcyl(d=_6902ZZ[0]-1+$slop*2,h=xx,extra=ep,anchor=LEFT);
}

module caster_screw_hole() {
    right(11.75) screw_hole("M4",l=30,head="button",atype="shaft",
        counterbore=30,orient=RIGHT,anchor=TOP,$slop=0)
    down(12-3.4) zrot(30) nut_trap_inline(20,"M4",orient=BOT,$slop=0.1);
}

// !yview(true,xray=true)
module caster(l) {
    down(l) {
        dd=_6902ZZ[0]+3;
        back((caster_d-4-dd)/2) {
            caster_leg_top(l);
            caster_leg_bottom(l) {
                caster_side() ball_bearing("6902ZZ",orient=RIGHT,anchor=TOP);
                caster_cap_right() caster_spacer();
                caster_cap_left() caster_spacer();
                %m4_30() down(12) m4_nut();
            }
        }
        up((caster_d-4)/2+14.5) ball_bearing("6902ZZ",anchor=BOT);
        up(l-ep) {
            ball_bearing("6902ZZ",anchor=TOP);
        }
    }
}
// !caster(caster_leg_len);

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
                        cuboid([20+$slop,40+$slop,zz-10+$slop],orient=BACK,anchor=FWD);
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

module body_tray() {
    wall=3;
    color("#f84") diff() {
        hull() {
            cuboid([184-wall*4-$slop*2,140-wall*4-$slop*2,ep],anchor=BOT+FWD,chamfer=12+$slop*2,edges=[BACK+LEFT,BACK+RIGHT]);
            up(5) back(5) cuboid([184-wall*4-$slop*2,140-wall*4-$slop*2-5,ep],anchor=BOT+FWD,chamfer=12+$slop*2,edges=[BACK+LEFT,BACK+RIGHT]);
        }
        tag("remove") down(ep) fwd(ep) cuboid([150+$slop*4,94+$slop*2+ep,5+ep*3],anchor=BOT+FWD);
    }
}

module body_lid() {
    w=250;
    wall=3;
    rr=45;
    slop=0.5;
    color("#ccc") diff() {
            back(120-55+slop) {
            cuboid([w-wall*2-slop*2,20+55-wall-slop*2,wall],anchor=FWD+TOP,rounding=rr-wall-slop,edges=[BACK+LEFT,BACK+RIGHT]);
            xflip_copy() right(184/2-wall-ep-slop) {
                back(ep) cuboid([12+ep,12+ep,wall],anchor=BACK+TOP+LEFT,rounding=6,edges=[RIGHT+FWD]);
                right(6) fwd(6) screw_hole("M3",l=13,head="socket",atype="threads",anchor=TOP,tolerance="tap")
                    attach(BOT) down(2) nut_trap_side(30,"M3",$slop=0.1,anchor=TOP);
            }
        }
        back(wall+4+slop+99/2) cuboid([184-wall*2-slop*2,99+2+wall*2-slop,wall],anchor=TOP);
        tag("remove") up(ep) back(120) cyl(d=20,h=wall+ep*2,anchor=TOP);
    }
}

module body() {
    w=250;
    zz=56+14;
    yy=113;
    yyy=79;
    xx=23;
    wall=3;
    rr=45;
    recolor("#ccc") back(yyy) diff() {
        cuboid([w,140,zz],anchor=FWD,rounding=rr,edges=[BACK+LEFT,BACK+RIGHT]);
        xflip_copy() left(w/2+3-45/2) cuboid([20-1-$slop,38,60-1-$slop],anchor=BACK);
        tag("remove") {
            // wire slot
            xflip_copy() fwd(ep) left(w/2+3-45/2-(20-$slop)/2-12) down((60-$slop)/2) {
                up(15) right(1) cuboid([5,(wall+ep)*2,30-$slop],anchor=FWD+LEFT+BOT);
                // back(wall*2) cuboid([5,115,100-$slop],anchor=FWD+LEFT+BOT);
            }

            // main body cutout
            //#down(zz/2-wall) back(wall*2) cuboid([150+2,99+2,64+6],anchor=BOT+FWD);
            up(zz/2+ep) back(wall*2) {
                cuboid([184-wall*4,140-wall*4,zz-wall],anchor=TOP+FWD,chamfer=12,edges=[BACK+LEFT,BACK+RIGHT]);
            }
            
            // top pocket lip
            up(zz/2+ep) {
                back(120-55) {
                    cuboid([w-wall*2,20+55-wall,wall],anchor=FWD+TOP,rounding=rr-wall,edges=[BACK+LEFT,BACK+RIGHT]);
                    xflip_copy() right(184/2-wall-ep) {
                        back(ep) cuboid([12+ep,12+ep,wall],anchor=BACK+TOP+LEFT,rounding=6,edges=[RIGHT+FWD]);
                        right(6) fwd(6) screw_hole("M3",l=13,head="socket",atype="threads",anchor=TOP,tolerance="tap")
                            attach(BOT) down(2) nut_trap_side(30,"M3",$slop=0.1,anchor=TOP);
                    }
                }
                back(wall+4+$slop+99/2) cuboid([184-wall*2,99+2+wall*2,wall],anchor=TOP);
            }
            // top pocket
            up(zz/2+ep*2-wall) back(120-55+wall) cuboid([w-wall*4,20+55-wall*3,10],anchor=FWD+TOP,rounding=rr-wall*2,edges=[BACK+LEFT,BACK+RIGHT]);
            
            // tool pin hole
            xflip_copy() back(20) fwd($slop) left(w/2+3-45/2) 
            cyl(d=15,h=zz,chamfer=-3,extra=ep);
            // leg screws
            xflip_copy() left(w/2+3-8.5) fwd(40/2+$slop) zflip_copy() up(15) yrot(-90)
            screw_hole("M5",l=33,head="button",atype="head",counterbore=10,anchor=BOT,$slop=0,tolerance="loose");
            // caster hole
            back(177-15.75-yyy) xflip_copy() left(w/2+2.25-45/2)  {
                zzz=$slop+caster_leg_len-50;
                down(35) {
                    cyl(d=_6902ZZ[1]+$slop,h=_6902ZZ[2]+$slop,anchor=BOT,extra=ep);
                    cyl(d=_6902ZZ[1]-4,h=zzz,anchor=BOT,extra=ep);
                    up(zzz) cyl(d=_6902ZZ[1]+$slop,h=_6902ZZ[2]+$slop*2+10,anchor=BOT,extra=ep);
                }
                // caster encoder screw holes
                up(zz/2+ep-wall-10+4) {
                    right(15) fwd(10) screw_hole("M3",l=13,head="socket",atype="threads",anchor=TOP,tolerance="tap")
                        attach(BOT) down(2) zrot(180) nut_trap_side(30,"M3",$slop=0.1,anchor=TOP);
                    back(15) left(10) screw_hole("M3",l=13,head="socket",atype="threads",anchor=TOP,tolerance="tap")
                        attach(BOT) down(2) zrot(242) nut_trap_side(20,"M3",$slop=0.1,anchor=TOP);
                }
            }

        }
    }

    xflip_copy() fwd($slop) left(w/2+3) children(0); // leg
    down(77.5-caster_leg_len) back(177-15.75) xflip_copy() left(w/2+2.25-45/2)
        zrot(180) children(1); // caster
    down(33) back(6+yyy+$slop) children(2); // battery
    back(yyy+$slop) down(zz/2-wall-$slop) back(wall*2) children(3); // body_tray
    up(zz/2+$slop) back(yyy) children(4); // body_lid
}

module robot() {
    // up(107.5) 
    body() {
        // nop();// 
        leg() {
            motor() m3_8();//*4
            drive_gear();
            wheel() m5_30() down(27) m5_nut();
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
        // nop();// 
        caster(caster_leg_len);
        color("#444") cuboid([150,94,65],anchor=BOT+FWD); // battery
        body_tray();
        body_lid();
    }
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

// !body_tray();
// !body_lid();

// zrot($t*360) render()
// zview(true)
//right(128-45/2) up(15) 
// back(154/2-5-5-5)

// yview() fwd(59) left(112.75-15)
robot();
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