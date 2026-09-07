include <BOSL2/std.scad>
include <BOSL2/screws.scad>
include <BOSL2/ball_bearings.scad>
use <nema17.scad>
use <nema17_tr8.scad>
use <sg15.scad>

$fn=0;$fa=1;$fs=$preview?0.5:0.25;ep=0.01;
$slop=0.2;

x_travel=84;
y_travel=66;
z_travel=50;

board_x=51;
board_y=70;
board_z=1.6;

module board(anchor=CENTER,spin=0,orient=UP) {
    attachable(anchor,spin,orient,size=[board_x,board_y,board_z]) {
        color_this("#853") cuboid([board_x,board_y,board_z]);
        children();
    }
}

module rod5(l=100,anchor=CENTER,spin=0,orient=UP) {
    attachable(anchor,spin,orient,d=5,l=l) {
        color_this("#bbb") cyl(d=5,l=l);
        children();
    }
}

w=60;

up(26) fwd(42.5) left(w+5) nema17_tr8(nut_pos=0,orient=RIGHT,spin=180);

nema17_tr8(nut_pos=0,orient=FWD,spin=180) {
    attach("nut_flange",TOP) {
        down(3.5) zrot_copies(n=4) left(8)
            %screw("M3,12",head="button",atype="threads");
    }
    attach(TOP,BOT) diff() {
        %cuboid([w*2+10,42,7.5-ep]);
        tag("remove") {
            up(2.5-$slop) xflip_copy() left(30) cyl(d=5+$slop,l=5+$slop,extra=ep,anchor=BOT);
            nema17_mount_mask(7.5);
        }
    }
}
fwd(2.5) xflip_copy() left(w)
    rod5(150,orient=FWD,anchor=BOT)
        attach(BACK,"groove") {
            fwd(70) back(8.5) sg15_2rs(spin=90);
            fwd(70) back(70) fwd(8.5) sg15_2rs(spin=90);
        }
up(5+4.65) fwd(7.5+8.5) rod5(w*2+10,orient=LEFT) {
    attach(RIGHT,"groove") {
        back(w-21+8.5) sg15_2rs(spin=90)
            attach(BOT) rod5(63,orient=DOWN,anchor=BOT);
        back(8.5) sg15_2rs(spin=90)
            attach(BOT) rod5(63,orient=DOWN,anchor=BOT);

    }
}
up(5+4.65) fwd(7.5-8.5+70) rod5(w*2+10,orient=LEFT) {
    attach(RIGHT,"groove") {
        back(w-21+8.5) sg15_2rs(spin=90);
        back(8.5) sg15_2rs(spin=90);
    }
}
down(2.5) fwd(6.5) xflip_copy() left(w) color_this("#bbb")
    fwd(70) ycopies(n=4,l=140,anchor=BACK)
    screw("M5,20",head="button",orient=DOWN,anchor=BOT)
        attach(BOT) down(2) color_this("#bbb") zrot(30) nut("M5",anchor=TOP);