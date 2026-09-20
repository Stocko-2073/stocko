// RP-SMA female bulkhead to MHF4 pigtail (1/4-36 UNS threads, 8 mm hex,
// 0.81 mm cable).  Dimensions are from the vendor drawing; the cable length
// varies by product, so it is a parameter.
//
// Coordinates: the connector axis is +Z.  Z=0 is the front face of the hex
// flange (the panel's rear surface), the threads run to Z=rpsma_thread_len
// where the mating face is, and the cable leaves the heat shrink at
// Z=rpsma_cable_z heading -Z.  Pass `route` as a turtle3d command list for the
// cable: the turtle starts at the end of the heat shrink heading away from the
// connector (-Z) with its "up" toward +Y, so "arcup"/"arcdown" bend toward
// +Y/-Y and "arcleft"/"arcright" toward -X/+X.  A number is a straight run.
//
// rpsma_pigtail() and rpsma_body() are BOSL2 attachables whose volume is the
// threaded barrel: BOT is the panel plane, TOP the mating face and the sides
// the thread.  Named anchors: "face" (mating face, UP), "hex" (back of the hex
// flange, DOWN), "cable" (cable start, DOWN), "hardware" (top of the panel nut
// stack, UP) and, on rpsma_pigtail(), "terminal" (the MHF4 plug's mating face,
// pointing away from the cable's "up" side).
include <BOSL2/std.scad>
include <BOSL2/threading.scad>
include <BOSL2/turtle3d.scad>

rpsma_thread_d=6.35;            // 1/4-36 UNS-2A
rpsma_thread_pitch=25.4/36;
rpsma_thread_len=11;            // hex front to mating face, includes the lip
rpsma_lip=[5.8,1];              // plain lip [d,h] at the mating face
rpsma_hex=8;                    // across flats
rpsma_hex_h=2;
rpsma_bore=[4.6,4.5];           // socket bore [d,depth] with the male pin inside
rpsma_pin_d=0.9;
rpsma_ferrule=[3.2,5];          // crimp ferrule behind the hex [d,h]
rpsma_shrink=[3.6,2.6,12.5];    // heat shrink [d over ferrule, d over cable, length]
rpsma_cable_z=-rpsma_hex_h-rpsma_shrink[2];
rpsma_cable_d=0.81;
rpsma_mhf4=[2.0,1.2,3.0];       // MHF4 plug [head d, height, length along cable]
rpsma_mhf4_sleeve=[1.2,1.6];
rpsma_nut=[8,1.75];             // hex nut [across flats, h]
rpsma_spring_washer=[8.6,6.6,1];// [od,id,h]
rpsma_lock_washer=[10.2,8,6.5,0.5]; // [od, tooth root d, id, h]
rpsma_stack_h=rpsma_lock_washer[3]+rpsma_spring_washer[2]+rpsma_nut[1];
rpsma_ep=0.03;

rpsma_gold="#d4a017";
rpsma_black="#444";

// Free cable length for a given overall length (hex back face to MHF4 tip).
function rpsma_route_len(cable_len) = cable_len-rpsma_shrink[2]-rpsma_mhf4[2];

function rpsma_cable_state(route) =
    turtle3d(is_num(route)?["move",route]:route,
        state=move([0,0,rpsma_cable_z])*frame_map(x=DOWN,z=BACK), full_state=true);
function rpsma_cable_path(route) =
    deduplicate([for (T=rpsma_cable_state(route)[0]) apply(T,[0,0,0])]);
// Frame at the MHF4 root: local +X along the cable, +Z the cable's "up".
function rpsma_cable_end(route) = last(rpsma_cable_state(route)[0]);
function _rpsma_sweep_transforms(s) = [for (i=idx(s[0])) s[0][i]*s[1][i]];

function rpsma_anchors(panel=1.5, s) = [
    named_anchor("face",[0,0,rpsma_thread_len],UP),
    named_anchor("hex",[0,0,-rpsma_hex_h],DOWN),
    named_anchor("cable",[0,0,rpsma_cable_z],DOWN),
    named_anchor("hardware",[0,0,panel+rpsma_stack_h],UP),
    if (is_def(s)) named_anchor("terminal",
        rot=last(s[0])*move([rpsma_mhf4[2]-rpsma_mhf4[0]/2,0,-rpsma_mhf4[1]/2])*xrot(180)),
];

module _rpsma_attachable(anchor, spin, orient, anchors) {
    attachable(anchor,spin,orient,d=rpsma_thread_d,l=rpsma_thread_len,
               cp=[0,0,rpsma_thread_len/2],anchors=anchors) {
        children(0);
        children(1);
    }
}

// Receptacle, ferrule and heat shrink.  `threads=true` models the 1/4-36 thread.
module rpsma_body(threads=false, anchor="origin", spin=0, orient=UP) {
    _rpsma_attachable(anchor,spin,orient,rpsma_anchors()) {
        _rpsma_body(threads);
        children();
    }
}

module _rpsma_body(threads=false) {
    tl=rpsma_thread_len-rpsma_lip[1];
    color(rpsma_gold) {
        difference() {
            union() {
                down(rpsma_hex_h) cyl(d=rpsma_hex/cos(30),h=rpsma_hex_h,$fn=6,anchor=BOT);
                if (threads)
                    threaded_rod(d=rpsma_thread_d,pitch=rpsma_thread_pitch,l=tl,
                        bevel2=true,internal=false,anchor=BOT);
                else
                    cyl(d=rpsma_thread_d,h=tl,chamfer2=0.3,anchor=BOT);
                up(tl) cyl(d=rpsma_lip[0],h=rpsma_lip[1],chamfer2=0.2,anchor=BOT);
            }
            up(rpsma_thread_len-rpsma_bore[1]) cyl(d=rpsma_bore[0],h=rpsma_bore[1]+rpsma_ep,anchor=BOT);
        }
        up(rpsma_thread_len-rpsma_bore[1]) cyl(d=rpsma_pin_d,h=rpsma_bore[1]-0.8,chamfer2=0.3,anchor=BOT);
        down(rpsma_hex_h) cyl(d=rpsma_ferrule[0],h=rpsma_ferrule[1],anchor=TOP);
    }
    color("#eee") up(rpsma_thread_len-rpsma_bore[1]) cyl(d=rpsma_bore[0],h=0.5,anchor=BOT);
    color(rpsma_black) down(rpsma_hex_h) {
        cyl(d=rpsma_shrink[0],h=rpsma_ferrule[1]+0.5,anchor=TOP);
        down(rpsma_ferrule[1]+0.5) cyl(d1=rpsma_shrink[0],d2=rpsma_shrink[1],h=1,anchor=TOP);
        down(rpsma_ferrule[1]+1.5) cyl(d=rpsma_shrink[1],h=rpsma_shrink[2]-rpsma_ferrule[1]-1.5,anchor=TOP);
    }
}

module rpsma_nut(threads=false) {
    color(rpsma_gold)
        if (threads)
            threaded_nut(nutwidth=rpsma_nut[0],id=rpsma_thread_d,h=rpsma_nut[1],
                pitch=rpsma_thread_pitch,shape="hex",bevel=false,ibevel=false,anchor=BOT);
        else difference() {
            cyl(d=rpsma_nut[0]/cos(30),h=rpsma_nut[1],$fn=6,anchor=BOT);
            down(rpsma_ep) cyl(d=rpsma_thread_d,h=rpsma_nut[1]+2*rpsma_ep,anchor=BOT);
        }
}

module rpsma_spring_washer() {
    w=rpsma_spring_washer;
    color(rpsma_gold) difference() {
        tube(od=w[0],id=w[1],h=w[2],anchor=BOT);
        // Split ring.
        translate([w[0]/2,0,w[2]/2]) cuboid([w[0]-w[1]+1,0.5,w[2]+2*rpsma_ep]);
    }
}

module rpsma_lock_washer() {
    w=rpsma_lock_washer;
    color(rpsma_gold) {
        tube(od=w[0],id=w[1],h=w[3],anchor=BOT);
        // Internal teeth.
        zrot_copies(n=12) right((w[1]+w[2])/4+w[2]/4)
            xrot(20) cuboid([(w[1]-w[2])/2+0.2,0.9,w[3]],anchor=BOT);
    }
}

// Panel hardware stacked on the threads behind a panel of the given thickness.
module rpsma_hardware(panel=1.5, threads=false) {
    lw=rpsma_lock_washer[3]; sw=rpsma_spring_washer[2];
    up(panel) rpsma_lock_washer();
    up(panel+lw) rpsma_spring_washer();
    up(panel+lw+sw) rpsma_nut(threads);
}

// MHF4 plug in the cable-end frame: cable arrives along +X, root at the origin,
// mating face toward -Z.
module rpsma_mhf4() {
    m=rpsma_mhf4; s=rpsma_mhf4_sleeve;
    color(rpsma_gold) {
        xcyl(d=s[0],l=s[1],anchor=LEFT);
        difference() {
            right(m[2]-m[0]/2) down(m[1]/2) cyl(d=m[0],h=m[1],rounding2=0.2,anchor=BOT);
            right(m[2]-m[0]/2) down(m[1]/2+rpsma_ep) cyl(d=0.7,h=0.5,anchor=BOT);
        }
    }
    color(rpsma_black) right(m[2]-m[0]/2) up(m[1]/2-0.1) cyl(d=1.2,h=0.1+rpsma_ep,anchor=BOT);
}

module rpsma_cable(route, cable_len=150) {
    _rpsma_cable(rpsma_cable_state(is_undef(route)?rpsma_route_len(cable_len):route),cable_len);
}

module _rpsma_cable(s, cable_len) {
    len=path_length(deduplicate([for (T=s[0]) apply(T,[0,0,0])]));
    if (abs(len-rpsma_route_len(cable_len))>1)
        echo(str("rpsma_cable: route is ",len," mm, free cable for a ",cable_len," mm pigtail is ",rpsma_route_len(cable_len)," mm"));
    color(rpsma_black) sweep(circle(d=rpsma_cable_d),_rpsma_sweep_transforms(s));
    multmatrix(last(s[0])) rpsma_mhf4();
}

// Whole pigtail.  `route` defaults to a straight cable of `cable_len` overall.
// `panel` is the panel thickness the hardware stacks behind; `hardware=false`
// omits the washers and nut.
module rpsma_pigtail(route, cable_len=150, panel=1.5, hardware=true, threads=false,
                     anchor="origin", spin=0, orient=UP) {
    s=rpsma_cable_state(is_undef(route)?rpsma_route_len(cable_len):route);
    _rpsma_attachable(anchor,spin,orient,rpsma_anchors(panel,s)) {
        union() {
            _rpsma_body(threads);
            if (hardware) rpsma_hardware(panel,threads);
            _rpsma_cable(s,cable_len);
        }
        children();
    }
}
