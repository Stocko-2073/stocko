// Mechanism and assembly notes: MECHANISM.md

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
m3_tap=2.7;   // hole an M3 forms its own thread in, printed
mb=1; // how far back the X/Y motor sits in its mount
mp_under=4;
m3_head=3;    // socket head height
hf=4+mb;      // Y motor mount face to the housing's front face, where the base plate starts
yc_wall=5.5+mb;   // the Y carriage's X motor mount wall
explode=0;    // pull the base plate this far off the tower, for looking at the joint
show_stage=true;   // draw the XY stage (off to look at the tower and plate on their own)
pb_holes=false;    // draw the protoboard's pad grid (1600-odd parts: on for the video, off for working)

color1="#ccc";
color2="#f84";

module x_carriage(anchor=BOT,spin=0,orient=UP) {
    color_this(color1) attachable(anchor,spin,orient) {
        tag_scope() diff() {
            tag("remove") zrot(45) tr8_nut_mount_mask(8,hole_d=m3_tap,anchor=BOT);
            yrot(-90) {
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
        }
        children();
    }
}

module y_carriage(anchor=BOT,spin=0,orient=UP) {
    color_this(color2) attachable(anchor,spin,orient) {
        tag_scope() diff() {
            tag("remove") {
                nema17_mount_mask(yc_wall,cbore=yc_wall-mp_under,anchor=BOT);
                cuboid([44,44,50],anchor=TOP);
                yrot(-90) right(17+mb) back(30) down(17) xrot(90)
                    zrot(45) tr8_nut_mount_mask(30,hole_d=m3_tap,anchor=BOT);
            }
            up(ep) yrot(-90) right(mb) {
                x=189;
                y=64;
                up(25) {
                    left(mb) cuboid([yc_wall,y-4,54],anchor=LEFT+TOP,chamfer=1,edges=[TOP+FWD,TOP+BACK]);
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
module tr8_nut_screws() {
    s=tr8_nut_spec("motor");
    tag("keep") zrot(45) zrot_copies(n=4) right(s[5]/2) down(s[4]) m3(8,orient=DOWN);
}

foot_x=[-7,60];         // foot across: 6 in from the plate's edge, 35 past the housing's side
foot_t=5;               // foot thickness, the plate is recessed this much to sit on it
foot_l=20;              // foot length forward of the housing face
foot_scr=[22,50];       // screw xs, both 12 forward of the housing face
foot_sz=hf+12;
foot_cb=3.2;            // head counterbore in the foot's underside
hx=22+wall;             // the housing's +x face

module tower(anchor=BOT,spin=0,orient=UP) {
    saddle_z=hf-26.5;
    saddle_offset=wall/2+0.5-ep;
    back_z=saddle_z-(43+wall)/2-saddle_offset;
    attachable(anchor,spin,orient) {
        tag_scope() diff() {
            color_this(color1) up(hf) fwd((44)/2)
                right(22+wall) cuboid([8+44+wall*2,44+wall,hf-back_z],anchor=TOP+FWD+RIGHT);
            translate([-8.5,64,saddle_z]) frame_map(x=LEFT,z=BACK) {
                fin_h=90;   // fins reach up to about the screw tip
                zp=mp_under;   // saddle top plate, mount face to top: M3x8 heads on it get 4 in the motor
                fin_fl=8;   // inward flange width
                color_this(color1) fwd(saddle_offset) {
                    up(zp) cuboid([43+wall*2,43+wall,39+zp],anchor=TOP);
                    up(zp-ep) xflip_copy() right(43/2) {
                        cuboid([wall,43+wall,fin_h-zp+ep],anchor=BOT+LEFT);
                        fwd((43+wall)/2) cuboid([fin_fl,wall,fin_h-zp+ep],anchor=BOT+RIGHT+FWD);
                    }
                }
                tag("remove") {
                    up(ep) back(ep) cuboid([43,20+43,39+ep*2],anchor=TOP);   // just into the housing top
                    nema17_mount_mask(zp+ep,anchor=BOT);
                    down(ep) cuboid([22+0.5,25+ep,zp+ep*2],anchor=BACK+BOT);
                }
            }
            color_this(color1) {
                translate([(foot_x[0]+foot_x[1])/2,-22,hf-ep]) cuboid([foot_x[1]-foot_x[0],foot_t,foot_l+ep],anchor=FWD+BOT);
                g=foot_x[1]-hx;
                translate([0,-22+foot_t,0]) xrot(90) linear_sweep([[hx,hf],[hx+g,hf],[hx,hf-g]],height=foot_t);
            }
            for (x=foot_scr) translate([x,-22,foot_sz]) {
                tag("remove") down(ep) { ycyl(d=6.4,h=foot_cb+ep,anchor=FWD); ycyl(d=3.4,h=foot_t+2*ep,anchor=FWD); }
            }
            tag("remove") {
                nema17_mount_mask(hf,cbore=m3_head,anchor=BOT);
                cuboid([44,44+ep,40],anchor=TOP);
                down(30) cuboid([15,20+44+ep,60],anchor=TOP);
            }
        }
        children();
    }
}

module base_plate(anchor=BOT,spin=0,orient=UP) {
    attachable(anchor,spin,orient) {
        tag_scope() diff() {
            color_this(color1) up(hf) fwd(22) left(10+wall)
                cuboid([99,9,142],anchor=BOT+FWD+LEFT,chamfer=2,edges="Z");
            tag("remove") {
                translate([(foot_x[0]+foot_x[1])/2,-22-ep,hf-ep])
                    cuboid([foot_x[1]-foot_x[0]+2*$slop,foot_t+$slop+ep,foot_l+$slop+ep],anchor=FWD+BOT);
                for (x=foot_scr) translate([x,-22-ep,foot_sz]) ycyl(d=3.4,h=9+2*ep,anchor=FWD);
            }
        }
        children();
    }
}

// BOT: nut flange face; "spindle": motor mount face, facing DOWN.
module z_carriage(anchor=BOT,spin=0,orient=UP) {
    h=51.5;                 // block height, and how much fin it grips
    front=15;               // block depth ahead of the screw axis: the nut flange plus a wall
    fin_x=43/2;             // fins' inner faces either side of the screw (the saddle pocket)
    fin_t=wall;             // fin thickness
    fin_back=25;            // fins' back edge, behind the screw
    fin_fl=8;               // the flange along that edge, turned inward
    rib=3;                  // the fins ride on vertical ribs this wide at each end of each channel wall
    relief=1;               // the wall between the ribs stands this far off the fin
    hook=fin_back+relief+wall;       // block's back face: the wall behind the fins' flanges
    bw=2*(fin_x+fin_t+$slop+wall);   // block wraps the fins with a wall outside each
    bd=hook+front;
    aw=30;                  // arm width
    r=95;                   // screw axis to spindle axis
    t=wall*2;               // arm plate
    pad=42+wall*2;          // spindle motor pad
    skirt=15;               // arm depth at the pad
    anchors=[named_anchor("spindle",[0,r,h/2],DOWN)];
    attachable(anchor,spin,orient,size=[bw,bd,h],anchors=anchors) {
        tag_scope() diff() down(h/2) {
            color(color2) {
                fwd(hook) cuboid([bw,bd,h],anchor=BOT+FWD);
                up(h) {
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
            }
            tag("remove") {
                zrot(45) tr8_nut_mount_mask(h,hole_d=m3_tap,anchor=BOT);
                up(h) back(r) nema17_mount_mask(t,cbore=m3_head,anchor=BOT,orient=DOWN);
                cd=fin_back+relief+front+ep;     // channel depth, hook face to out the front
                down(ep) fwd(fin_back+relief) xflip_copy() difference() {
                    union() {
                        right(fin_x-relief) cuboid([fin_t+2*relief,cd,h+2*ep],anchor=BOT+FWD+LEFT);
                        right(fin_x-fin_fl-relief) cuboid([fin_fl+relief-$slop,wall+2*relief,h+2*ep],anchor=BOT+FWD+LEFT);
                    }
                    right(fin_x-$slop) cuboid([fin_t+2*$slop,relief-$slop,h+4*ep],anchor=BOT+FWD+LEFT);   // hook rib, behind the fin's edge
                    for (y=[0,cd-rib])                        // outer face: back and front ends
                        right(fin_x+fin_t+$slop) back(y) cuboid([relief,y==0?rib+relief-$slop:rib,h+4*ep],anchor=BOT+FWD+LEFT);
                    for (y=[wall+2*relief,cd-rib])            // inner face: just ahead of the flange, and the front
                        right(fin_x-$slop) back(y) cuboid([relief,rib,h+4*ep],anchor=BOT+FWD+RIGHT);
                }
            }
        }
        children();
    }
}

pb_size=[90,70,1.6];
pb_pitch=2.54;
pb_n=[33,25];
pb_col="#a67233";
module protoboard(drilled=[], d=3.175, anchor=BOT, spin=0, orient=UP) {
    attachable(anchor,spin,orient,size=pb_size) {
        down(pb_size.z/2) difference() {
            union() {
                color(pb_col) cuboid(pb_size,anchor=BOT);
                if (pb_holes) up(pb_size.z) grid_copies(spacing=pb_pitch,n=pb_n) {
                    color("#dca070") cyl(d=1.9,h=0.1,anchor=BOT);
                    color("#2a1a0e") cyl(d=1,h=0.15,anchor=BOT);
                }
            }
            for (h=drilled) translate(h) color(pb_col) cyl(d=d,h=pb_size.z*3);
        }
        children();
    }
}

holes=[[8,8],[76,8],[42,35],[8,62],[76,62]];   // [x,y] table travel, in drilling order
work_top=29+pb_size.z;    // tip Z of the top of the work: the protoboard on the pocket floor
depth=pb_size.z+1;        // through the board, plus the drill point so the hole is full size underneath
z_safe=work_top+6;        // tip height for XY moves
z_retract=work_top+1;     // retract plane: rapid down to here, feed from here
rapid_xy=60;              // mm/s
rapid_z=20;
feed_z=6;
dwell=0.1;
tip_to_nut=21;            // bit tip Z minus Z nut_pos
spindle_rpm=180;          // rounded to whole turns per cycle
function bit_on_board(xy) = [42-xy.x, xy.y-35];

function smoothstep(u) = u*u*(3-2*u);
// Move: [duration, end point [x,y,tipz], eased?].
function drill_moves(i) = let(h=holes[i], n=holes[(i+1)%len(holes)]) [
    [(z_safe-z_retract)/rapid_z,       [h.x,h.y,z_retract],       true ],
    [(z_retract-(work_top-depth))/feed_z, [h.x,h.y,work_top-depth], false],
    [dwell,                             [h.x,h.y,work_top-depth], false],
    [(z_safe-(work_top-depth))/rapid_z, [h.x,h.y,z_safe],         true ],
    [norm(n-h)/rapid_xy,                [n.x,n.y,z_safe],         true ],
];
moves=[for (i=[0:len(holes)-1]) each drill_moves(i)];
move_ends=cumsum([for (m=moves) m[0]]);
demo_total=last(move_ends);
function demo_pos(t) = let(
        T=min(t*demo_total, demo_total-ep),
        k=[for (i=idx(moves)) if (T<move_ends[i]) i][0],
        t0=k==0 ? 0 : move_ends[k-1],
        a=k==0 ? [holes[0].x,holes[0].y,z_safe] : moves[k-1][1],
        b=moves[k][1],
        u=moves[k][0]<=0 ? 1 : (T-t0)/moves[k][0]
    ) lerp(a, b, moves[k][2] ? smoothstep(u) : u);

p=demo_pos($t);
pos=[p.x,p.y];
pos_z=p.z-tip_to_nut;
demo_T=$t*demo_total;
drilled=[for (i=idx(holes)) if (demo_T>=move_ends[5*i+1]) bit_on_board(holes[i])];   // holes bottomed out so far
spindle_ang=$t*round(demo_total*spindle_rpm/60)*360;
down(17) back(35.5+hf) right(17) tag_scope() diff() {
    tag_this("keep") nema17_tr8(nut_pos=pos.y+mb,nut_spin=45,orient=FWD) {
        attach(TOP) {
            tower();
            tag("keep") {
                translate([-8.5,64,hf-26.5]) frame_map(x=LEFT,z=BACK)
                    up(mp_under) grid_copies(spacing=31,n=2) m3_8();
                for (x=foot_scr) translate([x,-22,foot_sz]) back(foot_cb-ep) m3(13,orient=FWD);
                up(hf-m3_head) grid_copies(spacing=31,n=2) m3(6);
            }
            up(explode) {
                base_plate();
                tag("keep") for (x=foot_scr) translate([x,-13,foot_sz]) m3_nut(orient=BACK);
            }
        }
        attach("nut_flange") {
            tr8_nut_screws();
            
            if (show_stage) xrot(-90) fwd(30) up(17) left(17+mb) tag_scope() diff() 
            tag_this("keep") nema17_tr8(nut_pos=pos.x+mb,nut_spin=45,orient=RIGHT) {
                attach("nut_flange") {
                    x_carriage() yrot(-90) up(29.2) left(41) protoboard(drilled=drilled);
                    tr8_nut_screws();
                }
                attach(TOP) {
                    y_carriage();
                    tag("keep") up(mp_under) grid_copies(spacing=31,n=2) m3_8();   // heads sunk into the wall
                }
            }
        }
    }
}
right(8.5) back(62) up(47)
nema17_tr8(nut_pos=pos_z,nut_spin=45,spin=180) {
    attach("nut_flange") {
        tr8_nut_screws();
        z_carriage() attach("spindle") {
            up(wall*2-m3_head) grid_copies(spacing=31,n=2) m3(6);
            nema17_pancake()
                attach("shaft_tip") down(12) mini_chuck(bit=3.175,spin=90+spindle_ang)
                    position("bit_seat") drill_bit();
        }
    }
}

//right(40) tr8_flange_nut("brass");

// Printing
if(!is_undef(print)) {
    if (print=="x_carriage") !yrot(180) x_carriage();
    if (print=="y_carriage") !yrot(-90) y_carriage();
    if (print=="tower") !tower();
    if (print=="base_plate") !xrot(-90) base_plate();
    if (print=="z_carriage") !xrot(180) z_carriage();
}

echo(str("\n",
"sh ./do_mp4.sh xyz.scad ",
$vpt[0],",",$vpt[1],",",$vpt[2],",",
$vpr[0],",",$vpr[1],",",$vpr[2],",",
$vpd," ",ceil(demo_total*60),
"\n"));
