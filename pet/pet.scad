include <BOSL2/std.scad>
include <BOSL2/gears.scad>
include <BOSL2/screws.scad>
include <BOSL2/ball_bearings.scad>
include <../cad-practice/globals.scad>
include <mx1508.scad>
$fn=0;$fa=1;$fs=$preview?0.5:0.0625;
$slop=0.25;
nozzle=0.4;
layer=0.2;
ep=0.01;

theta = asin(40 / 45);
x=13+2.5;
wall=nozzle*2;

color1="#555";
color2="#785";

module as5600() {
    render() down(1.5) {
        color("#444") %zview()
            translate([93.5,-104,-10.5]) import("AS5600.stl");
        color("#eee") %down(1.5) zview() up(1.5) zview(true)
            translate([93.5,-104,-10.5]) import("AS5600.stl");
        *color("#444") down(1.5) zview(true) up(1.5)
            translate([93.5,-104,-10.5]) import("AS5600.stl");
    }
}

module magnet() {
    color("#888") %cyl(d=4,l=1,anchor=BOT);
}

module xiao_sense(camera_angle=180,camera_z=-1) {
    camera_offset = [-0.66,-4.1,0.9-1+camera_z];
    left(0.66) up(2) back(4) xrot(camera_angle) yrot(180) {
        color("#dc9") render()
        difference() {
            yrot(-90) fwd(12) up(6.75) left(8.75) import("xiao_sense.stl");
            fwd(6.1) down(3.1) {
                cuboid([15,2,10],anchor=FWD+BOT);
                up(10) cuboid([15,10,2.5],anchor=FWD+TOP);
            }
            fwd(12-7.95+ep)cuboid([8+ep,6+ep,8+ep],anchor=FWD);
        }
        color("#444") move(camera_offset) xrot(camera_angle) zrot(180) left(4) render() intersection() {
            up(6.75) left(4.75) fwd(7.95) import("xiao_sense.stl");
            cuboid([8,6,8],anchor=LEFT+FWD);
        }
    }
}

module inr14500() {
    %up(25) union() {
        color("#748d") cyl(d=14,h=50-ep, chamfer=0.5);
        color("#888d") cyl(d=11,h=50);
        color("#888d") up(25) cyl(d=5,h=2,anchor=BOT,chamfer2=0.5);
    }
}

module battery_tab_vcc() {
    %color("#888d") render() {
        difference() {
            union() {
                cuboid([12,12,0.25],rounding=1,edges="Z",anchor=BOT);
                left(6) cuboid([7,3,0.25],rounding=1.5,edges=[LEFT+FWD,LEFT+BACK],anchor=BOT+RIGHT);
                up(0.25) {
                    cyl(d1=7,d2=4,h=1.6,rounding1=-1,rounding2=1,anchor=BOT);
                    yflip_copy() fwd(5.75) cuboid([2.5,1,0.75],chamfer=0.75,edges=[LEFT+TOP,RIGHT+TOP],anchor=BOT+FWD);
                }
            }
            down(ep) {
                cyl(d1=7,d2=4,h=1.6,rounding1=-1,rounding2=1,anchor=BOT);
                yflip_copy() fwd(5.75) cuboid([2.5,1,0.75],chamfer=0.75,edges=[LEFT+TOP,RIGHT+TOP],anchor=BOT+FWD);
                left(6+7-1.5) cyl(d=1.25,h=1);
            }
        }
    }
}

module battery_tab_gnd() {
    %color("#888d") render() {
        difference() {
            union() {
                cuboid([12,12,0.25],rounding=1,edges="Z",anchor=BOT);
                left(6) cuboid([7,3,0.25],rounding=1.5,edges=[LEFT+FWD,LEFT+BACK],anchor=BOT+RIGHT);
                up(0.25) {
                    cyl(d1=7,d2=6,h=4,rounding=0.25, anchor=BOT);
                    yflip_copy() fwd(5.75) cuboid([2.5,1,0.75],chamfer=0.75,edges=[LEFT+TOP,RIGHT+TOP],anchor=BOT+FWD);
                }
            }
            down(ep) {
                up(0.25+ep) {
                    cyl(d1=6,d2=5,h=5,rounding=-0.25, anchor=BOT);
                }
                cyl(d=2.5,h=1,anchor=BOT);
                yflip_copy() fwd(5.75) cuboid([2.5,1,0.75],chamfer=0.75,edges=[LEFT+TOP,RIGHT+TOP],anchor=BOT+FWD);
                left(6+7-1.5) cyl(d=1.25,h=1);
            }
        }
    }
}

module battery_tab_neg(len=2,top=false,bot=true) {
    cuboid([12,12,1+$slop],anchor=BOT);
    cyl(d=7,h=6,anchor=BOT);
    if(bot) cuboid([len+6,7,6],anchor=BOT+LEFT);
    if(top) cuboid([len+6,7,6],anchor=BOT+RIGHT);
    left(6-ep) cuboid([len+ep,3,1+$slop],anchor=BOT+RIGHT);
    right(6-ep) cuboid([len+ep,12,1+$slop],anchor=BOT+LEFT);
}
*!union() {
    battery_tab_vcc();
    battery_tab_gnd();
    #%battery_tab_neg();

}

module form(x,wall,with_foot=true) {
    up(2) difference() {
        intersection() {
            hull() {
                back(8-wall) {
                    cuboid([x,35+15,2+wall],anchor=FWD+TOP+LEFT);
                    if(with_foot) right(x)down(2+wall)
                        cuboid([x*3/4,35+15,1],anchor=FWD+TOP+RIGHT);
                }
                xrot(theta) back(16-wall) {
                   cuboid([x,28.75+10,2+wall],anchor=FWD+BOT+LEFT,chamfer=1,edges=[RIGHT+TOP]);
                }
            }
            left(ep) fwd(13) down(11.25) 
                xcyl(r=61+wall,h=x+ep*2,anchor=LEFT,chamfer2=1);
        }
        left(ep) fwd(13) if(with_foot) {
            down(0.3) xcyl(r=24.8-wall,h=x/4+ep*2,anchor=LEFT);
            fwd(18) xcyl(r=40-wall,h=x+ep*2,anchor=LEFT);
        } else {
            down(0.3) xcyl(r=25-wall,h=x+ep*2,anchor=LEFT);            
        }
        xrot(theta) back(16+29+wall) right(x) up(2+wall) 
            rounding_edge_mask(r=2.5,h=20,chamfer2=1,excess=1,orient=RIGHT,spin=-90,anchor=TOP);
    }
}

module body(x,wall) {
    xflip_copy() right($slop/2)
    // right(wall*2+0.5-$slop/2) yrot(90) // print
    difference() {
        union() {
            form(x,wall);
            back(12-wall) down(wall*2+0.5) right(1-$slop) cuboid([nozzle*2,30,2],anchor=FWD+BOT+RIGHT);
        }
        left(wall)form(x+ep,ep,false);
        back(40) down(2+ep) right(5-ep) 
            cuboid([5+ep,12,7+ep],anchor=FWD+BOT+RIGHT);
        up(2) xrot(theta) back(17) up(2) left(ep)
            cuboid([19/2,13+ep,2+wall],anchor=FWD+BOT+LEFT,chamfer=wall,
                edges=[BOT+FWD,BOT+BACK,BOT+RIGHT]);
    }
}

module hat(x,wall) {
    xflip_copy() {
        difference() {
            union() {
                form(x,wall);
                back(12-wall) down(wall*2+0.5) right(1-$slop) cuboid([nozzle*2,30,2],
                    anchor=FWD+BOT+RIGHT);
            }
            difference() {
                xrot(theta) back(16-wall) up(wall) intersection() {
                    back(4) ycopies(n=9,l=25,sp=[0,0,0]) cuboid([x-wall,wall,2+wall],anchor=FWD+BOT+LEFT);
                    back(3) right(20) cyl(d=50,h=2+wall+ep,anchor=BOT);
                }
                up(2) xrot(theta) back(17-wall/2) up(2) left(ep)
                    cuboid([(19+wall*2)/2,13+ep+wall*1.5,2+wall],anchor=FWD+BOT+LEFT,chamfer=wall,
                        edges=[BOT+FWD,BOT+BACK,BOT+RIGHT]);
            }
            left(wall) form(x+ep,wall/2+$slop);
            down(38.4) back(8) xcyl(d=110,h=x*2+$slop,chamfer=-1);
            up(5-15) yrot(90) cuboid([30,60,x*2+$slop],anchor=FWD,chamfer=-1);
            back(40) down(2+ep) right(5-ep) 
                cuboid([5+ep,12,7+ep],anchor=FWD+BOT+RIGHT);
            up(2) xrot(theta) back(17-wall/2) up(2) left(ep)
                cuboid([19/2+wall/2,13+ep+wall,2+wall],anchor=FWD+BOT+LEFT,chamfer=wall,
                    edges=[BOT+FWD,BOT+BACK,BOT+RIGHT]);
            left(ep) fwd(13) down(11.25) xrot(106.75) yrot(-90)
                pie_slice(r=64+wall,h=x-wall,ang=-40,anchor=TOP);
        }
    }
    difference() {
        intersection() {
            xflip_copy() left(ep) fwd(13) down(11.25) xrot(106.75) yrot(-90)
                zrot(-15) xrot(17) zrot(15)
                zcopies(n=6,l=x*2) zrot(10) pie_slice(r=64+wall,h=wall,ang=-60,anchor=TOP);
            left(ep) fwd(13) down(11.25) xrot(106.75) yrot(-90)
                down(x-wall) back(2) zrot(1.8) pie_slice(r=63.3,h=x*2-wall*2,ang=-41);
        }
        left(ep) fwd(13) down(11.25+ep) {
            xrot(100) yrot(-90) down(x-wall) back(2) zrot(1.8)
                pie_slice(r=64.2-wall,h=x*2-wall*2,ang=-60);
            xcyl(d=20,l=x*3);
        }
    }
}
// !xrot(180-theta)render() hat(x+wall*2,wall*2+$slop); // print

*fwd(25) render() {
    color("#eee") body(x,wall);
    color("#B63") hat(x+wall*2,wall*2+$slop);
}





module n20(a=0) {
    color("#888") %nop() {
        cuboid([12,9,10],rounding=0.5,edges="Y",anchor=FWD);
        ycyl(d=4,h=1,anchor=BACK);
        yrot(a) difference() {
            ycyl(d=3,h=10,anchor=BACK);
            fwd(4) left(0.75) cuboid([2,7,4],anchor=RIGHT+BACK);
        }
        back(9) {
            intersection() {
                ycyl(d=12,h=15,anchor=FWD);
                cuboid([12,15,10],anchor=FWD);
            }
            back(15) {
                ycyl(d=5,h=1.5,anchor=FWD,rounding2=0.5);
                xflip_copy() left(4) ycyl(d=1,h=2,anchor=FWD);
            }
        }
    }
    children();
}
// !n20();

module drive_gear(a) {
    yrot(a) color("#588") difference() {
        fwd(10) crown_gear(spin=24,mod=0.8,teeth=8,backing=7.5,face_width=2,orient=FWD);
        difference() {
            ycyl(d=3+$slop,h=20,anchor=BACK);
            fwd(4) left(0.75+$slop)
                cuboid([2,17,4],anchor=RIGHT+BACK);
        }
    }
    fwd(8+5.25) children();
}
// !xrot(-90) render() drive_gear(0); // print

module crank(a,de) {
    xrot(-90) yrot(-a) {
        r=1.75+1-$slop;
        r2=3.814225;
        r3=r-1+$slop/2;
        color(color1) {
            back(12.9) difference() {
                union() {
                    yrot(22.5) yrot_copies(n=8) fwd(2) left(r2)
                        ycyl(d2=1.2,d1=0.7,h=5,anchor=BACK);
                    ycyl(r=r2,h=7,anchor=BACK);
                    back(1) ycyl(r=de+r,h=3,anchor=BACK);
                    down(de) {
                        ycyl(r=r,h=1,anchor=FWD);
                    }
                    fwd(7) intersection() {
                        spur_gear(mod=0.7,teeth=8,thickness=4,orient=FWD,anchor=BOT);
                        ycyl(d=7.75,h=4,anchor=BACK/*,chamfer1=1.66*/);
                    }
                }
                down(de) fwd(2+ep) ycyl(r=r3,h=12.5,anchor=FWD);
            }
            back(12.9) down(de) fwd(2+ep) yrot_copies(n=6) down(r3)
                ycyl(d1=0.75,d2=0.5,h=3,anchor=FWD);
            back(4.4) {
                ycyl(d=4.5,h=9.75,anchor=BACK);
                fwd(9.25) difference() {
                    fwd(1.6) ycyl(d=6,h=2,chamfer2=0.75,anchor=FWD);
                    fwd(0.5) ycyl(d=4.1,h=2.4,anchor=BACK);
                }
            }
        }
        back(12.9-2) down(de) {
            color("#ddd") %ycyl(r=r-1,h=12.5+2,anchor=FWD);
        }
    }
    up(5.3+$slop) magnet();
    down(6.9+ep) children();
}

module M3(len) {
    color("#bbbd")
    screw("M3,13",head="socket",drive="hex",atype="shaft",anchor=TOP);
}

module pip_joint(d=5,a=0,a2=0,upper_t=false,lower_t=false,anchor=CENTER,spin=0,orient=UP,color=undef,color2=undef) {
    offset=d/2+0.5;
    anchors=[
        named_anchor("lower",[offset*cos(a),offset*sin(a),0],rot=xrot(90)*yrot(a+90)),
        named_anchor("upper",[-offset*cos(a2),-offset*sin(a2),0],rot=xrot(90)*yrot(a2-90)),
        named_anchor("upper2",[offset*cos(a2),offset*sin(a2),0],rot=xrot(90)*yrot(a2+90)),
        named_anchor("lower2",[-offset*cos(a),-offset*sin(a),0],rot=xrot(90)*yrot(a-90))
    ];
    attachable(anchor,spin,orient,d=d+1,l=5,anchors=anchors) {
        up(nozzle) down(2.5) {
            sq2=sqrt(2);
            wtf=0.16585;
            s=((d/2)-sq2)/nozzle+0.125;
            union() {
                color(color) force_tag(color) cyl(r=nozzle*s-$slop,h=nozzle*6+$slop,anchor=BOT,
                    chamfer1=-nozzle*2,chamfer2=-nozzle*3-wtf-$slop);
                color(color2) force_tag(color2) cyl(r=nozzle*s-$slop+nozzle*2,h=nozzle,anchor=TOP);
                color(color) force_tag(color) up(nozzle*5+$slop) {
                    up(nozzle) cyl(r=nozzle*s+nozzle*(2+sq2),h=2,anchor=BOT);
                    zrot(a2) if(upper_t) {
                        cuboid([d+1,5,2+nozzle],anchor=BOT,
                            chamfer=$slop*2,edges=[BOT+FWD,BOT+BACK]);
                    } else {
                        cuboid([d/2+0.5,5,2+nozzle],anchor=RIGHT+BOT,
                            chamfer=$slop*2,edges=[BOT+FWD,BOT+BACK]);
                    }
                }
            }
            color(color2) force_tag(color2) difference() {
                down(nozzle) union() {
                    cyl(r=nozzle*s+nozzle*(2+sq2),h=nozzle*6,anchor=BOT);
                    zrot(a) if(lower_t) {
                        cuboid([d+1,5,2.4],anchor=BOT);
                    } else {
                        cuboid([d/2+0.5,5,2.4001],anchor=LEFT+BOT);
                    }
                }
                up(ep) cyl(r=nozzle*s,h=nozzle*5,anchor=BOT,
                    chamfer1=-nozzle*2,chamfer2=-(nozzle*2+wtf));
                cyl(r=nozzle*(s+2),h=nozzle,anchor=TOP);
            }
        }
        children();
    }
}

*!render() yview() pip_joint(a2=0,upper_t=false,lower_t=false) {
    attach("upper",LEFT) bar(5);
    attach("lower",LEFT) bar(5,false);
}

module pip_screw_joint(d=8,a=0,a2=0,upper_t=false,lower_t=false,anchor=CENTER,spin=0,orient=UP,color=undef,color2=undef) {
    offset=d/2+0.5;
    anchors=[
        named_anchor("lower",[offset*cos(a),offset*sin(a),0],rot=xrot(90)*yrot(a+90)),
        named_anchor("upper",[-offset*cos(a2),-offset*sin(a2),0],rot=xrot(90)*yrot(a2-90))
    ];
    attachable(anchor,spin,orient,d=d+1,l=5,anchors=anchors) {
        difference() {
            // 4.5mm offset
            pip_joint(d=d,a=a,a2=a2,upper_t=upper_t,lower_t=lower_t,color=color,color2=color2) {
                if($children>1) children(1);
                if($children>2) children(2);
            }
            up(1) screw_hole("M3",l=4,head="socket",head_oversize=0,
                atype="shaft",anchor=TOP,tolerance="tap");
        }
        if($children>0) up(1+$slop) children(0);
    }
}

module pip_pin_joint(d=8,a=0,a2=0,upper_t=false,lower_t=false,anchor=CENTER,spin=0,orient=UP,color=undef,color2=undef,include_bushing=false) {
    offset=d/2+0.5;
    anchors=[
        named_anchor("lower",[offset*cos(a),offset*sin(a),0],rot=xrot(90)*yrot(a+90)),
        named_anchor("upper",[-offset*cos(a2),-offset*sin(a2),0],rot=xrot(90)*yrot(a2-90))
    ];
    attachable(anchor,spin,orient,d=d+1,l=5,anchors=anchors) {
        difference() {
            // 4.5mm offset
            union() {
                pip_joint(d=d,a=a,a2=a2,upper_t=upper_t,lower_t=lower_t,color=color,color2=color2) {
                    if($children>1) children(1);
                    if($children>2) children(2);
                }
                if(include_bushing)
                    color(color) up(2.5) cyl(d=7,h=0.5,anchor=BOT,chamfer2=0.5);
            }
            if(include_bushing)
                up(2.5-ep) cyl(d=4,h=0.5+ep*2,anchor=BOT,chamfer2=-0.5);
            cyl(d=3.5,h=6);
        }
        if($children>0) up(1+$slop) children(0);
    }
}
*!pip_pin_joint();

module bar(l,top=true,color=undef,anchor=CENTER,spin=0,orient=UP) {
    attachable(anchor,spin,orient,size=[l,5,5]) {
        color(color) force_tag(color) {
            // #cuboid([l,5,5]);
            if(top) {
                up(2.55) cuboid([l,5,2.4],anchor=TOP,
                            chamfer=$slop*2,edges=[BOT+FWD,BOT+BACK]);
            } else {
                down(2.5) cuboid([l,5,2.4],anchor=BOT);
            }
        }
        children();
    }
}

module dot(p,color) color(color) translate(p) sphere(d=2.1);
module line(p1,p2,color) color(color) stroke([pt(sol,p1),pt(sol,p2)]);

module tri_pivot(oab,ab,color=undef) {
    color(color) 
    force_tag(color)
    difference() {
        h=2.4;
        down(1.3) hull() {
            cyl(d=8,h=h);
            zrot(oab+120) fwd(ab) cyl(d=5,h=h);
            zrot(oab+120-60) fwd(ab) cyl(d=5,h=h);
        }
        cyl(d=8-$slop,h=6);
        zrot(oab+120) fwd(ab) cyl(d=5-$slop,h=6);
        zrot(oab+120-60) fwd(ab) cyl(d=5-$slop,h=6);
    }
}

module leg(a,include_bushing=false,color=undef) {
    points = [[30, 0], [0, 0], [-16, 0], [5.96186, 16.984], [17.6895, 3.32888], [-16, 5.25], [-7.50946, -12.6372], [-10.7278, -18.0531], [6.9617, -14.7242], [-5.86577, -38.4825]];
    sol=solve2d([

        point("o",at=points[0]),
        point("a",at=points[1]),
        point("e",at=points[2]),
        point("b",at=points[3]),
        point("c",at=points[4]),
        point("d",at=[points[5].x,points[6].y*((a>180||a==0)?-1:1)]),
        point("f",at=points[6]),
        point("g",at=points[7]),
        point("h",at=points[8]),
        point("i",at=points[9]),   

        con_fixed("a"),
        con_fixed("e"),
        con_fixed("o"),

        con_distance("d","e",de),
        con_distance("d","b",db),
        con_distance("d","f",df),
        con_distance("f","g",fg),
        
        con_distance("a","b",ab),
        con_distance("b","c",ab),
        con_distance("a","c",ab),
        con_distance("g","h",ab),
        con_distance("a","g",ag),
        con_distance("c","h",ch),
        con_distance("g","i",gi),
        con_distance("h","i",hi),

        con_pt_on_segment("f","a","g"),
        con_parallel("a","c","g","h"),
        con_opposite_side("a","e","h","b"),
        con_opposite_side("g","h","a","i"),
        con_opposite_side("a","b","e","c"),

        con_directed_angle("e","a","e","d",a),
    ]
    // ,solve=false
    );
    *up(10) {
        // Preview system
        if (!solved(sol)) {
            echo(iterations(sol));            // 2 — one solve,found violation,re-solved
            echo(active_inequalities(sol));   // ["con_le_distance(a,b,4.000000)"]
            echo(failed_constraints(sol));
        }
        for(p=pts(sol)) color(solved(sol)?"blue":"red") translate(p) sphere(d=2);
        dot(pt(sol,"a"),"#ff0");
        dot(pt(sol,"e"),"#f0f");
        dot(pt(sol,"b"),"#0ff");
        dot(pt(sol,"c"),"#00f");
        line("a","b","#585");
        line("c","b","#585");
        line("c","a","#5c5");
        line("g","h","#585");
        line("d","e","#885");
        line("c","h","#855");
        line("a","g","#855");
        line("d","b","#855");
        line("d","f","#855");
        line("h","i","#558");
        line("g","i","#588");
    }
    // dot(pt(sol,"e"),"#ff0");

    afd=angle(sol,["a","f","d"])+180;
    bdf=angle(sol,["b","d","f"])+180;
    abd=angle(sol,["a","b","d"])+150;
    ach=angle(sol,["a","c","h"])+180+30;
    oab=angle(sol,["o","a","b"])-30;
    oag=angle(sol,["o","a","g"])+180;
    fgi=angle(sol,["f","g","i"])+180;
    chi=angle(sol,["c","h","i"])+180;
    gih=angle(sol,["g","i","h"])+180;
    abc_tri = ab / sqrt(3);
    pip_screw_joint(a=oab,a2=oag,color=color,color2=color) {
        %M3(12);
        union() {
            tri_pivot(oab,ab,color=color);
            attach("lower",LEFT) bar(abc_tri-4.5,false,color=color)
                attach(RIGHT,RIGHT) {
                    yrot(60) bar(abc_tri-3,false,color=color) 
                        attach(LEFT,"lower") pip_joint(a=-abd,color=color,color2=color)
                            attach("upper",RIGHT) bar(db-7.5,color=color)
                                attach(LEFT,"upper") pip_pin_joint(a=bdf,color=color,color2=color,include_bushing=include_bushing);
                    yrot(-60) bar(abc_tri-3,false,color=color)
                        attach(LEFT,"lower") pip_joint(a=-ach,color=color,color2=color)
                        attach("upper",RIGHT) bar(ch-6,color=color)
                        attach(LEFT,"upper") pip_joint(a=chi,color=color,color2=color);
                }
        }
        attach("upper",LEFT) bar(af-7.5,color=color)
            attach(RIGHT,"upper") pip_joint(a=afd,upper_t=true,color=color,color2=color) {
                attach("lower",LEFT) bar(df-7.5,false,color=color);
                attach("upper2",LEFT) bar(fg-6,color=color)
                attach(RIGHT,"upper") pip_joint(a=fgi,color=color,color2=color)
                attach("lower",LEFT) foot(gi,hi,gih,color=color);
            };
    }
}

module foot(gi,hi,gih,color=undef) {
    color(color) force_tag(color) {
        bar(gi-3,false,color=color) {
            attach(RIGHT,CENTER) fwd(1.3) ycyl(d=5,h=2.4);
            attach(RIGHT,LEFT) yrot(gih) bar(hi-3,false,color=color);
        }
        hull() {
            cyl(d=5,h=5);
            up(gi-5.5) cyl(d=5,h=5);
            right(13.84) cyl(d=5,h=5);
        }
    }
}

module body_top(head_y) {
    ch=7;
    ch2=16;
    difference() {
        up(3) 
        union() {
            back(75/2+5) up(13) {
                hull() {
                    up(14) fwd(5) cuboid([18,57,ep],rounding=ch/2,edges="Z",anchor=BACK+TOP);
                    fwd(20) down(3) cuboid([6+44,47,18],rounding=ch,edges="Z",anchor=BACK+TOP);
                    down(16+ch+5) fwd(2) cuboid([29,50-(sqrt(2)*2)+head_y,ep],rounding=ch,edges="Z",anchor=BACK+TOP);
                }
                back(2) hull() 
                {
                    up(14) fwd(2) cuboid([18,33,ep],rounding=ch/2,edges="Z",anchor=BACK+TOP);
                    down(3) xflip_copy() {
                        right(3+55/2-ch) fwd(35-ch) cyl(r=ch,h=18,anchor=TOP);
                        right(3+55/2-ch2) fwd(ch2) cyl(r=ch2,h=18,anchor=TOP);
                    }
                    down(16+ch+5) fwd(2) cuboid([29,33,1],rounding=ch,edges="Z",anchor=BACK+BOT);
                }
            }
            fwd(75/2+head_y+2) down(26/2) {
                offset=0;
                ch=12;
                y=22+head_y+2;
                up(29+$slop) back(y/2) hull() xflip_copy() yflip_copy() {
                    left(33/2-ch) back(y/2-ch) cyl(r=ch+offset,h=24+$slop,anchor=TOP,rounding2=0.5);
                }
            }
            fwd(16) xflip_copy() left(20+$slop) xcyl(d=6,h=3-$slop,anchor=RIGHT);
            back(16) xflip_copy() left(23.5) xcyl(d=6,h=5,anchor=RIGHT);
        }
        // crank hole
        xflip_copy() right(19) {
            xcyl(d=16+$slop*2,h=12+ep);
            cuboid([12+ep,16+$slop*2,8+ep],anchor=TOP,chamfer=-1.5,edges=[BOT+BACK,BOT+FWD]);
        }
        // battery slot
        up(3) {
            back(75/2+4) up(15) up(12+ep) fwd(2.5) cuboid([15,55,13],rounding=3,edges="Z",anchor=BACK+TOP);
            up(20) fwd(18.5) back(60/2) yflip_copy() fwd(60/2) xrot(-90) zrot(-90) battery_tab_neg();
        }

        // leg mounts
        fwd(16) xflip_copy() left(18+$slop) xcyl(d=3.2,h=15-$slop+ep,anchor=RIGHT);
        back(16) xflip_copy() left(23.5) xcyl(d=3.2,h=15+ep,anchor=RIGHT);
        
        // bottom pocket
        up(3) difference() {
            body_form(head_y,$slop*2);
            fwd(head_y+8-$slop) up(8+$slop*2) cuboid([25.2,11,6],anchor=BOT+FWD,chamfer=-2.3,edges=[TOP+FWD]);
        }
        back(42.75) up(3+12+$slop) cuboid([25+$slop,65,6+3],anchor=BACK+TOP);
        
        // bottom clip
        down(5) cuboid([100,100,30],anchor=TOP);
        
        // camera hole
        fwd(head_y+38.5) down(6.4) ycyl(d=9.5,h=2+ep,chamfer1=-1.25);
    }
}

module body_form(head_y,offset=0) {
    ch=5;
    ch2=13;
    fwd(75/2+head_y) down(26/2) {
        ch=10;
        y=22+head_y;
        back(y/2) hull() xflip_copy() yflip_copy() {
            left(29/2-ch) back(y/2-ch) cyl(r=ch+offset,h=27+offset,anchor=BOT,chamfer1=0.5,rounding=0.5);
        }
    }
    back(75/2+5) up(14) {
        hull() {
            fwd(22) down(ch-offset) cuboid([46+offset,43+offset,18+offset],rounding=ch,edges="Z",anchor=BACK+TOP);
            down(17+ch+5+offset) fwd(14) cuboid([29+offset,38-(sqrt(2)*2)+head_y+offset,ep],rounding=ch,edges="Z",anchor=BACK+TOP);
        }
        back(2) hull() 
        {
            down(ch-offset) xflip_copy() {
                ch=4.5;
                offset2=2+$slop;
                right(2+3+55/2-ch-2-offset2) fwd(35-ch-offset2) cyl(r=ch+offset,h=18+offset*2,anchor=TOP);
                right(2+3+55/2-ch2-2-offset2) fwd(ch2+offset2) cyl(r=ch2+offset,h=18+offset*2,anchor=TOP);
            }
            down(17+ch+5) fwd(8-offset) cuboid([29+offset*2,31-7+offset,1],rounding=ch,edges="Z",anchor=BACK+BOT);
        }
    }
}

module body_bottom(head_y) {
    ch=5;
    ch2=13;
    color(color1) 
    // render()
    union() {
        difference() {
            body_form(head_y);

            // camera hole
            fwd(head_y+36.5) down(6.4) ycyl(d=7.5,h=2.5,chamfer=-1);
            // usb hole
            fwd(head_y+26.12) down(11) cuboid([10,4,6],rounding=1.8,edges="Z");


            // screw holes
            xflip_copy() {
                fwd(16) {
                    right(17-ep) xcyl(d=3.2,h=15,anchor=LEFT);
                    right(19) nut_trap_side(30,"M3",poke_len=13,orient=LEFT);
                }
                back(16) {
                    right(20) xcyl(d=3.2,h=15,anchor=LEFT);
                    right(24.5) nut_trap_side(30,"M3",poke_len=13,orient=LEFT);
                }
            }

            fwd(75/2+head_y) down(26/2) {
                inset=2;
                ch=10;
                y=22+head_y;
                up(inset) back(y/2) hull() {
                    xflip_copy() left(29/2-ch) fwd(y/2-ch) cyl(r=ch-inset,h=27,anchor=BOT);
                    back(1.5) cuboid([29-inset*2,y/2,27],anchor=BOT+FWD);
                }
            }

            // motor slots
            xflip_copy() down(6)left(12.15) back(12.25-ep) difference() {
                w=10+$slop*2;
                union() {
                    back(2) cuboid([w,26,20],rounding=3.5,edges=[BACK+LEFT,BACK+RIGHT],anchor=FWD+BOT);
                    cuboid([w,3,20],chamfer=1,edges=[FRONT+LEFT,FRONT+RIGHT],anchor=FWD+BOT);
                }
                // crush ribs
                xflip_copy() back(17) left(w/2) ycopies(n=4,l=10) cyl(d1=1.2,d2=0.5,h=15,anchor=BOT);
            }

            // encoder/drive pocket
            back(75/2+5) up(13) {
                inset=2;
                up(inset) hull() {
                    fwd(22+6.5+inset-$slop) down(16+ch) cuboid([40-inset*2,28.3+$slop-inset*2,30],rounding=ch-inset,edges=[FWD+LEFT,FWD+RIGHT],anchor=BACK+BOT);
                    down(16+ch+6) fwd(30.5-$slop) cuboid([29,28.3+$slop-inset*2,ep],rounding=ch,edges="Z",anchor=BACK+TOP);
                }
            }

            // crank hole
            xflip_copy() right(23+ep) difference() {
                r=8+$slop;
                xcyl(r=r,h=6+ep*2,anchor=RIGHT,chamfer1=1);
                xrot_copies(n=6) fwd(r) xcyl(d1=1,d2=0.5,h=10.2,anchor=RIGHT);
            }

            // center wire channel
            down(2) fwd(15) cuboid([4,54.5,15],anchor=BOT+FWD);
            // rear wire channel
            down(2) back(39.5) cuboid([24,2.5,15],anchor=BOT+BACK);
        
        }
        // encoder mounts
        down(12.2) yflip_copy() fwd(12.5) xflip_copy() {
            w=1.5+$slop*2;
            difference() {
                cuboid([6.5,3,10.2],anchor=BOT+FWD+RIGHT);
                left(2.5-$slop) cuboid([w,3+ep,10.2+ep],anchor=BOT+FWD+RIGHT);
            }
            // crush ribs
            left(2.25+w/2) xflip_copy() left(w/2) back(1.5) yflip_copy() back(1) cyl(d1=1.2,d2=0.5,h=10.2,anchor=BOT);
        }

        // board mount
        fwd(head_y+21-$slop) down(12) cuboid([10,4,8],anchor=BOT);
        // camera mount
        fwd(head_y+28.5-$slop) down(12) hull() {
            cuboid([10,2,2.5],anchor=BOT+BACK);
            up(6) cuboid([10,nozzle,ep],anchor=BOT+BACK);
        }
        // board side mount
        fwd(head_y+21-$slop) down(12) xflip_copy() left(9) 
            cuboid([4,14,12],anchor=BOT+BACK+RIGHT,rounding=4,edges=[LEFT+FWD]);

    }
    children();
}

l=3;
db=l*8.3;
ab=l*6;
ch=l*7;
ag=l*7;
fg=l*2.1;
af=ag-fg;
gi=l*7;
hi=l*9;
df=l*6.6;
de=l*1.75;

*!render() {
    hide(color1) xflip_copy() left(25) leg(90); // print 1
}
// !hide(color2) xflip() render() leg(180); // print 1


module bot(t) {
    q=6;
    a=floor(((-t*360+360*3+180)%360)/q)*q;
    a2=floor(((-t*360+360*3)%360)/q)*q;
    b=floor(((t*360+360*3)%360)/q)*q;
    b2=floor(((t*360+360*3+180)%360)/q)*q;
    head_y=11.5;

    // !xview(true)
    // !render() yview(true)
    body_bottom(head_y)
        color(color2) body_top(head_y);

    *!xflip_copy() up(6) right(17.5) back(13) cuboid([10,20,6],anchor=BOT+FWD+RIGHT);

    // !body_top(head_y); // print

    //skip() 
    up(24) fwd(18.5) {
        xrot(-90) zrot(-90) battery_tab_vcc();
        back(60) yflip() xrot(-90) zrot(-90) battery_tab_gnd();
    }
    //skip() 
    up(24) back(36) xrot(90) inr14500();

    xflip_copy() right(18) ball_bearing("688ZZ",anchor=BOT,orient=RIGHT);

    back(13.25) left(12+$slop/2) yrot(90) {
        n20(a2) drive_gear(a2) crank(a,de);
    }
    xflip() back(13.25) left(12+$slop/2) yrot(90) {
        n20(a) drive_gear(a) crank(a2,de);
    }

    *!xrot(-90) drive_gear(a); // print
    *!crank(a2,de); // print

    nop() { // legs
        right(3+6+19.5+$slop) back(16) yrot(90) zrot(90) {
            up(5.5) leg(a,color="#eee");
            left(32) xflip() leg(b,include_bushing=true,color="#eee");
        }

        xflip() right(3+6+19.5+$slop) back(16) yrot(90) zrot(90) {
            up(5.5) leg(a2,color="#eee");
            left(32) xflip() leg(b2,include_bushing=true,color="#eee");
        }
    }

    *!back(20) { // print legs
        left(15) leg(90,include_bushing=true);
        right(15) fwd(30) zrot(170) xflip() leg(90,include_bushing=true);
    }


    %down(4.5) fwd(40+head_y) {
        down(0.8) back(0.5) yrot(180) xiao_sense(camera_z=-0.8);
        back(23) up(4) xrot(90) mx1508();
    }
    *xflip_copy() right(5.5) yrot(90) as5600();
}

// zview(true) 
// yrot(cos($t*2*360+45)*2) up(25)
//zrot($t*360)
// render() xview(true)
color("#555") circle(r=70);
physics() up(44) bot(t=$t*2);
















echo(str("\n",
"sh ./do_mp4.sh pet.scad ",
$vpt[0],",",$vpt[1],",",$vpt[2],",",
$vpr[0],",",$vpr[1],",",$vpr[2],",",
$vpd,
"\n"));
