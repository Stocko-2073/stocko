include <caster_as5600_mount.scad>

$fn=0; $fa=1; $fs=$preview?2:0.25; $slop=0.2;

caster_encoder();
up(5+caster_encoder_ep+$slop+6*caster_encoder_explode) caster_magnet_holder();

// !caster_as5600_mount(); // print left
// !xflip() caster_as5600_mount(); // print right
// !up(2) xrot(180) caster_as5600_mount_cap(); // print left
// !up(2) xrot(180) xflip() caster_as5600_mount_cap(); // print right
// !caster_magnet_holder(); // print
