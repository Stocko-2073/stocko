include <BOSL2/std.scad>
include <BOSL2/screws.scad>
include <../../lib/as5600.scad>
$fn=0;$fa=1;$fs=$preview?0.5:0.25;ep=0.01;$slop=0.2;

axis_z=130;         // output axis above the table
a=0;                // arm angle from straight down, the swing is +-100
plate_t=8;          // servo plate
seat=3;             // pad under the servo ears, so masses behind the arm clear the plate
horn_hub_d=7;horn_h=4;horn_t=1.5;   // stock double-arm horn: hub, overall height, arm plate
horn_l=32;horn_w=[6,3.5];           // tip to tip, arm width at the hub and at the tips
horn_hole_r=13;     // outermost horn holes, the hub screws self-tap into them
horn_screw=2;       // M2, or 1.6
arm=[20,8];         // pendulum width and thickness
stalk=13;           // magnet stalk
gap=1.5;            // magnet to chip
carriers=[[24,14],[30,20]]; // cup bore and depth

y_horn=seat+11.3+horn_h;    // horn top face, its hub 0.5 clear of the servo's boss
y_arm=y_horn-horn_t;        // pendulum back face
y_pcb=y_arm+arm.y+stalk+gap+3; // AS5600 board, back face
tower_y=ceil(y_arm+arm.y+carriers[1].y+5.5+4); // clear of the biggest carrier and its lid
base=[200,tower_y+78,8];    // from 28 behind the servo plate to past the tower feet

// http://www.ee.ic.ac.uk/pcheung/teaching/DE1_EE/stores/sg90_datasheet.pdf
// Sizes from MCAD's towerprosg90(). Anchored at the output axis on the ear
// underside, spline +Z, body along +X, cable out of the -X end, bent down.
module sg90(anchor="axis",spin=0,orient=UP) {
    anchors=[named_anchor("axis",[0,0,0],UP)];
    attachable(anchor,spin,orient,size=[22.5,11.8,22.7],cp=[5.35,0,-4.55],anchors=anchors) {
        union() {
            color("#36c") {
                right(5.35) down(4.55) cuboid([22.5,11.8,22.7]);
                difference() {
                    right(5.35) cuboid([31.9,11.8,2.5],anchor=BOT); // ears
                    xcopies([-8.2,18.9]) cyl(d=2,h=6);
                }
                up(6.8) hull() {
                    cyl(d=11.8,h=4,anchor=BOT);
                    right(6.3) cyl(d=5,h=4,anchor=BOT);
                }
            }
            color("#eee") up(10.8) cyl(d=4.6,h=3.2,anchor=BOT); // spline
            color("#b63") left(5.9) down(10.2) cuboid([1.2,3.6,11.8],anchor=RIGHT+TOP); // cable
        }
        children();
    }
}

module horn_shape() {
    circle(d=horn_hub_d);
    yflip_copy() hull() {
        circle(d=horn_w[0]);
        back(horn_l/2-horn_w[1]/2) circle(d=horn_w[1]);
    }
}

// Stock double-arm horn, anchored at its flat top face, arms along Y, the hub
// below it on the spline.
module horn(anchor=TOP,spin=0,orient=UP) {
    attachable(anchor,spin,orient,size=[horn_hub_d,horn_l,horn_h],cp=[0,0,-horn_h/2]) {
        color("#eee") difference() {
            union() {
                down(horn_t) linear_extrude(horn_t) horn_shape();
                cyl(d=horn_hub_d,h=horn_h,anchor=TOP);
            }
            down(horn_h+ep) cyl(d=4.8,h=3.2+ep,anchor=BOT); // spline
            cyl(d=2,h=horn_h*3);
            ycopies(horn_hole_r*2) cyl(d=1,h=horn_h*3);
        }
        children();
    }
}

// Table at Z=0, servo plate front face at Y=0, output axis along +Y at
// [0,0,axis_z]. The servo goes in from the front onto the seat pad; the side
// flanges and the base's back edge are the feet for lying it on its back.
module frame(anchor="table",spin=0,orient=UP) {
    h=axis_z+30;w=96;
    anchors=[named_anchor("table",[0,0,0],DOWN)];
    attachable(anchor,spin,orient,size=[base.x,base.y,h],cp=[0,base.y/2-28,h/2],anchors=anchors) {
        color("#f84") difference() {
            union() {
                fwd(28) cuboid(base,rounding=8,edges="Z",anchor=FWD+BOT);
                up(base.z) {
                    cuboid([w,plate_t,h-base.z],anchor=BACK+BOT);
                    xflip_copy() right(w/2) fwd(plate_t) cuboid([6,20,h-base.z],anchor=RIGHT+BACK+BOT);
                    fwd(plate_t) wedge([w-12,20,20],anchor=FWD+BOT,spin=180);
                }
                up(axis_z+5.35) cuboid([14.8,seat,34.9],chamfer=1,edges=FWD,anchor=FWD);
            }
            up(axis_z) {
                back((seat-plate_t)/2) {
                    up(5.35) cuboid([11.8+$slop*2,seat+plate_t+ep*2,22.5+$slop*2]);
                    down(5.9+$slop-ep) cuboid([4.4,seat+plate_t+ep*2,1.2+ep],anchor=TOP); // cable
                    zcopies([-8.2,18.9]) ycyl(d=1.6,h=seat+plate_t+ep*2); // M2 self-tapping
                }
                for (t=[-90:15:90]) yrot(t) down(30) back(ep)
                    ycyl(d=3+$slop,h=plate_t-2+ep,anchor=BACK); // index holes
            }
            back(base.y/2-28) grid_copies([base.x-16,base.y-16],n=2) cyl(d=5.5,h=base.z*3); // clamp or screw down
            back(tower_y+32) up(base.z+ep) xflip_copy() right(55) xcopies(16)
                cyl(d=4,h=6+ep,anchor=TOP); // M3 heat-set inserts
        }
        children();
    }
}
// !frame(); // print

// Anchored on the axis at the back face, arm toward +Y (down when hanging),
// magnet stalk +Z. The horn's top face sits on the pocket floor.
module pendulum(anchor="axis",spin=0,orient=UP) {
    anchors=[named_anchor("axis",[0,0,0],DOWN)];
    attachable(anchor,spin,orient,size=[arm.x,130,arm.y],cp=[0,45,arm.y/2],anchors=anchors) {
        color("#4a4") difference() {
            union() {
                hull() ycopies([-10,100]) cyl(d=arm.x,h=arm.y,anchor=BOT);
                up(arm.y) cyl(d=10,h=stalk,rounding1=-2,anchor=BOT);
            }
            down(ep) linear_extrude(horn_t+ep) offset(r=$slop) horn_shape();
            up(horn_t-ep) cyl(d=4.5+$slop*2,h=2.5+ep,anchor=BOT); // horn screw head
            ycopies(horn_hole_r*2) {
                cyl(d=horn_screw+$slop*2,h=arm.y*3);
                up(arm.y+ep) cyl(d=horn_screw*2+0.5,h=2+ep,anchor=TOP);
            }
            back(30) cyl(d=3+$slop,h=arm.y*3); // index pin
            ycopies(10,n=7,sp=40) cyl(d=5+$slop*2,h=arm.y*3); // M5, masses
            up(arm.y+stalk+ep) cyl(d=6+$slop,h=2.5+ep,anchor=TOP); // magnet
        }
        children();
    }
}
// !pendulum(); // print

// Mass cup, anchored at its floor on the arm face, bore up. An M5 bolt from the
// lid runs down the centre tube and through the arm, so cup, lid and a full load
// stay centred on the bolt. Fill it to the rim.
module carrier(size,anchor=BOT,spin=0,orient=UP) {
    d=size.x+4;h=size.y+3;
    attachable(anchor,spin,orient,d=d,l=h) {
        color("#ec4") down(h/2) difference() {
            union() {
                tube(od=d,id=size.x,h=h,anchor=BOT);
                cyl(d=d,h=3,anchor=BOT);
                cyl(d=10,h=h-5.5,anchor=BOT); // meets the lid's boss
            }
            down(ep) cyl(d=5+$slop*2,h=h+ep*2,anchor=BOT);
        }
        children();
    }
}
// !carrier(carriers[0]); // print
// !carrier(carriers[1]); // print

// Anchored at its underside on the rim. The spigot is a light press fit in the
// bore, the bolt head sits in the boss.
module carrier_lid(size,anchor=BOT,spin=0,orient=UP) {
    d=size.x+4;
    attachable(anchor,spin,orient,d=d,l=2.5) {
        color("#ca3") down(1.25) difference() {
            union() {
                cyl(d=d,h=2.5,anchor=BOT);
                tube(od=size.x,wall=1.5,h=2,anchor=TOP); // spigot
                cyl(d=13,h=5.5,anchor=TOP);
            }
            up(2.5+ep) cyl(d=8.5+$slop*2,h=5+ep,anchor=TOP); // M5 socket head
            cyl(d=5+$slop*2,h=20);
        }
        children();
    }
}
// !xrot(180) carrier_lid(carriers[0]); // print
// !xrot(180) carrier_lid(carriers[1]); // print

// Portal in front of everything that swings, anchored at the middle of its front
// face on the base. The feet slide in their slots to set the magnet gap, and the
// board plate hangs from the beam on two screws in oversize holes, +-1.5 to
// centre the chip on the axis, tightened from behind.
module tower(anchor=FWD+BOT,spin=0,orient=UP) {
    h=axis_z-base.z;
    t=16;
    size=[126,48,h+30];
    attachable(anchor,spin,orient,size=size,cp=[0,size.y/2,size.z/2]) {
        color("#a6d") difference() {
            union() {
                xflip_copy() right(55) {
                    cuboid([16,t,size.z],anchor=FWD+BOT);
                    cuboid([26,size.y,6],anchor=FWD+BOT); // foot
                    back(t) up(6) wedge([6,30,40],anchor=FWD+BOT);
                }
                up(h+12) cuboid([size.x,t,18],anchor=FWD+BOT);
            }
            up(h+21) xcopies(20) {
                ycyl(d=3+$slop*2+3,h=t*3);
                back(t+ep) ycyl(d=12.4,h=4.5+ep,anchor=BACK); // M3 head on a 9 mm washer
            }
            xflip_copy() right(55) back(32) xcopies(16)
                hull() ycopies(6) cyl(d=3+$slop*2,h=20); // M3, +-3 of gap adjustment
        }
        children();
    }
}
// !xrot(90) tower(); // print

// Holds the AS5600 by its top two holes, chip toward -Y, above the headers.
// Anchored at the board centre on its back face.
module board_plate(anchor="pcb",spin=0,orient=UP) {
    t=tower_y-y_pcb;
    anchors=[named_anchor("pcb",[0,0,0],FWD)];
    attachable(anchor,spin,orient,size=[32,t,24.5],cp=[0,t/2,17.75],anchors=anchors) {
        color("#d6a") difference() {
            up(5.5) cuboid([32,t,24.5],anchor=FWD+BOT);
            up(8) xcopies(16) fwd(ep) ycyl(d=2.5,h=7+ep,anchor=FWD); // M3 self-tapping
            up(21) xcopies(20) back(t+ep) ycyl(d=4,h=6+ep,anchor=BACK); // M3 heat-set inserts
        }
        children();
    }
}
// !xrot(90) board_plate(); // print

frame();
up(axis_z) back(seat) sg90(spin=-90,orient=BACK)
    up(y_horn-seat) zrot(90+a) horn()
        down(horn_t) pendulum() {
            up(arm.y+stalk) color("#bbc") cyl(d=6,h=2.5,anchor=TOP); // 6x2.5 diametric magnet
            %back(30) down(y_arm+plate_t-2) color("#888") cyl(d=3,h=40,anchor=BOT); // index pin, reaches 31 from the arm face
            for (m=[[50,carriers[0],30],[90,carriers[1],35]]) back(m[0]) {
                up(arm.y) carrier(m[1]) position(TOP) carrier_lid(m[1]) position(TOP) down(5)
                    color("#888") screw("M5",l=m[2],head="socket",drive="hex",thread=false,anchor="head_bot");
                color("#888") nut("M5",thread=false,anchor=TOP);
            }
        }
back(tower_y) up(base.z) tower()
    up(axis_z-base.z) fwd(tower_y-y_pcb) board_plate()
        fwd(3) xrot(90) as5600();
