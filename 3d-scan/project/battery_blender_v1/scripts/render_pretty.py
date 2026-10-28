"""Material renders (run inside Blender): photo-matched views and studio beauty shots.

photo_match(rids): renders from each photo's calibrated camera with the mat as a white ground
plane, into out/pretty/match_<rid>.png, for side-by-side comparison with the photo.
beauty(): four studio views into out/pretty/beauty_<n>.png.
"""
import bpy, json, os, math
from mathutils import Matrix, Vector

PROJ = '/Users/samw3/prj/Make/stocko/3d-scan/project/battery_blender_v1'
OUT = os.path.join(PROJ, 'out')
PRETTY = os.path.join(OUT, 'pretty')


def _engine(name):
    sc = bpy.context.scene
    try:
        sc.render.engine = name
    except TypeError as e:
        print('engine', e)


def setup(samples=96):
    sc = bpy.context.scene
    _engine('CYCLES')
    cy = sc.cycles
    cy.samples = samples
    cy.use_denoising = True
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        for dt in ('METAL', 'CUDA', 'OPTIX', 'HIP', 'ONEAPI'):
            try:
                prefs.compute_device_type = dt; break
            except TypeError:
                continue
        prefs.get_devices()
        for d in prefs.devices: d.use = True
        cy.device = 'GPU'
    except Exception as e:
        print('gpu setup', e)
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGB'
    try:
        sc.view_settings.view_transform = 'AgX'
    except TypeError:
        sc.view_settings.view_transform = 'Filmic'
    # world: soft bright room
    w = sc.world or bpy.data.worlds.new('World'); sc.world = w
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs['Color'].default_value = (0.8, 0.8, 0.82, 1); bg.inputs['Strength'].default_value = 0.9
    # lights
    for name, loc, energy, size in (('Key', (-150, 120, 260), 9e5, 180), ('Fill', (200, -160, 160), 3.5e5, 220), ('Rim', (60, 220, 90), 2.5e5, 120)):
        ob = bpy.data.objects.get(name)
        if ob is None:
            ld = bpy.data.lights.new(name, 'AREA'); ob = bpy.data.objects.new(name, ld); sc.collection.objects.link(ob)
        ob.data.type = 'AREA'; ob.data.energy = energy; ob.data.size = size
        ob.location = loc
        d = Vector((0, 0, 20)) - Vector(loc); ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    for n in ('Light',):
        if bpy.data.objects.get(n): bpy.data.objects[n].hide_render = True
    # ground plane (the mat)
    g = bpy.data.objects.get('Ground')
    if g is None:
        bpy.ops.mesh.primitive_plane_add(size=1)
        g = bpy.context.active_object; g.name = 'Ground'
        for c in g.users_collection: c.objects.unlink(g)
        sc.collection.objects.link(g)
    g.scale = (216, 279, 1)
    m = bpy.data.materials.get('Mat_Paper') or bpy.data.materials.new('Mat_Paper'); m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    b.inputs['Base Color'].default_value = (0.85, 0.85, 0.85, 1); b.inputs['Roughness'].default_value = 0.9
    g.data.materials.clear(); g.data.materials.append(m)
    for ob in sc.objects:
        if ob.type == 'MESH' or ob.type == 'FONT':
            ob.hide_render = not (ob.name.startswith('Battery') or ob.get('battery_dress') or ob.name == 'Ground')
    return g


def _cam(name):
    cam = bpy.data.objects.get(name)
    if cam is None:
        cd = bpy.data.cameras.new(name); cam = bpy.data.objects.new(name, cd); bpy.context.scene.collection.objects.link(cam)
    return cam


def photo_match(rids, samples=96):
    g = setup(samples)
    views = json.load(open(os.path.join(OUT, 'views.json')))
    sc = bpy.context.scene
    cam = _cam('PhotoCam'); sc.camera = cam; cd = cam.data
    os.makedirs(PRETTY, exist_ok=True)
    for rid in rids:
        v = views[rid]; K = v['K']; w, h = v['w'], v['h']
        sc.render.resolution_x, sc.render.resolution_y = w, h
        sc.render.resolution_percentage = 100
        cd.sensor_fit = 'HORIZONTAL'; cd.sensor_width = 36.0; cd.lens = K[0][0] * 36.0 / w
        cd.shift_x = (w / 2.0 - (K[0][2] + 0.5)) / w; cd.shift_y = ((K[1][2] + 0.5) - h / 2.0) / w
        cd.clip_start = 5; cd.clip_end = 5000
        flip = Matrix(((1, 0, 0), (0, -1, 0), (0, 0, -1)))
        M = (Matrix(v['R']) @ flip).to_4x4(); M.translation = Vector(v['t']); cam.matrix_world = M
        g.matrix_world = Matrix(v['mat_to_batt']) @ Matrix.Diagonal((216, 279, 1, 1))
        sc.render.filepath = os.path.join(PRETTY, f'match_{rid}.png')
        bpy.ops.render.render(write_still=True)


def beauty(samples=128, res=(1600, 1200)):
    g = setup(samples)
    g.matrix_world = Matrix.Diagonal((600, 600, 1, 1))
    sc = bpy.context.scene
    cam = _cam('BeautyCam'); sc.camera = cam; cd = cam.data
    cd.sensor_fit = 'AUTO'; cd.lens = 85; cd.shift_x = cd.shift_y = 0; cd.clip_start = 5; cd.clip_end = 5000
    sc.render.resolution_x, sc.render.resolution_y = res; sc.render.resolution_percentage = 100
    os.makedirs(PRETTY, exist_ok=True)
    shots = [(-35, 32, 420), (145, 30, 420), (215, 55, 420), (60, 18, 430), (-90, 89, 420)]
    for i, (az, el, d) in enumerate(shots):
        target = Vector((0, 0, 20))
        a, e = math.radians(az), math.radians(el)
        pos = target + d * Vector((math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)))
        cam.location = pos
        cam.rotation_euler = (target - pos).to_track_quat('-Z', 'Y').to_euler()
        sc.render.filepath = os.path.join(PRETTY, f'beauty_{i}.png')
        bpy.ops.render.render(write_still=True)
    # underside: flip the view by hiding the ground and looking from below
    g.hide_render = True
    cam.location = Vector((0, 0, -420)); cam.rotation_euler = (0, math.radians(180), math.radians(90))
    sc.render.filepath = os.path.join(PRETTY, 'beauty_bottom.png')
    bpy.ops.render.render(write_still=True)
    g.hide_render = False
