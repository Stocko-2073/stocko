include <../../lib/globals.scad>
include <BOSL2/std.scad>
include <BOSL2/screws.scad>
include <BOSL2/gears.scad>
include <BOSL2/ball_bearings.scad>
include <../../lib/as5600.scad>

$fn=0;$fa=1;$fs=$preview?0.5:0.25;ep=0.01;$slop=0.2;
_6007ZZ=ball_bearing_info("6007ZZ");
_688ZZ=[8,16,5,true,false,0,0]; // ID, OD, width, shielded, flanged, flange OD, flange width
wall=2;

// https://en.robotis.com/data/item/explain/1893207946_3f718e6b_xl330.png
// Horn face at the origin, shaft along +Z, case extending toward -Y and -Z.
// Idler anchor follows the rear mounting face (case or disk), pointing along -Z.
// drive rotates the disks and their attachment frames about +Z, in degrees.
// Undimensioned recesses, seams and screw pilot depths are approximate.
module xl330(anchor="horn",spin=0,orient=UP,idler_disk=false,drive=0,simple=true) {
    size=[20,34,23];
    screws=[[-8.4,4.5],[8.4,4.5],[-8.4,-19.5],[5,-22.5]];
    anchors=[
        named_anchor("horn",[0,0,0],UP,drive),
        named_anchor("idler",[0,0,idler_disk?-29:-26],DOWN,idler_disk?-drive:0)
    ];
    attachable(anchor,spin,orient,size=size,cp=[0,-7.5,-14.5],anchors=anchors) {
        if (simple) {
            color("#333") fwd(7.5) down(3) cuboid(size,anchor=TOP);
            color("#444") zrot(drive) {
                cyl(d=16,h=3,anchor=TOP);
                if (idler_disk) down(26) cyl(d=16,h=3,anchor=TOP);
            }
        } else union() {
            color("#333") difference() {
                fwd(7.5) down(3) cuboid(size,chamfer=0.8,edges="Z",anchor=TOP);

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
                color("#444") difference() {
                    cyl(d=16,h=3+ep,chamfer=0.15,anchor=TOP);
                    up(ep) zrot_copies(n=4) right(6)
                        cyl(d=1.6,h=3+ep*2,anchor=TOP); // PCD 12, M2 tapping screws
                    up(ep) cyl(d=4.2,h=1.8+ep,anchor=TOP);
                    up(ep) cyl(d=2+$slop,h=3+ep*2,anchor=TOP);
                }
                color("#888") down(0.3)
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

            // Two opposing three-pin connector sockets.
            xflip_copy() right(9.4) fwd(9) down(22.2) {
                color("#ddd") difference() {
                    cuboid([3.4,9.6,6.8],anchor=RIGHT);
                    right(ep) cuboid([2.6+ep,7.6,4.8],anchor=RIGHT);
                }
                color("#ba8") left(0.6) ycopies(2.5,n=3)
                    cuboid([2.2,0.6,0.6],anchor=RIGHT);
            }

            color("#aaa") fwd(15.5) down(3.05)
                cuboid([13.2,5.6,0.15+ep],rounding=0.4,edges="Z",anchor=TOP);
            color("#a43") back(8.5) down(25.9) cuboid([5,1.8,0.5+ep],anchor=BOT);
        }
        children();
    }
}

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
        named_anchor("motor",rot=back(43.2)*right(25)*left(10.5)*up(29.5)*zrot(270)*xrot(-90))
    ];
    attachable(anchor,orient,spin,anchors=anchors) {
        color("#6ba") difference() {
            diff() {
                up($slop) {
                    up(z-2-$slop) {
                        up(_6007ZZ[1]/2+wall*2) xcyl(d=_6007ZZ[1]+wall*2,l=23+wall*2);
                        cuboid([23+wall*2,_6007ZZ[1]+wall*2,_6007ZZ[1]/2+wall*2],anchor=BOT);
                        up(1) back(_6007ZZ[1]/2+wall)
                            cuboid([23+wall*2,20,34+7+wall],anchor=BOT+FWD,chamfer=20,edges=[BACK+BOT]);
                        tag("remove") {
                            up(_6007ZZ[1]/2+wall+2) {
                                xcyl(d=_6007ZZ[1]+$slop*2,l=_6007ZZ[2]+$slop*2);
                                xcyl(d=_6007ZZ[1]-8,l=23);
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
        }
        children();
    }
}

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
    anchors=[
        named_anchor("motor",rot=left(x)*up(23/2+3)*zrot(180))
    ];
    attachable(anchor,orient,spin,anchors=anchors) {
        color("#ddd") diff() {
            zz=_6007ZZ[2]/2;
            up($slop/2) cyl(d=_6007ZZ[0]-$slop,l=zz,anchor=BOT);
            up(zz+$slop/2) {
                cyl(d=_6007ZZ[0]+16,l=wall*2+3.4,anchor=BOT);
                up(wall*2+3.4) {
                    hull() {
                        zrot(146) pie_slice(r=33.501,h=5.5,ang=154.5,anchor=BOT);
                        left(x) cyl(d=16,l=5.5,anchor=BOT);
                    }
                    tag("remove") left(34.2) back(31.5) zrot(-108) pie_slice(d=30,l=8,ang=45,anchor=BOT);
                    spur_gear(mod=1,teeth=65,thickness=5.5,anchor=BOT,spin=55.53,hide=27);
                }
            }
        }            
        children();
    }
}

module l2_cap(anchor,orient,spin) {
    x=60;
    zz=_6007ZZ[2]/2;
    attachable(anchor,orient,spin) {
        color("#ddd") diff() {
            up($slop/2) cyl(d=_6007ZZ[0]-$slop,l=zz,anchor=BOT);            
            up(zz+$slop/2) {
                cyl(d=_6007ZZ[0]+16,l=wall*2+3.4,anchor=BOT);
                up(wall*2+3.4) {
                    hull() {
                        cyl(r=33.501,h=5.5,anchor=BOT);
                        right(x) cyl(d=16,l=5.5,anchor=BOT);
                    }
                }
            }
        }
        children();
    }
}

module l3(anchor,orient,spin,l=0) {
    anchors=[
        named_anchor("motor",rot=right(7.5)*up(25.5+wall+$slop*2+l))
    ];
    attachable(anchor,orient,spin,anchors=anchors) {
        color("#6ba") diff() {
            up(wall+l) cuboid([34+wall*2,23+wall*2,wall+20+l],chamfer=wall,edges=[TOP],anchor=TOP);
            tag("remove") {
                down($slop) cuboid([34+$slop*2,23+$slop*2,20+$slop*2],anchor=TOP);
                down(10) right(7.5) {
                    ycyl(d=18,l=29);
                    yrot(40) cuboid([18,29,28],anchor=TOP);
                }
            }
        }
        children();
    }
}

module wrist(anchor,orient,spin) {
    z=30;
    t1=12;
    t2=12;
    face_width=5;
    attachable(anchor,orient,spin) {
        union() zrot(45) up(wall) {
            l4();
            right(2.6) fwd($slop/2) xl330(spin=270,anchor=BOT+LEFT)
                attach("horn") {
                    cyl(d=16,h=wall,anchor=BOT)
                    cyl(d=6,h=30-wall,chamfer2=-2,anchor=BOT)
                    attach(TOP) bevel_gear(mod=1,teeth=t1,mate_teeth=t1,anchor=BOT,spiral=0,cutter_radius=0,face_width=face_width)
                        attach_gear(45+180) bevel_gear(mod=1,teeth=t1,mate_teeth=t1,spiral=0,cutter_radius=0,face_width=face_width)
                            attach(BOT,BOT) bevel_gear(mod=1,teeth=t1,mate_teeth=t2,spiral=0,cutter_radius=0,face_width=face_width)
                            attach_gear(-45+30) bevel_gear(mod=1,teeth=t2,mate_teeth=t1,spiral=0,cutter_radius=0,face_width=face_width)
                            attach(BOT) cyl(d=11,h=10,anchor=BOT)
                            attach(TOP,FWD) xl330(spin=45-30,idler_disk=true);
                }
            left(2.6) back($slop/2) xl330(spin=90,anchor=BOT+LEFT)
                attach("horn") {
                    cyl(d=16,h=wall,anchor=BOT)
                    cyl(d=8,h=30-wall,chamfer2=-1,anchor=BOT)
                    attach(TOP) bevel_gear(mod=1,teeth=t1,mate_teeth=t1,anchor=BOT,spiral=0,cutter_radius=0,face_width=face_width)
                        attach_gear(45+180) bevel_gear(mod=1,teeth=t1,mate_teeth=t1,spiral=0,cutter_radius=0,face_width=face_width)
                        attach(BOT,BOT) bevel_gear(mod=1,teeth=t1,mate_teeth=t2,spiral=0,cutter_radius=0,face_width=face_width);
                }
        }
        children();
    }
}

module l4(anchor,orient,spin) {
    attachable(anchor,orient,spin) {
        color("#6ba") diff() {
            xy=20*2-0.6;
            down(wall-$slop) cuboid([xy,xy,24.5+wall],chamfer=5-$slop/2,edges=[LEFT+FWD,RIGHT+BACK],anchor=BOT);
            tag("remove") zrot_copies(n=2) up(23-$slop) {
                fwd(10) right(2.5) cuboid([34+$slop*2,20+$slop*2,22.5+$slop*2],anchor=TOP);
                fwd(10+$slop/2) right(10+$slop/2) up(3) {
                    z=22.5+$slop*2+3;
                    cyl(d=18,l=z,anchor=TOP);
                    zrot(-45) cuboid([18,18,z],anchor=LEFT+TOP);
                }
            }

        }
        children();
    }
}

// xyview(angle=-55,xray=true) 
// zrot(-$t*360)
// xview(true,xray=false)

// pose=[sin($t*360)*60,sin($t*360)*90+25,-sin($t*360)*60+(90-35)];
// pose=[0,115/*-69.25,115*/,-(115-90)/*109*/,0];
pose=[0,45,45,0];

base(anchor=BOT) {
    attach(TOP) base_cap();
    attach(TOP,BOT) zrot(pose[0]) {
        up(11) xflip_copy() right(13) %color("#999") screw("M4,25",head="button",drive="hex",atype="head")
            attach(BOT) up(20.2) nut("M4",spin=60);
        l1_bushing();
        l1_bot();
        l1(pose) {
            attach("motor") xl330() 
                color("#ddd") spur_gear(mod=1,teeth=28,spin=3+(65/28)*pose[1],thickness=5.5,orient=DOWN,anchor=TOP);
            attach("j1") ball_bearing("6007ZZ");
            attach("j1") l2() {
                attach(BOT,BOT) l2_cap();
                attach("motor") xl330(spin=pose[2],idler_disk=true)
                    attach(RIGHT,BOT) l3() 
                        attach("motor") xl330(spin=270,drive=pose[3])
                        attach("horn") wrist();
            }
        }
    }
    attach(TOP,BOT) down(_6007ZZ[2]) ball_bearing("6007ZZ");
    attach("motor",TOP) %color() xl330(orient=TOP,anchor=BOT,spin=90,simple=true)
        attach("horn") color("#6ba") spur_gear(mod=1,teeth=14,thickness=10,anchor=BOT,spin=-(73/14)*pose[0]);
}
as5600(pins=false,anchor=BOT);

echo(str("\n",
    "sh ./do_mp4.sh arm00.scad ",
    $vpt[0],",",$vpt[1],",",$vpt[2],",",
    $vpr[0],",",$vpr[1],",",$vpr[2],",",
    $vpd,
    "\n"));
