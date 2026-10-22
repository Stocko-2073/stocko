include <BOSL2/std.scad>
include <globals.scad>

servo25kg_params = [20.5,40.26,40.6,28.5,7,5,10,3];

body_size=[55,30,200];

color1="#e0e0e0";
color2="#b63b";
color3="#444";

module board_carrier(columns = 18,rows = 18) {
    boardThickness = 1.6;
    pinDepth = 0.9;
    w = columns * 2.54 + 4.5;
    h = rows * 2.54 + 3;
    d = nozzle * 2 + boardThickness + pinDepth;
    difference() {
        fwd(4*nozzle) cuboid([w+(4*nozzle),d,h+(4*nozzle)],anchor=BACK);
        fwd(4*nozzle + pinDepth) cuboid([w,boardThickness,h+20],anchor=BACK);
        fwd(2*nozzle-ep) cuboid([w-4,10,h-4+5.7],anchor=BACK,chamfer=-2.8);
    }
    children();
}
*!board_carrier();

module board(columns = 18,rows = 18) {
    w = columns * 2.54 + 4.5;
    h = rows * 2.54 + 3;
    color("#eee") {
        cuboid([w-0.5,1.5,h+(4*nozzle)],anchor=BACK);
        cuboid([w-0.5-4,20,h+(4*nozzle)],anchor=BACK);
    }
}

module mounting_cone() {
    wall=2;
    h=1+3.5;
    d1=12;
    d2=d1-2*h*tan(45);
    color(color1) cyl(d1=d1,d2=d2,h=h,orient=RIGHT,anchor=BOT);
}

module ovonic_2s1p() {
    x=17; y=76; z=33;
    %color("#848") {
        hull() {
            cuboid([x,y-x,z],anchor=FWD+TOP,rounding=1);
            cyl(d=x,h=z,anchor=TOP,rounding=1);
        }
        cuboid([x,x,4],anchor=TOP+BACK,rounding=1.5,edges="Y");
    }
}

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
                                    right(length/2+arm_length-2.5) fwd(5) cyl(d=3.5, h=8);
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

body_fillets=[TOP+FRONT];

module body_form(body_size=body_size) {
    difference() {
        l=body_size.z-(body_size.y/2-3);
        up(body_size.z/2)
        union() {
            cuboid([body_size.x,body_size.y,l],
                rounding=10,edges=body_fillets, anchor=TOP);
                down(l) hull() {
                    xcyl(d=body_size.y,h=body_size.x);
                    down(body_size.y/2-10)
                    back(body_size.y/2-10)
                        xcyl(r=10,h=body_size.x);
                }
        }
        render() down(27+44) left(13.4) zrot(90) xrot(-90) {
            for(i=[0:10])
                down(i) big_servo_neg(servo25kg_params);
            down(10.395) big_servo_neg(servo25kg_params);
        }
    }
}

module body_top() {
    w=4.05;
    color(color2) render() {
        intersection() {
            difference() {
                body_form();
                cuboid([body_size.x-w,body_size.y-w,body_size.z-w],rounding=8,edges=body_fillets);
                fwd(body_size.y/2-8) left(body_size.x/2) up(body_size.z/2-35) 
                    cuboid([10,5,12],rounding=2,edges="X",anchor=TOP+FWD);
            }
            h=200*2/5;
            up(200/2-h)cuboid([55,55,h+ep],anchor=BOT);
        }
        up(91-27) back(body_size.y/2-2.5) board_carrier();
    }
    up(91-27) back(body_size.y/2-2.5) fwd(4*nozzle + 0.95) children();
}

module body_mid() {
    h=200/5;
    h2=200/3;
    color(color1) render()
    difference() {
        union() {
            intersection() {
                body_form([body_size.x-4-$slop,body_size.y-4-$slop,body_size.z-4-$slop]);
                cuboid([55,55,h2+ep]);
            }
            intersection() {
                body_form();
                cuboid([55,55,h-$slop*2+ep]);
            }
        }
        cuboid([body_size.x-8,17+$slop*2,body_size.z-8],rounding=8,edges=body_fillets);
    }
    down(27) left(22) zrot(-90) xrot(90) children();
}

module body_bot() {
    w=4.05;
    color(color1) render() 
    intersection() {
        difference() {
            body_form();
            cuboid([body_size.x-w,body_size.y-w,body_size.z-98]);
            cuboid([body_size.x-w,servo25kg_params[0],body_size.z-w],rounding=8,edges=body_fillets);
        }
        h=200*2/5+3;
        down(200/2-h+3)cuboid([55,55,h+ep],anchor=TOP);
    }
    down(27) down(44) left(13.4) zrot(90) xrot(-90) children();
    down(body_size.z/2-18.85) right(body_size.x/2) mounting_cone();
}
//!render() yview() body_bot();

module body() {
    up(27) {
        //up(max(0,sin($t*360)*50)) 
        body_top() children(0); // board
        body_mid() children(1); // battery
        //down(max(0,sin($t*360)*50)) 
        body_bot() children(2); // motor
    }
}

// !body_top(); // print
// !body_mid(); // print
!xrot(180) body_bot(); // print

module servo_gear_socket(h=3.5) {
    $fn=16;
    union() {
        r=2.85;
        difference() {
            cyl(r=r+0.35,h=h, anchor=TOP);
            union() for (i=[0:24]) hull() {
                zrot(i*360/25) fwd(r) cyl(d=0.4,h=h, anchor=TOP);
                zrot(i*360/25) fwd(r+0.35) cyl(d=0.8,h=h, anchor=TOP);
            }
        }
    }
}

module servo_gear_socket_with_screw_hole() {
    union() {
        servo_gear_socket();
        down(3.5/2) {
            cyl(d=3,h=10,$fn=16,anchor=BOT);
            up(4) cyl(d=8,h=10,$fn=16,anchor=BOT,chamfer1=2.5,chamfang=20);
        }
    }
}

module foot() {
    color(color3) difference() {
        z=35;
        d=body_size.y*1.3;
        d2=body_size.y*0.9;
        d3=10;
        down(3+body_size.x/2) {
            up(1.1+body_size.x/2) {
                hull() {
                    cyl(d=d2,h=10,anchor=BOT,chamfer2=5);
                    right(z) cyl(d=d,h=10,anchor=BOT,chamfer2=5);
                }
                cyl(d=10,h=1.5,anchor=TOP);
            }
            down(1.1+body_size.x/2) difference() {
                hull() {
                    cyl(d=d2,h=10,anchor=TOP,chamfer1=5);
                    right(z) cyl(d=d,h=10,anchor=TOP,chamfer1=5);
                }
                up(1.1-$slop) yrot(90) mounting_cone();
            }
            right(z) {
                hull() {
                    yflip_copy() fwd((d-d3)/2) cyl(d=d3,h=body_size.x+2.2);
                    intersection() {
                        cyl(d=d,h=body_size.x+2.2);
                        cuboid([d,d,body_size.x+2.2],anchor=LEFT);
                    }
                }
                arc_copies(d=d, n=20, sa=-80, ea=80)
                    cuboid([1.5,nozzle*2,body_size.x+10+1],chamfer=1.5,edges=[TOP+RIGHT,BOT+RIGHT],anchor=LEFT);
            }
        }
        servo_gear_socket_with_screw_hole();
    }
}
// !xrot(180) foot(); // print

zrot(sin($t*360)*90) 
render() // xview()
body() {
    board();
    ovonic_2s1p();
    big_servo(servo25kg_params) {
        zrot(85) foot();
    }
}

echo(str("\n",
"sh ./do_mp4.sh stand-bot.scad ",
$vpt[0],",",$vpt[1],",",$vpt[2],",",
$vpr[0],",",$vpr[1],",",$vpr[2],",",
$vpd,
"\n"));
