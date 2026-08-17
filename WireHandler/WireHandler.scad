include <BOSL2/std.scad>
include <BOSL2/screws.scad>
include <BOSL2/gears.scad>
include <BOSL2/nema_steppers.scad>

$fn=0;$fa=1;$fs=$preview?0.5:0.25;ep=0.01;
$slop=0.2;
nozzle=0.4;
mg995_params = [20.5,40.26,40.6,28.5,7,3.5,10,3,4.5];

module big_servo_neg(params=servo_params,wires_left=true,with_screw_holes=false,wire_channel_len=0) {
    width=params[0];
    length=params[1];
    height=params[2];
    arm_offset=params[3];
    arm_length=params[4];
    arm_thickness=params[5];
    axel_offset=params[6];
    wires_offset=params[7];

    zrot(90) down(arm_offset) union() {
        // body
        union() {
            down(ep/2)cuboid([length+ep,width+ep,height+ep],anchor=BOT);
            up(arm_offset) {
                difference() {
                    cuboid([length+arm_length*2+ep*2,width,arm_thickness],anchor=BOT);
                    if (with_screw_holes) {
                        union() {
                            xflip_copy()
                                yflip_copy() {
                                    d=4.75;
                                    up(arm_thickness)right(length/2+arm_length-2.5) fwd(5) cyl(d1=nozzle*4, d2=d, h=(d-nozzle*2)/sqrt(2),$fn=12,anchor=TOP);
                                }
                        }
                    }
                }
            }
            right(length/2) left(axel_offset) up(height) {
                cyl(d=12+$slop*2, h=10, anchor=BOT);
            }
            // wires
            up(wires_offset) right(length/2-ep) cuboid([6.5,8,5], anchor=BOT+LEFT, rounding=2.5,edges=[RIGHT+BOT]);
        }
    }
}

module big_servo(params=servo_params) {
    width=params[0];
    length=params[1];
    height=params[2];
    arm_offset=params[3];
    arm_length=params[4];
    arm_thickness=params[5];
    axel_offset=params[6];
    wires_offset=params[7];
    screw_hole_size=params[8];
    zrot(90) down(arm_offset) union() {
        // body
        %union() {
            color("#444") render() union() {
                cuboid([length,width,height],anchor=BOT);
                up(arm_offset) {
                    difference() {
                        cuboid([length+arm_length*2,width,arm_thickness],anchor=BOT);
                        // screw holes
                        union() {
                            xflip_copy()
                                yflip_copy() {
                                    right(length/2+arm_length-2.5) fwd(5) cyl(d=screw_hole_size, h=8, anchor=BOT);
                                }
                        }
                    }
                }
                right(length/2) left(axel_offset) up(height) {
                    cyl(d=11, h=1, anchor=BOT);
                }
            }
            // wires
            color("#883333a4") render() up(wires_offset) right(length/2) cuboid([10,6,4], anchor=BOT+LEFT);
            // shaft
            right(length/2) left(axel_offset) up(height+1) {
                color("#ffffffa4") render() cyl(d=5.5,h=3.5,anchor=BOT, $fn=32);
            }
        }
        right(length/2) left(axel_offset) up(height+1) {
            up(3.5) children();
        }
    }
}

module servo_gear_socket(h=3.5,r=2.95,flip=false) {
    difference() {
        union() {
            if (flip) {
                cyl(r=r+0.35,h=h,anchor=TOP);
                up(nozzle*2) {
                    cyl(r2=3,d1=3,h=nozzle*2,anchor=BOT);
                    up(nozzle*2) cyl(r=3,h=5,anchor=BOT);
                }
            } else down(nozzle*2) {
                cyl(r=r+0.35,h=h-nozzle*2,anchor=TOP);
                cyl(r1=r+0.35,d2=3,h=nozzle*2,anchor=BOT);
            }
        }
        for (i=[0:24]) zrot(i*360/25) fwd(r) hull() {
            cyl(d=nozzle,h=h,anchor=TOP,$fn=16);
            fwd(0.35) cyl(d=nozzle*2,h=h,anchor=TOP,$fn=16);
        }
    }
}
servo_gear_socket();

module extruder_mount() {
    color("#844") render() difference() {
        right(42/2+20) {
            left(2) 
            cuboid([42+18,42,2],chamfer=2,edges=[LEFT+FWD,LEFT+BACK],
                    anchor=BOT+RIGHT);
            cuboid([5,42,12],chamfer=2,edges=[RIGHT+TOP,RIGHT+BOT],
                    anchor=RIGHT+BOT);
        }
        nema_mount_mask(size=17,depth=5,l=0,$slop=0.2);
        right(42/2+20+ep) 
        up(7) {
            fwd(42/2-15) zrot(90) teardrop(d=4+$slop,l=5+ep*2,anchor=FWD);
            yflip_copy() back(15) {
                right(5) screw_hole("M3",l=11,head="socket",atype="head",
                                    $slop=0,tolerance="tight",
                                    orient=RIGHT,anchor=BOT);
                zrot(90) teardrop(d=3+$slop,l=5+ep*2,anchor=FWD);
                left(2.5) nut_trap_inline(3,"M3",orient=LEFT);
            }
        }
    }
    right(42/2+20+$slop) children();
}
//!extruder_mount(); // print

module cutter_pos() {

}

module cutter_pattern() {
    xcyl(d=3,h=2);
    xrot(6) hull() {
        fwd(55) xcyl(d=15,h=8);
        fwd(14) xcyl(d=15,h=8);
    }
    back(27) xcyl(d=3,h=2);
    xrot(16) back(13) xcyl(d=3,h=2);
    up(6.5) back(47) xcyl(d=8,h=2); // pivot
    %color("red") up(6) back(65) xcyl(d=1,h=2); // cutter
}
// !cutter_pattern();

module cutter(a=40) {
    %up(6.5) back(47) {
        right(2) xrot(a) down(6.5) fwd(47) cutter_pattern();
        xrot(-5) zflip() down(6.5) fwd(47) cutter_pattern();
    }
}

module screw_with_nut(a=0,l=11,counterbore=undef) {
    screw_hole("M3",l=l,head="socket",atype="head",orient=RIGHT,anchor=BOT,$slop=0,tolerance="tight",counterbore=counterbore);
    xrot(a) {
        left((l-5)+ep) nut_trap_inline(3,"M3",orient=LEFT);
        // zrot(90) teardrop(d=4+$slop,l=11+ep*2,anchor=FWD);
    }
}

module screw_with_nut2(a=0,l=11,counterbore=undef) {
    screw_hole("M3",l=l+2,head="socket",atype="head",orient=RIGHT,anchor=BOT,$slop=0,tolerance="tight",counterbore=counterbore);
    xrot(a) {
        left((l-5)+ep) nut_trap_side(10,"M3",orient=LEFT);
    }
}

module cutter_mount() {
    color("#488") 
    difference() {
        union() {
            cuboid([5,42,12],anchor=LEFT+BOT,chamfer=-2,edges=[LEFT+TOP,LEFT+BOT]);
            fwd(42/2) left(2) {
                cuboid([7,72,20],anchor=LEFT+TOP+FWD,chamfer=6,edges=[TOP+BACK]);
                down(20)
                    cuboid([7,72,19],anchor=LEFT+TOP+FWD,chamfer=2,edges=[BOT+RIGHT,BOT+LEFT]);
            }
        }
        up(7) left(ep) {
            fwd(42/2-15) zrot(90) teardrop(d=4+$slop,l=5+ep*2,anchor=BACK);
            back(15) {
                right(1+ep) screw_hole("M3",l=11,head="socket",atype="head",
                                    $slop=0,tolerance="tight",counterbore=4,
                                    orient=RIGHT,anchor=BOT);
                zrot(90) teardrop(d=3+$slop,l=5+ep*2,anchor=BACK);
                left(2.5) nut_trap_inline(3,"M3",orient=LEFT);
            }
            yflip() back(15) {
                right(2+ep) screw_hole("M3",l=11,head="socket",atype="head",
                                    $slop=0,tolerance="tight",counterbore=4,
                                    orient=RIGHT,anchor=BOT);
                zrot(90) teardrop(d=3+$slop,l=5+ep*2,anchor=BACK);
                left(2.5) nut_trap_inline(3,"M3",orient=LEFT);
            }
        }
        up(7) right(7) fwd(42/2-15)
        back(0.125) up(1.5) xrot(172) down(6) fwd(65) 
        up(6.5) back(47) xrot(-5) zflip() down(6.5) fwd(47) {
            back(27) left(6) zrot(180) screw_with_nut(-13);
            xrot(16) back(13) left(6) zrot(180) screw_with_nut(-13-16);
            up(6.5) back(47) xcyl(d=9,h=6); 
        }
        fwd(42/2) back(72/2) right(8.925) down(35.7-3) 
            fwd(20) ycopies(n=2,l=20) xrot(180) screw_with_nut2();
        fwd(42/2) back(72/2) right(2) down(35.7-3) 
            back(20) ycopies(n=2,l=20) xrot(180) screw_with_nut2();
    }
    up(7) right(6) fwd(42/2-15){
        %xcyl(d=2,h=1); // Wire
        back(0.125) up(1.5) xrot(172) down(6) fwd(65)
        cutter(12);
    }
}
// !yrot(90) cutter_mount(); // print

module servo_mount() {
    y=61.5;
    x=7.6;
    color("#848") left(7) diff() {
        right(52) down(55/2-ep) left(5.8-9)
        {
            back(50-1.5) cuboid([2,y+8,11.5],chamfer=-2,edges=[LEFT+BOT],anchor=RIGHT+BACK+TOP);
            left(2) back(50-1.5-(y+11)) {
                cuboid([63+$slop,99-$slop,11.5],rounding=3,edges="Z",anchor=LEFT+FWD+TOP)
                    attach(RIGHT) down(7) back(6) right(25)
                        zcopies(n=2,l=5.5)
                        xcopies(n=8,l=40)
                        xrot(-90) screw_hole("M3",l=15,head="socket",atype="head",anchor=BOT,$slop=0,tolerance="tight");
                down(11.5) {
                    fwd(6) cuboid([63+$slop,48.5-$slop,3],rounding=3,edges="Z",anchor=LEFT+FWD+BOT);
                    fwd(1.6) {
                        cuboid([63+$slop,48.5+3.2-$slop,20.5],rounding=3,edges="Z",anchor=LEFT+FWD+BOT)
                        attach(FWD) {
                            cyl(d=7,h=2,anchor=BOT);
                            up(3) screw_hole("M3",l=15,head="socket",atype="head",anchor=BOT,$slop=0,tolerance="tight");
                        }
                    }
                }
            }
        }
        down(39) right(71.8) back(y-10.25+ep) fwd(13.1) {
            zz=11.5;
            xx=4.0;
            up(zz) right(xx+7.4)
            cuboid([8.5+9.5+xx,23.5+10,62-zz],anchor=RIGHT+FWD+BOT,rounding=12,edges=[TOP+FWD]);
            left(18.6) {
                cuboid([5,13.04-$slop,2],anchor=LEFT+FWD+BOT,chamfer=-2,edges=[LEFT+BOT]);
                cuboid([7,23.5,11.5],anchor=LEFT+FWD+BOT,chamfer=2,edges=[BACK+TOP]);
            }
        }
        down(37) right(71.8+5) back(y+ep+13.35)
            up(58/2) zflip_copy() up(58/2-4.35+0.5)
                left(1.5+3) xflip_copy() left(9.5-2.5) zrot(90) screw_with_nut2();
        tag("remove") {
            right(71.8+55) down(39) cuboid([15,17,10],anchor=BOT+RIGHT);
            down(39+ep) right(71.8+10.4+1+$slop) back(y+10.15) 
                cuboid([22+$slop*2,3+$slop*2,62+ep*2],anchor=RIGHT+FWD+BOT,chamfer=-2-$slop,edges=[FWD+TOP,FWD+BOT]);
            fwd(20) fwd(1.15+$slop) right(67.85-$slop) down(55/2-ep-3-30) left(5.8-9) {
                cuboid([42.5+$slop*2,42.5+$slop*2,50],chamfer=2,edges="Z",anchor=LEFT+FWD+TOP);
            }
            down(8) right(71.8+1.5) back(y) zrot(270) xrot(90)  {
                big_servo_neg(mg995_params);
            }
            fwd(42/2) back(72/2) right(42/2+20+8) down(35.7-3) 
                back(20) ycopies(n=2,l=20) zrot(180) xrot(180) screw_with_nut2();
            fwd(42/2) back(72/2) right(42/2+20+1.1) down(35.7-3) 
                fwd(20) ycopies(n=2,l=20) zrot(180) xrot(180) screw_with_nut2();
            // fwd(42/2) back(72/2) right(42/2+20+$slop+7+7) down(35.7-3) 
            //     ycopies(n=4, l=60) screw_with_nut(counterbore=20);
        }
    }
    down(8) right(71.8-7+1.5) back(y) zrot(270) xrot(90) children(0);
    children(1);
}
// !xflip() servo_mount(); // print

module servo_mount_cap() {
    y=61.5;
    color("#484")
    difference() {
        down(39) right(71.8+4.4) back(y+10.15+$slop) 
            cuboid([22,3,62],anchor=RIGHT+FWD+BOT,chamfer=-2,edges=[FWD+TOP,FWD+BOT]);
        left(7)
        down(37) right(71.8+5) back(y+ep+13.35)
            up(58/2) zflip_copy() up(58/2-4.35+0.5)
                left(1.5+3) xflip_copy() left(9.5-2) zrot(90) screw_with_nut2();
    }
}
// !xrot(-90) servo_mount_cap(); // print

module servo_gear() {
    down(3) color("#448") difference() {
        spur_gear(
            mod=1,teeth=14,thickness=5,
            helical=-30,herringbone=true,slices=5,
            spin=31,
            anchor=BOT
        );
        up(3.5-ep) servo_gear_socket();
        cyl(d=3,h=15);
    }
}
// !xrot(180) servo_gear();// print

module cutter_gear() {
    color("#AA4")
    right(39) up(7)
    xflip()
    fwd(42/2-15)
    back(0.125) up(1.5) xrot(172) down(6) fwd(65) 
    up(6.5) back(47) xrot(2) {
        difference() {
            union() {
                difference() {
                    spur_gear(
                        mod=1,teeth=73,thickness=5,shaft_diam=5,
                        hide=66,spin=190,
                        helical=-30,herringbone=true,slices=5,
                        orient=RIGHT,anchor=BOT
                    );
                    left(ep) xcyl(d=50,h=10+ep*2,anchor=LEFT);
                }
                fwd(40) down(7) 
                xrot(8) cuboid([5,25,10],anchor=FWD+TOP+LEFT,
                    rounding=5,edges=[BOT+FWD,BACK+TOP,BACK+BOT]);
                xrot(10) down(6.5) fwd(47) hull() {
                    back(27) xcyl(d=6,l=9.2,anchor=RIGHT);
                    xrot(16) back(13) xcyl(d=6,l=9.2,anchor=RIGHT);
                }
            }
            right(2) xrot(10) down(6.5) fwd(47) {
                back(27) screw_hole("M3",l=15,head="socket",atype="head",orient=RIGHT,anchor=BOT,$slop=0,tolerance="tight");
                xrot(16) back(13) screw_hole("M3",l=15,head="socket",atype="head",orient=RIGHT,anchor=BOT,$slop=0,tolerance="tight");
            }
        }
    }
}
// !yrot(-90) cutter_gear(); // print

nema_stepper_motor(size=17, h=39, shaft_len=30);
extruder_mount() cutter_mount();
cutter_gear();
right(85.4-$slop) xflip() servo_mount() {
    big_servo(mg995_params) up(1.5) servo_gear();
    servo_mount_cap();
}
right(11) fwd(28) down(36) {
    color("#8c8") cuboid([70,1.6,31],anchor=BOT+BACK);
    %cuboid([70,2.5,31],anchor=BOT+FWD);
}
// !yrot(cos($t*360)*90-90) zrot($t*360) servo_gear();

echo(str("\n",
"sh ./do_mp4.sh WireHandler.scad ",
$vpt[0],",",$vpt[1],",",$vpt[2],",",
$vpr[0],",",$vpr[1],",",$vpr[2],",",
$vpd,
"\n"));