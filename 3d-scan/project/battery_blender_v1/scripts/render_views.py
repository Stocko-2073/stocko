"""Render the battery model from photo cameras (run inside Blender).

Reads out/views.json, renders each listed view with the Workbench engine over a transparent
background to out/render/<rid>.png (flat single colour, studio light -> shading edges
survive, alpha = silhouette).  render(rids) is the entry point.
"""
import bpy, json, os, math
from mathutils import Matrix, Vector

PROJ = '/Users/samw3/prj/Make/stocko/3d-scan/project/battery_blender_v1'
OUT = os.path.join(PROJ, 'out')


def _camera():
    cam = bpy.data.objects.get('PhotoCam')
    if cam is None:
        cd = bpy.data.cameras.new('PhotoCam')
        cam = bpy.data.objects.new('PhotoCam', cd)
        bpy.context.scene.collection.objects.link(cam)
    return cam


def setup_scene():
    sc = bpy.context.scene
    try:
        sc.render.engine = 'BLENDER_WORKBENCH'
    except TypeError as e:
        print('engine error', e)
    sh = sc.display.shading
    sh.light = 'STUDIO'
    sh.color_type = 'SINGLE'
    sh.single_color = (0.8, 0.8, 0.8)
    sh.show_object_outline = False
    sh.show_cavity = False
    sh.show_specular_highlight = False
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGBA'
    sc.display_settings.display_device = sc.display_settings.display_device
    try:
        sc.view_settings.view_transform = 'Standard'
    except TypeError:
        pass
    sc.render.resolution_percentage = 100
    for ob in sc.objects:
        if ob.type in ('MESH', 'FONT', 'CURVE'):
            ob.hide_render = not ob.name.startswith('Battery')   # geometry only: no dressing, no ground


def render(rids=None, subdir='render'):
    views = json.load(open(os.path.join(OUT, 'views.json')))
    rids = rids or list(views)
    setup_scene()
    sc = bpy.context.scene
    cam = _camera(); sc.camera = cam
    cd = cam.data
    os.makedirs(os.path.join(OUT, subdir), exist_ok=True)
    for rid in rids:
        v = views[rid]
        K = v['K']; w, h = v['w'], v['h']
        sc.render.resolution_x, sc.render.resolution_y = w, h
        cd.type = 'PERSP'; cd.sensor_fit = 'HORIZONTAL'; cd.sensor_width = 36.0
        cd.lens = K[0][0] * 36.0 / w
        # principal point -> lens shift (in units of the larger image dimension)
        cd.shift_x = (w / 2.0 - (K[0][2] + 0.5)) / w
        cd.shift_y = ((K[1][2] + 0.5) - h / 2.0) / w
        cd.clip_start = 5.0; cd.clip_end = 5000.0
        R = Matrix(v['R']); t = Vector(v['t'])
        flip = Matrix(((1, 0, 0), (0, -1, 0), (0, 0, -1)))   # OpenCV cam -> Blender cam axes
        Rb = R @ flip
        M = Rb.to_4x4(); M.translation = t
        cam.matrix_world = M
        sc.render.filepath = os.path.join(OUT, subdir, rid + '.png')
        bpy.ops.render.render(write_still=True)
    return len(rids)
