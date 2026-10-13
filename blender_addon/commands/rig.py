import bpy
from typing import Dict, Any, List

def cmd_generate_rig(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Runs Rigify generate from the metarig in the current scene.
    Returns the generated rig name and full bone list.
    """
    metarig = bpy.data.objects.get("metarig")
    if not metarig:
        raise RuntimeError("No 'metarig' object found in scene to generate rig from")

    # Ensure rigify add-on is active
    bpy.ops.preferences.addon_enable(module="rigify")

    # Make metarig active and select it
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = metarig
    metarig.select_set(True)

    # Generate rig
    bpy.ops.pose.rigify_generate()

    rig = bpy.data.objects.get("rig")
    if not rig:
        raise RuntimeError("Rigify generation failed to produce 'rig' object")

    bone_names = [b.name for b in rig.data.bones]
    return {
        "rig_name": rig.name,
        "bone_count": len(bone_names),
        "bones": bone_names
    }


def cmd_bind_mesh(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parents the body mesh to the generated rig with automatic weights.
    Verifies that zero vertices remain unweighted.
    """
    mesh_name = params.get("mesh_name", "base_character")
    rig_name = params.get("rig_name", "rig")

    body = bpy.data.objects.get(mesh_name)
    rig = bpy.data.objects.get(rig_name)

    if not body:
        raise RuntimeError(f"Body mesh object '{mesh_name}' not found")
    if not rig:
        raise RuntimeError(f"Armature object '{rig_name}' not found")

    # Remove any existing armature modifier targeting metarig
    for mod in list(body.modifiers):
        if mod.type == 'ARMATURE':
            body.modifiers.remove(mod)

    # Parent mesh to generated rig with automatic weights
    bpy.ops.object.select_all(action='DESELECT')
    body.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig

    bpy.ops.object.parent_set(type='ARMATURE_AUTO')

    # Verify unweighted vertices
    unweighted = [v.index for v in body.data.vertices if len(v.groups) == 0]
    if unweighted:
        # Fallback: assign unweighted vertices to spine/pelvis
        pelvis_group = body.vertex_groups.get("DEF-spine") or body.vertex_groups.get("DEF-spine.001")
        if pelvis_group:
            for idx in unweighted:
                pelvis_group.add([idx], 1.0, 'REPLACE')
        unweighted = [v.index for v in body.data.vertices if len(v.groups) == 0]

    return {
        "bound": True,
        "mesh": body.name,
        "rig": rig.name,
        "vertex_count": len(body.data.vertices),
        "unweighted_count": len(unweighted)
    }


def cmd_list_bones(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lists all bones in the specified armature.
    """
    rig_name = params.get("rig_name", "rig")
    rig = bpy.data.objects.get(rig_name)
    if not rig or rig.type != 'ARMATURE':
        raise RuntimeError(f"Armature object '{rig_name}' not found")

    return {
        "rig_name": rig.name,
        "bones": [b.name for b in rig.data.bones]
    }
