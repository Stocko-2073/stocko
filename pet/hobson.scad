include <BOSL2/std.scad>
$fn=0;$fa=1;$fs=$preview?0.5:0.0625;
ep=0.01;
$slop=0.2;

colors=["#585","#558","#555","#885","#858","#888"];

r=10;
r2=2;
r3=r-r2*2;

t=$t*360;

zrot(t) difference() {
    union() {
        color("#855") cyl(r=r,h=20,anchor=TOP);
        color("#633") down(ep)
            cyl(r=r+1,h=20,anchor=TOP,$fn=6);
    }
    up(ep) zrot_copies(n=6) fwd(r3)
        cyl(r=r2+$slop,h=20+ep*2,anchor=TOP);
}

left(r) up(r)
xrot(360-t) difference() {
    union() {
        color("#588") xcyl(r=r,h=20,anchor=RIGHT);
        color("#366") left(ep) 
            xcyl(r=r+1,h=20,anchor=RIGHT,$fn=6);
    }
    right(ep) xrot_copies(n=6) fwd(r-r2*2)
        xcyl(r=r2+$slop,h=20+ep*2,anchor=RIGHT);

}

for(i=[0:5]) zrot(t+i*60) up(r+(sin(t+i*60))*r3) {
    fwd(r-r2*2) zrot(-(t+i*60)) color(colors[i]) {
        cyl(r=r2,h=20+ep*2,anchor=TOP);
        xcyl(r=r2,h=20+ep*2,anchor=RIGHT);
        sphere(r=r2);
    }
}



























 
