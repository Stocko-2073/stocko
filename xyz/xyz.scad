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
explode=0;    // pull the base plate this far off the tower, for looking at the joint
show_stage=true;   // draw the XY stage (off to look at the tower and plate on their own)

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
module m3(l=8,anchor=TOP,spin=0,orient=UP) {
    color_this("#ccc") screw(str("M3,",l),head="socket",drive="hex",atype="threads",anchor=anchor,spin=spin,orient=orient);
}
module m3_nut(anchor=BOT,spin=0,orient=UP) {
    color_this("#ccc") nut("M3",anchor=anchor,spin=spin,orient=orient);
}

// Base plate to tower joint, in the tower's frame (Y motor mount face at the origin,
// +Y up, +Z along the plate). The plate is x -13..86, y -22..-13 (9 thick, floor at
// -22), from the housing's front face at z=4. The tower grows a foot forward along the
// floor under the plate's end, the plate is recessed underneath to sit on it, and two
// M3x13 come up through the foot into nuts sitting on the plate's top; nut and screw
// end stand about 7 above the bed. The Y carriage's nut mount runs the length of the
// plate within 12 of the Y screw axis, and comes right up to the housing face, so nothing
// may stand on the bed inside x=+-12; the screws sit to the right of that, and the foot
// reaches out past the housing to carry them.
foot_x=[-7,60];         // foot across: 6 in from the plate's edge, 35 past the housing's side
foot_t=5;               // foot thickness, the plate is recessed this much to sit on it
foot_l=20;              // foot length forward of the housing face
foot_scr=[22,50];       // screw xs, both 12 forward of the housing face
foot_sz=4+12;
foot_cb=3.2;            // head counterbore in the foot's underside
hx=22+wall;             // the housing's +x face

// Tower: the Y motor housing with the Z motor saddle and its guide fins on top, one
// print. Its origin is the Y motor's mount face (attach it to the motor's TOP) with the
// motor inside; the base plate butts against its front face. Printed on its side so
// the fins' layer lines run along the slide.
module tower(anchor=BOT,spin=0,orient=UP) {
    attachable(anchor,spin,orient) {
        tag_scope() diff() {
            color_this("#884") up(4) fwd((44)/2)
                right(22+wall) cuboid([8+44+wall*2,44+wall,4.5+44+wall],anchor=TOP+FWD+RIGHT);
            // Z motor mount: a saddle on top of the Y motor housing, flush with its left
            // and back faces, drawn in the Z motor's frame (mount face at the origin,
            // screw along +Z). The assembly puts that motor at global (8.5,62,47) with
            // spin=180; this module hangs off the Y motor facing FWD, so here that is
            // (x-17, z+17, 39.5-y) with the screw along +Y and the motor's +X to the left.
            translate([-8.5,64,-22.5]) frame_map(x=LEFT,z=BACK) {
                fin_h=90;   // fins reach up to about the screw tip
                fin_fl=8;   // flange along each fin's back edge, turned inward: stiffens it, and
                            // is what the Z carriage hooks behind
                color_this("#884") fwd(wall/2+0.5-ep) {
                    up(wall) cuboid([43+wall*2,43+wall,42],anchor=TOP);
                    // the side walls carry on up as guide fins for the Z carriage to wrap;
                    // the flange stiffens each one, gives the carriage's hook wall a wide
                    // face to bear on, and stays clear of the motor sliding in
                    up(wall-ep) xflip_copy() right(43/2) {
                        cuboid([wall,43+wall,fin_h-wall+ep],anchor=BOT+LEFT);
                        fwd((43+wall)/2) cuboid([fin_fl,wall,fin_h-wall+ep],anchor=BOT+RIGHT+FWD);
                    }
                }
                tag("remove") {
                    up(ep) back(ep) cuboid([43,20+43,42-wall+ep*2],anchor=TOP);   // just into the housing top
                    nema17_mount_mask(7+ep,anchor=BOT);
                    // slot for the pilot boss out the back edge, so the motor slides in from behind
                    down(ep) cuboid([22+0.5,25+ep,wall+ep*2],anchor=BACK+BOT);
                }
            }
            // -- base plate joint, tower side: the foot, screwed up into the plate
            color_this("#884") {
                translate([(foot_x[0]+foot_x[1])/2,-22,4-ep]) cuboid([foot_x[1]-foot_x[0],foot_t,foot_l+ep],anchor=FWD+BOT);
                // gusset beside the housing under the part of the foot that reaches past it,
                // a 45 so the tower prints as drawn here (back face down) without support
                g=foot_x[1]-hx;
                translate([0,-22+foot_t,0]) xrot(90) linear_sweep([[hx,4],[hx+g,4],[hx,4-g]],height=foot_t);
            }
            for (x=foot_scr) translate([x,-22,foot_sz]) {
                tag("remove") down(ep) { ycyl(d=6.4,h=foot_cb+ep,anchor=FWD); ycyl(d=3.4,h=foot_t+2*ep,anchor=FWD); }
                tag("keep") back(foot_cb-ep) m3(13,orient=FWD);   // head just under the floor
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

// Base plate the Y carriage rides on, same origin as the tower; it starts at the
// tower's front face and runs out under the table.
module base_plate(anchor=BOT,spin=0,orient=UP) {
    attachable(anchor,spin,orient) {
        tag_scope() diff() {
            color_this("#a84") up(4) fwd(22) left(10+wall)
                cuboid([99,9,142],anchor=BOT+FWD+LEFT,chamfer=2,edges="Z");
            // -- joint, plate side: recess for the foot, screws through to nuts on top
            tag("remove") {
                translate([(foot_x[0]+foot_x[1])/2,-22-ep,4-ep])
                    cuboid([foot_x[1]-foot_x[0]+2*$slop,foot_t+$slop+ep,foot_l+$slop+ep],anchor=FWD+BOT);
                for (x=foot_scr) translate([x,-22-ep,foot_sz]) ycyl(d=3.4,h=9+2*ep,anchor=FWD);
            }
            tag("keep") for (x=foot_scr) translate([x,-13,foot_sz]) m3_nut(orient=BACK);
        }
        children();
    }
}

// Z carriage: a block standing on the shipped nut's flange, the nut under it so the
// carriage's weight seats it on the flange instead of hanging off screws threaded down
// into the block. It wraps the two fins on the Z motor mount as its linear guide (the way
// the X and Y carriages hook over their rails), with a cantilever arm out to the spindle
// motor. The spindle's weight pitches the block nose-down: its top pushes toward the
// table, its bottom away. The nut holds the bottom; a wall behind the fins' back edges,
// wrapping their flanges, holds the top, so the fin channels are open toward the table.
// BOT is the nut's flange face (attach it to the screw's "nut_flange"). Named anchor
// "spindle" is the motor mount face over the table, facing DOWN.
module z_carriage(anchor=BOT,spin=0,orient=UP) {
    h=51.5;                 // block height, and how much fin it grips
    front=15;               // block depth ahead of the screw axis: the nut flange plus a wall
    fin_x=43/2;             // fins' inner faces either side of the screw (the saddle pocket)
    fin_t=wall;             // fin thickness
    fin_back=25;            // fins' back edge, behind the screw
    fin_fl=8;               // the flange along that edge, turned inward
    hook=fin_back+$slop+wall;        // block's back face: the wall behind the fins' flanges
    bw=2*(fin_x+fin_t+$slop+wall);   // block wraps the fins with a wall outside each
    bd=hook+front;
    aw=30;                  // arm width
    r=95;                   // screw axis to spindle axis
    t=wall*2;               // arm plate
    pad=42+wall*2;          // spindle motor pad
    skirt=15;               // arm depth at the pad
    anchors=[named_anchor("spindle",[0,r,h/2],DOWN)];
    color_this("#488") attachable(anchor,spin,orient,size=[bw,bd,h],anchors=anchors) {
        tag_scope() diff() down(h/2) {
            fwd(hook) cuboid([bw,bd,h],anchor=BOT+FWD);
            up(h) {
                // arm: plate on top, a web down each side tapering from the block to the pad
                back(front-ep) {
                    cuboid([aw,r-front,t],anchor=TOP+FWD);
                    xflip_copy() right((aw-wall)/2) hull() {
                        cuboid([wall,ep,h],anchor=TOP+FWD);
                        back(r-front-pad/2) cuboid([wall,ep,skirt],anchor=TOP+FWD);
                    }
                }
                back(r) {
                    cuboid([pad,pad,t],anchor=TOP);
                    rect_tube(size=pad,wall=wall,h=skirt,anchor=TOP);
                }
            }
            tag("remove") {
                zrot(45) tr8_nut_mount_mask(h,anchor=BOT);
                up(h) back(r) nema17_mount_mask(t,anchor=TOP);
                // channels the fins run in: open toward the table, closed behind by the
                // hook wall, which wraps each fin's flange as well
                down(ep) fwd(fin_back+$slop) xflip_copy() {
                    right(fin_x-$slop) cuboid([fin_t+2*$slop,fin_back+$slop+front+ep,h+2*ep],anchor=BOT+FWD+LEFT);
                    right(fin_x-fin_fl-$slop) cuboid([fin_fl+2*$slop,wall+2*$slop,h+2*ep],anchor=BOT+FWD+LEFT);
                }
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
pos_z=10.5+sin($t*360*6)*4+2;   // nut under the block now: 55 lower (block plus flange) for the same spindle height
up(32) fwd(33) right(8.5) color("red") sphere(2);
down(17) back(39.5) right(17) tag_scope() diff() {
    tag_this("keep") nema17_tr8(nut_pos=pos.y,nut_spin=45,orient=FWD) {
        attach(TOP) { tower(); up(explode) base_plate(); }
        attach("nut_flange") {
            zrot(45) tag("remove") tr8_nut_mount_mask(30,anchor=BOT);
            
            if (show_stage) xrot(-90) fwd(30) up(17) left(17) tag_scope() diff() 
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
// Z motor; its mount is part of tower()
right(8.5) back(62) up(47)
nema17_tr8(nut_pos=pos_z,nut_spin=45,spin=180) {
    // Z carriage on the nut, carrying the pancake motor with the mini chuck on its
    // Ø5 shaft (bore is 12 deep) holding the 1/8" x 60 drill, shank pushed in to
    // the bit seat
    attach("nut_flange") z_carriage()
        attach("spindle") nema17_pancake()
            attach("shaft_tip") down(12) mini_chuck(bit=3.175,spin=90)
                position("bit_seat") drill_bit();
}

//right(40) tr8_flange_nut("brass");


echo(str("\n",
"sh ./do_mp4.sh xyz.scad ",
$vpt[0],",",$vpt[1],",",$vpt[2],",",
$vpr[0],",",$vpr[1],",",$vpr[2],",",
$vpd,
"\n"));
