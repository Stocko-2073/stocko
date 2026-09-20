// Stubby RP-SMA male WiFi antenna: 28.4 mm overall, 7.9 mm body, 8.3 mm hex
// coupling nut.  Dimensions are from the vendor drawing.
//
// Coordinates: the axis is +Z.  Z=0 is the mating plane at the bottom of the
// coupling nut's bore, the body extends toward +Z to the tip and the nut's
// open end hangs below Z=0 by rpsma_antenna_bore_depth.  The attachable
// volume is the body from the mating plane to the tip, so `attach("face")
// rpsma_antenna()` on a pigtail mates it: BOT lands on the pigtail's face and
// the nut wraps the exposed thread.  Named anchors: "tip" (UP) and "nut" (the
// open end of the coupling nut, DOWN).
include <BOSL2/std.scad>

rpsma_antenna_len=28.4;
rpsma_antenna_body_d=7.9;
rpsma_antenna_body_len=20.3;
rpsma_antenna_nut_d=7.7;        // round part of the coupling nut
rpsma_antenna_nut_len=5.6;
rpsma_antenna_hex=8.3;          // across flats
rpsma_antenna_hex_h=rpsma_antenna_len-rpsma_antenna_body_len-rpsma_antenna_nut_len; // 2.5
rpsma_antenna_bore=[5.7,6];     // coupling nut bore [d, depth from the open end]
rpsma_antenna_bore_depth=rpsma_antenna_bore[1];
rpsma_antenna_tip_z=rpsma_antenna_len-rpsma_antenna_bore_depth; // 22.4
rpsma_antenna_ep=0.03;

module rpsma_antenna(anchor="origin", spin=0, orient=UP) {
    anchors=[
        named_anchor("tip",[0,0,rpsma_antenna_tip_z],UP),
        named_anchor("nut",[0,0,-rpsma_antenna_bore_depth],DOWN),
    ];
    attachable(anchor,spin,orient,d=rpsma_antenna_body_d,l=rpsma_antenna_tip_z,
               cp=[0,0,rpsma_antenna_tip_z/2],anchors=anchors) {
        _rpsma_antenna();
        children();
    }
}

module _rpsma_antenna() {
    z0=-rpsma_antenna_bore_depth;
    zhex=z0+rpsma_antenna_nut_len;
    zbody=zhex+rpsma_antenna_hex_h;
    color("#d4a017") difference() {
        union() {
            up(z0) cyl(d=rpsma_antenna_nut_d,h=rpsma_antenna_nut_len,chamfer1=0.3,anchor=BOT);
            up(zhex) cyl(d=rpsma_antenna_hex/cos(30),h=rpsma_antenna_hex_h,$fn=6,anchor=BOT);
        }
        up(z0-rpsma_antenna_ep) cyl(d=rpsma_antenna_bore[0],h=rpsma_antenna_bore_depth+rpsma_antenna_ep,anchor=BOT);
    }
    // Insulator with the female socket at the mating plane.
    color("#eee") difference() {
        cyl(d=4.1,h=1,anchor=TOP);
        down(1+rpsma_antenna_ep) cyl(d=0.9,h=1+2*rpsma_antenna_ep,anchor=BOT);
    }
    color("#444") up(zbody) difference() {
        cyl(d=rpsma_antenna_body_d,h=rpsma_antenna_body_len,rounding2=2.5,anchor=BOT);
        up(rpsma_antenna_body_len-3.2) torus(d_maj=rpsma_antenna_body_d,d_min=0.5);
    }
}
