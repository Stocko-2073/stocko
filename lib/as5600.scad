module as5600(anchor,orient,spin,pins=true) {
    h=pins?12:3;
    attachable(anchor,orient,spin,size=[24,24,h],cp=[0,0,-(h/2)]) {
        color("#eee") down(1.5) {
            intersection() {
                translate([93.5,-104,-10.5]) import("AS5600.stl");
                up(1.5) cuboid([24,24,h],anchor=TOP);
            }
        }
        children();        
    }
}

