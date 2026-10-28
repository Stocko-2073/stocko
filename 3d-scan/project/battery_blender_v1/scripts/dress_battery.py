"""Materials and non-structural dressing for the battery model (run inside Blender after build).

Adds: plastic/metal materials, side label artwork (PWR CORE 20 / LITHIUM / 2Ah badge), the
charge-gauge panel graphics, spring contacts in the three terminal slots, screw heads, and the
bottom rating sticker.  Everything added here lives in the 'Battery_Dress' collection so the
printable geometry (objects named Battery*) stays clean for export.
"""
import bpy, bmesh, math
from mathutils import Vector

DRESS = 'Battery_Dress'


def _coll():
    c = bpy.data.collections.get(DRESS)
    if c is None:
        c = bpy.data.collections.new(DRESS)
        bpy.context.scene.collection.children.link(c)
    return c


def clear():
    c = bpy.data.collections.get(DRESS)
    if c:
        for ob in list(c.objects):
            bpy.data.objects.remove(ob, do_unlink=True)


def material(name, color, rough=0.5, metal=0.0, spec=0.5, emit=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = (*color, 1.0)
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Metallic'].default_value = metal
    for key in ('Specular IOR Level', 'Specular'):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = spec
            break
    m.diffuse_color = (*color, 1.0)
    return m


def assign(ob, mat):
    ob.data.materials.clear(); ob.data.materials.append(mat)


def _link(ob):
    for c in ob.users_collection: c.objects.unlink(ob)
    _coll().objects.link(ob)
    return ob


def poly_obj(name, pts2d, mat, place):
    """flat polygon (2D in label coords u, v) mapped to 3D by place(u, v) -> Vector"""
    bm = bmesh.new()
    vs = [bm.verts.new(place(u, v)) for u, v in pts2d]
    bm.faces.new(vs)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); _coll().objects.link(ob); assign(ob, mat)
    return ob


def box_obj(name, x0, x1, y0, y1, z0, z1, mat):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts:
        v.co = Vector((x0 if v.co.x < 0 else x1, y0 if v.co.y < 0 else y1, z0 if v.co.z < 0 else z1))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); _coll().objects.link(ob); assign(ob, mat)
    return ob


def text_obj(name, body, box, side, mat, p, italic=False, bold=False):
    """Text fitted into box=(u0, u1, v0, v1) on a side label (u along the pack's x, v = height)."""
    cu = bpy.data.curves.new(name, 'FONT'); cu.body = body; cu.size = 10
    cu.align_x = 'LEFT'; cu.align_y = 'BOTTOM'
    if italic: cu.shear = 0.2
    ob = bpy.data.objects.new(name, cu); _coll().objects.link(ob); assign(ob, mat)
    bpy.context.view_layer.update()
    # measure in local units
    bb = [Vector(c) for c in ob.bound_box]
    w = max(c.x for c in bb) - min(c.x for c in bb); h = max(c.y for c in bb) - min(c.y for c in bb)
    x0l = min(c.x for c in bb); y0l = min(c.y for c in bb)
    u0, u1, v0, v1 = box
    sx, sy = (u1 - u0) / w, (v1 - v0) / h
    ob.scale = (sx, sy, 1)
    _place_on_side(ob, side, p, u0 - x0l * sx, v0 - y0l * sy)
    return ob


def _side_y(side, p):
    return side * (p['half_w'] - p['label_depth']) + side * 0.04


def _place_on_side(ob, side, p, u, v):
    y = _side_y(side, p)
    if side < 0:      # right side (-Y): text runs toward +X
        ob.rotation_euler = (math.radians(90), 0, 0); ob.location = (u, y, v)
    else:             # left side (+Y): text runs toward -X, u given in +X coords of the right side mirrored
        ob.rotation_euler = (math.radians(90), 0, math.radians(180)); ob.location = (-u, y, v)


def side_label(side, p, mats):
    """Artwork measured on the -Y side (x along the pack); mirrored for the +Y side."""
    def place(u, v):
        return Vector((u if side < 0 else -u, _side_y(side, p) + side * 0.01, v))
    text_obj('lbl_PWR', 'PWR', (-41.0, -26.0, 9.5, 17.0), side, mats['label_grey'], p)
    text_obj('lbl_CORE', 'CORE 20', (-25.0, 3.5, 9.5, 17.0), side, mats['red'], p)
    text_obj('lbl_TM', 'TM', (4.0, 6.0, 16.2, 17.2), side, mats['red'], p)
    text_obj('lbl_LITHIUM', 'LITHIUM', (7.0, 22.0, 9.6, 11.8), side, mats['white'], p, bold=True)
    poly_obj('lbl_stripe', [(7.0, 15.0), (24.0, 15.0), (24.0, 16.4), (7.0, 16.4)], mats['white'], place)
    badge = [(26.0, 8.8), (38.0, 8.8), (39.6, 10.4), (39.6, 15.0), (38.0, 16.6), (23.0, 16.6), (23.0, 15.0)]
    poly_obj('lbl_badge', badge, mats['white'], place)
    # the 2Ah text sits a hair proud of the badge
    ob = text_obj('lbl_2Ah', '2Ah', (27.5, 37.0, 10.2, 15.6), side, mats['label_dark'], p, italic=True)
    ob.location.y += side * 0.02


def gauge(p, mats):
    xb = p['x_back'] - p['gauge_proud'] - 0.03
    hw, z0, z1 = p['gauge_hw'], p['gauge_z0'], p['gauge_z1']
    def place(u, v):
        return Vector((xb, u, v))
    t = 0.7   # red frame
    for (a, b, c, d) in ((-hw, hw, z0, z0 + t), (-hw, hw, z1 - t, z1), (-hw, -hw + t, z0, z1), (hw - t, hw, z0, z1)):
        poly_obj('gauge_frame', [(a, c), (b, c), (b, d), (a, d)][::-1], mats['red'], place)
    y0, y1, bz0, bz1 = p['gauge_btn']
    xbb = p['x_back'] - p['gauge_proud'] - 0.53
    for (a, b, c, d) in ((y0, y1, bz0, bz0 + 0.5), (y0, y1, bz1 - 0.5, bz1), (y0, y0 + 0.5, bz0, bz1), (y1 - 0.5, y1, bz0, bz1)):
        poly_obj('gauge_btn_ring', [(a, c), (b, c), (b, d), (a, d)][::-1], mats['red'], lambda u, v: Vector((xbb, u, v)))
    lw, lz0, lz1 = p['gauge_led']
    for y in p['gauge_leds']:
        box_obj('gauge_led', p['x_back'] - p['gauge_proud'] - 0.02, p['x_back'] + 0.2, y - lw / 2 + 0.1, y + lw / 2 - 0.1, lz0 + 0.1, lz1 - 0.1, mats['led'])


def contacts(p, mats):
    """X-shaped spring contacts in the -, D, + slots"""
    for y in (p['slot_ys'][0], 0.0, p['slot_ys'][-1]):
        for sgn in (1, -1):
            ob = box_obj('contact', 10.0, 26.0, y - 0.15, y + 0.15, 36.0, 36.6, mats['metal'])
            ob.data.transform(__import__('mathutils').Matrix.Translation((-18.0, -y, -36.3)))
            ob.rotation_euler = (0, sgn * math.radians(24), 0)
            ob.location = (18.0, y, 37.3)


def screws(p, mats):
    for (sx, sy) in p['screw_pos']:
        # head fills the top of the counterbore: z from cb_depth - 1 to cb_depth
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=p['screw_cb_r'] - 0.8, depth=1.0,
                                            location=(sx, sy, p['screw_cb_depth'] - 0.5))
        ob = _link(bpy.context.active_object); ob.name = 'screw'; assign(ob, mats['screw'])
        for a in (0, 90):   # Phillips cross
            zf = p['screw_cb_depth'] - 1.0   # exposed face of the head
            c = box_obj('screw_x', sx - 1.3, sx + 1.3, sy - 0.25, sy + 0.25, zf - 0.03, zf + 0.03, mats['black'])
            c.data.transform(__import__('mathutils').Matrix.Translation((-sx, -sy, 0)))
            c.rotation_euler = (0, 0, math.radians(a)); c.location = (sx, sy, 0)


def sticker(p, mats):
    def place(u, v):
        return Vector((u, v, -0.03))
    pts = [(1.5, -29.5), (32.0, -29.5), (36.5, -25.0), (36.5, 25.0), (32.0, 29.5), (1.5, 29.5)][::-1]
    poly_obj('sticker', pts, mats['sticker'], place)
    # logo reads along +X with its top toward -Y when the pack is seen from below (as in r0106)
    cu = bpy.data.curves.new('sticker_skil', 'FONT'); cu.body = 'SKIL'; cu.size = 8.5; cu.shear = 0.25
    ob = bpy.data.objects.new('sticker_skil', cu); _coll().objects.link(ob); assign(ob, mats['white'])
    ob.rotation_euler = (math.radians(180), 0, 0); ob.location = (4.0, -22.0, -0.06)


def dress(p):
    clear()
    mats = dict(
        plastic=material('Plastic_Black', (0.018, 0.018, 0.02), rough=0.42),
        button=material('Plastic_Button', (0.025, 0.025, 0.028), rough=0.32),
        metal=material('Contact_Metal', (0.85, 0.85, 0.87), rough=0.22, metal=1.0),
        screw=material('Screw_Metal', (0.2, 0.2, 0.21), rough=0.35, metal=1.0),
        red=material('Label_Red', (0.62, 0.03, 0.04), rough=0.5),
        white=material('Label_White', (0.85, 0.85, 0.85), rough=0.5),
        label_grey=material('Label_Grey', (0.62, 0.64, 0.66), rough=0.5),
        label_dark=material('Label_Dark', (0.08, 0.08, 0.085), rough=0.5),
        led=material('LED', (0.9, 0.9, 0.9), rough=0.3),
        sticker=material('Sticker', (0.06, 0.06, 0.065), rough=0.35),
        black=material('Black', (0.005, 0.005, 0.005), rough=0.8),
    )
    for ob in bpy.data.objects:
        if ob.name == 'Battery': assign(ob, mats['plastic'])
        if ob.name in ('Battery_LatchButton', 'Battery_LatchPawl'): assign(ob, mats['button'])
    for side in (1, -1): side_label(side, p, mats)
    gauge(p, mats); contacts(p, mats); screws(p, mats); sticker(p, mats)
    for ob in _coll().objects:
        ob['battery_dress'] = 1
    return len(_coll().objects)
