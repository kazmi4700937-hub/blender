import bpy
import os

ADDON_VERSION = "1.0.0"

def cmd_ping(params):
    return {
        "blender_version": bpy.app.version_string,
        "addon_version": ADDON_VERSION
    }

def cmd_get_scene_info(params):
    scene = bpy.context.scene
    objects = []
    armatures = []
    
    for obj in bpy.data.objects:
        info = {
            "name": obj.name,
            "type": obj.type,
            "location": [round(v, 4) for v in obj.location],
            "visible": obj.visible_get()
        }
        objects.append(info)
        if obj.type == 'ARMATURE':
            armatures.append(obj.name)
            
    return {
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "frame_current": scene.frame_current,
        "fps": scene.render.fps,
        "objects": objects,
        "armatures": armatures
    }

def cmd_clear_scene(params):
    # Deselect all
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    
    # Remove orphan data blocks
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)
    for block in bpy.data.armatures:
        if block.users == 0:
            bpy.data.armatures.remove(block)
    for block in bpy.data.materials:
        if block.users == 0:
            bpy.data.materials.remove(block)
    for block in bpy.data.actions:
        if block.users == 0:
            bpy.data.actions.remove(block)
            
    return {"cleared": True}

def cmd_save_blend(params):
    path = params.get("path")
    if not path:
        raise ValueError("Param 'path' is required for save_blend")
    abs_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=abs_path)
    return {"saved": True, "path": abs_path}

def cmd_render_preview(params):
    path = params.get("path")
    if not path:
        raise ValueError("Param 'path' is required for render_preview")
    frame = params.get("frame", bpy.context.scene.frame_current)
    bpy.context.scene.frame_set(frame)
    
    abs_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    
    orig_path = bpy.context.scene.render.filepath
    orig_format = bpy.context.scene.render.image_settings.file_format
    orig_engine = bpy.context.scene.render.engine
    orig_res_x = bpy.context.scene.render.resolution_x
    orig_res_y = bpy.context.scene.render.resolution_y
    try:
        bpy.context.scene.render.filepath = abs_path
        bpy.context.scene.render.image_settings.file_format = 'PNG'
        bpy.context.scene.render.engine = 'BLENDER_WORKBENCH'
        bpy.context.scene.render.resolution_x = 640
        bpy.context.scene.render.resolution_y = 480
        # Ensure a camera exists if none present
        if not bpy.context.scene.camera:
            bpy.ops.object.camera_add(location=(0, -4, 1.2), rotation=(1.5708, 0, 0))
            bpy.context.scene.camera = bpy.context.active_object
        bpy.ops.render.render(write_still=True)
    finally:
        bpy.context.scene.render.filepath = orig_path
        bpy.context.scene.render.image_settings.file_format = orig_format
        bpy.context.scene.render.engine = orig_engine
        bpy.context.scene.render.resolution_x = orig_res_x
        bpy.context.scene.render.resolution_y = orig_res_y
        
    return {"rendered": True, "path": abs_path, "frame": frame}

def cmd_set_frame_range(params):
    start = params.get("start")
    end = params.get("end")
    if start is None or end is None:
        raise ValueError("Params 'start' and 'end' are required for set_frame_range")
    if start > end:
        raise ValueError(f"Start frame ({start}) cannot be greater than end frame ({end})")
    bpy.context.scene.frame_start = int(start)
    bpy.context.scene.frame_end = int(end)
    return {"frame_start": bpy.context.scene.frame_start, "frame_end": bpy.context.scene.frame_end}

# Helper test command for Phase 1 acceptance test
def cmd_create_cube(params):
    name = params.get("name", "Cube")
    size = params.get("size", 1.0)
    bpy.ops.mesh.primitive_cube_add(size=size)
    cube = bpy.context.active_object
    cube.name = name
    return {"created": cube.name}
