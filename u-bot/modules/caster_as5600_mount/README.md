# Caster AS5600 mount

[caster_as5600_mount.scad](caster_as5600_mount.scad) contains the caster encoder
mount, cap, magnet holder, PCB reference, assembly, and their shared dimensions.
[u-bot.scad](../../u-bot.scad) includes this file and places the encoder and
magnet holder on the caster as before.

Open [preview.scad](preview.scad) to view the encoder and magnet holder together.
Set `caster_encoder_explode=1` for an exploded view. The print calls at the
bottom select the left/right mount, inverted left/right cap, or magnet holder.
The mount and magnet holder print base-down; the cap prints inverted with its
outer face on the bed.

The module uses BOSL2 and the existing shared AS5600 board model in
`../../../lib/as5600.scad`. It does not duplicate that model, which is also
used by the drive axle encoders. Print clearances continue to use `$slop`
(0.2 mm in the preview and robot).
