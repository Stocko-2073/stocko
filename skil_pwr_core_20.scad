include <BOSL2/std.scad>
$fn=0;$fa=1;$fs=$preview?0.5:0.25;ep=0.01;$slop=0.2;
g1="#888";g2="#aaa";g3="#bbb";g4="#ccc";

function chord_sagitta_to_radius(chord, sagitta) =
    chord^2/(8*sagitta)+sagitta/2;

// 63 - 3,  117
diff() {
    hull() 
    {
        color("#8f8") back(107-90) intersection() {
            r=chord_sagitta_to_radius(63,3);
            fwd(r) back(90) {
                zcopies([0,31]) cyl(r=r,h=ep);
            }
            cuboid([63,90,100],anchor=FWD);
        }
        color(g1) up(19+9) back(7+9) cuboid([73.5,105-18,ep],anchor=FWD);
        color(g2) up(19) back(7) cuboid([73.5,105,ep],anchor=FWD);
        color(g2) up(19) back(7) cuboid([73.5-6,105+2,ep],anchor=FWD);
        color(g2) up(5) back(7-6) cuboid([48,105+6,ep],anchor=FWD);
        color(g2) up(0.5) back(7-6) cuboid([39,105+6,ep],anchor=FWD);
        color(g3) up(19) back(7-6) cuboid([48,105+6,ep],anchor=FWD);
        color(g3) up(9) back(7.5) cuboid([73.5,104,ep],anchor=FWD);
        color(g3) up(9) back(7.5) cuboid([73.5-6,104+2,ep],anchor=FWD);
        color(g4) up(3) back(7.5+7) cuboid([73.5,104-12,ep],anchor=FWD);
    }
}