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

// Fixed right/rear datum: x=4, y=35. Slots accept 89..92 x 69..72.
pb_floor=29.2;
pb_clamp_mounts=[[-95,-20],[-3,-44]];
pb_clamp_angles=[180,270];
function pb_center() = [4-pb_size.x/2,35-pb_size.y/2,pb_floor];
pb_clamp_height=5.6;

// Two identical clamps. Local +X points outward from the board edge.
// Print upside down: the top is flat and the 1.6 mm underside lip needs no support.
module board_clamp() {
    difference() {
        union() {
            translate([0,-5,2]) cube([18,10,pb_clamp_height-2]);
            translate([-1.2,-5,1.6]) cube([1.2+ep,10,pb_clamp_height-1.6]);
        }
        hull() for (x=[7,10]) translate([x,0,-ep])
            cylinder(d=3.4,h=pb_clamp_height+2*ep,$fn=32);
    }
}

module board_clamps() {
    assert(pb_size.x>=89 && pb_size.x<=92 && pb_size.y>=69 && pb_size.y<=72,
           "Board clamp range is 89..92 x 69..72 mm");
    translate([4-pb_size.x,-20,pb_floor]) zrot(180)
        asm("board_clamps",UP,20) color(color1) board_clamp();
    translate([-3,35-pb_size.y,pb_floor]) zrot(270)
        asm("board_clamps",UP,20) color(color1) board_clamp();
    for (a=pb_clamp_mounts) {
        translate([a.x,a.y,pb_floor-3]) asm("clamp_nuts",DOWN,15) m3_nut();
        translate([a.x,a.y,pb_floor+pb_clamp_height])
            asm("clamp_screws",UP,20,engage=8) m3(8);
    }
}

module x_carriage(anchor=BOT,spin=0,orient=UP) {
    color_this(color1) attachable(anchor,spin,orient) {
        tag_scope() diff() {
            tag("remove") zrot(45) tr8_nut_mount_mask(8,hole_d=m3_tap,anchor=BOT);
            yrot(-90) {
                d=24;
                xcyl(d=d,h=7,anchor=LEFT);
                cuboid([7,d,d/2+14+$slop],anchor=LEFT+BOT);
                up(d/2+14+$slop) {
                    // Floor and guide hooks retain their original height and rail fit.
                    translate([-42,-1,0]) cuboid([98,78,wall],anchor=BOT);
                    right(7) yflip_copy() fwd(60/2+$slop) {
                        cuboid([96,5.5,12],anchor=RIGHT+TOP+BACK);
                        tag("remove") back(3.5) down(1)
                            cuboid([96,5.5,10.5],anchor=RIGHT+TOP+BACK,chamfer=2,edges="X");
                    }
                    // Short datum walls leave the board corners unobstructed.
                    translate([5.5,0,wall]) cuboid([3,50,3],anchor=BOT);
                    translate([-41,36.5,wall]) cuboid([70,3,3],anchor=BOT);
                    // Left/front tabs with bottom-loading captive M3 nuts.
                    // Front tab ends at x=7, flush with the right-side print-bed face.
                    for (i=[0:1]) let(a=pb_clamp_mounts[i])
                    translate([a.x,a.y,wall+2]) {
                        zrot(pb_clamp_angles[i]) right(1.5) cuboid([17,20,5],anchor=TOP);
                        tag("remove") down(5+ep) {
                            cyl(d=3.4,h=5+2*ep,anchor=BOT);
                            cyl(d=5.8,h=2.6+ep,circum=true,$fn=6,anchor=BOT);
                        }
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
                cuboid([44,44,90],anchor=TOP);   // motor clearance, run out the plate's left end so the motor comes in along its axis
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
    zrot(45) zrot_copies(n=4) right(s[5]/2) down(s[4]) m3(8,orient=DOWN);
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
                cuboid([44,44+ep,-back_z+ep],anchor=TOP);   // motor pocket, open at the back so the motor slides in from behind
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
work_top=pb_floor+pb_size.z;    // tip Z of the top of the work: the protoboard on the pocket floor
depth=pb_size.z+1;        // through the board, plus the drill point so the hole is full size underneath
z_safe=work_top+6;        // tip height for XY moves
z_retract=work_top+1;     // retract plane: rapid down to here, feed from here
rapid_xy=60;              // mm/s
rapid_z=20;
feed_z=6;
dwell=0.1;
tip_to_nut=21;            // bit tip Z minus Z nut_pos
spindle_rpm=180;          // rounded to whole turns per cycle
function bit_on_board(xy) = [42-xy.x+(pb_size.x-90)/2, xy.y-35+(pb_size.y-70)/2];

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

// ---- animation mode -----------------------------------------------------------
anim="drill";      // "drill": the drilling cycle above; "assemble": the assembly sequence below
check=undef;       // -D 'check="z_carriage"': path check for that assembly step (./check_assembly.sh runs them all)
check_u=undef;     // with check: one position along the path (0 start, 1 seated) instead of the whole sweep

drilling = anim=="drill" && is_undef(check);
p = drilling ? demo_pos($t) : [42,35,z_safe+40];   // assembling: stage centered, Z run up for tool room
pos=[p.x,p.y];
pos_z=p.z-tip_to_nut;
demo_T=$t*demo_total;
drilled = drilling ? [for (i=idx(holes)) if (demo_T>=move_ends[5*i+1]) bit_on_board(holes[i])] : [];   // holes bottomed out so far
spindle_ang = drilling ? $t*round(demo_total*spindle_rpm/60)*360 : 0;

// ---- assembly sequence --------------------------------------------------------
// Every part in the scene is wrapped in asm(id, dir, dist): in the "assemble" animation
// the part appears `dist` along `dir` from where it seats and slides home during its step,
// and whatever is attached to it rides along, so the tree has to match the sequence: a
// part is fitted before anything attached to it. `dir` is in the frame asm() is called in;
// the world direction it amounts to is in each call's comment. `engage` is the length of
// path a screw spends in its tapped hole (or a nut on its thread); the path check stops
// there, since that overlap is the design. Steps run in this order: [id, seconds] or
// [id, seconds, appear], where `appear` names an earlier step at whose start this part is
// already visible, waiting at the start of its path, so parts can be fitted to it before
// it goes on (a sub-assembly built off the machine).
asm_steps=[
    ["tower",           0  ],
    ["y_motor",         1.0],
    ["y_motor_screws",  0.7],
    ["plate",           1.0],
    ["foot_screws",     0.7],
    ["foot_nuts",       0.7],
    ["z_motor",         1.0],
    ["z_motor_screws",  0.7],
    ["x_motor",         1.0],
    ["x_motor_screws",  0.7],
    ["clamp_nuts",      0.5],
    ["x_carriage",      1.0, "clamp_nuts"],   // load captive nuts while clear of the rails
    ["x_nut_screws",    0.7],
    ["y_carriage",      1.4, "x_motor"],   // hovers from the X motor step on, gets the X stage built onto it, then goes on
    ["y_nut_screws",    0.7],
    ["z_carriage",      1.2],
    ["z_nut_screws",    0.7],
    ["spindle",         1.0],
    ["spindle_screws",  0.7],
    ["chuck",           0.8],
    ["bit",             0.8],
    ["board",           0.8],
    ["board_clamps",    0.5],
    ["clamp_screws",    0.5],
];
asm_gap=0.15;     // pause between steps
asm_hold=1.5;     // hold on the finished machine
asm_ends=cumsum([for (s=asm_steps) s[1]+asm_gap]);
asm_total=last(asm_ends)+asm_hold;
asm_T=$t*asm_total;
check_step=2;     // the path check samples the part this far apart along its path
function asm_index(id) = let(f=[for (i=idx(asm_steps)) if (asm_steps[i][0]==id) i])
    assert(len(f)==1, str("asm: unknown step ",id)) f[0];
function asm_start(i) = asm_ends[i]-asm_steps[i][1]-asm_gap;
// where the part sits with `rem` of path still to travel: path is listed from the seat
// outward, so path[0] is the final approach
function asm_disp(path, rem) = rem<=0 || len(path)==0 ? [0,0,0] :
    let(n=norm(path[0])) n<=rem ? path[0]+asm_disp(list_tail(path), rem-n) : path[0]*rem/n;
// asm(id, dir, dist) for a straight approach, asm(id, path=[v0,v1,..]) for one with corners:
// v0 is the last move (the seat is at the origin), v1 the one before it, and so on
module asm(id, dir=UP, dist=0, path=undef, engage=0) {
    i=asm_index(id);
    st=asm_steps[i];
    pth = is_undef(path) ? [dir*dist] : path;
    total = sum([for (v=pth) norm(v)]);
    // the check looks at the scene as the checked step begins
    T = is_undef(check) ? asm_T : asm_start(asm_index(check));
    t0=asm_start(i);
    t_show = len(st)>2 ? asm_start(asm_index(st[2])) : t0;
    u = st[1]>0 ? constrain((T-t0)/st[1],0,1) : (T>=t0 ? 1 : 0);
    disp = asm_disp(pth,(1-smoothstep(u))*total);
    vis = T>=t_show;
    if (!is_undef(check)) {
        // two copies of the scene: the checked part swept along its path (with anything
        // fitted to it earlier), and everything fitted before it, in place. Hidden parts
        // still pass their placement down to what is attached to them.
        n=max(2,ceil((total-engage)/check_step)+1);
        rems=!is_undef(check_u) ? [(1-check_u)*total] : [for (k=[0:n-1]) engage+(total-engage)*k/(n-1)];
        if ($asm_role=="moving") {
            if (id==check) { $asm_in=true; for (r=rems) translate(asm_disp(pth,r)) children(); }
            else if ($asm_in && vis) translate(disp) children();
            else hide_this() translate(disp) children();
        } else {
            if (id==check || $asm_under) { $asm_under=true; hide_this() translate(disp) children(); }
            else if (vis) translate(disp) children();
            else hide_this() translate(disp) children();
        }
    } else if (anim=="assemble") {
        if (vis) translate(disp) children();
        else hide_this() translate(disp) children();
    } else children();
}

module scene(role="all") {
    $asm_role=role; $asm_in=false; $asm_under=false;
    // the tower is drawn in the Y motor's frame: origin on the mount face, screw out along
    // +z, which is the machine's front; +y is up
    down(17) back(35.5+hf) right(17) xrot(90) asm("tower") tower() {
        asm("y_motor", DOWN, 60) nema17_tr8(nut_pos=pos.y+mb,nut_spin=45) {         // DOWN: world +y; in through the open back of the housing, screw first
            attach("nut_flange") {
                asm("y_nut_screws", DOWN, 20, engage=8) tr8_nut_screws();           // DOWN: from the motor's side of the flange
                if (show_stage) xrot(-90) fwd(30) up(17) left(17+mb)                // world-aligned from here
                asm("y_carriage", path=[FWD*110, UP*60]) yrot(90) y_carriage() {    // built hovering out front, then down to the plate and back along it onto the screw and the rails
                    asm("x_motor", DOWN, 60) nema17_tr8(nut_pos=pos.x+mb,nut_spin=45) {   // DOWN: world -x; in from the left along its axis, under the plate
                        attach("nut_flange") {
                            asm("x_carriage", LEFT, 50) x_carriage()                // LEFT: world up, down over the Y carriage's rails
                                yrot(-90) {
                                    translate(pb_center())
                                        asm("board", UP, 40) protoboard(drilled=drilled);
                                    board_clamps();
                                }
                            asm("x_nut_screws", DOWN, 20, engage=8) tr8_nut_screws();   // DOWN: from the motor's side of the flange
                        }
                        attach(TOP) asm("x_motor_screws", UP, 20, engage=8)         // UP: world +x, from inside the carriage; heads sink into the wall
                            up(mp_under) grid_copies(spacing=31,n=2) m3_8();
                    }
                }
            }
        }
        asm("y_motor_screws", UP, 20, engage=6) up(hf-m3_head) grid_copies(spacing=31,n=2) m3(6);   // UP: from the front, flush in the housing face
        asm("plate", UP, 60) up(explode) base_plate();                              // UP: world -y; slid back under the screw and onto the foot
        asm("foot_screws", FWD, 25, engage=13)                                      // FWD: world down, up through the foot
            for (x=foot_scr) translate([x,-22,foot_sz]) back(foot_cb-ep) m3(13,orient=FWD);
        asm("foot_nuts", BACK, 20, engage=3) up(explode)                            // BACK: world up, onto the screw ends
            for (x=foot_scr) translate([x,-13,foot_sz]) m3_nut(orient=BACK);
        translate([-8.5,64,hf-26.5]) frame_map(x=LEFT,z=BACK)                        // the Z motor's frame
            asm("z_motor_screws", UP, 20, engage=8) up(mp_under) grid_copies(spacing=31,n=2) m3_8();   // UP: world up, down through the saddle top
    }
    // Z motor; its saddle is part of tower()
    right(8.5) back(62) up(47) asm("z_motor", BACK, 60) nema17_tr8(nut_pos=pos_z,nut_spin=45,spin=180) {   // BACK: in under the saddle top from behind
        attach("nut_flange") {
            asm("z_nut_screws", DOWN, 25, engage=8) tr8_nut_screws();               // DOWN: from below the flange
            asm("z_carriage", UP, 80) z_carriage() attach("spindle") {             // UP: down over the fins from the top
                asm("spindle_screws", UP, 20, engage=6)                             // UP: world down, up from inside the skirt
                    up(wall*2-m3_head) grid_copies(spacing=31,n=2) m3(6);
                asm("spindle", DOWN, 50) nema17_pancake()                           // DOWN: world up, onto the pad from above
                    attach("shaft_tip") down(12) asm("chuck", UP, 30, engage=12)    // UP: world down, pushed onto the shaft
                        mini_chuck(bit=3.175,spin=90+spindle_ang)
                            position("bit_seat") asm("bit", UP, 40, engage=30) drill_bit();   // UP: world down, shank up into the chuck
            }
        }
    }
}
if (is_undef(check)) scene();
if (!is_undef(check)) scene("moving");
if (!is_undef(check)) scene("fixed");

//right(40) tr8_flange_nut("brass");

// Printing
if(!is_undef(print)) {
    if (print=="board_clamp") !up(pb_clamp_height) xrot(180) board_clamp();
    if (print=="board_holder") !yrot(90) x_carriage() yrot(-90) {
        translate(pb_center()) protoboard();
        board_clamps();
    }
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
$vpd," ",ceil((anim=="assemble" ? asm_total : demo_total)*60),
"\n"));
