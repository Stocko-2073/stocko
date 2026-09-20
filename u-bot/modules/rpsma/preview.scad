include <rpsma_pigtail.scad>
include <rpsma_antenna.scad>

$fn=0; $fa=1; $fs=0.25;

panel=1.5;
// Example route for a 150 mm pigtail: drop behind the panel, run along it, turn.
route=["move",15,"arcup",6,90,"move",40,"arcup",6,90,"move",30,"arcleft",6,90,"move",21.2];
rpsma_pigtail(route,cable_len=150,panel=panel,threads=true) {
    attach("face",BOT) rpsma_antenna();
    attach("terminal",BOT) color("green",0.5) cuboid([3,3,1.2]); // MHF4 board receptacle stand-in
}
echo(free_cable=path_length(rpsma_cable_path(route)),nominal=rpsma_route_len(150));

// !rpsma_pigtail();                 // straight 150 mm pigtail with hardware
// !rpsma_body(threads=true);        // receptacle only
// !rpsma_antenna();
// !rpsma_nut(); // !rpsma_spring_washer(); // !rpsma_lock_washer(); // !rpsma_mhf4();

// Panel the bulkhead mounts through.
color("#8ab4") difference() {
    cuboid([40,40,panel],anchor=BOT);
    cyl(d=6.5,h=3*panel);
}
