"""Build the SKIL PWRCore 20 2Ah battery pack in Blender (run inside Blender).

Units: 1 Blender unit = 1 mm.  Battery frame: origin at the footprint centre on the bottom
face, +X toward the terminal (front) end, +Z up through the rails, +Y to the left when
looking from the back toward the front.

Every dimension lives in P so the review loop can tweak numbers and rebuild.
"""
import bpy, bmesh, math, json, os
from mathutils import Vector

PROJ = os.environ.get('BATTERY_PROJ', '/Users/samw3/prj/Make/stocko/3d-scan/project/battery_blender_v1')

P = dict(
    # lower housing
    x_back=-59.0, x_front=52.0, half_w=37.0, deck_z=31.0,
    bot_chamfer=2.8,            # bottom edge chamfer all round
    side_top_ch_h=4.3, side_top_ch_v=4.3,   # long top edges (side -> deck)
    front_top_ch_h=5.5, front_top_ch_v=5.5, # front top edge
    back_top_ch_h=6.0, back_top_ch_v=6.0,
    corner_ch_back=9.5, corner_ch_front=5.0,  # vertical corner chamfers (plan view)
    parting_z=16.0, parting_depth=0.5, parting_w=0.6,
    # label recess on each side
    label_x0=-47.0, label_x1=45.0, label_z0=3.5, label_z1=21.5, label_ch=5.0, label_depth=0.6,
    # front feet
    foot_y0=13.8, foot_y1=27.3, foot_x1=57.8, foot_top_back=30.0, foot_top_front=28.0,
    foot_front_ch=3.5, foot_bot_ch=4.5,
    # tongue (terminal block with rails)
    t_x0=-32.0, t_x1=34.5,
    t_base_hw=23.3, t_base_z1=37.5,       # lower tongue body
    t_groove_hw=21.0, t_groove_z1=41.3,    # rail groove under the lip
    t_plate_hw=23.3, t_plate_z1=43.6, t_plate_x1=22.0,  # top plate / rail lips
    t_front_step_z=37.0, t_step_hw=20.5,   # lower front step that carries the slots to the front face
    t_horn_x1=27.0, t_horn_xc=30.5, t_horn_y0=17.5, t_finger_x1=27.0,
    rail_windows=7, rail_win_x0=-22.0, rail_win_x1=26.0, rail_win_z0=38.7, rail_win_z1=41.3,
    # terminal slots
    slot_ys=[13.7, 6.9, 0.0, -6.9, -13.7], slot_w=2.5, slot_x0=7.5, slot_z0=32.0,
    # latch catch window on the plate
    catch_x0=-25.0, catch_x1=-16.0, catch_hw=15.0, catch_depth=4.0,
    # latch block at the back
    lb_x0=-59.0, lb_x1=-32.0, lb_hw=26.0, lb_hw_back=32.5, lb_corner_x0=-41.0, lb_corner_x1=-34.0,
    lb_z1=46.0, lb_slope_x1=-41.0, lb_back_z=31.5, lb_side_ch=3.0,
    btn_x0=-56.5, btn_x1=-42.0, btn_hw=17.0, btn_recess=0.8, btn_gap=0.8, btn_groove_x=[-51.5, -48.5], pawl_z=47.0,
    # front vents on the deck
    vent_x0=36.5, vent_x1=45.0, vent_ys=[14.0, 9.0, 3.9, -3.9, -9.0, -14.0], vent_w=2.6, vent_depth=0.8,
    vent_hole_r=0.45, vent_hole_nx=5, vent_hole_ny=2,
    # plate markings
    screw_boss=(-1.5, 0.0), screw_boss_r=2.6, sym_x=8.5, sym_r=2.6,
    # bottom vents: (x0, x1, y0, y1)
    bvents=[(-54.0, -51.6, 0.5, 8.5), (-54.0, -51.6, -9.0, -1.0), (-44.0, -41.6, 10.0, 24.0), (-44.0, -41.6, -4.0, 7.5), (-44.0, -41.6, -23.0, -8.5)],
    bvent_depth=1.2,
    bpads=[(-46.0, 31.0), (-46.0, -31.0), (41.0, 31.0), (41.0, -31.0)], bpad_r=2.8, bpad_depth=0.3,
    bpins=[(-15.5, 32.5), (-15.5, -32.5), (15.5, 32.5), (15.5, -32.5), (42.5, 15.0), (42.5, -15.0), (-1.5, 0.0)], bpin_r=0.6,
    screw_cb_r=3.6, screw_cb_depth=1.5,
    # gauge panel details (back face): button on the +Y side, four LED windows on the -Y side
    gauge_btn=(4.0, 14.0, 4.5, 9.0), gauge_leds=[-3.5, -6.5, -9.5, -12.5], gauge_led=(0.9, 5.0, 9.0),
    # gauge panel on the back face
    gauge_hw=17.0, gauge_z0=3.0, gauge_z1=10.5, gauge_proud=0.4,
    # bottom
    bslot_x0=-14.0, bslot_x1=-5.0, bslot_hw=22.75, bslot_depth=3.0,
    screw_pos=[(-54.5, 23.25), (-54.5, -23.25), (52.5, 19.75), (52.5, -19.75)], screw_r=3.0, screw_depth=3.0,
)


# ----------------------------------------------------------------------------- helpers
def _new_obj(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def prism(name, poly, axis, a0, a1):
    """Extrude a CCW 2D polygon along an axis.
    axis 'z': poly in (x, y); axis 'y': poly in (x, z); axis 'x': poly in (y, z)."""
    bm = bmesh.new()
    def v3(p, a):
        if axis == 'z': return (p[0], p[1], a)
        if axis == 'y': return (p[0], a, p[1])
        return (a, p[0], p[1])
    lo = [bm.verts.new(v3(p, a0)) for p in poly]
    hi = [bm.verts.new(v3(p, a1)) for p in poly]
    bm.faces.new(lo[::-1]); bm.faces.new(hi)
    n = len(poly)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _new_obj(name, bm)


def box(name, x0, x1, y0, y1, z0, z1):
    return prism(name, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], 'z', z0, z1)


def convex_solid(name, planes, bbox):
    """Convex solid = bbox cut by half-spaces. planes: list of (point, outward normal)."""
    (x0, x1), (y0, y1), (z0, z1) = bbox
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((x0 if v.co.x < 0 else x1, y0 if v.co.y < 0 else y1, z0 if v.co.z < 0 else z1))
    for co, no in planes:
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=Vector(co), plane_no=Vector(no).normalized(), clear_outer=True, dist=1e-5)
        boundary = [e for e in bm.edges if e.is_boundary]
        if boundary:
            bmesh.ops.holes_fill(bm, edges=boundary, sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _new_obj(name, bm)


def stadium(name, a0, a1, c, w, axis, z0, z1, seg=8):
    """Slot with round ends, long axis a (x for axis 'z', y for 'zy'), centred at c across, width w."""
    r = w / 2; pts = []
    for k in range(seg + 1):
        t = -math.pi / 2 + math.pi * k / seg
        pts.append((a1 - r + r * math.cos(t), c + r * math.sin(t)))
    for k in range(seg + 1):
        t = math.pi / 2 + math.pi * k / seg
        pts.append((a0 + r + r * math.cos(t), c + r * math.sin(t)))
    if axis == 'zy':
        pts = [(q, pp) for pp, q in pts][::-1]
    return prism(name, pts, 'z', z0, z1)


def cylinder(name, x, y, z0, z1, r, seg=16):
    return prism(name, [(x + r * math.cos(2 * math.pi * k / seg), y + r * math.sin(2 * math.pi * k / seg)) for k in range(seg)], 'z', z0, z1)


def ring(name, x, y, z0, z1, r, w, seg=32):
    outer = cylinder(name, x, y, z0, z1, r, seg)
    inner = cylinder(name + '_in', x, y, z0 - 1, z1 + 1, r - w, seg)
    return boolean(outer, inner, 'DIFFERENCE')


def chamfer_rect(x0, x1, y0, y1, c):
    """CCW rectangle with 45 deg corner chamfers (c may be a 4-tuple: x0y0, x1y0, x1y1, x0y1)."""
    if not isinstance(c, (list, tuple)): c = (c, c, c, c)
    a, b, d, e = c
    return [(x0 + a, y0), (x1 - b, y0), (x1, y0 + b), (x1, y1 - d), (x1 - d, y1), (x0 + e, y1), (x0, y1 - e), (x0, y0 + a)]


def boolean(target, tool, op, apply=True):
    m = target.modifiers.new(name=f'{op}_{tool.name}', type='BOOLEAN')
    m.operation = op; m.object = tool; m.solver = 'EXACT'
    if apply:
        bpy.context.view_layer.objects.active = target
        bpy.ops.object.modifier_apply(modifier=m.name)
        bpy.data.objects.remove(tool, do_unlink=True)
    return target


def union_all(target, tools):
    for t in tools: boolean(target, t, 'UNION')
    return target


def cut_all(target, tools):
    for t in tools: boolean(target, t, 'DIFFERENCE')
    return target


# ----------------------------------------------------------------------------- parts
def lower_housing(p):
    xb, xf, hw, zt = p['x_back'], p['x_front'], p['half_w'], p['deck_z']
    bc = p['bot_chamfer']
    corners = (p['corner_ch_back'], p['corner_ch_front'], p['corner_ch_front'], p['corner_ch_back'])
    plan = prism('housing', chamfer_rect(xb, xf, -hw, hw, corners), 'z', 0, zt)
    sh, sv = p['side_top_ch_h'], p['side_top_ch_v']
    end = prism('end_prof', [(-hw + bc, 0), (hw - bc, 0), (hw, bc), (hw, zt - sv), (hw - sh, zt), (-hw + sh, zt), (-hw, zt - sv), (-hw, bc)],
                'x', xb - 1, xf + 1)
    fh, fv, bh, bv = p['front_top_ch_h'], p['front_top_ch_v'], p['back_top_ch_h'], p['back_top_ch_v']
    side = prism('side_prof', [(xb + bc, 0), (xf - bc, 0), (xf, bc), (xf, zt - fv), (xf - fh, zt), (xb + bh, zt), (xb, zt - bv), (xb, bc)],
                 'y', -hw - 1, hw + 1)
    boolean(plan, end, 'INTERSECT'); boolean(plan, side, 'INTERSECT')
    return plan


def feet(p):
    out = []
    for s in (1, -1):
        y0, y1 = sorted((s * p['foot_y0'], s * p['foot_y1']))
        xf0 = p['x_front'] - 4.0
        # side profile: sloped top, chamfered front-bottom
        f = prism('foot', [(xf0, 0), (p['foot_x1'] - p['foot_bot_ch'], 0), (p['foot_x1'], p['foot_bot_ch']),
                           (p['foot_x1'], p['foot_top_front'] - 1.5), (p['foot_x1'] - 1.5, p['foot_top_front']),
                           (xf0, p['foot_top_back'])], 'y', y0, y1)
        # plan: chamfer the two front vertical edges
        c = p['foot_front_ch']
        pl = prism('foot_plan', [(xf0 - 1, y0), (p['foot_x1'] - c, y0), (p['foot_x1'], y0 + c), (p['foot_x1'], y1 - c),
                                 (p['foot_x1'] - c, y1), (xf0 - 1, y1)], 'z', -1, 40)
        boolean(f, pl, 'INTERSECT')
        out.append(f)
    return out


def tongue(p):
    """Terminal tongue: lower body, recessed rail groove, top plate with overhanging rail lips.
    Front end: plate stops at t_plate_x1 in the middle, rib fingers run on to t_finger_x1, the
    rail lips end in chamfered horns, and a lower step carries the slots out to the front face."""
    x0, x1 = p['t_x0'], p['t_x1']
    zt = p['deck_z'] - 0.5
    hw, gw, pz0, pz1 = p['t_plate_hw'], p['t_groove_hw'], p['t_groove_z1'], p['t_plate_z1']
    xh, xhc, hy = p['t_horn_x1'], p['t_horn_xc'], p['t_horn_y0']
    base = box('t_base', x0, xh, -p['t_base_hw'], p['t_base_hw'], zt, p['t_base_z1'])
    groove = box('t_groove', x0, xh, -gw, gw, p['t_base_z1'] - 0.01, pz0)
    # plate outline in plan: full width back to the horns, chamfered horn tips, recessed middle
    c = xhc - xh
    plan = [(x0, -hw), (xh, -hw), (xhc, -hw + c), (xhc, -hy), (p['t_plate_x1'], -hy), (p['t_plate_x1'], hy),
            (xhc, hy), (xhc, hw - c), (xh, hw), (x0, hw)]
    plate = prism('t_plate', plan, 'z', pz0 - 0.01, pz1)
    step = box('t_step', xh - 1, x1, -p['t_step_hw'], p['t_step_hw'], zt, p['t_front_step_z'])
    parts = [groove, plate, step]
    # rib fingers between the slots, at plate height
    ys = sorted(p['slot_ys'])
    for a, b in zip(ys[:-1], ys[1:]):
        y0, y1 = a + p['slot_w'] / 2, b - p['slot_w'] / 2
        parts.append(box('t_finger', p['t_plate_x1'] - 0.5, p['t_finger_x1'], y0, y1, p['t_front_step_z'] - 0.5, pz1))
    union_all(base, parts)
    return base


def _slope_z(p, x):
    """height of the latch block's inclined top at x (plane through the back edge and the front bar)"""
    x0, z0, x1, z1 = p['lb_x0'], p['lb_back_z'], p['lb_slope_x1'], p['lb_z1']
    return z0 + (x - x0) * (z1 - z0) / (x1 - x0)


def latch_block(p):
    """Latch housing at the back: as wide as the deck at the back, narrowing to the front bar beside
    the tongue; inclined top (the button sits in it), flat front bar, chamfered top edges."""
    x0, x1, hw, hwb = p['lb_x0'], p['lb_x1'], p['lb_hw'], p['lb_hw_back']
    zt = p['deck_z'] - 0.5
    xs, z1, zb = p['lb_slope_x1'], p['lb_z1'], p['lb_back_z']
    b = (z1 - zb) / (xs - x0)                        # slope of the inclined top
    c = p['lb_side_ch']
    xc0, xc1 = p['lb_corner_x0'], p['lb_corner_x1']
    planes = [((x0, 0, zb), (-b, 0, 1)),             # inclined top
              ((0, 0, z1), (0, 0, 1))]               # flat front bar
    for s in (1, -1):
        planes.append(((xc0, s * hwb, 0), (hwb - hw, s * (xc1 - xc0), 0)))  # angled front corners
        planes.append(((x0, s * (hwb - c), zb), (-b, s * 1, 1)))      # top edge chamfer (inclined part)
        planes.append(((x1, s * (hw - c), z1), (0, s * 1, 1)))        # top edge chamfer (front bar)
    return convex_solid('latch_block', planes, ((x0, x1), (-hwb, hwb), (zt, z1)))


def latch_button_cut_and_part(p):
    """Pocket in the inclined top and the push button that sits in it (top 0.8 mm below the housing)."""
    g, hw = p['btn_gap'], p['btn_hw']
    bx0, bx1, rec = p['btn_x0'], p['btn_x1'], p['btn_recess']
    z0, z1 = _slope_z(p, bx0), _slope_z(p, bx1)
    cut = prism('btn_pocket', [(bx0 - g, z0 - 8), (bx1 + g, z1 - 8), (bx1 + g, 60), (bx0 - g, 60)], 'y', -hw - g, hw + g)
    btn = prism('latch_button', [(bx0, z0 - 6), (bx1, z1 - 6), (bx1, z1 - rec), (bx0, z0 - rec)], 'y', -hw, hw)
    grooves = []
    for gx in p['btn_groove_x']:
        zz = _slope_z(p, gx) - rec
        grooves.append(prism('btn_groove', [(gx - 0.4, zz - 0.6), (gx + 0.4, zz - 0.6), (gx + 0.4, zz + 3), (gx - 0.4, zz + 3)],
                             'y', -hw + 3.5, hw - 3.5))
    cut_all(btn, grooves)
    return cut, btn


def latch_pawl(p):
    """Catch that stands up out of the window in the tongue plate: ramp rising toward the back."""
    x0, x1, hw = p['catch_x0'], p['catch_x1'], p['catch_hw']
    zb = p['t_plate_z1'] - p['catch_depth']
    return prism('pawl', [(x0 + 0.8, zb), (x1 - 0.8, zb), (x1 - 0.8, p['t_plate_z1'] - 0.3), (x0 + 0.8, p['pawl_z'])],
                 'y', -hw + 0.8, hw - 0.8)


def detail_cuts(p):
    cuts = []
    # parting line groove around the housing
    hw, xb, xf = p['half_w'], p['x_back'], p['x_front']
    z0, z1, d = p['parting_z'] - p['parting_w'] / 2, p['parting_z'] + p['parting_w'] / 2, p['parting_depth']
    outer = box('pl_outer', xb - 2, xf + 8, -hw - 2, hw + 2, z0, z1)
    inner = prism('pl_inner', chamfer_rect(xb + d, xf - d, -hw + d, hw - d, (p['corner_ch_back'], p['corner_ch_front'], p['corner_ch_front'], p['corner_ch_back'])), 'z', z0 - 1, z1 + 1)
    boolean(outer, inner, 'DIFFERENCE'); cuts.append(outer)
    # side label recesses
    for s in (1, -1):
        a0, a1 = (hw - p['label_depth'], hw + 2) if s > 0 else (-hw - 2, -hw + p['label_depth'])
        cuts.append(prism('label', chamfer_rect(p['label_x0'], p['label_x1'], p['label_z0'], p['label_z1'], p['label_ch']), 'y', a0, a1))
    # terminal slots: open to the front and top of the tongue
    for y in p['slot_ys']:
        cuts.append(box('slot', p['slot_x0'], p['t_x1'] + 2, y - p['slot_w'] / 2, y + p['slot_w'] / 2, p['slot_z0'], 50))
    # rail windows in the groove wall (both sides)
    n = p['rail_windows']; span = (p['rail_win_x1'] - p['rail_win_x0']); pitch = span / n
    for s in (1, -1):
        for i in range(n):
            wx0 = p['rail_win_x0'] + i * pitch + 0.6; wx1 = wx0 + pitch - 1.2
            y0, y1 = sorted((s * (p['t_groove_hw'] - 2.0), s * (p['t_groove_hw'] + 1)))
            cuts.append(box('rail_win', wx0, wx1, y0, y1, p['rail_win_z0'], p['rail_win_z1']))
    # latch catch window
    cuts.append(box('catch', p['catch_x0'], p['catch_x1'], -p['catch_hw'], p['catch_hw'], p['t_plate_z1'] - p['catch_depth'], 50))
    # deck vents: stadium-shaped pockets with a grid of small holes
    zv = p['deck_z']
    for y in p['vent_ys']:
        cuts.append(stadium('vent', p['vent_x0'], p['vent_x1'], y, p['vent_w'], 'z', zv - p['vent_depth'], zv + 6))
        nx, ny = p['vent_hole_nx'], p['vent_hole_ny']
        for i in range(nx):
            for j in range(ny):
                hx = p['vent_x0'] + 1.3 + i * (p['vent_x1'] - p['vent_x0'] - 2.6) / (nx - 1)
                hy = y + (j - (ny - 1) / 2) * 1.1
                cuts.append(cylinder('vent_hole', hx, hy, zv - 4, zv, p['vent_hole_r']))
    # plate markings: screw boss ring and the three terminal symbol rings
    zp = p['t_plate_z1']
    bx, by = p['screw_boss']
    cuts.append(ring('boss_ring', bx, by, zp - 0.4, zp + 1, p['screw_boss_r'], 0.35))
    cuts.append(cylinder('boss_hole', bx, by, zp - 2.5, zp + 1, 1.1))
    for y in (p['slot_ys'][0], 0.0, p['slot_ys'][-1]):
        cuts.append(ring('sym_ring', p['sym_x'], y, zp - 0.3, zp + 1, p['sym_r'], 0.3))
    # bottom vents
    for (x0, x1, y0, y1) in p['bvents']:
        cuts.append(stadium('bvent', y0, y1, (x0 + x1) / 2, x1 - x0, 'zy', -1, p['bvent_depth']))
    # gauge LED windows on the back face
    lw, lz0, lz1 = p['gauge_led']
    for y in p['gauge_leds']:
        cuts.append(box('led', p['x_back'] - 2, p['x_back'] - p['gauge_proud'] + 0.4, y - lw / 2, y + lw / 2, lz0, lz1))
    # bottom finger slot
    cuts.append(box('bslot', p['bslot_x0'], p['bslot_x1'], -p['bslot_hw'], p['bslot_hw'], -1, p['bslot_depth']))
    # screws on the bottom: counterbore + hole
    for (sx, sy) in p['screw_pos']:
        cuts.append(cylinder('screw_cb', sx, sy, -1, p['screw_cb_depth'], p['screw_cb_r'], 24))
        cuts.append(cylinder('screw_hole', sx, sy, -1, p['screw_depth'] + 3, 1.3, 16))
    # shallow round pads and small pin holes on the bottom
    for (x, y) in p['bpads']:
        cuts.append(ring('bpad', x, y, -1, p['bpad_depth'], p['bpad_r'], 0.35))
    for (x, y) in p['bpins']:
        cuts.append(cylinder('bpin', x, y, -1, 1.0, p['bpin_r'], 12))
    return cuts


def gauge_panel(p):
    xb = p['x_back']
    panel = box('gauge', xb - p['gauge_proud'], xb + 1, -p['gauge_hw'], p['gauge_hw'], p['gauge_z0'], p['gauge_z1'])
    y0, y1, z0, z1 = p['gauge_btn']
    btn = box('gauge_btn', xb - p['gauge_proud'] - 0.5, xb, y0, y1, z0, z1)
    return boolean(panel, btn, 'UNION')


def cleanup(ob):
    """merge boolean slivers and close the few pinholes the thin marking rings leave behind"""
    bm = bmesh.new(); bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.002)
    bnd = [e for e in bm.edges if e.is_boundary]
    if bnd:
        bmesh.ops.holes_fill(bm, edges=bnd, sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data); bm.free()


def build(p=P):
    # clear scene of old battery parts
    for ob in list(bpy.data.objects):
        if ob.get('battery_part') or ob.name.startswith(('Battery', 'housing', 'latch_button', 'pawl', 'Cube')):
            bpy.data.objects.remove(ob, do_unlink=True)
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'; sc.unit_settings.scale_length = 0.001; sc.unit_settings.length_unit = 'MILLIMETERS'
    body = lower_housing(p)
    union_all(body, feet(p) + [tongue(p), latch_block(p), gauge_panel(p)])
    pocket, btn = latch_button_cut_and_part(p)
    cut_all(body, [pocket] + detail_cuts(p))
    pawl = latch_pawl(p)
    cleanup(body)
    body.name = 'Battery'; body['battery_part'] = 1
    btn.name = 'Battery_LatchButton'; btn['battery_part'] = 1
    pawl.name = 'Battery_LatchPawl'; pawl['battery_part'] = 1
    for ob in (body, btn, pawl):
        ob.data.name = ob.name
    return body, btn, pawl


if __name__ == '__main__':
    build()
