// 24-pin FPC camera module (CV-JH640G2V1-T140 style: M7 lens, 120 deg FOV,
// 9 x 9 mm holder, 75 mm overall).  Dimensions are from ../../camera_design.jpg.
//
// Coordinates: optical axis is +Z and the lens looks toward +Z.  Z=0 is the
// back face of the holder, where the flex leaves the head.  The flex ribbon
// runs along -Y from the holder's edge (y=-4.5) by default; pass `route` as a
// turtle3d command list to bend it wherever it needs to go.  The turtle starts
// at the holder edge, heading away from the head (-Y), with its "up" toward the
// lens (+Z), so "arcup"/"arcdown" fold the ribbon toward/away from the lens
// and "arcleft"/"arcright" curve it sideways.
//
// fpc_camera() and fpc_camera_head() are BOSL2 attachables.  The attachable
// volume is the 9 x 9 holder from the flex pad back face to the lens front
// (the barrel overhangs it by 0.5 mm per side).  The default anchor "origin"
// leaves the model at the coordinates above.  Named anchors: "lens" (lens
// front centre, UP), "base" (top of the holder base, UP), "flex" (ribbon exit
// at the holder edge, FWD) and, on fpc_camera(), "connector" (centre of the
// connector tab's contact face, pointing away from the lens side).
include <BOSL2/std.scad>
include <BOSL2/turtle3d.scad>

fpc_camera_base=[9,9,1.9];      // holder base on the flex
fpc_camera_flange=[8,2.0];      // round boss [d,h]
fpc_camera_neck=[7,2.7];        // M7 lens thread [d,h]
fpc_camera_ring=[9,1.0];        // lens barrel step [d,h]
fpc_camera_barrel=[10,2.8];     // lens barrel [d,h]
fpc_camera_depth=fpc_camera_base.z+fpc_camera_flange[1]+fpc_camera_neck[1]
    +fpc_camera_ring[1]+fpc_camera_barrel[1]; // holder back to lens front, 10.4
fpc_camera_flex_w=6;
fpc_camera_flex_t=0.12;
fpc_camera_flex_len=61.5;       // nominal free cable, holder edge to connector
fpc_camera_conn=[12.5,4.5,0.35]; // [width, length, thickness with stiffener]
fpc_camera_pins=24;
fpc_camera_pitch=0.5;
fpc_camera_pin_w=0.3;
fpc_camera_pin_len=3;
fpc_camera_len=fpc_camera_base.y+fpc_camera_flex_len+fpc_camera_conn.y; // 75
fpc_camera_ep=0.03;

fpc_camera_flex_color="#a8702e";
fpc_camera_body_color="#222";

// Turtle state for the free cable: starts at the holder edge heading -Y, up=+Z.
function fpc_camera_flex_state(route=fpc_camera_flex_len) =
    turtle3d(is_num(route)?["move",route]:route,
        state=move([0,-fpc_camera_base.y/2,0])*zrot(-90), full_state=true);

// Centerline of the free cable, from holder edge to connector root.
function fpc_camera_flex_path(route=fpc_camera_flex_len) =
    deduplicate([for (T=fpc_camera_flex_state(route)[0]) apply(T,[0,0,0])]);

// Frame at the connector root: local +X along the cable, +Z toward the lens side.
function fpc_camera_flex_end(route=fpc_camera_flex_len) =
    last(fpc_camera_flex_state(route)[0]);

function _fpc_camera_sweep_transforms(s) = [for (i=idx(s[0])) s[0][i]*s[1][i]];

fpc_camera_size=[fpc_camera_base.x,fpc_camera_base.y,fpc_camera_depth+fpc_camera_flex_t];
fpc_camera_cp=[0,0,(fpc_camera_depth-fpc_camera_flex_t)/2];

// Named anchors; `s` is a turtle state from fpc_camera_flex_state() for the
// route-dependent "connector" anchor.
function fpc_camera_anchors(s) = [
    named_anchor("lens",[0,0,fpc_camera_depth],UP),
    named_anchor("base",[0,0,fpc_camera_base.z],UP),
    named_anchor("flex",[0,-fpc_camera_base.y/2,-fpc_camera_flex_t/2],FWD),
    if (is_def(s)) named_anchor("connector",
        rot=last(s[0])*move([fpc_camera_conn.y/2,0,-fpc_camera_flex_t])*xrot(180)),
];

module fpc_camera_head(anchor="origin", spin=0, orient=UP) {
    attachable(anchor,spin,orient,size=fpc_camera_size,cp=fpc_camera_cp,anchors=fpc_camera_anchors()) {
        _fpc_camera_head();
        children();
    }
}

module _fpc_camera_head() {
    b=fpc_camera_base;
    z1=b.z; z2=z1+fpc_camera_flange[1]; z3=z2+fpc_camera_neck[1];
    z4=z3+fpc_camera_ring[1]; z5=z4+fpc_camera_barrel[1];
    // Flex pad and sensor stiffener behind the holder.
    color(fpc_camera_flex_color) down(fpc_camera_flex_t)
        cuboid([b.x,b.y,fpc_camera_flex_t],rounding=0.5,edges="Z",anchor=BOT);
    color(fpc_camera_body_color) {
        cuboid(b,rounding=0.3,edges="Z",anchor=BOT);
        up(z1) cyl(d=fpc_camera_flange[0],h=fpc_camera_flange[1],anchor=BOT);
        up(z2) cyl(d=fpc_camera_neck[0],h=fpc_camera_neck[1],anchor=BOT);
        up(z3) cyl(d=fpc_camera_ring[0],h=fpc_camera_ring[1],anchor=BOT);
        up(z4) difference() {
            cyl(d=fpc_camera_barrel[0],h=fpc_camera_barrel[1],chamfer2=0.4,anchor=BOT);
            up(fpc_camera_barrel[1]-0.5) cyl(d=6.5,h=1,anchor=BOT);
        }
    }
    // Front element and aperture.
    color("#1a2a44") up(z5-0.5) cyl(d=6.5,h=0.2,anchor=BOT);
    color("#0a1020") up(z5-0.3) cyl(d=2.2,h=0.15,anchor=BOT);
    color("#334") up(z5-0.15) cyl(d=1.4,h=0.1,anchor=BOT);
}

// Connector tab in the local frame of the cable end: root at the origin,
// tab along +X, stiffener toward +Z (lens side), contacts on the -Z face.
module fpc_camera_connector() {
    c=fpc_camera_conn; t=fpc_camera_flex_t;
    color(fpc_camera_flex_color) down(t) {
        cuboid([c.y,c.x,c.z],rounding=0.5,edges=[RIGHT+FWD,RIGHT+BACK],anchor=LEFT+BOT);
        // Fillets where the 6 mm ribbon widens to the tab.
        yflip_copy() back(fpc_camera_flex_w/2) difference() {
            cuboid([1,1,t],anchor=LEFT+FWD+BOT);
            translate([-fpc_camera_ep,1,-fpc_camera_ep]) cyl(r=1,h=t+2*fpc_camera_ep,anchor=BOT);
        }
    }
    color("gold") down(t) for (i=[0:fpc_camera_pins-1])
        translate([c.y-0.3-fpc_camera_pin_len/2,(i-(fpc_camera_pins-1)/2)*fpc_camera_pitch,0])
            cuboid([fpc_camera_pin_len,fpc_camera_pin_w,0.03],anchor=TOP);
}

// Free cable plus connector.  `route` is a turtle3d command list (see header),
// or a number for a straight run of that length.
module fpc_camera_flex(route=fpc_camera_flex_len) {
    _fpc_camera_flex(fpc_camera_flex_state(route));
}

module _fpc_camera_flex(s) {
    len=path_length(deduplicate([for (T=s[0]) apply(T,[0,0,0])]));
    if (abs(len-fpc_camera_flex_len)>0.5)
        echo(str("fpc_camera_flex: route is ",len," mm, nominal cable is ",fpc_camera_flex_len," mm"));
    color(fpc_camera_flex_color)
        sweep(rect([fpc_camera_flex_t,fpc_camera_flex_w],anchor=LEFT),_fpc_camera_sweep_transforms(s));
    multmatrix(last(s[0])) fpc_camera_connector();
}

module fpc_camera(route=fpc_camera_flex_len, flex=true, anchor="origin", spin=0, orient=UP) {
    s=fpc_camera_flex_state(route);
    attachable(anchor,spin,orient,size=fpc_camera_size,cp=fpc_camera_cp,anchors=fpc_camera_anchors(s)) {
        union() {
            _fpc_camera_head();
            if (flex) _fpc_camera_flex(s);
        }
        children();
    }
}
