import bpy
import math
from typing import Dict, Any

def apply_motion_idle(rig: bpy.types.Object, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Applies gentle idle breathing animation to Rigify control bones.
    """
    duration_s = float(params.get("duration_s", 2.0))
    fps = int(params.get("fps", 24))
    total_frames = max(12, int(duration_s * fps))

    action_name = "IDLE_01"
    action = bpy.data.actions.get(action_name) or bpy.data.actions.new(action_name)
    if not rig.animation_data:
        rig.animation_data_create()
    rig.animation_data.action = action

    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='POSE')

    torso = rig.pose.bones.get("torso")
    chest = rig.pose.bones.get("chest")

    for f in range(1, total_frames + 1):
        t = (f - 1) / (total_frames - 1)
        cycle = math.sin(t * 2 * math.pi)

        if torso:
            torso.location = (0, 0, cycle * 0.012)
            torso.keyframe_insert(data_path="location", frame=f)

        if chest:
            chest.rotation_mode = 'XYZ'
            chest.rotation_euler = (cycle * 0.02, 0, 0)
            chest.keyframe_insert(data_path="rotation_euler", frame=f)

    bpy.ops.object.mode_set(mode='OBJECT')

    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = total_frames

    return {
        "action": action_name,
        "frame_start": 1,
        "frame_end": total_frames,
        "fps": fps
    }
