include <../../lib/globals.scad>
include <BOSL2/std.scad>
include <BOSL2/screws.scad>
include <BOSL2/gears.scad>
include <BOSL2/ball_bearings.scad>
include <BOSL2/rounding.scad>
include <../../lib/as5600.scad>

$fn=0;$fa=1;$fs=$preview?0.5:0.25;ep=0.01;$slop=0.2;
_6007ZZ=ball_bearing_info("6007ZZ");
_688ZZ=[8,16,5,true,false,0,0]; // ID, OD, width, shielded, flanged, flange OD, flange width
wall=2;
motor_recess=0.8;
horn_recess=2.5;

// https://en.robotis.com/data/item/explain/1893207946_3f718e6b_xl330.png
// Horn face at the origin, shaft along +Z, case extending toward -Y and -Z.
// Idler anchor follows the rear mounting face (case or disk), pointing along -Z.
// drive rotates the disks and their attachment frames about +Z, in degrees.
// horn=false removes the stock horn and its screw, retaining the "horn" mounting frame.
// Undimensioned recesses, seams and screw pilot depths are approximate.
module xl330(anchor="horn",spin=0,orient=UP,idler_disk=false,drive=0,simple=false,horn=true) {
    size=[20,34,23];
    screws=[[-8.4,4.5],[8.4,4.5],[-8.4,-19.5],[5,-22.5]];
    anchors=[
        named_anchor("horn",[0,0,0],UP,drive),
        named_anchor("idler",[0,0,idler_disk?-29:-26],DOWN,idler_disk?-drive:0)
    ];
    attachable(anchor,spin,orient,size=size,cp=[0,-7.5,-14.5],anchors=anchors) {
        if (simple) {
            color("#333") difference() {
                fwd(7.5) down(3) cuboid(size,anchor=TOP);
                if (!horn) down(3-ep) {
                    cyl(d=8,h=3+ep,anchor=TOP);
                    cyl(d=2.64,h=7+ep,anchor=TOP);
                }
            }
            color("#444") zrot(drive) {
                if (horn) cyl(d=16,h=3,anchor=TOP);
                if (idler_disk) down(26) cyl(d=16,h=3,anchor=TOP);
            }
        } else union() {
            color("#333") difference() {
                fwd(7.5) down(3) cuboid(size,chamfer=0.8,edges="Z",anchor=TOP);
                if (!horn) down(3-ep) {
                    cyl(d=8,h=3+ep,anchor=TOP);
                    cyl(d=2.64,h=7+ep,anchor=TOP);
                }

                // 16 x 30 mounting pattern; stepped entries from drawing details A/B.
                fwd(7.5) grid_copies([16,30],n=2) {
                    down(3-ep) cyl(d=1.6,h=8+ep,anchor=TOP);
                    down(3-ep) cyl(d=2,h=3.5+ep,anchor=TOP);
                    down(26+ep) cyl(d=1.6,h=8+ep,anchor=BOT);
                    down(26+ep) cyl(d=2,h=4.5+ep,anchor=BOT);
                }

                fwd(7.5) zcopies([-7,-21]) difference() {
                    cuboid([size.x+ep*2,size.y+ep*2,0.2]);
                    cuboid([size.x-0.5,size.y-0.5,0.2+ep*2],chamfer=0.8,edges="Z");
                }

                xflip_copy() right(10+ep) fwd(9) down(26+ep)
                    cuboid([4+ep,10.4,9.2+ep],anchor=RIGHT+BOT);

                // Rear idler seat.
                down(26+ep) {
                    cyl(d=14,h=0.4+ep,anchor=BOT);
                    cyl(d=10,h=0.9+ep,anchor=BOT);
                    cyl(d=7,h=1.4+ep,anchor=BOT);
                    cyl(d=2.6,h=4+ep,anchor=BOT);
                }

                for (p=screws) move([p.x,p.y,-3+ep])
                    cyl(d=3.4,h=1.6+ep,anchor=TOP);
                fwd(15.5) down(3-ep)
                    cuboid([13.4,5.8,0.2+ep],rounding=0.5,edges="Z",anchor=TOP);
                back(8.5) down(26+ep) cuboid([5.2,2,0.6+ep],anchor=BOT);
            }

            zrot(drive) {
                if (horn) color("#444") difference() {
                    cyl(d=16,h=3+ep,chamfer=0.15,anchor=TOP);
                    up(ep) zrot_copies(n=4) right(6)
                        cyl(d=1.6,h=3+ep*2,anchor=TOP); // PCD 12, M2 tapping screws
                    up(ep) cyl(d=4.2,h=1.8+ep,anchor=TOP);
                    up(ep) cyl(d=2+$slop,h=3+ep*2,anchor=TOP);
                }
                if (horn) color("#888") down(0.3)
                    screw("M2",l=4,head="pan",drive="phillips",thread=false,anchor="head_top");

                if (idler_disk) color("#444") down(29) xrot(180) difference() {
                    cyl(d=16,h=3+ep,chamfer=0.15,anchor=TOP);
                    up(ep) zrot_copies(n=4) right(6)
                        cyl(d=1.6,h=3+ep*2,anchor=TOP); // PCD 12, M2 tapping screws
                    up(ep) cyl(d=6,h=3+ep*2,anchor=TOP); // idler cap opening
                }
            }

            color("#777") for (p=screws) move([p.x,p.y,-3.2]) difference() {
                screw("M1.6",l=4,head="pan",thread=false,anchor="head_top");
                up(ep) cuboid([2,0.4,0.7+ep],anchor=TOP);
                up(ep) cuboid([0.4,2,0.7+ep],anchor=TOP);
            }

            // JST B3B-EH-A headers: mating direction -Z, open sides facing outward.
            // https://www.jst-mfg.com/product/pdf/eng/eEH.pdf
            // Guide-tab and wall details are approximate.
            xflip_copy() right(9.8) fwd(9) down(26-9.2) {
                color("#ddd") difference() {
                    cuboid([3.8,10,6],anchor=RIGHT+TOP);
                    down(6+ep) left(0.6)
                        cuboid([2.6,8.8,4.2+ep],anchor=RIGHT+BOT);
                    down(6+ep) right(ep)
                        cuboid([0.6+ep*2,7,4.2+ep],anchor=RIGHT+BOT);
                }
                color("#bbb") left(2.2) down(1.8-ep) ycopies(2.5,n=3)
                    cuboid([0.64,0.64,3.3+ep],anchor=TOP);
            }

            color("#aaa") fwd(15.5) down(3.05)
                cuboid([13.2,5.6,0.15+ep],rounding=0.4,edges="Z",anchor=TOP);
            color("#a43") back(8.5) down(25.9) cuboid([5,1.8,0.5+ep],anchor=BOT);
        }
        children();
    }
}

// !xl330();

// Corvid's tested micro_servo_horn() insert, registered to the stock horn face.
module base_motor_gear(anchor="horn",spin=0,orient=UP) {
    anchors=[
        named_anchor("horn",[0,0,0]),
        named_anchor("screw",[0,0,-1.65])
    ];
    attachable(anchor,spin,orient,d=14,l=10,cp=[0,0,5],anchors=anchors) {
        color("#6ba") difference() {
            union() {
                down(2.9) intersection() {
                    xrot(90) import("../corvid/xl330-horn.stl",convexity=10);
                    up(1.25) cyl(d=8,h=4,anchor=TOP);
                }
                down(2.4) cyl(d=9.7,h=2.4+ep,chamfer1=1,anchor=BOT);
                spur_gear(mod=1,teeth=14,thickness=10,anchor=BOT);
            }
            down(1.65) {
                cyl(d=2.64,h=4+ep,anchor=TOP);
                cuboid([1.45,2.1,4+ep],rounding=0.2,edges="Z",anchor=TOP+BACK);
                cyl(d=6,h=11.65+ep,anchor=BOT);
            }
        }
        children();
    }
}
// !xrot(180) base_motor_gear(anchor=TOP); // print

module base(anchor,orient,spin) {
    d=_6007ZZ[1]+wall*2;
    l=5+_6007ZZ[2]+wall*3;
    anchors=[
        named_anchor("motor",rot=back(43+$slop)*up(10.5+wall),flip=true)
    ];
    attachable(anchor,orient,spin,d=d,l=l,anchors=anchors) {
        color("#ccc") diff() {
            down(l/2) {
                tag("remove") left(1.5) cuboid([10,100,8],anchor=FWD+BOT);
                cuboid([34+wall*2,43+10+$slop+wall,23+wall],anchor=FWD+BOT);
                up(wall) tag("remove") back(43) cuboid([34+$slop*2,20+$slop*2,23+$slop*2],anchor=BOT);
            }
            cyl(d=d,l=l)
            attach(TOP,TOP,inside=true) tag("remove") cyl(d=d-wall*2+$slop,l=_6007ZZ[2]+$slop);
            attach(TOP,TOP,inside=true) tag("remove") cyl(d=_6007ZZ[1]-8,l=l);
        }
        children();
    }
}
module base_cap(anchor,orient,spin) {
    d=_6007ZZ[1]+wall*6;
    l=5+_6007ZZ[2]+wall*5;
    attachable(anchor,orient,spin) {
        color("#ddd") diff() {
            up(wall*2) {
                cyl(d=d,l=l-wall*2,rounding1=-2,anchor=TOP);
                down(l) cyl(d=d+20,l=wall*2,anchor=BOT);
            }
            down(l-wall*2) {
                tag("remove") left(1.5) cuboid([10,100,8],anchor=FWD+BOT);
                cuboid([34+wall*4,43+10+$slop+wall*2,23+wall*2],rounding=1,except=BOT,anchor=FWD+BOT);
                tag("remove") {
                    cuboid([34+wall*2+$slop*2,43+10+$slop+wall+$slop,23+wall+$slop],anchor=FWD+BOT);
                    up(wall) back(43) cuboid([34+$slop*2,20+$slop*2,23+$slop],anchor=BOT);
                    back(43+$slop) right(34/2-9.5) cyl(d=16+wall,h=30,anchor=BOT);
                }
            }
            up($slop) tag("remove") {
                cyl(d=d-wall*4+$slop*2,l=l-wall*2+$slop+ep,anchor=TOP);
                up(wall*2) cyl(d=d-wall*6-8+$slop*2,l=l-wall*2+$slop+ep,anchor=TOP);
            }
        }
        children();
    }
}

module l1(pose,anchor,orient,spin) {
    z=14;
    anchors=[
        named_anchor("j1",rot=up(wall+z+_6007ZZ[1]/2)*yrot(90)*zrot(pose[1])),
        named_anchor("motor",rot=back(43.2)*right(25)*left(10.5)*up(29.5)*zrot(270)*xrot(-90)),
        named_anchor("motor_mount",[0,43.2,52])
    ];
    attachable(anchor,orient,spin,anchors=anchors) {
        color("#6ba") difference() {
            diff() {
                up($slop) {
                    up(z-2-$slop) {
                        hull() {
                            up(_6007ZZ[1]/2+wall*2) xcyl(d=_6007ZZ[1]+wall*3.5,l=23+wall*2);
                            back(wall*0.25) cuboid([23+wall*2,_6007ZZ[1]+wall*1.5,_6007ZZ[1]/2+wall*2],anchor=BOT);
                        }
                        up(1) back(_6007ZZ[1]/2+wall)
                            cuboid([23+wall*2,20,34+7+wall],anchor=BOT+FWD,chamfer=20,edges=[BACK+BOT]);
                        tag("remove") {
                            up(_6007ZZ[1]/2+wall+2) {
                                xcyl(d=_6007ZZ[1]+$slop*2,l=_6007ZZ[2]+$slop*2);
                                xcyl(d=_6007ZZ[1]-8,l=27);
                                cuboid([_6007ZZ[2]+$slop*2,_6007ZZ[1]+$slop*2,_6007ZZ[1]/2+wall*2+ep],anchor=TOP);
                            }
                        }
                    }
                }
                up(5) spur_gear(mod=1,teeth=73,spin=3.1,thickness=8,anchor=BOT);
                tag("remove") back(43.2) right(25) left(10.5) up(20) {
                    left(29/2) down($slop) cuboid([23+$slop*2,20+$slop*2,34+$slop*2],anchor=BOT);
                    up(9.5) {
                        xcyl(d=18,l=3,anchor=RIGHT);
                        cuboid([3,10,18],anchor=RIGHT+FWD);
                    }
                }
            }
            difference() {
                cyl(d=_6007ZZ[0]+12+$slop,l=5+3+$slop,chamfer2=2,anchor=BOT);
                up(5+$slop) cyl(d=_6007ZZ[0]+3-$slop,l=3,chamfer2=-2,anchor=BOT);
            }
            up(10.8) xflip_copy() right(13) screw_hole("M4",l=25,head="button",atype="head",counterbore=3+z,orient=TOP,anchor=BOT,$slop=0.1) 
                attach(BOT) up(20) nut_trap_side(10,"M4",spin=180);
            position("motor_mount") ycopies(16) {
                xcyl(d=2+$slop*2,l=23+wall*2+ep*2);
                xflip_copy() right(23/2+wall+ep)
                    xcyl(d=4+$slop*2,l=motor_recess+ep,anchor=RIGHT);
            }
        }
        children();
    }
}

module l1_motor_gear(anchor=BOT,spin=0,orient=UP) {
    attachable(anchor,spin,orient,d=28,l=5.5,cp=[0,0,2.75]) {
        color("#ddd") difference() {
            spur_gear(mod=1,teeth=28,spin=3,thickness=5.5,orient=DOWN,anchor=TOP);
            zrot_copies(n=4) right(6) {
                down(ep) cyl(d=2+$slop*2,l=5.5+ep*2,anchor=BOT);
                up(5.5-horn_recess) cyl(d=4+$slop*2,l=horn_recess+ep,anchor=BOT);
            }
        }
        children();
    }
}
// !l1_motor_gear(); // print

module l1_bushing() {
    color("#ddd") diff() {
        up($slop) {
            difference() {
                cyl(d=_6007ZZ[0]+12,l=5+3-$slop,chamfer2=2,anchor=BOT);
                up(5-$slop) cyl(d=_6007ZZ[0]+3,l=3,chamfer2=-2,anchor=BOT);
            }
            up(5-$slop) difference() {
                cuboid([_6007ZZ[2],_6007ZZ[1],_6007ZZ[1]/2+wall*2+ep-8],anchor=TOP);
                up(wall*2-$slop) xcyl(d=_6007ZZ[1]+$slop*2,l=_6007ZZ[2]+wall*2);
            }
            down(_6007ZZ[2]/2) cyl(d=_6007ZZ[0]-$slop,h=_6007ZZ[2]/2); 
        }
        up(10.8) xflip_copy() right(13) screw_hole("M4",l=25,head="button",atype="head",counterbore=10,orient=TOP,anchor=BOT,$slop=0.1) 
            attach(BOT) up(20) nut_trap_side(10,"M4",spin=180);
    }
}

module l1_bot() {
    diff() {
        down(_6007ZZ[2]+$slop) {
            cyl(d=_6007ZZ[0]-$slop,h=_6007ZZ[2]/2+$slop); 
            down(wall) cyl(d=_6007ZZ[0]+8,h=wall); 
        }
        up(10.8) xflip_copy() right(13) screw_hole("M4",l=25,head="button",atype="head",counterbore=10,orient=TOP,anchor=BOT,$slop=0.1) 
            attach(BOT) up(20) nut_trap_side(10,"M4",spin=180);
    }
}

module l2(anchor,orient,spin) {
    x=60;
    zz=_6007ZZ[2]/2;
    h=zz+$slop/2+wall*2+3.4+5.5;
    anchors=[
        named_anchor("motor",rot=left(x)*up(23/2+3)*zrot(180)),
        named_anchor("horn_mount",[-x,0,h]),
        named_anchor("tie_bolts",[0,0,h])
    ];
    attachable(anchor,orient,spin,anchors=anchors) {
        color("#ddd") diff() {
            // The hub halves meet at Z=0 to preserve the arm spacing when clamped.
            cyl(d=_6007ZZ[0]-$slop,l=zz+$slop/2,anchor=BOT);
            up(zz+$slop/2) {
                cyl(d=_6007ZZ[0]+16,l=wall*2+3.4,anchor=BOT);
                up(wall*2+3.4) {
                    hull() {
                        zrot(146) pie_slice(r=33.501,h=5.5,ang=154.5,anchor=BOT);
                        left(x) cyl(d=18,l=5.5,anchor=BOT);
                    }
                    tag("remove") left(34.2) back(31.5) zrot(-108) pie_slice(d=30,l=8,ang=45,anchor=BOT);
                    spur_gear(mod=1,teeth=65,thickness=5.5,anchor=BOT,spin=55.53,hide=27);
                }
            }
            tag("remove") position("horn_mount") {
                zrot_copies(n=4) right(6) {
                    up(ep) cyl(d=2+$slop*2,l=5.5+ep*2,anchor=TOP);
                    up(ep) cyl(d=4+$slop*2,l=horn_recess+ep,anchor=TOP);
                }
            }
            tag("remove") position("tie_bolts") xcopies(20) {
                up(ep) cyl(d=4+$slop*2,l=h+ep*2,anchor=TOP);
                up(ep) cyl(d=7.6+$slop*2,l=6+ep,anchor=TOP);
            }
        }
        children();
    }
}

module l2_cap(anchor,orient,spin) {
    x=60;
    zz=_6007ZZ[2]/2;
    h=zz+$slop/2+wall*2+3.4+5.5;
    anchors=[
        named_anchor("idler_mount",[x,0,h]),
        named_anchor("tie_bolts",[0,0,h])
    ];
    attachable(anchor,orient,spin,anchors=anchors) {
        color("#ddd") diff() {
            cyl(d=_6007ZZ[0]-$slop,l=zz+$slop/2,anchor=BOT);
            up(zz+$slop/2) {
                cyl(d=_6007ZZ[0]+16,l=wall*2+3.4,anchor=BOT);
                up(wall*2+3.4) {
                    hull() {
                        cyl(r=33.501,h=5.5,anchor=BOT);
                        right(x) cyl(d=18,l=5.5,anchor=BOT);
                    }
                }
            }
            tag("remove") position("idler_mount") {
                zrot_copies(n=4) right(6) {
                    up(ep) cyl(d=2+$slop*2,l=5.5+ep*2,anchor=TOP);
                    up(ep) cyl(d=4+$slop*2,l=horn_recess+ep,anchor=TOP);
                }
            }
            tag("remove") position("tie_bolts") xcopies(20) {
                up(ep) cyl(d=4+$slop*2,l=h+ep*2,anchor=TOP);
                up(ep) nut_trap_inline(8+ep,"M4",anchor=TOP);
            }
        }
        children();
    }
}

module l3(anchor,orient,spin,l=0) {
    anchors=[
        named_anchor("motor",rot=right(7.5)*up(26+wall*2+l)),
        named_anchor("motor_mount",[-15,0,-10]),
        named_anchor("upper_motor_mount",[0,0,wall])
    ];
    attachable(anchor,orient,spin,anchors=anchors) {
        color("#6ba") diff() {
            up(wall*2+l) cuboid([34+wall*2,23+wall*2,wall*2+20+l],chamfer=wall,edges=[TOP],anchor=TOP);
            tag("remove") {
                up($slop) cuboid([34+$slop*2,23+$slop*2,20+$slop*2],anchor=TOP);
                down(10) right(7.5) {
                    ycyl(d=18,l=29);
                    yrot(40) cuboid([18,29,28],anchor=TOP);
                }
                position("motor_mount") zcopies(16) {
                    ycyl(d=2+$slop*2,l=23+wall*2+ep*2);
                    yflip_copy() back(23/2+wall+ep)
                        ycyl(d=4+$slop*2,l=motor_recess+ep,anchor=BACK);
                }
                position("upper_motor_mount") grid_copies([30,16],n=2) {
                    down(wall-$slop+ep) cyl(d=2+$slop*2,l=wall*2+l-$slop+ep*2,anchor=BOT);
                    cyl(d=4+$slop*2,l=wall-$slop+ep,anchor=TOP);
                }
            }
        }
        children();
    }
}

mod=1.028;
t1=12;
t2=12;
t3=12;
face_width=4;

// shaft_l sets the two 9 mm shafts; servo_mount_l sets the upper 11 mm servo mount.
module wrist(anchor,orient,spin,shaft_l=28,servo_mount_l=10) {
    attachable(anchor,orient,spin) {
        zrot(45) l4() {
            // Install before the two wrist motors; 3 mm engagement in the horn.
            position("horn_mount") zrot(-45) zrot_copies(n=4) right(6)
                color("#888") screw("M2",l=6,head="pan",drive="phillips",thread=false,
                    atype="head",anchor=BOT);
            position("wrist") {
                zrot(-45) up(shaft_l+33.14+$slop) {
                    wrist_pin2() {
                        %color("#888") screw("M3,14",head="socket",atype="head",drive="hex",orient=TOP)
                            attach(BOT) up(9.9) nut("M3",thickness=4,bevel=true);
                    }
                    xflip_copy() wrist_pin3();
                }
                right(2.6) fwd($slop/2) xl330(spin=270,anchor=BOT+LEFT)
                    attach("horn") up($slop) wrist_pin(shaft_l) {
                        wrist_pivot() {
                            wrist2(servo_mount_l) xl330(spin=90,idler_disk=true,drive=-grip) gripper();
                        }
                        %color("#888") screw("M3,14",head="socket",atype="head",drive="hex")
                            attach(BOT) up(9.8) nut("M3",thickness=4,bevel=true,spin=-15);
                        zrot_copies(n=4) right(6)
                            color("#888") screw("M2",l=6,head="pan",drive="phillips",thread=false,
                                atype="head",anchor=BOT);
                    }
                left(2.6) back($slop/2) xl330(spin=90,anchor=BOT+LEFT)
                    attach("horn") up($slop) wrist_pin(shaft_l) {
                        wrist_pivot();
                        %color("#888") screw("M3,14",head="socket",atype="head",drive="hex")
                            attach(BOT) up(9.8) nut("M3",thickness=4,bevel=true,spin=-15);
                        zrot_copies(n=4) right(6)
                            color("#888") screw("M2",l=6,head="pan",drive="phillips",thread=false,
                                atype="head",anchor=BOT);
                    }
            }
        }
        children();
    }
}

module wrist_pin2() {
    tag_scope("wrist_pin2") color_this("#ccc") diff() {
        xcyl(d=5-$slop,l=14.3-$slop);
        xcyl(d=5.5,l=8,chamfer=0.5);
        up(0.5) cyl(d=5.5,l=6.7-$slop*2);
        down(3) screw_hole("M3",l=14,head="socket",atype="head",orient=BOT,anchor=BOT,$slop=0.1);
    }
    up(8.6) children(0); // screw
}

module wrist_pin3() {
    color_this("#ccc") diff() right(7.15+$slop/2) {
        x=3.406;
        xcyl(d=5-$slop,l=x,anchor=LEFT);
        right(x) {
            xcyl(d=7.5-$slop*2,h=7.25,chamfer=0.7+$slop,anchor=LEFT);
            up(3.55+$slop) right(7.25/2) screw_hole("M3",l=14,head="socket",atype="head",orient=TOP,anchor=BOT,$slop=0.1);
        }
    }
}

// The flange reaches the horn at -$slop, preserving the gear height.
module wrist_pin(shaft_l=28) {
    head_r=2+$slop;
    diff() {
        color_this("#ccc") down($slop) cyl(d=18,h=3,anchor=BOT);
        color_this("#ccc") up(wall/2) cyl(d=5.8,h=shaft_l+wall+0.4,anchor=BOT);
        color_this("#ccc") cyl(d=9,h=shaft_l,chamfer2=-0.8,anchor=BOT)
        attach(TOP) color_this("#ccc")
            bevel_gear(mod=mod,teeth=t1,mate_teeth=t2,anchor=BOT,spiral=0,cutter_radius=0,face_width=face_width) {
                if ($children>0) attach_gear(45+180) children(0); // wrist_pivot
                if ($children>1) attach(BOT,BOT) down(1) tag("keep") children(1); // m3 screw
                attach(BOT,BOT) down(1)
                    screw_hole("M3",l=14,head="socket",atype="head",anchor=BOT,$slop=0.1,counterbore=shaft_l+wall);
            }
        tag("remove") zrot_copies(n=4) right(6) {
            down($slop+ep) cyl(d=2+$slop*2,h=3+ep*2,anchor=BOT);
            up(3-$slop+ep) zscale(2)
                cyl(r=head_r,h=0.9+head_r,rounding2=head_r,anchor=BOT);
        }
    }
    if ($children>2) up(3-$slop) children(2); // horn screws
}
// !up($slop) wrist_pin(); // print

module wrist_pivot() {
    tag_scope() diff() {
        color_this("#6ba") bevel_gear(mod=mod,teeth=t2,mate_teeth=t1,spiral=0,cutter_radius=0,face_width=face_width)
        attach(BOT,BOT) color_this("#6ba") bevel_gear(mod=mod,teeth=t2,mate_teeth=t3,spiral=0,cutter_radius=0,face_width=face_width)
        attach_gear(90) {
            tag("remove") cyl(d=5,h=11);
            children();
        }
    }
}

module wrist2(servo_mount_l=10) {
    face_width=4;
    color_this("#6ba") tag_scope() diff() {
        bevel_gear(mod=mod,teeth=t3,mate_teeth=t2,spiral=0,cutter_radius=0,face_width=face_width)
            attach(BOT) color_this("#6ba") cyl(d=11,h=servo_mount_l,anchor=BOT) {
                attach(TOP,BOT) down(servo_mount_l)
                    screw_hole("M3",l=14,head="socket",atype="head",anchor=BOT,$slop=0.1,counterbore=servo_mount_l+0.2);
                position(TOP) color_this("#6ba") wrist_bracket();
                attach(TOP,FWD) up($slop) children(0); // servo
            }
    }
}
// !wrist2(16); // print

// U-bracket for the gripper motor, printed as part of wrist2.
// Seat at the origin, flush with the shaft end; arms on ±X at the motor's lower 16 x 30 holes.
module wrist_bracket() {
    x=23/2+$slop;
    difference() {
        union() {
            cuboid([x*2+wall*2,22.4,wall],anchor=TOP);
            xflip_copy() right(x)
                cuboid([wall,22.4,7],chamfer=2,edges=[TOP+FWD,TOP+BACK],anchor=LEFT+BOT);
            down(wall) cyl(d1=11,d2=19,h=wall,anchor=TOP);
        }
        up(2+$slop) xflip_copy() ycopies(16) {
            right(x-ep) xcyl(d=2+$slop*2,h=wall+ep*2,anchor=LEFT);
            right(x+wall+ep) xcyl(d=4+$slop*2,h=motor_recess+ep,anchor=RIGHT);
        }
    }
}

finger_l=40; // pivot to pad centre
pad=5;
// The finger gears and the horn gear set where the two finger pivots sit above the horn.
pivot_x=gear_dist(mod=1,teeth1=14,teeth2=14)/2;
pivot_y=sqrt(gear_dist(mod=1.5,teeth1=12,teeth2=12)^2-pivot_x^2);

// Everything the gripper motor carries, as children of its xl330(drive=-grip):
// closed at horn zero, opening turns the horn negative.
module gripper() {
    // PHS M2x8 TAP: the upper four hold the palm, the lower four the wrist bracket.
    down(14.5) zflip_copy() up(23/2+$slop+wall-motor_recess) fwd(7.5) grid_copies([16,30],n=2)
        color("#888") screw("M2",l=8,head="pan",drive="phillips",thread=false,
            atype="head",anchor=BOT);
    gripper_palm();
    attach("horn") gripper_pinion()
        position(TOP) down(1.5) zrot_copies(n=4) right(6)
            color("#888") screw("M2",l=8,head="pan",drive="phillips",thread=false,
                atype="head",anchor=BOT);
    // PHS M2x6 TAP locks each finger to its shaft.
    move([-pivot_x,pivot_y,-14.5]) zrot(grip) {
        gripper_finger();
        gripper_shaft(drive=true);
        up(6) zrot(150) right(5.5-motor_recess)
            color("#888") screw("M2",l=6,head="pan",drive="phillips",thread=false,
                atype="head",anchor=BOT,orient=RIGHT);
    }
    move([pivot_x,pivot_y,-14.5]) zrot(-grip) {
        gripper_finger(right=true);
        zrot(-120) gripper_shaft();
        up(6) zrot(30) right(5.5-motor_recess)
            color("#888") screw("M2",l=6,head="pan",drive="phillips",thread=false,
                atype="head",anchor=BOT,orient=RIGHT);
    }
}

// Saddle on the top end of the gripper motor, on its upper 16 x 30 holes.
// Horn face at the origin as in xl330(); the fingers pivot at [±pivot_x,pivot_y].
module gripper_palm(anchor="horn",spin=0,orient=UP) {
    w=22.4;
    t=23+$slop*2+wall*2;
    floor_y=9.5+$slop;
    top_y=pivot_y+6.3;
    cheek=[pivot_x*2+12.6,top_y-floor_y];
    anchors=[named_anchor("horn",[0,0,0])];
    attachable(anchor,spin,orient,size=[cheek.x,top_y-4,t],
        cp=[0,top_y/2+2,-14.5],anchors=anchors) {
        color("#ddd") down(14.5) difference() {
            union() {
                back(floor_y) cuboid([w,1.6,t],anchor=FWD);
                zflip_copy() up(t/2) back(floor_y+ep)
                    cuboid([w,floor_y-4,wall],rounding=2,edges=[FWD+LEFT,FWD+RIGHT],anchor=TOP+BACK);
                // Cheeks: 4 in front, the rest behind the 12 wide finger slot.
                back(floor_y) up(t/2)
                    cuboid([cheek.x,cheek.y,4],chamfer=(cheek.x-w)/2,edges="Z",anchor=TOP+FWD);
                back(floor_y) down(t/2)
                    cuboid([cheek.x,cheek.y,t-16-$slop*2],chamfer=(cheek.x-w)/2,edges="Z",anchor=BOT+FWD);
            }
            cyl(d=17,h=t+ep*2); // horn and idler
            back(floor_y-ep) up(t/2-4)
                cuboid([9,1.6+ep*2,12+$slop*2],anchor=FWD+TOP); // lets the sector gears pass
            back(pivot_y) xcopies(pivot_x*2) {
                up(t/2+ep) cyl(d=9+$slop,h=4+ep*2,anchor=TOP);
                down(t/2+ep) cyl(d=7+$slop,h=t-16-$slop*2+ep*2,anchor=BOT);
            }
            zflip_copy() up(t/2+ep) back(7.5) xcopies(16) {
                cyl(d=2+$slop*2,h=wall+ep*2,anchor=TOP);
                cyl(d=4+$slop*2,h=motor_recess+ep,anchor=TOP);
            }
        }
        children();
    }
}
// !xrot(180) gripper_palm(); // print

// Left finger, closed: pivot axis at the origin, pad on the X=pivot_x plane and centred on Z=0.
// right=true mirrors it and turns the sector gear half a tooth so the pair meshes.
module gripper_finger(right=false,anchor="pivot",spin=0,orient=UP) {
    anchors=[named_anchor("pivot",[0,0,0])];
    attachable(anchor,spin,orient,d=11,l=12,cp=[0,0,3.5],anchors=anchors) {
        color("#6ba") xscale(right?-1:1) difference() {
            union() {
                hull() {
                    cyl(d=11,h=pad);
                    move([pivot_x,finger_l])
                        cuboid([3,pad,pad],rounding=1.5,edges=LEFT+BACK,anchor=RIGHT);
                }
                up(3.5) cyl(d=11,h=12);
                up(3.5) zrot(right?180/14:0) intersection() {
                    spur_gear(mod=1,teeth=14,thickness=12,backlash=0.1,gear_spin=-90);
                    zrot(-900/14) pie_slice(r=9,h=12,ang=1080/14,anchor=CENTER);
                }
            }
            up(3.5) cyl(d=(7+$slop/2)/cos(30),h=12+ep*2,$fn=6); // snug on the shaft
            up(6) zrot(150) right(5.5+ep) {
                xcyl(d=2+$slop*2,h=3,anchor=RIGHT);
                xcyl(d=4+$slop*2,h=motor_recess+ep,anchor=RIGHT);
            }
        }
        children();
    }
}
// !gripper_finger(); // print
// !gripper_finger(right=true); // print

// Hex shaft a finger locks onto: same origin as the finger, pushed in from the horn side.
// drive=true adds the sector gear the pinion turns, drawn for the left finger.
module gripper_shaft(drive=false,anchor=CENTER,spin=0,orient=UP) {
    t=23/2+$slop+wall;
    to_horn=atan2(-pivot_y,pivot_x);
    attachable(anchor,spin,orient,d=9,l=t*2) {
        color("#ccc") difference() {
            union() {
                down(t) cyl(d=7-$slop,h=t,anchor=BOT);
                down(2.5) cyl(d=7/cos(30),h=12,$fn=6,anchor=BOT);
                up(9.5) cyl(d=9-$slop,h=drive?11.5:4.2,anchor=BOT);
                // A gap faces the horn when closed; three teeth carry it past 40 degrees.
                if (drive) up(15.1) intersection() {
                    spur_gear(mod=1.5,teeth=12,thickness=5.9,backlash=0.1,
                        gear_spin=to_horn-105,anchor=BOT);
                    zrot(to_horn-60) pie_slice(r=12,h=5.9,ang=90,anchor=BOT);
                }
            }
            up(6) zrot(150) xcyl(d=1.6,h=9);
        }
        children();
    }
}
// !xrot(180) gripper_shaft(drive=true); // print
// !xrot(180) gripper_shaft(); // print

// Horn gear, 1:1 with the drive shaft. A tooth faces the left pivot at drive=0.
module gripper_pinion(anchor=BOT,spin=0,orient=UP) {
    attachable(anchor,spin,orient,d=18,l=6.5,cp=[0,0,3.25]) {
        color("#ccc") difference() {
            union() {
                cyl(d=16,h=0.6+ep,anchor=BOT); // lifts the teeth over the palm screws
                up(0.6) spur_gear(mod=1.5,teeth=12,thickness=5.9,backlash=0.1,
                    gear_spin=atan2(pivot_y,-pivot_x)-90,anchor=BOT);
            }
            zrot_copies(n=4) right(6) {
                down(ep) cyl(d=2+$slop*2,h=6.5+ep*2,anchor=BOT);
                up(5) cyl(d=4+$slop*2,h=1.5+ep,anchor=BOT);
            }
        }
        children();
    }
}
// !xrot(180) gripper_pinion(anchor=TOP); // print

module l4(anchor="horn",spin=0,orient=UP) {
    xy=20*2-0.6;
    floor_z=0.5-3*$slop;
    floor_h=4.8; recess=1.8;
    size=[xy,xy,24.5+$slop-floor_z+floor_h];
    anchors=[
        named_anchor("horn",[0,0,floor_z-floor_h],DOWN),
        named_anchor("horn_mount",[0,0,floor_z-recess]),
        named_anchor("wrist",[0,0,0])
    ];
    attachable(anchor,spin,orient,size=size,
        cp=[0,0,floor_z-floor_h+size.z/2],anchors=anchors) {
        color("#6ba") diff() {
            up(floor_z-floor_h) offset_sweep(
                rect([xy,xy],chamfer=[5-$slop/2,0,5-$slop/2,0]),
                height=size.z,bottom=os_chamfer(height=wall),anchor=BOT);
            tag("remove") zrot_copies(n=2) up(23+$slop) {
                fwd(10) right(2.5) cuboid([34+$slop*2,20+$slop*2,22.5+$slop*4],anchor=TOP);
                fwd(10+$slop/2) right(10+$slop/2) up(3) {
                    z=22.5+$slop*2+3;
                    cyl(d=18,l=z,anchor=TOP);
                    zrot(-45) cuboid([18,18,z],anchor=LEFT+TOP);
                }
            }
            tag("remove") position("horn_mount") zrot(-45) zrot_copies(n=4) right(6) {
                up(recess+ep) cyl(d=2+$slop*2,h=floor_h+ep*2,anchor=TOP);
                down(ep) cyl(d=4+$slop*2,h=recess+ep*2,anchor=BOT);
            }
            tag("remove") up(floor_z+ep) cyl(d=4.2+$slop*2,h=floor_h+ep*2,anchor=TOP);
        }
        children();
    }
}
// !l4(); // print

// xyview(angle=-55,xray=true) 
// zrot(-$t*360)
// xview(true,xray=false)

// pose=[sin($t*360)*60,sin($t*360)*90+25,-sin($t*360)*60+(90-35)];
// pose=[0,115/*-69.25,115*/,-(115-90)/*109*/,0];
pose=[0,45,45,0];
// grip=17.5-17.5*cos($t*360);
grip=15; // finger opening from closed, degrees; 0 to 35 in use

// up(115) zview(true,xray=true) down(115)
// yview()
base(anchor=BOT) {
    attach(TOP) base_cap();
    attach(TOP,BOT) zrot(pose[0]) {
        up(11) xflip_copy() right(13) %color("#999") screw("M4,25",head="button",drive="hex",atype="head")
            attach(BOT) up(20.2) nut("M4",spin=60);
        l1_bushing();
        l1_bot();
        l1(pose) {
            // PHS M2x8 TAP; unthreaded envelopes for the bought screws.
            position("motor_mount") ycopies(16) xflip_copy() right(23/2+wall-motor_recess)
                color("#888") screw("M2",l=8,head="pan",drive="phillips",thread=false,
                    atype="head",anchor=BOT,orient=RIGHT);
            attach("motor") xl330(drive=-(65/28)*pose[1])
                attach("horn") l1_motor_gear()
                    position(TOP) down(horn_recess) zrot_copies(n=4) right(6)
                        color("#888") screw("M2",l=6,head="pan",drive="phillips",thread=false,
                            atype="head",anchor=BOT);
            attach("j1") ball_bearing("6007ZZ");
            attach("j1") l2() {
                position("tie_bolts") down(6) xcopies(20)
                    color("#888") screw("M4",l=30,head="button",drive="hex",thread=false,
                        atype="head",anchor=BOT);
                // PHS M2x6 TAP into the horn and idler; 3 mm engagement.
                position("horn_mount") down(horn_recess) zrot_copies(n=4) right(6)
                    color("#888") screw("M2",l=6,head="pan",drive="phillips",thread=false,
                        atype="head",anchor=BOT);
                attach(BOT,BOT) l2_cap() {
                    position("tie_bolts") down(8) xcopies(20)
                        color("#888") nut("M4",thread=false,anchor=BOT,spin=30);
                    position("idler_mount") down(horn_recess) zrot_copies(n=4) right(6)
                        color("#888") screw("M2",l=6,head="pan",drive="phillips",thread=false,
                            atype="head",anchor=BOT);
                }
                attach("motor") xl330(spin=pose[2],drive=-pose[2],idler_disk=true)
                    attach(RIGHT,BOT) l3() {
                        position("motor_mount") zcopies(16) yflip_copy() back(23/2+wall-motor_recess)
                            color("#888") screw("M2",l=8,head="pan",drive="phillips",thread=false,
                                atype="head",anchor=BOT,orient=BACK);
                        // PHS M2x8 TAP, installed from inside the cradle before the lower motor.
                        position("upper_motor_mount") grid_copies([30,16],n=2)
                            color("#888") screw("M2",l=8,head="pan",drive="phillips",thread=false,
                                atype="head",anchor=BOT,orient=DOWN);
                        attach("motor") xl330(spin=270,drive=pose[3])
                        attach("horn") wrist(shaft_l=9,servo_mount_l=4);
                    }
            }
        }
    }
    attach(TOP,BOT) down(_6007ZZ[2]) ball_bearing("6007ZZ");
    attach("motor",TOP) xl330(orient=TOP,anchor=BOT,spin=90,simple=true,
        horn=false,drive=-(73/14)*pose[0])
        attach("horn") base_motor_gear()
            // Original retaining screw; its head underside is Z=4.9 in the source mesh.
            position("screw") color("#888") down(4.9)
                import("../corvid/xl330/part_10.stl",convexity=10);
}
as5600(pins=false,anchor=BOT);

echo(str("\n",
    "sh ./do_mp4.sh arm00.scad ",
    $vpt[0],",",$vpt[1],",",$vpt[2],",",
    $vpr[0],",",$vpr[1],",",$vpr[2],",",
    $vpd,
    "\n"));
