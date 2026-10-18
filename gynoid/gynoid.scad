include <BOSL2/std.scad>
include <BOSL2/screws.scad>
include <../lib/globals.scad>
$fn=0;$fa=1;$fs=$preview?0.5:0.25;ep=0.01;$slop=0.2;

nozzle=0.4;
neck_rod=43.25;neck_crank=18;
bracket_wall=nozzle*6;

// Fixed stem mounts from the original 16 mm horns and 35 mm rods at +/-125 degrees.
// Head ball-center frame, +Z down; changing rod/horn sizes does not move these mounts.
neck_base=[for (s=[-1,1])
    apply(neck_motor(s)*zrot(s==1?180:0)*left(16)*up(5)*zrot(125*s),[-35,0,0])];
neck_home=[for (s=[-1,1]) neck_servo(s,[0,0])];

function neck_motor_pos() = back(60)*down(20)*xrot(45)*fwd(31)*up(15);
function neck_motor(side) =
    yrot(180)*up(39.5)*neck_motor_pos()*move([side*10,-4,4])*yrot(180)*zrot(180);
function neck_horn_tip(side,angle) =
    apply(neck_motor(side)*zrot(angle+(side==1?180:0)),[-neck_crank,0,5]);

// Intersect each crank circle with the sphere about its fixed stem ball.
// The sign keeps the outward crank branch used by the original linkage.
function neck_servo(side,a) =
    let(c=apply(neck_motor(side),[0,0,5]),
        u=neck_horn_tip(side,0)-c,v=neck_horn_tip(side,90)-c,
        q=apply(xrot(-a[0])*zrot(-a[1]),neck_base[(side+1)/2])-c,
        x=q*u,y=q*v,k=(q*q+neck_crank*neck_crank-neck_rod*neck_rod)/2)
    atan2(y,x)-side*acos(k/norm([x,y]));

// Servo commands are offsets from the upright pose for the current rod and horn.
function neck_tip(side,drive) = neck_horn_tip(side,drive+neck_home[(side+1)/2]);
function neck_error(r,p) = [for (i=[0:1]) norm(apply(r,p[i])-neck_base[i])-neck_rod];
function neck_jacobian(r,p) =
    [for (i=[0:1]) let(u=apply(r,p[i]),d=u-neck_base[i]) cross(u,d)/norm(d)];

// OpenSCAD's XYZ convention with yrot=0: zrot(yaw)*xrot(pitch).
function neck_roll_rotation(a) = zrot(a[1])*xrot(a[0]);
function neck_roll_descent(a,p,w,n=12) =
    let(next=a+w*180/PI)
    n==0 || norm(neck_error(neck_roll_rotation(next),p))<norm(neck_error(neck_roll_rotation(a),p))?
        next : neck_roll_descent(a,p,w/2,n-1);

function neck_roll_solve(p,a=[0,0],n=30) =
    let(r=neck_roll_rotation(a),e=neck_error(r,p))
    max(v_abs(e))<1e-8? a : n==0? undef :
    let(j=neck_jacobian(r,p),axis=apply(zrot(a[1]),RIGHT),
        w=linear_solve([for (row=j) [row*axis,row.z]],-e))
    w==[]? undef :
    neck_roll_solve(p,neck_roll_descent(a,p,w*min(1,0.15/max(v_abs(w)))),n-1);

// With roll fixed at zero, solve pitch and yaw from the two rod lengths.
function neck_roll_angles(drive,seed=[0,0]) =
    neck_roll_solve([neck_tip(-1,drive[0]),neck_tip(1,drive[1])],seed);

// https://www.molicel.com/product/inr-18650-m35a/
// Nominal 18 x 65 flat-top cell; negative at BOT, positive at TOP.
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
module u_bracket(w=20,anchor="horn",spin=0,orient=UP) {
    wall=bracket_wall;span=29+$slop;reach=14+$slop;
    size=[w,reach+wall+w/2,span+wall*2];
    anchors=[
        named_anchor("horn",[0,0,0],DOWN),
        named_anchor("middle",[0,reach+wall,-span/2],BACK)
    ];
    attachable(anchor,spin,orient,size=size,cp=[0,(reach+wall-w/2)/2,-span/2],anchors=anchors) {
        color("#f84") difference() {
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
        color("#f84") difference() {
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

module wedge(a=10,w=20,l=34,anchor="bracket",spin=0,orient=UP) {
    h=l*sin(a);y=l/2*(1-cos(a));
    anchors=[
        named_anchor("bracket",[0,0,0],DOWN),
        named_anchor("motor",[0,y,h/2],xrot(-a,p=UP))
    ];
    attachable(anchor,spin,orient,anchors=anchors) {
        color("#f84") back(l/2) hull() {
            cuboid([w,l,ep],anchor=BACK);
            xrot(-a) cuboid([w,l,ep],anchor=BACK);
        }
        children();
    }
}
// !wedge(); // print

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
        color("#f84") difference() {
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

module shoulder(l=10,anchor="horn",spin=0,orient=UP) {
    wall=nozzle*4;seat=[23+$slop*2,20+$slop*2,8];
    size=[seat.x+wall*2,seat.y,l+wall+seat.z];
    anchors=[
        named_anchor("horn",[0,0,0],DOWN),
        named_anchor("base",[0,0,l+wall],UP)
    ];
    attachable(anchor,spin,orient,size=size,cp=[0,0,size.z/2],anchors=anchors) {
        color("#f84") diff() hull() {
            cyl(d=16,h=l,chamfer=0.4,anchor=BOT);
            zrot(45) xrot(-20) back(5) yrot(10) zrot(90) up(l) {
                cuboid([34,seat.y,wall],anchor=BOT);
            }
        }
        zrot(45) xrot(-20) back(5) yrot(10) zrot(90)
        children();
    }
}
// !shoulder(); // print

module head(anchor=UP,spin=0,orient=UP) {
    r=50;a=0.66;f=0.2;i=0.6;
    motor_pos=neck_motor_pos();
    anchors=[
        named_anchor("neck_l",rot=neck_motor(-1)),
        named_anchor("neck_r",rot=neck_motor(1))
    ];
    attachable(anchor,spin,orient,anchors=anchors) {
        color_this("#ccc") diff() {
            yrot(180) up(39.5) {
                zscale(0.9) xrot(4) {
                    xrot(-8) difference() {
                        color("#ccc") intersection() {
                            hull() {
                                sphere(r=r);
                                cuboid([r,r,r],anchor=TOP);
                                fwd(r*0.55) down(r-r/3) xcyl(r=r*i,h=r*2*i,rounding=r*i);
                            }
                            up(r*0.3) fwd(r*0.4) xcyl(r=r*1.5,h=r*2*a,rounding1=r*a*1.22);
                            up(r*0.3) fwd(r*0.4) xcyl(r=r*1.5,h=r*2*a,rounding2=r*a*1.22);
                            back(r*1.15) up(r*-0.1) sphere(r=r*2);
                        }
                        // eyes
                        color("#bbb") xrot(10) back(r*-0.79) down(r*0.25) xflip_copy() left(r*0.34) yrot(7)
                        intersection() {
                            ycyl(r=r*0.22,h=5,anchor=BACK);
                            up(r*0.2) ycyl(r=r*0.27,h=5,anchor=BACK);
                        }
                    }
                    // ears
                    color("#ccc") fwd(r*0.1) down(r*0.3) xflip_copy() right(r*(i-0.04))
                    hull()
                    {
                        xcyl(r=r*f,l=r*f*1.3,anchor=FWD);
                        down(r*f*0.5) xcyl(r=r*f*0.6,l=r*f*1.3,anchor=FWD);
                    }
                }

                multmatrix(motor_pos) xflip_copy() left(10)
                yrot(180) down(8) back(11) {
                    tag("remove") down(22) fwd(7.5) {
                        down($slop)cuboid([20+$slop*2,34+$slop*2,40+$slop*2],anchor=BOT);
                        up(17.5+5) xrot(2) back(34)cuboid([20+10,34+30,40],rounding=18,edges=[BOT+BACK,BOT+FWD],anchor=BOT+BACK);
                    }
                }
            }
            tag("remove") {
                sphere(r=10+$slop);
                cyl(d1=0,d2=48,h=20+ep,anchor=BOT);
            }
        }
        children();
    }
}
// !yrot(180) head(); // print

module hand() {
    s1=15;
    s2=20;
    color("#ccc") {
        hull() {
            cuboid([20,23,1],anchor=BOT);
            up(s1) {
                cuboid([20/2,23,1],anchor=BOT+RIGHT,rounding=2,edges="Z");
                yrot(30) cuboid([20/2,23,1],anchor=BOT+RIGHT,rounding=2,edges="Z");
            }
        }
        up(s1) yrot(30) {
            hull() {
                cuboid([20/2,23,1],anchor=BOT+RIGHT,rounding=2,edges="Z");
                up(s2) {
                    cuboid([20/2,23,1],anchor=BOT+RIGHT,rounding=2,edges="Z");
                    yrot(20) cuboid([20/2,23,1],anchor=BOT+RIGHT+TOP,rounding=2,edges="Z");
                }
            }
            up(s2) yrot(20) hull(){
                cuboid([20/2,23,1],anchor=BOT+RIGHT+TOP,rounding=2,edges="Z");
                up(10) yrot(30) cuboid([20/3,23,1],anchor=BOT+RIGHT+TOP,rounding=2,edges="Z");
            }
        }
    }
}

// Fits xl330(idler_disk=true); equal arms share the thumb load across both disks.
// Box anchors describe the mounting disks; the contact pad is centered between them.
module thumb(anchor="horn",spin=0,orient=UP) {
    wall=bracket_wall;span=29+$slop;s1=20;s2=20;
    anchors=[named_anchor("horn",[0,0,0],DOWN)];
    attachable(anchor,spin,orient,size=[20,20,span+wall*2],cp=[0,0,-span/2],anchors=anchors) {
        color("#ccc") difference() {
            union() {
                up((-span)/2) zflip_copy() down((-span)/2)
                    cyl(d=16+ep,h=wall,anchor=BOT,rounding2=2);
                zrot(30) {
                    up((-span)/2) zflip_copy() down((-span)/2) left(3)
                        cuboid([10,s1+wall,wall],anchor=FWD+BOT,rounding=2,edges=[TOP+LEFT,TOP+RIGHT]);
                    down(span/2) hull() {
                        left(3) back(s1) cuboid([10,wall,span+wall*2],anchor=FWD,rounding=2,edges="Y");
                        right(2) back(s1+s2) cuboid([5,wall,23],rounding=2,edges="Y",anchor=FWD);
                    }
                }
            }
            *zcopies([-ep,-span-wall-ep]) {
                cyl(d=6+$slop,h=wall+ep*2,anchor=BOT);
                zrot_copies(n=4) right(6)
                    cyl(d=2+$slop,h=wall+ep*2,anchor=BOT); // M2, PCD 12
            }
        }
        children();
    }
}
// !thumb(anchor=BOT); // print

module chest(anchor=UP,spin=0,orient=UP) {
    zz=22+7;
    anchors=[
        named_anchor("arm_l",rot=right(29/2)*up(29.5)*fwd(6)*right(4)*
            xrot(90-45)*yrot(-90)*back(34/2)*right(20/2)
        ,flip=true),
        named_anchor("arm_r",rot=right(29/2)*up(29.5)*fwd(6)*left(4)*zrot(180)*
            xrot(90+45)*yrot(-90)*back(34/2)*left(20/2)
        ,flip=true),
        named_anchor("head",rot=right(29/2)*up(29.5)*fwd(6)*
            xrot(-45)*up(34)*fwd(20)*xrot(45)*down(sqrt(2)*10)*up(zz+9)
        ,flip=true)
    ];
    attachable(anchor,spin,orient,anchors=anchors) {
        color("#f84") diff() {
            right(29/2) xflip_copy() left(29/2) {
                hull() {
                    left(3) xcyl(d=16,h=3+29/2,anchor=LEFT);
                    up(29.5) fwd(6) right(14.5) xrot(-45) left(27) down(3) {
                        cuboid([12.5+29/2,ep,3],anchor=BOT+FWD+LEFT);
                    }
                }

                up(29.5) fwd(6) right(14.5) xrot(-45) {
                    cuboid([27,20,3],anchor=TOP+BACK+RIGHT,rounding=3,edges=[FWD+LEFT]);
                    cuboid([4,20,34],anchor=BOT+BACK+RIGHT);
                    up(34) fwd(20) xrot(45) down(sqrt(2)*10) {
                        hull() {
                            cyl(d=8,h=zz,anchor=BOT);
                            up(zz) xrot(-161)
                            fwd(2) cuboid([8,4,zz+3],anchor=BOT);
                        }
                        up(zz+9) sphere(r=10);
                    }
                }

            }
            tag("remove") right(29/2) xcyl(d=30,h=29);
        }
        children();
    }
}

module abdomen(anchor=UP,spin=0,orient=UP) {
    a=-115;
    anchors=[
        named_anchor("leg_l",rot=
            back(22)*up(23/2)*left(8)*zrot(90)*left(20)*back(5)*yrot(90)*
            down(37.5)*left(31)*yrot(73)*fwd(23)*
            yrot(180)*xrot(90)*back(-7.5),flip=true),
        named_anchor("leg_r",rot=
            back(22)*up(23/2)*left(8)*zrot(90)*left(20)*back(5)*yrot(90)*
            down(37.5)*zrot(180)*left(31)*yrot(73)*
            yrot(180)*xrot(90)*back(-7.5),flip=true)
    ];
    attachable(anchor,spin,orient,anchors=anchors) {
        color("#f84") diff() {
            tag("remove") cuboid([20,23,34],orient=FWD,anchor=FWD);
            back(22) up(23/2) zflip_copy() left(8)
            zrot(90) left(20) back(5) yrot(90) {
                hull()
                {
                    down(5) fwd(23/2) cuboid([19,23/2,1],rounding=5,edges=[LEFT+FWD,LEFT+BACK],anchor=RIGHT+TOP+BACK);
                    down(37.5) left(31) yrot(73) down(9.5)
                        cuboid([20,23,34],anchor=BACK+BOT);
                    down(20) left(36) yrot(-25) down(32) {
                        down(9.5) right(10) {
                            yrot(25) up(34) right(9.3983) cuboid([6,23,38],anchor=BACK+RIGHT+TOP);
                        }
                    }
                }
                tag("remove") down(37.5) left(31) yrot(73) down(9.5)
                    cuboid([20,25,34],anchor=BACK+BOT);
            }
        }
        children();
    }
}

module leg(anchor=UP,spin=0,orient=UP) {
    wall=bracket_wall;w=20;span=29+$slop;foot=5;
    attachable(anchor,spin,orient) {
        color("#f84") {
            hull() {
                cuboid([w,span+wall*2,wall],anchor=TOP);
                fwd(0) cyl(d=foot,l=170,rounding1=foot/2,anchor=TOP);
            }
        }
        children();
    }
}

module neck_link_1(anchor="horn",spin=0,orient=UP) {
    anchors=[
        named_anchor("horn",[0,0,0],DOWN),
        named_anchor("tip",[-neck_crank,0,5],UP)
    ];
    attachable(anchor,spin,orient,anchors=anchors) {
        color("#f84") hull() {
            cyl(d=16,h=3,anchor=BOT);
            left(neck_crank) cyl(d=4,h=3,anchor=BOT);
        }
        children();
    }
}
// !neck_link_1(); // print

module neck_link_2(anchor="tip",spin=0,orient=UP) {
    anchors=[named_anchor("tip",[0,0,0],RIGHT)];
    attachable(anchor,spin,orient,size=[neck_rod+4,4,4],cp=[-neck_rod/2,0,0],anchors=anchors) {
        color("#444") union() {
            sphere(d=4);
            xcyl(d=2,l=neck_rod,anchor=RIGHT);
            left(neck_rod) sphere(d=4);
        }
        children();
    }
}

module neck(drive=[0,0],pose,anchor=UP,spin=0,orient=UP) {
    a=drive+neck_home;
    r=is_undef(pose)?neck_roll_rotation(neck_roll_angles(drive)):pose;
    tips=[apply(r,neck_tip(-1,drive[0])),apply(r,neck_tip(1,drive[1]))];
    attachable(anchor,spin,orient) {
        union() {
            multmatrix(r) tag("head") head() {
                tag("hardware") {
                    attach("neck_l") xl330(drive=a[0])
                        attach("horn","horn") neck_link_1();
                    attach("neck_r") xl330(drive=180+a[1])
                        attach("horn","horn") neck_link_1();
                }
            }
            for (i=[0:1]) tag("hardware")
                move(tips[i]) rot(from=LEFT,to=neck_base[i]-tips[i]) neck_link_2();
        }
        children();
    }
}

// xview(true)
up(298)
// zrot(-360*(1-cos($t*180)))
up(100) {
    ta=-7;
    ha=4;
    wa=0;

    fwd(4+$slop) left(29/2) down(54)
    xrot(wa)
    back(4+$slop) right(29/2) up(54)
    {
        fwd(4+$slop) left(29/2) down(54)
        xl330(drive=wa,idler_disk=true,orient=LEFT,spin=-90) {
            attach("horn",RIGHT) chest() {
                attach("head") neck(drive=[0,0]);
                attach("arm_r",BOT)
                    xl330(drive=0) {
                        // arm
                        attach("horn","horn") shoulder()
                        attach("base",RIGHT)
                        xl330(drive=20,orient=FWD,spin=0,anchor="idler")
                        attach("horn","horn") pole(30)
                            attach("base",FWD)
                            xl330(drive=40,idler_disk=true,orient=FWD,spin=90,anchor="idler")
                                attach("horn","horn") u_bracket()
                                    attach("middle","bracket") wedge()
                                    attach("motor",BOT)
                                    xl330(drive=0,orient=FWD,spin=0,anchor="idler")
                                        attach("horn","horn") pole(20)
                                            attach("base",FWD) xl330(idler_disk=true,spin=90){
                                                attach(BACK) hand();
                                                attach("horn","horn") thumb();
                                            }
                    }
                attach("arm_l",BOT)
                    xl330(drive=0) {
                        // arm
                        attach("horn","horn") xflip() shoulder()
                        attach("base",RIGHT)
                        xl330(drive=20,orient=FWD,spin=0,anchor="idler")
                        attach("horn","horn") pole(30)
                            attach("base",FWD)
                            xl330(drive=40,idler_disk=true,orient=FWD,spin=90,anchor="idler")
                                attach("horn","horn") u_bracket()
                                    attach("middle","bracket") wedge()
                                    attach("motor",BOT)
                                    xl330(drive=0,orient=FWD,spin=0,anchor="idler")
                                        attach("horn","horn") pole(20)
                                            attach("base",FWD) xl330(idler_disk=true,spin=90){
                                                attach(BACK) hand();
                                                attach("horn","horn") thumb();
                                            }
                    }
                }
            attach(BOT,TOP) abdomen() {
                attach("leg_l",TOP) xl330(drive=ha,idler_disk=true)
                    attach("horn","horn") hip(spin=55)
                        attach("side","bracket") wedge(spin=0,a=18,w=34,l=23)
                        attach("motor",LEFT) xl330(drive=ta,spin=180,idler_disk=true)
                        attach("horn","horn") u_bracket(spin=-90)
                        attach("middle",BOT) xl330(drive=90,spin=180)
                        attach("horn","horn") pole(15)
                        attach("base",FWD) xl330(drive=90+ta,idler_disk=true,spin=90)
                        attach("horn","horn") u_bracket(spin=-90)
                        attach("middle",TOP) leg()
                        ;
                attach("leg_r",TOP) xl330(drive=ha,idler_disk=true)
                    attach("horn","horn") hip(spin=55)
                        attach("side","bracket") wedge(spin=0,a=18,w=34,l=23)
                        attach("motor",LEFT) xl330(drive=ta,spin=0,idler_disk=true)
                        attach("horn","horn") u_bracket(spin=-90)
                        attach("middle",BOT) xl330(drive=90,spin=0)
                        attach("horn","horn") pole(15)
                        attach("base",FWD) xl330(drive=90-ta,idler_disk=true,spin=90)
                        attach("horn","horn") u_bracket(spin=-90)
                        attach("middle",TOP) leg()
                        ;
                    }
        }
    }
}
// left(130) xflip_copy() left(10) inr18650();

echo(str("\n",
    "sh ./do_mp4.sh gynoid.scad ",
    $vpt[0],",",$vpt[1],",",$vpt[2],",",
    $vpr[0],",",$vpr[1],",",$vpr[2],",",
    $vpd,
    "\n"));
