$fn=0;
$fa=1;
$fs=$preview?1:0.25;

color1="#f8f8f8";
color2="#aaabaf";
color3="#88e0dd";

nozzle=0.4;
ep=0.01;
$slop=0.2;
d1=83;
x=68;
h1=x/2;
y=40;
//z1=sqrt(3/2)*256/3+x/4;
z1=175;
z2=93;
z3=z1+6;
wrist_gear_height=6;
axel_diameter=6;

//num_assembly_steps=32;

function map(val,fromLow,fromHigh,toLow,toHigh) = toLow + (val - fromLow) * (toHigh - toLow) / (fromHigh - fromLow);
function animate_keyframes(t,i,keyframes) = 
    let(tt=map(t,0,1,0,len(keyframes)-1)-0.000001)
    map(tt%1,0,1,keyframes[floor(tt)][i],keyframes[floor(tt)+1][i]);
function reverse(l) = [for(i=[len(l)-1:-1:0]) l[i]];
function inner_radius(mod,teeth,helical) =
    2*pitch_radius(mod=mod,teeth=teeth,helical=helical) - 
    outer_radius(mod=mod,teeth=teeth,helical=helical);

assembly_steps_per_frame=20;
function num_assembly_frames(n)=n*assembly_steps_per_frame;
function asm_step(n) = ((n+2)/num_assembly_steps);
module asm(n=1000,orient=TOP) {
    if(is_undef(show_assembly)) {
        children();
    } else {
        time_step = min(1,max(0,($t*num_assembly_steps-n)/2));
        s = pow(1-time_step,3); // Ease out cubic
        if(s < 1) translate(orient*(200*s)) render() children();
    }
}

module origin_point(color="red",d=10) {
    %color(color) sphere(d=d);
    if($children>0) children();
}

module origin_cone(d=10) {
    color("blue") %difference() {
        cyl(d1=d,d2=0,h=d,anchor=TOP);
        cuboid([d,d,d],anchor=BACK+TOP);
    }
    color("red") %difference() {
        cyl(d1=d,d2=0,h=d,anchor=TOP);
        cuboid([d,d,d],anchor=FWD+TOP);
    }
    children();
}

module nop() { children(); }

module skip() {}

module zview(flip=false, xray=false) {
    render() difference() {
        union() children();
        if (flip) {
            cuboid([500,500,500],anchor=BOT);
        } else {
            cuboid([500,500,500],anchor=TOP);
        }
    }
    % color("#88888848") if(xray) {
        render() difference() {
            union() children();
            if (!flip) {
                cuboid([500,500,500],anchor=BOT);
            } else {
                cuboid([500,500,500],anchor=TOP);
            }
        }
    }
}

module xview(flip=false, xray=false) {
    difference() {
        union() children();
        if (flip) {
            cuboid([500,500,500],anchor=LEFT);
        } else {
            cuboid([500,500,500],anchor=RIGHT);
        }
    }
    % color("#88888848") if(xray) {
        render() difference() {
            union() children();
            if (!flip) {
                cuboid([500,500,500],anchor=LEFT);
            } else {
                cuboid([500,500,500],anchor=RIGHT);
            }
        }
    }
}

module xyview(orient=1,angle=45,xray=false) {
    render() zrot(-angle*orient) difference() {
        union() zrot(angle*orient) children();
        cuboid([500,500,500],anchor=RIGHT);
    }
    % color("#88888848") if(xray) {
        render() zrot(-angle*orient+180) difference() {
            union() zrot(angle*orient+180) children();
            right(ep) cuboid([500,500,500],anchor=RIGHT);
        }
    }
}

module xzview(orient=1, angle=45, xray=false) {
    render() yrot(-angle*orient) difference() {
        union() yrot(angle*orient) children();
        cuboid([500,500,500], anchor=TOP);
    }
    % color("#88888848") if(xray) {
        render() yrot(-angle*orient+180) difference() {
            union() yrot(angle*orient+180) children();
            up(ep) cuboid([500,500,500], anchor=TOP);
        }
    }
}

module yzview(orient=1, angle=45, xray=false) {
    render() xrot(-angle*orient) difference() {
        union() xrot(angle*orient) children();
        cuboid([100,500,500], anchor=RIGHT);
    }
    % color("#88888848") if(xray) {
        render() xrot(-angle*orient+180) difference() {
            union() xrot(angle*orient+180) children();
            right(ep) cuboid([100,500,500], anchor=RIGHT);
        }
    }
}


module yview(flip=false, xray=false, xray_color="#88888848") {
    difference() {
        union() children();
        if (flip) {
            cuboid([500,100,500],anchor=FWD);
        } else {
            cuboid([500,100,500],anchor=BACK);
        }
    }
    % color(xray_color) if(xray) {
        render() difference() {
            union() children();
            if (!flip) {
                cuboid([500,100,500],anchor=FWD);
            } else {
                cuboid([500,100,500],anchor=BACK);
            }
        }
    }
}

module xray(xray_color="#88888848") {
    % color(xray_color) render() children();
}

// Add inout to ribs
module ribs(n=8,d,h,anchor,flip=false,inout=false) {
    d1=flip?0.3:0.6;
    d2=flip?0.6:0.3;
    difference() {
        union() children();
        translate(anchor*(-h/2))
        zrot_copies(n=n) left(d/2) {
            if(inout) {
                cyl(d1=d1, d2=d2, h=(h+ep*2)/2, anchor=UP);
                cyl(d1=d2, d2=d1, h=(h+ep*2)/2, anchor=DOWN);
            } else {
                cyl(d1=d1,d2=d2,h=h+ep*2);
            }
        }
    }
}

module ribs_pos(n=8,d,h,anchor=[0,0,0],flip=false,inout=false) {
    d1 = flip ? 0.3 : 0.6;
    d2 = flip ? 0.6 : 0.3;
    translate(anchor * (-h/2))
    zrot_copies(n=n) left(d/2)
        // For ribs_pos, inout is not implemented, as in yribs_pos
        cyl(d1=d1, d2=d2, h=h);
}

// Add inout to xribs
module xribs(n=8,d,h,anchor=[0,0,0],flip=false,inout=false) {
    d1=flip?0.3:0.6;
    d2=flip?0.6:0.3;
    difference() {
        union() children();
        translate(anchor*(-h/2)) 
        xrot_copies(n=n) down(d/2) {
            if(inout) {
                xcyl(d1=d1, d2=d2, h=(h+ep*2)/2, $fs=0.05, anchor=RIGHT);
                xcyl(d1=d2, d2=d1, h=(h+ep*2)/2, $fs=0.05, anchor=LEFT);
            } else {
                xcyl(d1=d1,d2=d2,h=h+ep*2,$fs=0.05);
            }
        }
    }
}

module xribs_pos(n=8,d,h,anchor=[0,0,0],flip=false,inout=false) {
    d1=flip?0.3:0.6;
    d2=flip?0.6:0.3;
    translate(anchor*(-h/2)) 
    xrot_copies(n=n) down(d/2)
        // For xribs_pos, inout is not implemented, as in yribs_pos
        xcyl(d1=d1,d2=d2,h=h,$fs=0.05);
}

module yribs(n=8,d,h,anchor=[0,0,0],flip=false,inout=false) {
    d1=flip?0.3:0.6;
    d2=flip?0.6:0.3;
    difference() {
        union() children();
        translate(anchor * (-h/2)) 
        yrot_copies(n=n) left(d/2) {
            if(inout) {
                ycyl(d1=d1, d2=d2, h=(h+ep*2)/2, $fs=0.05, anchor=FWD);
                ycyl(d1=d2, d2=d1, h=(h+ep*2)/2, $fs=0.05, anchor=BACK);
            } else {
                ycyl(d1=d1, d2=d2, h=h+ep*2, $fs=0.05);
            }

        }
    }
}

module yribs_pos(n=8, d, h, anchor=[0,0,0], flip=false) {
    d1 = flip ? 0.3 : 0.6;
    d2 = flip ? 0.6 : 0.3;
    translate(anchor * (-h/2))
    yrot_copies(n=n) left(d/2)
        ycyl(d1=d1, d2=d2, h=h, $fs=0.05);
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
        union() for (i=[0:24]) hull() {
            zrot(i*360/25) fwd(r) cyl(d=0.4,h=h,anchor=TOP,$fn=16);
            zrot(i*360/25) fwd(r+0.35) cyl(d=0.8,h=h,anchor=TOP,$fn=16);
        }
    }
}

module servo_gear_socket_with_screw_hole(len=10,h=3.5,flip=false) {
    union() {
        servo_gear_socket(h=h,flip=flip);
        down(3.5/2)cyl(d=3,h=len,$fn=16);
    }
}

module bearing(type,orient,anchor) {
    %
    render() color("#FFF8") ball_bearing(type,orient=orient,anchor=anchor);
}

module m3_screw(orient) {
    //%
    color("#FFF8") 
        screw("M3,14",head="socket",thread="none",drive="hex",atype="threads",anchor=TOP,orient=orient);
    children();
}

module m3_nut(orient) {
    //%
    color("#FFF8") nut("M3",thread="none",orient=orient,anchor=TOP);
}

module rounded_cuboid(
    size=1, corner_radius=0,
    chamfer, chamfer1, chamfer2,
    rounding, rounding1, rounding2,
    anchor=CENTER, spin=0, orient=UP
) {
    s = force_list(size, 3);
    r = corner_radius;
    c1 = first_defined([chamfer1, chamfer]);
    c2 = first_defined([chamfer2, chamfer]);
    rd1 = first_defined([rounding1, rounding]);
    rd2 = first_defined([rounding2, rounding]);
    attachable(anchor=anchor, spin=spin, orient=orient, size=s) {
        if (r == 0) {
            assert(r != 0, "rounded_cuboid: corner_radius must not be zero");
        } else {
            hull() {
                yflip_copy()
                xflip_copy()
                translate([s.x/2 - r, s.y/2 - r, 0])
                    cyl(r=r, h=s.z, chamfer1=c1, chamfer2=c2, rounding1=rd1, rounding2=rd2);
            }
        }
        children();
    }
}


