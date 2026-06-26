include <MCAD/servos.scad>
include <customizable-servo-arm.scad>
include <BOSL2/std.scad>
$fn=0;$fa=1;$fs=$preview?0.5:0.25;ep=0.01;

module sg90() {
    towerprosg90([0,0,26.7],[180,0,0],0,0,1);
    down(4.5) children();
}

module as5600() translate([93.5,-104,-10.5]) %import("AS5600.stl");
module magnet() color("#888") %cyl(d=4,l=1,anchor=TOP);

module body() {
    up(12) left(6) difference() {
        cuboid([43.7,24,36.5],anchor=LEFT+TOP);
        up(ep) right(3)
            cuboid([22,30,34],anchor=LEFT+TOP,chamfer=3,edges=[BOT+LEFT]);
        right(25-ep) down(5.8) cuboid([16,30,23.1],anchor=LEFT+TOP);
        back(12+ep) right(41-ep) up(ep) cuboid([10,15+ep,23.1],anchor=RIGHT+TOP+BACK);
        down(12) yflip_copy() zflip_copy() back(8) up(8) xcyl(d=4,h=12);
        right(20) down(17.5) zflip_copy() down(13.5) xcyl(d=2,h=12,anchor=LEFT);
        down(31) xcyl(d=4,h=20);
    }
}

module arm() {
    magnet_slop=0.2;
    color("#848") difference() {
        right(6.5) 
            cuboid([35,10,3],anchor=RIGHT+TOP,rounding=5,edges=[FWD+RIGHT,BACK+RIGHT]);
        down(2) cyl(d=4+magnet_slop,l=10,anchor=TOP);
        left(16)cyl(d=1.5,l=10);
    }
    children();
}

body();
right(8) yrot(90) sg90() {
    render() zrot(180) servo_arm(SG90_SPLINE,arm_length=16);
    arm() magnet();
}

left(1.5) yrot(90) as5600();