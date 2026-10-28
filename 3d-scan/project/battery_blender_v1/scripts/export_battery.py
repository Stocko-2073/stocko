"""Export the battery (run inside Blender): STL (geometry, mm) and GLB (dressed, metres)."""
import bpy, os

PROJ = '/Users/samw3/prj/Make/stocko/3d-scan/project/battery_blender_v1'


def export():
    sc = bpy.context.scene
    geo = [o for o in sc.objects if o.name.startswith('Battery') and o.type == 'MESH']
    dress = [o for o in sc.objects if o.get('battery_dress')]
    bpy.ops.object.select_all(action='DESELECT')
    for o in geo: o.select_set(True)
    bpy.context.view_layer.objects.active = geo[0]
    bpy.ops.wm.stl_export(filepath=os.path.join(PROJ, 'skil_pwrcore20_2ah.stl'), export_selected_objects=True,
                          global_scale=1.0, use_scene_unit=False, apply_modifiers=True)
    # glTF is in metres: export through a temporary 0.001-scaled parent.  Blender keeps the world
    # transform when a child is un-parented, so remember every object's matrix and put it back.
    saved = {o.name: o.matrix_world.copy() for o in geo + dress}
    root = bpy.data.objects.new('BatteryRoot_mm', None); sc.collection.objects.link(root)
    root.scale = (0.001, 0.001, 0.001)
    for o in geo + dress:
        o.parent = root
    bpy.ops.object.select_all(action='DESELECT')
    root.select_set(True)
    for o in geo + dress: o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=os.path.join(PROJ, 'skil_pwrcore20_2ah.glb'), export_format='GLB',
                              use_selection=True, export_apply=True)
    for o in geo + dress:
        o.parent = None
        o.matrix_world = saved[o.name]
    bpy.data.objects.remove(root, do_unlink=True)
    return len(geo), len(dress)


def save():
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(PROJ, 'battery.blend'), check_existing=False)
