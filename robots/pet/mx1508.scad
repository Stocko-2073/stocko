include <BOSL2/std.scad>
$fn=0;$fa=1;$fs=$preview?0.5:0.0625;
ep=0.01;

module tht() {
    up(ep) tag("remove")
        cyl(d=2+ep,h=1.6+ep*2,anchor=TOP);
    tag("keep") color("#888") difference() {
        cyl(d=2,h=1.6,anchor=TOP);
        up(ep) cyl(d=1.1,h=1.6+ep*2,anchor=TOP);
    }
}

module cap() {
    color("#444") cuboid([6,6,1],chamfer=1.5,edges=[BACK+LEFT,BACK+RIGHT],anchor=BOT);
    color("#eee") cyl(d=5.8,h=6,anchor=BOT,chamfer2=0.5);
}

module mx1508() {
    in10th=2.54;
    size=[24.5,21,1.6];
    diff() {
        color("#833") cuboid(size,anchor=TOP);
        left(size.x/2) fwd(size.y/2-1) {
            right(2*in10th)
                ycopies([0,in10th,3+in10th,3+in10th*2]) tht(); 
            right(19.75)
                ycopies([0,in10th,3+in10th,3+in10th*2]) tht(); 
            back(9.75/2-0.5) right(13) {
                color("#444") cuboid([3,9.75,1.25],anchor=BOT);
                color("#888") ycopies(n=8,l=9) cuboid([5,0.5,0.5]);
            }
            right(5+3) back(12+3) {
                cap();
                right(6.5) zrot(180) cap();
            }
            right(1.5) back(in10th*6) {
                tht();
                back(in10th) tht();
            }
            right(2) back(12) tag("remove")
                up(ep) cyl(d=2.5,h=1.6+ep*2,anchor=TOP);
        }
        right(size.x/2) back(size.y/2-1) {
            left(4) fwd(4.5) {
                color("#eee") ycyl(d=1.25,3.5,anchor=BOT);
                color("#444") ycyl(d=1.5,3,anchor=BOT);
            }
            left(1.5) fwd(5) {
                color("#444") cuboid([1.25,2,0.5],anchor=BOT);
                color("#eee") cuboid([1.125,2.5,0.45],anchor=BOT);
            }
        }
    }
}
// !mx1508();
