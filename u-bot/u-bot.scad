include <BOSL2/std.scad>
include <BOSL2/screws.scad>
include <BOSL2/gears.scad>
include <BOSL2/ball_bearings.scad>
include <BOSL2/nema_steppers.scad>
include <../lib/as5600.scad>
include <../lib/globals.scad>

// $fn=0;$fa=1;$fs=$preview?2:0.25;ep=0.03;$slop=0.2;
$fn=0;$fa=1;$fs=2;ep=0.03;$slop=0.2;
// $fn=0;$fa=1;$fs=0.25;ep=0.03;$slop=0.2;
_6902ZZ=ball_bearing_info("6902ZZ");
echo(_6902ZZ);

wheel_mod=5;
wheel_teeth=40; //72;
drive_teeth=12; //22;
wheel_bearing_spacing=30;

module m3_11() {
    recolor("#888") screw("M3,11",head="socket",drive="hex",atype="head",thread="none",orient=RIGHT,anchor=BOT) children();
}

module m3_nut() {
    recolor("#888") nut("M3",thread="none");
}

module m4_30() {
    recolor("#888") screw("M4,30",head="button",drive="hex",atype="shaft",thread="none",orient=RIGHT,anchor=TOP) children();
}

module m4_nut() {
    recolor("#888") nut("M4",thread="none");
}

module m5_16(orient=UP,anchor=BOT) {
    recolor("#888") screw("M5,16",head="button",drive="hex",atype="head",thread="none",orient=orient,anchor=anchor) children();
}

module m5_30(orient=UP,anchor=BOT) {
    recolor("#888") screw("M5,30",head="button",drive="hex",atype="head",thread="none",orient=orient,anchor=anchor) children();
}

module m5_nut(orient=undef,anchor=undef) {
    recolor("#888") nut("M5",orient=orient,anchor=anchor,thread="none");
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
            right(3+$slop) xcyl(d=_6902ZZ[0]-0.8+$slop*2,h=40,anchor=RIGHT,extra=$slop);
            left(36+ep) {
                xcyl(d=120,h=16+ep,chamfer2=16,anchor=LEFT);
                right(7) xrot_copies(n=4) back(55) zrot(45) xcyl(d=10,h=30);
            }
        }
        d=_6902ZZ[0]-0.8;
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
// !yrot(-90) wheel(); // print


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
// !axle(); // print

module motor() {
    nema_stepper_motor(size=17,h=39,shaft_len=30,orient=FWD)
        attach(TOP) up(2+$slop) children();
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
// !up(102) drive_gear();

module axle_mount() {
    recolor("#f84") diff() {
        left(3+ep) {
            cuboid([6,50,50],anchor=LEFT,rounding=4,edges="X");
            cuboid([wheel_bearing_spacing+7,34,50],anchor=LEFT,chamfer=1,edges="X");
            zflip_copy() yflip_copy() back(41/2) up(41/2) {
                right(3-ep) screw_hole("M3",l=15,head="socket",atype="head",orient=LEFT,anchor=BOT,$slop=0);
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
    zflip_copy() yflip_copy() back(41/2) up(41/2) yrot(180) children(2); // mounting screws
}
// !yview() xflip_copy() left(50) yrot(-90) axle_mount();

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
// !yrot(-90) as5600_mount_cap(); // print

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
// !yrot(-90) as5600_mount(); // print



caster_x=50;
caster_d=60;
caster_leg_x=15;

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
    recolor("#666") diff() {
        d=caster_d-4;
        xcyl(d=d,h=caster_leg_x);
        cuboid([caster_leg_x,d/2,d/2],anchor=BOT+BACK,chamfer=caster_leg_x/3,edges=[FWD+LEFT,FWD+RIGHT]);
        fwd(d/2)
        cuboid([caster_leg_x,caster_leg_x,l],chamfer=caster_leg_x/3,edges="Z",anchor=BOT+FWD);

        tag("remove") xcyl(d=_6902ZZ[0]-1+$slop,h=caster_leg_x+1+ep);
    }

    xflip_copy() right(caster_leg_x/2+$slop) children(0); // caster
    children(1); // caster_cap_right
    children(2); // caster_cap_left
    right(11.75) children(3); // bolt
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
    xx=(caster_x-caster_leg_x)/2-$slop*2-_6902ZZ[2]-3;
    #xcyl(d1=_6902ZZ[0]+8,d2=_6902ZZ[0]+4,h=xx,anchor=LEFT);
    xcyl(d=_6902ZZ[0]-1+$slop*2,h=xx,extra=ep,anchor=LEFT);
}

module caster_screw_hole() {
    right(11.75) screw_hole("M4",l=30,head="button",atype="shaft",
        counterbore=30,orient=RIGHT,anchor=TOP,$slop=0)
    down(12-3.4) zrot(30) nut_trap_inline(20,"M4",orient=BOT,$slop=0.1);
}

// !yview(true,xray=true)
module caster(l) {
    down(l) back((caster_d-caster_leg_x-4)/2) caster_leg(l) {
        caster_side() %ball_bearing("6902ZZ",orient=RIGHT,anchor=TOP);
        caster_cap_right() caster_spacer();
        caster_cap_left() caster_spacer();
        %m4_30() down(12) m4_nut();
    }
}
// !caster(60);

module leg() {
    recolor("#ccc")
    diff() {
        left(3) {
            fwd(75) {
                zz=56;
                zzz=100;
                yy=34;
                right(3) cuboid([45,30,zz],rounding=4,edges=[FWD],anchor=LEFT+FWD)
                attach(BACK) cuboid([45,124,zz],orient=FWD,anchor=FWD,chamfer=5,edges=[TOP+BACK]) {
                    tag("remove") attach(BACK) up(ep) {
                        cuboid([20+$slop,40+$slop,zz-10+$slop],orient=BACK,anchor=FWD,chamfer=2,edges=[BACK]);
                        xrot(90) left(14) fwd(40/2) zflip_copy() up(15) yrot(-90)
                            screw_hole("M5",l=33,head="button",atype="head",counterbore=10,anchor=BOT,$slop=0)
                            down(33) nut_trap_inline(10,"M5",orient=BOT,$slop=0.1);
                    }
                }
            }
        }
        tag("remove") {
            // axel mount cutout
            left(3+ep) {
                cuboid([6+$slop,50+$slop*2,50+$slop*2],anchor=LEFT,rounding=4+$slop,edges="X");
                cuboid([52.5+ep*2,34+$slop*2,50+$slop*2],anchor=LEFT);
                zflip_copy() yflip_copy() back(41/2) up(41/2) {
                    right(3-ep) screw_hole("M3",l=13,head="socket",atype="head",orient=LEFT,anchor=BOT,tolerance="tap");
                    right(12) xrot(90) nut_trap_side(23,"M3",orient=LEFT,$slop=0.1);
                }
            }
            // stepper cutout
            fwd(73-2) right(21.35-ep) {
                nema_stepper_motor(size=17,h=39,shaft_len=30,orient=FWD,details=false);
                ycyl(d=22.5,h=10,anchor=BACK);
            }
            // stepper shaft cutout
            fwd(73+ep) right(42.5/2) {
                zz=13.75;
                fwd(2) cuboid([25+ep,4+ep*2,22],anchor=RIGHT+FWD);
                zflip_copy() xflip_copy() left(15.5) up(15.5)
                    screw_hole("M3",l=8,head="socket",atype="head",orient=FWD,anchor=BOT,tolerance="tap");

                back(42) cuboid([30,12,18],anchor=BACK+LEFT);
            }
        }
    }
    fwd(73-2) right(21.25) children(0); // motor
    xrot(-90) right(23.5+1.25) left(3.35) children(1); // drive gear
    left(3.35) children(2); // wheel
    children(3); // axle_mount
    right(45+$slop) children(4); // leg cap
}
// !xflip_copy() left(50) yrot(90) leg(); // print

module leg_cap() {
    recolor("#f84") fwd(71) {
        zz=56;
        zzz=100;
        yy=34;
        cuboid([10-$slop,30,zz],anchor=LEFT+FWD,chamfer=5,edges=[FWD+RIGHT])
        attach(BACK) cuboid([10-$slop,120,zz],orient=FWD,anchor=FWD,chamfer=5,edges=[TOP+BACK]);
    }
}

module body() {
    w=210;
    zz=56;
    zzz=105;
    yy=113;
    yyy=79;
    xx=23;
    recolor("#ccc")
    back($slop) diff() {
        xflip_copy() 
        left(w/2-0.5) {
            back(yyy) down(zz/2-5) {
                left(xx) {
                    cuboid([w/2+xx,yy-50,zzz],anchor=FWD+LEFT+BOT,rounding=10,edges=LEFT+FWD)
                        attach(BACK) cuboid([w/2+xx,50,zzz],orient=FWD,anchor=FWD,rounding=50,edges=RIGHT+BACK);
                    wall=5;
                    tag("remove") {
                        up(wall) back(wall) right(wall)
                        difference() {
                            cuboid([50,yy-50-wall*2,zzz],anchor=FWD+LEFT+BOT,rounding=10-wall,edges=LEFT+FWD)
                                attach(BACK) down(ep)
                                    cuboid([50,50,zzz],orient=FWD,anchor=FWD,rounding=50-wall,edges=RIGHT+BACK);
                            right(xx+w/2-0.5-wall)
                            left(152/2+3)
                            {
                                cuboid([w/2-wall*2,yy-wall*2,zzz],anchor=FWD+LEFT+BOT);
                            }
                            // wheel cutout
                            right(50) fwd(yyy) up(zz/2-5)
                            xcyl(d=220+1,h=50,rounding1=-5,anchor=RIGHT);
                        }
                    }
                }
                right(22.5) up((zz-10)/2) {
                    cuboid([20,40,zz-10],anchor=BACK,chamfer=2,edges=[FWD]);
                    tag("remove") left(14) fwd(40/2) zflip_copy() up(15) yrot(-90)
                        screw_hole("M5",l=33,head="button",atype="head",counterbore=10,anchor=BOT,$slop=0)
                        down(33) nut_trap_inline(10,"M5",orient=BOT,$slop=0.1);

                }
            }
            tag("remove") {
                // wheel cutout
                xcyl(d=220,h=xx+ep,rounding1=-5,anchor=RIGHT);
            }
        }
        // battery cutout
        tag("remove") {
            down(20) back(yyy+8) {
                cuboid([152+$slop*2,65+$slop*2,zzz+$slop],anchor=BOT+FWD);
                cuboid([30,100,zzz+$slop],anchor=BOT+FWD);
                back(65+3)
                    cuboid([152+$slop*2,32,zzz+$slop],anchor=BOT+FWD);
            }
        }
    }
    xflip_copy()
    // xflip()
    fwd($slop) left(w/2-0.5) children(0); // leg
    down(17.5) back(177.5-15) xflip_copy() left(112.75-15)
        zrot(180) children(1); // caster
    down(17) back(yyy+8+$slop) children(2); // battery
}
// !body(); // print

module robot() {
    up(107.5) 
    //zview()
    body() {
        leg() {
            motor();
            // skip()
            drive_gear();
            // skip() 
            wheel() %m5_30() down(27) m5_nut();
            // skip() 
            // !render() yview(true,xray=true)
            axle_mount() {
                %axle() {
                    %ball_bearing("6902ZZ",orient=RIGHT,anchor=BOT);
                    %magnet();
                }
                //skip()
                as5600_mount() {
                    as5600();
                    as5600_mount_cap() m3_11() down(11) m3_nut();
                }
                m3_11() down(10.5) m3_nut();
            }
            leg_cap();
        }
        caster(60);
        color("#444") cuboid([150,65,99],anchor=BOT+FWD); // battery
    }
}

// yview(true)
robot();
up(300) {
    measure([-50,50,0],[50,50,0]);
    // measure([-50,-93,0],[50,-93,0]);
    measure([-105,-50,0],[105,-50,0]);
    measure([-30,-71,0],[-30,79,0]);
    measure([-128,200,0],[128,200,0]);
}
/*
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

echo(str("\n",
"sh ./do_mp4.sh u-bot.scad ",
$vpt[0],",",$vpt[1],",",$vpt[2],",",
$vpr[0],",",$vpr[1],",",$vpr[2],",",
$vpd,
"\n"));