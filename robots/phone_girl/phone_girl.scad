include <BOSL2/std.scad>
include <../../lib/globals.scad>
$fn=0;$fa=1;$fs=$preview?0.5:0.25;ep=0.01;$slop=0.2;

iphone_size=[71.45,149.61,8.25];
nozzle=0.4;
bracket_wall=nozzle*6;

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

// https://developer.apple.com/download/files/accessories/dimensional-drawings/iphone-16-pro.pdf
// Screen +Z, handset top +Y. Anchors follow the body, excluding buttons and cameras.
// Corner/edge profiles and port internals are simplified; dimensions are in mm.
// simple omits surface details and uses coarser curves for simulation.
module iphone_16_pro(anchor=CENTER,spin=0,orient=UP,simple=true) {
    size=iphone_size;
    // Bare mass: 199 g, https://support.apple.com/en-us/121031
    // Screen-up balance on a 3 mm pin: 31 mm from right body edge, 75 mm from bottom, assumed to pin center.
    // CoM=[size.x/2-31,75-size.y/2,0]=[4.725,0.195,0] mm; Z assumed at the body midplane.
    // A flat pin contact permits up to 1.5 mm radial offset, before measurement error.
    glass=[69.45,147.61,0.4];
    display=[66.57,144.79,0.4];
    r=12.5;
    cameras=[[14.17,14.17],[14.17,33.41],[32.16,23.79]];
    sensors=[[32.16,10.22,6.92,"#edc"],[32.16,38.14,6,"#222"],[38,34.14,0.75,"#111"]];
    attachable(anchor,spin,orient,size=size) {
        let($fa=simple?10:$fa,$fs=simple?2:$fs) union() {
            color("#444") difference() {
                cuboid(size,rounding=r,edges="Z");
                if (!simple) zflip_copy() up(size.z/2+ep)
                    cuboid(glass+[0,0,ep],rounding=r-1,edges="Z",anchor=TOP);
                right(size.x/2+ep) back(size.y/2-98.19)
                    cuboid([0.2+ep,17.3,3.23],rounding=3.23/2,edges="X",anchor=RIGHT);
                fwd(size.y/2+ep) {
                    cuboid([9.72,4+ep,3.14],rounding=3.14/2,edges="Y",anchor=FRONT);
                    if (!simple) {
                        left(size.x/2) xcopies([19.70,21.955,24.21,47.23,49.485,51.74,53.995,56.25])
                            ycyl(d=1.35,h=2+ep,anchor=FRONT);
                        left(size.x/2) xcopies([28.79,42.64])
                            ycyl(d=1.5,h=0.5+ep,anchor=FRONT);
                    }
                }
            }
            if (!simple) color("#b7b2a9") down(size.z/2)
                cuboid(glass+[0,0,ep],rounding=r-1,edges="Z",anchor=BOT);
            if (!simple) up(size.z/2) {
                color("#111") difference() {
                    cuboid(glass+[0,0,ep],rounding=r-1,edges="Z",anchor=TOP);
                    up(ep) cuboid(display+[0,0,ep*3],rounding=r-2.44,edges="Z",anchor=TOP);
                }

                color("#26343e") difference() {
                    cuboid(display+[0,0,ep],rounding=r-2.44,edges="Z",anchor=TOP);
                    back(size.y/2-7.71) up(ep)
                        cuboid([20.73,6.07,0.4+ep*3],rounding=6.07/2,edges="Z",anchor=TOP);
                }
                color("#080808") back(size.y/2-7.71)
                    cuboid([20.73,6.07,0.4+ep],rounding=6.07/2,edges="Z",anchor=TOP);
            }
            up(size.z/2) fwd(size.y*0.2) face();
            // Action, volume, side button, and flush Camera Control.
            color("#444") {
                left(size.x/2-ep) for (button=[[34.08,6.9],[48.23,11.2],[62.43,11.2]])
                    back(size.y/2-button.x)
                        cuboid([0.45+ep,button.y,2.66],rounding=1.33,edges="X",anchor=RIGHT);
                if (!simple) right(size.x/2-ep) back(size.y/2-55.33)
                    cuboid([0.45+ep,17.7,2.66],rounding=1.33,edges="X",anchor=LEFT);
            }
            color("#444") right(size.x/2) back(size.y/2-98.19)
                cuboid([0.2+ep,17.1,3.03],rounding=3.03/2,edges="X",anchor=RIGHT);
            if (!simple) color("#333") fwd(size.y/2-0.7)
                cuboid([6.6,3.5,0.7],anchor=FRONT); // USB-C tongue

            // Rear coordinates in Apple's drawing start at the upper left, viewed from behind.
            right(size.x/2) back(size.y/2) down(size.z/2) {
                color("#444") difference() {
                    left((1.04+45.22)/2) fwd((1.04+46.54)/2) up(ep)
                        cuboid([44.18,45.5,2.05+ep],rounding=12,edges="Z",anchor=TOP);
                    if (!simple) for (sensor=sensors) left(sensor.x) fwd(sensor.y) down(2.05+ep)
                        cyl(d=sensor.z,h=0.2+ep,anchor=BOT);
                }
                for (camera=cameras) left(camera.x) fwd(camera.y) down(2.05-ep) {
                    if (simple) color("#444") cyl(d=16.2,h=4.28-2.05+ep,anchor=TOP);
                    else {
                        color("#77736e") tube(od=16.2,id=14.6,h=4.28-2.05+ep,anchor=TOP);
                        color("#111923") cyl(d=14.6,h=4.28-2.05+ep,anchor=TOP);
                    }
                }
                if (!simple) for (sensor=sensors) color(sensor[3]) left(sensor.x) fwd(sensor.y) down(2.05)
                    cyl(d=sensor.z,h=0.2+ep,anchor=BOT);
            }
        }
        children();
    }
}

// https://www.molicel.com/product/inr-18650-m35a/
// Nominal 18 x 65 flat-top cell; negative at BOT, positive at TOP.
// Mass is 48g.  Assume CoM is in the center of the battery
module inr18650(anchor=BOT,spin=0,orient=UP) {
    attachable(anchor,spin,orient,d=18,l=65,cp=[0,0,32.5]) {
        union() {
            color("#748") up(0.1) cyl(d=18,h=64.8,chamfer=0.3,anchor=BOT);
            color("#aaa") cyl(d=13,h=0.3,anchor=BOT);
            color("#333") up(64.65) cyl(d=13,h=0.25,anchor=BOT);
            color("#aaa") up(64.65) cyl(d=6.5,h=0.35,anchor=BOT);
        }
        children();
    }
}

module face() {
    r=12;s=r*1.4;
    color("#ccc") {
        xflip_copy() left(s) {
            left(r*0.1) zrot(-13) xscale(1.4) difference() {
                cyl(d=r*1.5,l=ep,anchor=BOT);
                fwd(r*0.15) right(r*0.1) down(ep) cyl(d=r*1.7,l=ep*3,anchor=BOT);
            }
            back(r*0.14) zrot(-10) intersection() {
                cyl(r=r,l=ep,anchor=BOT);
                fwd(r*0.7) cyl(r=r*0.9,l=ep,anchor=BOT);

            }
        }
        fwd(r) difference() {
            yy=r*0.2;
            cuboid([r*0.2,yy,ep],rounding=yy/2,edges="Z",anchor=BOT);
            fwd(yy*0.3) cyl(d=r*10,l=ep*6,anchor=FWD);
        }
        fwd(r*1.65) difference() {
            yy=r*0.2;
            cuboid([r*1,yy,ep],rounding=yy/2,edges="Z",anchor=BOT);
            fwd(yy*0.3) cyl(d=r*10,l=ep*6,anchor=FWD);
        }
    }
}

module wedge(a=10,w=20,l=34,anchor="bracket",spin=0,orient=UP) {
    h=l*sin(a);y=l/2*(1-cos(a));
    anchors=[
        named_anchor("bracket",[0,0,0],DOWN),
        named_anchor("motor",[0,y,h/2],xrot(-a,p=UP))
    ];
    attachable(anchor,spin,orient,anchors=anchors) {
        color("#6ba") back(l/2) hull() {
            cuboid([w,l,ep],anchor=BACK);
            xrot(-a) cuboid([w,l,ep],anchor=BACK);
        }
        children();
    }
}
// !wedge(); // print

// Fits xl330(idler_disk=true); attach("horn","horn") keeps the shaft axes aligned.
// The middle anchor is centered on the outer bridge face, pointing toward +Y.
module u_bracket(w=20,anchor="horn",spin=0,orient=UP) {
    wall=bracket_wall;span=29+$slop;reach=14+$slop;
    size=[w,reach+wall+w/2,span+wall*2];
    anchors=[
        named_anchor("horn",[0,0,0],DOWN),
        named_anchor("middle",[0,reach+wall,-span/2],BACK)
    ];
    attachable(anchor,spin,orient,size=size,cp=[0,(reach+wall-w/2)/2,-span/2],anchors=anchors) {
        color("#6ba") difference() {
            union() {
                zcopies([0,-span-wall]) {
                    cyl(d=w,h=wall,anchor=BOT);
                    cuboid([w,reach+wall,wall],anchor=FWD+BOT);
                }
                back(reach) down(span/2)
                    cuboid([w,wall,span+wall*2],anchor=FWD);
            }
            *zcopies([-ep,-span-wall-ep]) {
                cyl(d=6+$slop,h=wall+ep*2,anchor=BOT); // center screw / idler cap access
                zrot_copies(n=4) right(6)
                    cyl(d=2+$slop,h=wall+ep*2,anchor=BOT); // M2, PCD 12
            }
        }
        children();
    }
}
// !xrot(-90) u_bracket(anchor="middle"); // print

// Cylinder runs from the horn face at Z=0 to Z=l.
// The cradle takes the servo's bottom end: attach("base",FWD) xl330(spin=90).
module pole(l=10,anchor="horn",spin=0,orient=UP) {
    wall=nozzle*4;seat=[23+$slop*2,20+$slop*2,8];
    size=[seat.x+wall*2,seat.y,l+wall+seat.z];
    anchors=[
        named_anchor("horn",[0,0,0],DOWN),
        named_anchor("base",[0,0,l+wall],UP)
    ];
    attachable(anchor,spin,orient,size=size,cp=[0,0,size.z/2],anchors=anchors) {
        color("#6ba") difference() {
            union() {
                hull() {
                    cyl(d=20,h=l,chamfer=0.4,anchor=BOT);
                    up(l) cuboid([size.x,seat.y,wall],anchor=BOT);
                }
                xflip_copy() right(seat.x/2) up(l)
                    cuboid([wall,seat.y,wall+seat.z],rounding=2,edges="X",anchor=LEFT+BOT);
            }

            *down(ep) cyl(d=4+$slop,h=l+wall+ep*2,anchor=BOT); // horn screw access
            *zrot_copies(n=4) right(6) {
                down(ep) cyl(d=2+$slop,h=l+wall+ep*2,anchor=BOT); // M2, PCD 12
                up(wall) cyl(d=4+$slop,h=l+ep,anchor=BOT); // recessed screw heads
            }
            *up(l+wall+2) ycopies(16,n=2)
                xcyl(d=2+$slop,h=size.x+ep*2); // lower case holes, both faces
        }
        children();
    }
}
// !pole(); // print

// Fits xl330(idler_disk=true); attach("horn","horn") to the driving servo.
// attach("side",LEFT) or attach("side",RIGHT) mounts the next servo at right angles.
module hip(anchor="horn",spin=0,orient=UP) {
    wall=bracket_wall;w=23+$slop*2;span=29+$slop;reach=16+$slop;
    size=[w+wall*2,reach+wall+6+10,span+wall*2];
    anchors=[
        named_anchor("horn",[0,0,0],DOWN),
        named_anchor("side",[0,reach+wall,-span/2],BACK,90)
    ];
    attachable(anchor,spin,orient,size=size,cp=[0,(reach+wall+6-10)/2,-span/2],anchors=anchors) {
        color("#6ba") difference() {
            union() {
                zcopies([0,-span-wall]) hull() {
                    cyl(d=20,h=wall,anchor=BOT);
                    back(reach) cuboid([w,wall,wall],anchor=FWD+BOT);
                }
                back(reach) down(span/2) {
                    cuboid([w,wall,span+wall*2],anchor=FWD);
                }
            }
        }
        children();
    }
}
// !hip(anchor=BOT); // print

// The u_bracket() shape with the foot on its bridge, running toward +Y.
// Fits xl330(idler_disk=true) like u_bracket(): attach("horn","horn").
module leg(anchor="horn",spin=0,orient=UP) {
    wall=bracket_wall;w=20;span=29+$slop;reach=14+$slop;foot=23;l=70;
    size=[w,w/2+reach+wall+l,span+wall*2];
    anchors=[
        named_anchor("horn",[0,0,0],DOWN),
        named_anchor("base",[0,l+span/2+2+$slop-34,-span/2],BACK)
    ];
    attachable(anchor,spin,orient,size=size,cp=[0,(reach+wall+l-w/2)/2,-span/2],anchors=anchors) {
        color("#6ba") difference() {
            union() {
                zcopies([0,-span-wall]) {
                    cyl(d=w,h=wall,anchor=BOT);
                    cuboid([w,reach+wall,wall],anchor=FWD+BOT);
                }
                back(reach) down(span/2)
                    cuboid([w,wall,span+wall*2],anchor=FWD);
                back(reach+wall) down(span/2) 
                hull() 
                {
                    cuboid([w,wall,span+wall*2],anchor=FWD);
                    cuboid([20,l,23],anchor=FWD);
                }
            }
            back(reach+wall) down(span/2) back(l) {
                cuboid([20,34,23],anchor=BACK);
                cuboid([20,11,29],anchor=BACK);
                cyl(d=22.5,l=29,anchor=BACK);
            }
            xrot(-90) down(10) back(29/2+$slop) yrot(20) left(3.5) {
                cuboid([21,29+$slop*2,36],anchor=BOT);
                up(36) hull() {
                    cuboid([21,29+$slop*2,ep],anchor=BOT);
                    up(25) cyl(d=21,h=1,anchor=TOP);
                }
            }
        }
        children();
    }
}

module foot(w=20,anchor="horn",spin=0,orient=UP) {
    wall=bracket_wall;span=29+$slop;reach=24+$slop;
    size=[w,reach+wall+w/2,span+wall*2];
    anchors=[
        named_anchor("horn",[0,0,0],DOWN),
        named_anchor("middle",[0,reach+wall,-span/2],BACK)
    ];
    attachable(anchor,spin,orient,size=size,cp=[0,(reach+wall-w/2)/2,-span/2],anchors=anchors) {
        dd=24.5+bracket_wall*2+$slop;
        color("#6ba") difference() {
            union() {
                up(wall) difference() {
                    hull() {
                        cyl(d=w,h=span+wall*2,chamfer=2.25,anchor=TOP);
                        back(4) cyl(d=w,h=span+wall*2,chamfer=2.25,anchor=TOP);
                    }
                }
                down(span/2) back(w/2) difference() {
                    left(w/2+4.5) xcyl(d=dd,l=w*2.7,rounding2=(29+$slop)/3,anchor=LEFT);
                    fwd(4.7) right(w/2) zrot(27) left(w) xrot(3) cuboid([100,dd,dd+5],anchor=LEFT+BACK);
                    left(w/2) zrot(-35) right(w)cuboid([100,dd,dd],anchor=RIGHT+BACK);
                }
            }
            cyl(d=16+$slop*2,h=span,anchor=TOP);
            down(span/2) back(w/2) {
                left(w/2+14.5+bracket_wall/2) xcyl(d=dd-bracket_wall,l=w*2.7+10,rounding=(31+$slop)/3-1.5,anchor=LEFT);
                cuboid([w,34,24.5+$slop],anchor=BACK);
            }

        }
        children();
    }
}
// !xrot(-90) foot(); // print

module abdomen(anchor=UP,spin=0,orient=UP) {
    a=-115;
    anchors=[
        named_anchor("leg_l",rot=xrot(-90)*zrot(90)*right(29/2)*
            down(20)*left(4)*yrot(110)*right(10)*zrot(180),flip=true),
        named_anchor("leg_r",rot=xrot(-90)*zrot(90)*right(29/2)*
            down(20)*right(4)*yrot(-110)*left(10),flip=true)
    ];
    attachable(anchor,spin,orient,anchors=anchors) {
        color("#6ba") diff() down(26) {
            tag("remove") down(3) {
                cyl(d=28,l=29,anchor=BOT);
            }
            
            hull() {
                up(29/2-3) cyl(d=20,l=40);
                xrot(-90) zrot(90) left(23/2) 
                down(20) xflip_copy() right(4) yrot(-110)
                cuboid([20,23,34],anchor=TOP+RIGHT);
            }
            tag("remove") 
                xrot(-90) zrot(90) left(23/2) 
                down(20) xflip_copy() right(4) yrot(-110)
                cuboid([20,23,34],anchor=TOP+RIGHT);
        }
        children();
    }
}

module chest(anchor=UP,spin=0,orient=UP) {
    zz=22+7;
    yy=4;
    anchors=[
        named_anchor("arm_l",rot=fwd(2.875)*yrot(90)*left(23)*right(iphone_size.x/2+1.5)
            *back(iphone_size.z/2-1.25)*down(14)*up(51.125-$slop)*xrot(90)*yrot(-90)
        ,flip=true),
        named_anchor("arm_r",rot=fwd(2.875)*yrot(90)*right(23)*left(iphone_size.x/2+1.5)
            *back(iphone_size.z/2-1.25)*down(14)*up(51.125-$slop)*zrot(180)*xrot(90)*yrot(-90)
        ,flip=true),
        named_anchor("head",rot=fwd(2.875)*yrot(90)*down(14)*up(54)*yrot(180),flip=true),
        named_anchor("backpack",rot=
            fwd(2.875)*yrot(90)*down(14)*up(54)*
            fwd(iphone_size.z/2+3)*back(20)*up(iphone_size.y*0.27-1.5)
            ,flip=true)
    ];
    attachable(anchor,spin,orient,anchors=anchors) {
        color("#6ba") diff() {
            fwd(2.875) yrot(90) down(14) up(54) {
                fwd(iphone_size.z/2+3) back(20) up(iphone_size.y*0.27-1.5) {
                    cuboid([iphone_size.x,60-2.5,19],rounding=12+1.5-1.5,edges=[BACK+LEFT,BACK+RIGHT],orient=FWD,anchor=BACK+TOP);
                    tag("remove") down(1.5) 
                        cuboid([iphone_size.x-3,60-2.5-3,19],rounding=12-1.5,edges=[BACK+LEFT,BACK+RIGHT],orient=FWD,anchor=BACK+TOP);
                }
                difference() {
                    fwd(iphone_size.z/2+3)
                        cuboid([iphone_size.x+3,iphone_size.y*0.27,20],rounding=12+1.5,edges=[BACK+LEFT,BACK+RIGHT],orient=FWD,anchor=FWD+TOP);
                    up(1.5) cuboid(iphone_size+[$slop*2,$slop*2,$slop*2],rounding=12,edges="Z",orient=FWD,anchor=FWD);
                    // up(6.5) cuboid([iphone_size.x-10,iphone_size.x-10,20],rounding=7.5,edges="Z",orient=FWD,anchor=FWD+BOT);
                    // up(50) cuboid([iphone_size.x-30,15,20],rounding=7.5,edges="Z",orient=FWD,anchor=FWD+BOT);
                    up(iphone_size.y*0.54) cuboid(iphone_size+[3,3,-3],orient=FWD,anchor=FWD);
                    up(iphone_size.y*0.40) {
                        back(iphone_size.z/2+$slop) intersection() {
                            left(iphone_size.x/2+5) ycyl(d=iphone_size.x*1.3,l=100,anchor=LEFT+BACK);
                            right(iphone_size.x/2+5) ycyl(d=iphone_size.x*1.3,l=100,anchor=RIGHT+BACK);
                        }
                        cuboid(iphone_size+[3,3,100],orient=FWD,anchor=FWD);        
                        back(iphone_size.z/2+$slop) cuboid([iphone_size.x+6,25,iphone_size.z+100],orient=BACK,anchor=FWD+TOP);        
                    }
                }    
            }
            yrot(90) {
                up(34+19.925+$slop) cuboid([28.45-$slop*2,20,34],anchor=TOP);
                tag("remove") up(34) {
                    cuboid([23,20,34],anchor=TOP);
                    up(19.925) xflip_copy() right(25.725) cuboid([23,20,34],anchor=TOP);
                }
            }
        }
        children();
    }
}

module shoulder(l=10,anchor="horn",spin=0,orient=UP) {
    wall=nozzle*4;seat=[23+$slop*2,20+$slop*2,8];
    size=[seat.x+wall*2,seat.y,l+wall+seat.z];
    anchors=[
        named_anchor("horn",[0,0,0],DOWN),
        named_anchor("base",[-20/2,0,l+wall],UP)
    ];
    attachable(anchor,spin,orient,size=size,cp=[0,0,size.z/2],anchors=anchors) {
        color("#6ba") diff() hull() {
            cyl(d=16,h=l,chamfer=0.4,anchor=BOT);
            zrot(45) xrot(-20) back(5) yrot(10) zrot(90) up(l) {
                left(20/2)cuboid([20,seat.y,wall],anchor=BOT);
            }
        }
        zrot(45) xrot(-20) back(5) yrot(10) zrot(90)
        children();
    }
}
// !shoulder(); // print

module hand(anchor=UP,spin=0,orient=UP) {
    s1=15;
    s2=16;
    attachable(anchor,spin,orient) {
        color("#ccc") {
            hull() {
                cyl(d=16,h=1,anchor=BOT);
                // cuboid([20,20,1],anchor=BOT);
                up(s1) {
                    cuboid([20/2,16,1],anchor=BOT+RIGHT,rounding=2,edges="Z");
                    yrot(20) cuboid([20/2,20,1],anchor=BOT+RIGHT,rounding=2,edges="Z");
                }
            }
            up(s1) yrot(20) {
                hull() {
                    cuboid([20/2,20,1],anchor=BOT+RIGHT,rounding=2,edges="Z");
                    up(s2) {
                        cuboid([20/2,20,1],anchor=BOT+RIGHT,rounding=2,edges="Z");
                        yrot(20) cuboid([20/2,20,1],anchor=BOT+RIGHT+TOP,rounding=2,edges="Z");
                    }
                }
                up(s2) yrot(20) hull(){
                    cuboid([20/2,20,1],anchor=BOT+RIGHT+TOP,rounding=2,edges="Z");
                    up(10) yrot(30) cuboid([20/3,16,1],anchor=BOT+RIGHT+TOP,rounding=2,edges="Z");
                }
            }
        }
        children();        
    }
}

module electronics(anchor=UP,spin=0,orient=UP) {
    attachable(anchor,spin,orient) {
        union() {
            //
            down(2) cuboid([67,18,16],rounding=10,edges=[TOP+RIGHT,TOP+LEFT],anchor=TOP+FWD);
            // batteries
            down(28) back(10) {
                inr18650(orient=LEFT,anchor=CENTER);
                down(18.5) inr18650(orient=LEFT,anchor=CENTER);
            }
        }
        children();
    }
}

module backpack_lid(anchor=UP,spin=0,orient=UP) {
    attachable(anchor,spin,orient) {
        color("#333") back($slop) up(1.5) difference() {
            cuboid([74.4,20.5,61],rounding=12+1.5,edges=[TOP+RIGHT,TOP+LEFT],anchor=TOP+FWD);
            down(1.5-$slop) cuboid([74.4-3+$slop*2,20.5-1.5,61-3],rounding=12+$slop,edges=[TOP+RIGHT,TOP+LEFT],anchor=TOP+FWD);
        }
        children();
    }
}

module robot(pose) {
    left(29/2)
    xl330(drive=pose[0]+180,idler_disk=true,orient=LEFT,spin=90) {
        attach(BACK,RIGHT) chest() {
            attach("head",FWD) iphone_16_pro(orient=FWD,anchor=FWD,spin=180,simple=true);
            attach("backpack",TOP) electronics();
            attach("backpack",TOP) backpack_lid();
            attach("arm_r",BOT)
                xl330(drive=pose[1],orient=LEFT,spin=0)
                    // arm
                    attach("horn","horn") shoulder()
                    attach("base",BACK)
                    xl330(drive=pose[2]+90,orient=FWD,spin=0,anchor="idler")
                    attach("horn","horn") pole(15)
                        attach("base",FWD)
                        xl330(drive=pose[3],idler_disk=true,orient=FWD,spin=90,anchor="idler")
                            attach("horn","horn") u_bracket()
                                attach("middle","bracket") wedge()
                                attach("motor",BOT)
                                xl330(drive=pose[4],orient=FWD,spin=0,anchor="idler")
                                    attach("horn",BOT) hand();
            attach("arm_l",BOT)
                xl330(drive=-pose[5],orient=LEFT,spin=0)
                    // arm
                    attach("horn","horn") xflip() shoulder()
                    attach("base",BACK)
                    xl330(drive=pose[6]+90,orient=FWD,spin=0,anchor="idler")
                    attach("horn","horn") pole(15)
                        attach("base",FWD)
                        xl330(drive=pose[7],idler_disk=true,orient=FWD,spin=90,anchor="idler")
                            attach("horn","horn") u_bracket()
                                attach("middle","bracket") wedge()
                                attach("motor",BOT)
                                xl330(drive=pose[8],orient=FWD,spin=0,anchor="idler")
                                    attach("horn",BOT) hand();
        }
        attach("horn",BOT) abdomen() {
            attach("leg_l",FWD) xl330(drive=pose[9],idler_disk=true)
                attach("horn","horn") hip(spin=55)
                    attach("side","bracket") wedge(spin=0,a=18,w=34,l=23)
                    attach("motor",LEFT) xl330(drive=pose[10],spin=180,idler_disk=true)
                    attach("horn","horn") u_bracket(spin=-90)
                    attach("middle",BOT) xl330(drive=pose[11]-90,spin=0)
                    attach("horn","horn") pole(25)
                    attach("base",FWD) xl330(drive=-pose[12]+90,idler_disk=true,spin=-90)
                    attach("horn","horn") leg(spin=-90)
                    attach("base",FWD) xl330(drive=pose[13],spin=180,idler_disk=true)
                    attach("horn","horn") xflip() foot(spin=0)
                    ;
            attach("leg_r",FWD) xl330(drive=pose[14],idler_disk=true)
                attach("horn","horn") hip(spin=55)
                    attach("side","bracket") wedge(spin=0,a=18,w=34,l=23)
                    attach("motor",LEFT) xl330(drive=pose[15],spin=0,idler_disk=true)
                    attach("horn","horn") u_bracket(spin=-90)
                    attach("middle",BOT) xl330(drive=-pose[16]-90,spin=180)
                    attach("horn","horn") pole(25)
                    attach("base",FWD) xl330(drive=-pose[17]+90,idler_disk=true,spin=90)
                    attach("horn","horn") leg(spin=-90)
                    attach("base",FWD) xl330(drive=-pose[18],idler_disk=true)
                    attach("horn","horn") foot(spin=0)
                    ;
        }
    }
}

// yview()
// Servo drive angles in degrees, each limb from the body out.
default_pose=[
    0,            // waist 0
    40,-10,20,70, // arm_r 1-4
    40,-10,20,70, // arm_l 5-8
    38,-7,0,-7,0, // leg_l 9-13
    38,-7,0,-7,0  // leg_r 14-18
];
collision_test_pose=[
    20,            // waist 0
    158,-18.5,109,135,  // arm_r 1-4
    158,-18.5,109,135,  // arm_l 5-8
    -77,112,110,156,30,  // leg_l 9-13
    -77,112,110,156,30   // leg_r 14-18
];
jump_test_pose=[
    -20,            // waist 0
    210,-10,20,70, // arm_r 1-4
    158,-10,109,135,  // arm_l 5-8
    -50,112,90,156,50,  // leg_l 9-13
    43,-7,0,7,-50  // leg_r 14-18
];
pose=jump_test_pose;
// pose=default_pose;
zrot(-360*(1-cos($t*180)))
xrot(pose[0]) 
robot(pose);

echo(str("\n",
    "sh ./do_mp4.sh phone_girl.scad ",
    $vpt[0],",",$vpt[1],",",$vpt[2],",",
    $vpr[0],",",$vpr[1],",",$vpr[2],",",
    $vpd,
    "\n"));