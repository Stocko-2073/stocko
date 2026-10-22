include <fpc_camera.scad>

$fn=0; $fa=1; $fs=$preview?1:0.25;

// Example route: down the back of a 20 mm panel, then fold under it.
route=["move",10,"arcdown",2,90,"move",20,"arcdown",2,90,"move",25.2];
fpc_camera(route)
    attach("connector") color("#ccc",0.5) cuboid([6,15,3],anchor=BOT); // mating connector stand-in
echo(free_cable=path_length(fpc_camera_flex_path(route)),nominal=fpc_camera_flex_len);

// !fpc_camera();           // straight, as drawn
// !fpc_camera_head();      // head only
// !fpc_camera_flex(30);    // straight 30 mm cable with connector
