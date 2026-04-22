include <BOSL2/std.scad>
ep=0.01;
nozzle = 0.4;
$fn=0;
$fa=1;
$fs=$preview?0.5:0.25;

servo25kg_params = [20.5,40.26,40.6,28.5,7,5,10,3];

module board_carrier(color="#488",columns = 18,rows = 18) {
    boardThickness = 1.6;
    pinDepth = 0.9;
    w = columns * 2.54 + 4.5;
    h = rows * 2.54 + 3;
    d = nozzle * 6 + boardThickness + pinDepth;
    color(color) difference() {
        cuboid([w+(4*nozzle),d,h+(4*nozzle)],anchor=BACK);
        fwd(2*nozzle) cuboid([w,pinDepth,h+20],anchor=BACK);
        fwd(4*nozzle + pinDepth) cuboid([w,boardThickness,h+20],anchor=BACK);
        fwd(2*nozzle) cuboid([w-4,10,h-4+20],anchor=BACK);
    }
    fwd(4*nozzle + pinDepth+0.05)
    children();
}
*!board_carrier();

module board(columns = 18,rows = 18) {
    w = columns * 2.54 + 4.5;
    h = rows * 2.54 + 3;
    color("#eee") cuboid([w-0.5,1.5,h+(4*nozzle)],anchor=BACK);
}

module ovonic_2s1p() {
    x=17; y=76; z=33;
    color("#848") {
        hull() {
            cuboid([x,y-x,z],anchor=FWD+TOP,rounding=1);
            cyl(d=x,h=z,anchor=TOP,rounding=1);
        }
        cuboid([x,x,4],anchor=TOP+BACK,rounding=1.5,edges="Y");
    }
}

module big_servo_neg(params=servo_params,wires_left=true,with_screw_holes=false,wire_channel_len=10) {
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
                cyl(d=11, h=1, anchor=BOT);
            }
            // wires
            up(wires_offset) right(length/2-ep) cuboid([10,8,5], anchor=BOT+LEFT);
            if(wires_left) {
                up(wires_offset) right(length/2-ep) cuboid([10,wire_channel_len+0.5,5], anchor=BOT+LEFT+BACK);
            } else {
                up(wires_offset) right(length/2-ep) cuboid([10,wire_channel_len+0.5,5], anchor=BOT+LEFT+FWD);
            }
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
        }
        // shaft
        right(length/2) left(axel_offset) up(height+1) {
            % color("#ffffffa4") render() cyl(d=5.5,h=3.5,anchor=BOT, $fn=32);
            up(3.5) children();
        }
    }
}

module body() {
    %difference() {
        up(27) cuboid([54,25,202],rounding=10,edges="Y");
        down(44) left(15) zrot(90) xrot(-90) {
            big_servo_neg(servo25kg_params);
        }
    }
    up(95) children(0); // board
    left(25) zrot(-90) xrot(90) children(1); // battery
    down(44) left(15) zrot(90) xrot(-90) children(2); // motor
}

body() {
    board_carrier() board();
    ovonic_2s1p();
    big_servo(servo25kg_params) down(3) {
        cyl(d=10,h=2,anchor=BOT);
    }
}
