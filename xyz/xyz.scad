include <BOSL2/std.scad>
include <BOSL2/screws.scad>
use <nema17.scad>
use <nema17_tr8.scad>
use <mini_chuck.scad>
use <drill_bit.scad>

$fn=0;$fa=1;$fs=$preview?0.5:0.25;
ep=0.01;
$slop=0.2;
wall=3;

module x_carriage(anchor=BOT,spin=0,orient=UP) {
    color_this("#848") attachable(anchor,spin,orient) {
        tag_scope() diff() yrot(-90) {
            d=24;
            xcyl(d=d,h=7,anchor=LEFT);
            cuboid([7,d,d/2+14+$slop],anchor=LEFT+BOT);
            up(d/2+14+$slop) {
                y=70+wall*2;
                right(7) {
                    cuboid([90+wall*2,y,wall*2],anchor=RIGHT+BOT);
                    yflip_copy() fwd(60/2+$slop) {
                        cuboid([90+wall*2,5.5,12],anchor=RIGHT+TOP+BACK);
                        tag("remove") back(3.5) down(1)cuboid([90+wall*2,5.5,10.5],anchor=RIGHT+TOP+BACK,chamfer=2,edges="X");

                    }
                    left(wall) up(wall) tag("remove") cuboid([90,70,wall+ep],anchor=RIGHT+BOT);
                }
            }
        }
        children();
    }
}

module y_carriage(anchor=BOT,spin=0,orient=UP) {
    attachable(anchor,spin,orient) {
        up(ep) color_this("#448") attachable(anchor,spin,orient) {
        tag_scope() diff() yrot(-90) {
            x=189;
            y=64;
            up(25) {
                cuboid([5.5,y-4,54],anchor=LEFT+TOP,chamfer=1,edges=[TOP+FWD,TOP+BACK]);
                xx=53.5;
                right(xx) xflip_copy() left(xx) down(54) {
                    cuboid([4+1.5,y-4,9.5],anchor=LEFT+TOP);
                    tag("remove") right(4-$slop) down(1) cuboid([4+1.5,y-4,9],chamfer=2,edges="Y",anchor=LEFT+TOP);
                }
                right(101.5) cuboid([5.5,y-4,54],anchor=LEFT+TOP,chamfer=1,edges=[TOP+FWD,TOP+BACK]);
                right(12.5) cuboid([x,y,10],chamfer=2,edges="X",anchor=TOP);
            }
            d=24;
            back(y/2-2) down(17+d/2) right(5) {
                // ycyl(d=d,h=7,anchor=LEFT+BACK);
                cuboid([d,7,54-1],rounding=8,edges=[BOT+RIGHT],anchor=LEFT+BACK+BOT);
            }
            tag("remove") right(5.5) cuboid([93.5,40,60-ep*2],anchor=LEFT);
        }
        children(); 
    }

        children();
    }
}

module m3_8(anchor=TOP,spin=0,orient=UP) {
    color_this("#ccc") screw("M3,8",head="socket",drive="hex",atype="threads",anchor=anchor,spin=spin,orient=orient);
}

module base(anchor=BOT,spin=0,orient=UP) {
    attachable(anchor,spin,orient) {
        tag_scope() diff() {
            color_this("#884") up(4) fwd((44)/2) {
                right(22+wall) cuboid([8+44+wall*2,44+wall,4.5+44+wall],anchor=TOP+FWD+RIGHT);
                down(5) left(10+wall) {
                    cuboid([99,9,147],anchor=BOT+FWD+LEFT,chamfer=2,edges="Z");
                }
            }
            // Z motor mount: a saddle on top of the Y motor housing, flush with its left
            // and back faces, drawn in the Z motor's frame (mount face at the origin,
            // screw along +Z). The assembly puts that motor at global (8.5,62,47) with
            // spin=180; this module hangs off the Y motor facing FWD, so here that is
            // (x-17, z+17, 39.5-y) with the screw along +Y and the motor's +X to the left.
            translate([-8.5,64,-22.5]) frame_map(x=LEFT,z=BACK) {
                color_this("#884") up(wall) fwd(wall/2+0.5-ep) cuboid([43+wall*2,43+wall,42],anchor=TOP);
                tag("remove") {
                    up(ep) back(ep) cuboid([43,20+43,42-wall+ep*2],anchor=TOP);   // just into the housing top
                    nema17_mount_mask(7+ep,anchor=BOT);
                    // slot for the pilot boss out the back edge, so the motor slides in from behind
                    down(ep) cuboid([22+0.5,25+ep,wall+ep*2],anchor=BACK+BOT);
                }
            }
            tag("remove") {
                nema17_mount_mask(7,anchor=BOT);
                cuboid([44,44+ep,40],anchor=TOP);
                down(30) cuboid([15,20+44+ep,60],anchor=TOP);
            }
            tag("keep") {
                up(4) {
                    fwd(15.5) left(15.5) m3_8();
                    back(15.5) left(15.5) m3_8();
                    back(15.5) right(15.5) m3_8();
                }
            }
        }
        children();
    }
}

// Z carriage: a block on the lead screw, clamped between the shipped nut on top and
// a brass nut underneath so the two nuts share the arm's moment, with a cantilever
// arm out to the spindle motor. TOP is the shipped nut's flange face (attach it to
// the screw's "nut_flange"); the block top sits one flange below it. Named anchors:
// "spindle" (motor mount face over the table, facing DOWN) and "nut2" (underside of
// the block, where the brass nut's flange bolts up).
// TODO: nothing stops the carriage turning with the screw yet; it needs a guide
module z_carriage(anchor=TOP,spin=0,orient=UP) {
    w=30;                   // block, square on the screw
    top=3.5;                // shipped nut's flange thickness, the block top is under it
    nut2=60;                // top flange face to the brass nut's stub end
    h=nut2-(1.5+3.5)-top;   // 51.5: block bottom is the brass nut's flange face (stub + flange)
    r=95;                   // screw axis to spindle axis
    t=wall*2;               // arm plate
    pad=42+wall*2;          // spindle motor pad
    skirt=15;               // arm depth at the pad
    anchors=[
        named_anchor("spindle",[0,r,(top+h)/2-top],DOWN),
        named_anchor("nut2",   [0,0,-(top+h)/2],DOWN),
    ];
    color_this("#488") attachable(anchor,spin,orient,size=[w,w,top+h],anchors=anchors) {
        tag_scope() diff() up((top+h)/2-top) {
            cuboid([w,w,h],anchor=TOP);
            // arm: plate on top, a web down each side tapering from the block to the pad
            back(w/2-ep) {
                cuboid([w,r-w/2,t],anchor=TOP+FWD);
                xflip_copy() right((w-wall)/2) hull() {
                    cuboid([wall,ep,h],anchor=TOP+FWD);
                    back(r-w/2-pad/2) cuboid([wall,ep,skirt],anchor=TOP+FWD);
                }
            }
            back(r) {
                cuboid([pad,pad,t],anchor=TOP);
                rect_tube(size=pad,wall=wall,h=skirt,anchor=TOP);
            }
            tag("remove") {
                up(top) zrot(45) tr8_nut_mount_mask(top+h,anchor=TOP);
                back(r) nema17_mount_mask(t,anchor=TOP);
            }
        }
        children();
    }
}

// Draw a square path: interpolate $t from 0 to 1 around the square
// This version ensures the value goes from 0 to the extent, rather than negative to positive

function square_interp(t, w, h) = 
    t < 0.25 ? [t*4*w, 0] :
    t < 0.5  ? [w, (t-0.25)*4*h] :
    t < 0.75 ? [w - (t-0.5)*4*w, h] :
               [0, h - (t-0.75)*4*h];

pos = square_interp($t, 84, 70);
pos_z=65.5+sin($t*360*6)*4+2;
up(32) fwd(33) right(8.5) color("red") sphere(2);
down(17) back(39.5) right(17) tag_scope() diff() {
    tag_this("keep") nema17_tr8(nut_pos=pos.y,nut_spin=45,orient=FWD) {
        attach(TOP) base();
        attach("nut_flange") {
            zrot(45) tag("remove") tr8_nut_mount_mask(30,anchor=BOT);
            
            xrot(-90) fwd(30) up(17) left(17) tag_scope() diff() 
            tag_this("keep") nema17_tr8(nut_pos=pos.x,nut_spin=45,orient=RIGHT) {
                attach("nut_flange") {
                    x_carriage();
                    zrot(45) tag("remove") tr8_nut_mount_mask(8,anchor=BOT);
                }
                attach(TOP) {
                    y_carriage();
                    tag("remove") {
                        nema17_mount_mask(7+ep,anchor=BOT);
                        cuboid([44,44,50],anchor=TOP);
                    }
                }
            }
        }
    }
}
// Z motor; its mount is part of base()
right(8.5) back(62) up(47)
nema17_tr8(nut_pos=pos_z,nut_spin=45,spin=180) {
    // Z carriage on the nut, carrying the pancake motor with the mini chuck on its
    // Ø5 shaft (bore is 12 deep) holding the 1/8" x 60 drill, shank pushed in to
    // the bit seat; the brass nut bolts up under the block
    attach("nut_flange") z_carriage() {
        attach("spindle") nema17_pancake()
            attach("shaft_tip") down(12) mini_chuck(bit=3.175,spin=90)
                position("bit_seat") drill_bit();
        attach("nut2","flange_top",spin=45) tr8_flange_nut("brass");
    }
}

//right(40) tr8_flange_nut("brass");


echo(str("\n",
"sh ./do_mp4.sh xyz.scad ",
$vpt[0],",",$vpt[1],",",$vpt[2],",",
$vpr[0],",",$vpr[1],",",$vpr[2],",",
$vpd,
"\n"));
