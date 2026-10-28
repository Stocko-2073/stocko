include <BOSL2/std.scad>
include <BOSL2/screws.scad>
$fn=0;$fa=1;$fs=$preview?0.5:0.25;ep=0.01;$slop=0.2;

nozzle=0.4;
bracket_wall=2.5-$slop;

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

// Fits xl330(idler_disk=true); attach("horn","horn") keeps the shaft axes aligned.
// The middle anchor is centered on the outer bridge face, pointing toward +Y.
module u_bracket(l=14,w=20,anchor="horn",spin=0,orient=UP) {
    wall=bracket_wall;span=29+$slop*2;reach=l+$slop;
    size=[w,reach+wall+w/2,span+wall*2];
    anchors=[
        named_anchor("horn",[0,0,0],DOWN),
        named_anchor("middle",[0,reach+wall,-span/2+$slop],BACK)
    ];
    attachable(anchor,spin,orient,size=size,cp=[0,(reach+wall-w/2)/2,-span/2],anchors=anchors) {
        color("#f84") difference() {
            union() up($slop) {
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

module y_cap(l=ep,anchor=UP,spin=0,orient=UP) {
    size=[20,l,27];
    attachable(anchor,spin,orient,size=size) {
        color("#f84") {
            cuboid(size);
            zflip_copy() up(23/2) 
                cuboid([20,4,2],chamfer=1,edges=[BACK+TOP],anchor=BOT+FWD);
        }
        children();
    }
}

module thigh(l=10,anchor=UP,spin=0,orient=UP) {
    size=[34,20,l];
    attachable(anchor,spin,orient,size=size) {
        color("#f84") {
            hull() {
                up(size.z/2) cuboid([size.x,size.y,ep]);    
                down(size.z/2) cuboid([27,size.y,ep]);   
            }
            down(size.z/2) left(27/2) zrot(90+5) y_cap(orient=BACK);
        }
        children();
    }
}

module calf(l=28,anchor=UP,spin=0,orient=UP) {
    w=20;
    wall=bracket_wall;span=29+$slop*2;reach=l+$slop;
    size=[w,reach+wall+w/2,span+wall*2];

    ankle_angle=5+ep;
    ankle_offset=sin(ankle_angle)*w/2;
    zz=cos(ankle_angle)*span/2;
    z3=(span/2)-zz;
    ankle_w=ankle_offset-z3+1;

    knee=up(0);
    ankle=fwd(reach)*down(zz)*yrot(ankle_angle)*up(zz);

    anchors=[
        named_anchor("knee",rot=knee*xrot(180)),
        named_anchor("ankle",rot=ankle*xrot(180))
    ];
    attachable(anchor,spin,orient,size=size,cp=[0,(reach+wall-w/2)/2,-span/2],anchors=anchors) {
        color("#f84") difference() {
            union() up($slop) {
                down(span/2) yrot_copies(n=2) up(span/2) 
                {
                    hull() 
                    {
                        cyl(d=w,h=ep,anchor=BOT);
                        up(ankle_offset) yrot(ankle_angle) cyl(d=w,h=ep,anchor=TOP);
                    }
                }

                // down(span/2) yrot_copies(n=2) up(span/2) 
                hull() {
                    up(ankle_offset) yrot(ankle_angle) cyl(d=w,h=2,anchor=BOT);
                    multmatrix(ankle) up(ankle_offset) cyl(d=w,h=2,anchor=BOT);
                }
                
                hull() 
                {
                    down(span+ankle_offset) yrot(ankle_angle) down(2) 
                        cyl(d=w,h=2,anchor=BOT);
                    multmatrix(ankle) down(span+ankle_offset) cyl(d=w,h=2,anchor=TOP);
                }

                multmatrix(ankle) down(span/2) zflip_copy() up(span/2) {
                    cyl(d=w,h=ankle_w,anchor=BOT);
                }
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

module foot(anchor=UP,spin=0,orient=UP) {
    size=[34*1.5,34,6];
    attachable(anchor,spin,orient,size=size) {
        color("#f84") 
            left(8.5)
            cuboid(size,rounding=6,edges="Z");
        children();
    }
}

// !xl330() attach(FWD,BACK) y_cap();

la=0;//135;
// la=140;
xflip_copy() left(25)
u_bracket(orient=BACK,spin=180) attach("horn","horn")
xl330(drive=180,idler_disk=true,orient=BACK,spin=180)
attach(FWD,BACK) y_cap(l=1,orient=FWD,spin=0)
attach(FWD,FWD) zrot(5) xrot(45) y_cap(l=1,orient=FWD,spin=90)
attach(BACK,FWD) xl330(drive=-45-la,idler_disk=true,orient=RIGHT,spin=0)
attach("horn","horn") u_bracket(l=15,orient=LEFT,spin=90)
attach("middle",TOP) thigh(l=20,spin=90)
attach(BOT,FWD) xl330(drive=-90-la,orient=LEFT,spin=-90,idler_disk=true)
    attach("horn","knee") calf(orient=LEFT,spin=90)
    attach("ankle","horn") xl330(drive=180+90,spin=-90,idler_disk=true)
        attach(LEFT,TOP) foot();
