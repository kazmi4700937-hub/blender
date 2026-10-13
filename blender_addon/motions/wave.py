import bpy
import math
from typing import Dict, Any
from mathutils import Euler

def apply_motion_wave(rig: bpy.types.Object, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Applies hand wave animation using Rigify FK arm controls.
    """
    duration_s = float(params.get("duration_s", 2.0))
    fps = int(params.get("fps", 24))
    total_frames = max(16, int(duration_s * fps))

    action_name = "WAVE_01"
    action = bpy.data.actions.get(action_name) or bpy.data.actions.new(action_name)
    if not rig.animation_data:
        rig.animation_data_create()
    rig.animation_data.action = action

    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='POSE')

    # Switch right arm to FK
    arm_parent = rig.pose.bones.get("upper_arm_parent.R")
    if arm_parent and "IK_FK" in arm_parent:
        arm_parent["IK_FK"] = 1.0
        arm_parent.keyframe_insert(data_path='["IK_FK"]', frame=1)

    upper_arm = rig.pose.bones.get("upper_arm_fk.R")
    forearm = rig.pose.bones.get("forearm_fk.R")
    hand = rig.pose.bones.get("hand_fk.R")

    # If FK bones not found, check standard/IK controls
    if not upper_arm:
        upper_arm = rig.pose.bones.get("upper_arm.R")
    if not forearm:
        forearm = rig.pose.bones.get("forearm.R")
    if not hand:
        hand = rig.pose.bones.get("hand.R")

    for f in range(1, total_frames + 1):
        t = (f - 1) / (total_frames - 1)
        # 3 wave cycles
        wave_cycle = math.sin(t * 6 * math.pi)

        # Upper arm raised outward
        if upper_arm:
            upper_arm.rotation_mode = 'XYZ'
            upper_arm.rotation_euler = Euler((0, math.radians(-75), math.radians(65)), 'XYZ')
            upper_arm.keyframe_insert(data_path="rotation_euler", frame=f)

        # Forearm waving back and forth
        if forearm:
            forearm.rotation_mode = 'XYZ'
            forearm.rotation_euler = Euler((0, math.radians(45) + wave_cycle * math.radians(25), 0), 'XYZ')
            forearm.keyframe_insert(data_path="rotation_euler", frame=f)

        # Hand flutter
        if hand:
            hand.rotation_mode = 'XYZ'
            hand.rotation_euler = Euler((0, wave_cycle * math.radians(15), 0), 'XYZ')
            hand.keyframe_insert(data_path="rotation_euler", frame=f)

    bpy.ops.object.mode_set(mode='OBJECT')

    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = total_frames

    return {
        "action": action_name,
        "frame_start": 1,
        "frame_end": total_frames,
        "fps": fps
    }
