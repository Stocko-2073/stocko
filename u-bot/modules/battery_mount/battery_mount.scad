include <BOSL2/std.scad>
include <../../../lib/globals.scad>
$fn=0;$fa=1;$fs=$preview?0.5:0.25;ep=0.01;$slop=0.2;

module battery_simplified(anchor="mount",spin=0,orient=UP) {
    h=12;
    yy=1;
    size=[73,134,32+h+5];
    c=[0,(32-102)/2,(h+5-32)/2]; // box centre in the battery's own frame
    // tongue root on the pack's top face; mates with battery_mount's "battery"
    anchors=[named_anchor("mount",-c,UP)];
    attachable(anchor,spin,orient,size=size,anchors=anchors) {
        tag_scope("battery_simplified") diff() move(-c) {
            color("#444") {
                back(12) cuboid([73,75+15+2+22,32],anchor=TOP+BACK,chamfer=5);
                back(2) up(15) cuboid([73,30,47],anchor=TOP+FWD,chamfer=5,except=[FWD+TOP]);
            }
            color("#888") {
                back(2) hull() {
                    up(15) cuboid([63,ep,ep],anchor=TOP+FWD);
                    cuboid([63,11,ep],anchor=BOT+BACK);
                }
                cuboid([37,60,h],anchor=BACK+BOT,chamfer=0.5,edges=[TOP+FWD]);
                cuboid([49,12,h],anchor=BACK+BOT,chamfer=0.5,edges=[TOP]);
                tag("keep") fwd(68) {
                    left(10) cuboid([2,5,4.5],anchor=BOT+FWD);
                    left(3.5) {
                        cuboid([2,5,2],anchor=BOT+FWD);
                        cuboid([4,2,2],anchor=BOT+FWD);
                    }
                    back(0.5) right(10) cuboid([1.5,4.5,4.5],anchor=BOT+FWD);
                }
                fwd(68) up(h) {
                    xcopies([-13.5,0,13.5]) {
                        tag("remove") {
                            up(ep) back(8-ep) {
                                cuboid([2.5,15,h],chamfer=0.5,edges=[BACK+LEFT,BACK+RIGHT],anchor=TOP+FWD);
                                xflip_copy() right(1.25) rounding_edge_mask(l=h,r=1,anchor=TOP);
                            }
                        }
                    }
                    xcopies([-6.5,6.5]) tag("remove") {
                        up(ep) back(8-ep) {
                            cuboid([4,15,3],chamfer=0.5,edges=[BACK+LEFT,BACK+RIGHT],anchor=TOP+FWD);                    
                            cuboid([2.5,15,h],chamfer=0.5,edges=[BACK+LEFT,BACK+RIGHT],anchor=TOP+FWD);                    
                        }
                    }
                    xflip_copy() right(34/2) {
                        hull() {
                            cuboid([2,68,h],anchor=TOP+FWD+LEFT,chamfer=0.5,edges=[TOP]);
                            back(4) cuboid([3,64,h],anchor=TOP+FWD+LEFT,chamfer=0.5,edges=[TOP]);
                        }
                        back(4) {
                            hull() {
                                cuboid([3,64,4.5],anchor=TOP+FWD+LEFT,chamfer=0.5,edges=[TOP,BOT]);
                                back(3.5) {
                                    cuboid([7.5,64,4.5],anchor=TOP+FWD+LEFT,chamfer=0.5,edges=[TOP,BOT]);
                                }
                            }
                            back(3.5+15) hull() {
                                cuboid([7.5,64-15,4.5],anchor=TOP+FWD+LEFT,chamfer=0.5,edges=[TOP,BOT]);
                                back(2) cuboid([7,62-15,6],anchor=TOP+FWD+LEFT,chamfer=0.5,edges=[TOP,BOT]);
                            }
                        }
                    }
                }
                tag("remove") {
                    fwd(6.5+yy) up(h+ep) {
                        cuboid([29+$slop*2,9.5,35+h],anchor=TOP+BACK);
                        down(2) back(2) cuboid([29+4+$slop*2,9.5+4,26+h],anchor=TOP+BACK,chamfer=2,edges=[TOP]);
                    }
                    down(32+ep) fwd(11.5) xflip_copy() left(15-2) cuboid([12,15,10],anchor=BOT+RIGHT,chamfer=2,edges="Z");
                }
            }
            tag("keep") color("#444") {
                fwd(6.5+yy) fwd($slop) up(h+ep) {
                    hull() 
                    {
                        cuboid([29,9.5-$slop*2,32+h],chamfer=0.5,anchor=TOP+BACK);
                        up(5) cuboid([29,0.5,35+h],chamfer=0.5,anchor=TOP+BACK,except=[FRONT]);
                    }
                    down(2+$slop) back(1.5) cuboid([29+3,9.5+3-$slop*2,26+h-$slop*2-5],anchor=TOP+BACK,chamfer=2,edges=[BOT,TOP]);
                }
            }
        }
        children();
    }
}

module battery_mount(channel_size=[1.2,15.5,50],chamfer=0,anchor=BOT+BACK,spin=0,orient=UP) {
    h=12;
    yy=1;
    size=[75,68,20];
    // where battery_simplified's "mount" anchor seats
    anchors=[named_anchor("battery",[0,size.y/2,-size.z/2],DOWN)];
    attachable(anchor,spin,orient,size=size,anchors=anchors) {
        render()
        tag_scope("battery_mount") diff() back(size.y/2) down(size.z/2) {
            cuboid(size,anchor=BOT+BACK,chamfer=chamfer,edges=[FWD+LEFT,FWD+RIGHT]);
            tag("remove") {
                fwd($slop) up(h+ep+$slop) {
                    fwd(6+yy) hull() 
                    {
                        cuboid([32,9.5,ep],anchor=TOP+BACK);
                        up(5) cuboid([32,1.5,5],anchor=TOP+BACK,except=[FRONT]);
                    }
                    hull() {
                        fwd($slop) cuboid([50,12-$slop,ep],anchor=TOP+BACK);
                        fwd(9) down(h+$slop) cuboid([50,3,ep],anchor=BACK+BOT);
                    }
                    fwd(12) {
                        hull() {
                            cuboid([50,31,6.5+$slop*2],anchor=TOP+BACK);
                            cuboid([50,33.5+$slop*2,4+$slop*2],anchor=TOP+BACK);
                        }
                        hull() {
                            cuboid([50,48.5+$slop,5.5],anchor=TOP+BACK);
                            cuboid([40+$slop*2,52.25+$slop,5.5],anchor=TOP+BACK);
                        }
                        cuboid([40+$slop*2,56+$slop,h+$slop],anchor=TOP+BACK);
                    }
                    // down(h+$slop) fwd(12) cuboid([50,60,6-$slop],anchor=BOT+BACK);
                }
                back(2) hull() {
                    up(15.5) cuboid([75,0.5,ep],anchor=TOP+BACK);
                    cuboid([75,11.75,ep],anchor=BOT+BACK);
                }
                back(2) up($slop) cuboid([75,105,5+$slop*2],anchor=TOP+BACK);
                fwd(68) xcopies([-13.5,0,13.5]) {
                    up(ep) back(8-ep+15/2+min(channel_size.y/2,15/2)) {
                        cuboid(channel_size,chamfer=0.5,edges=[BACK+LEFT,BACK+RIGHT],anchor=BACK+BOT);
                    }
                }
            }
        }
        children();
    }
}

!yrot(180) battery_mount(); // print
// xview()
// yview() back(10)
battery_simplified();
#battery_mount();