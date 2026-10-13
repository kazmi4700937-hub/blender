import bpy
import math
from typing import Dict, Any
from mathutils import Vector

def apply_motion_walk(rig: bpy.types.Object, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Applies forward walk cycle with alternating feet IK steps and torso bobbing.
    """
    duration_s = float(params.get("duration_s", 2.0))
    distance_m = float(params.get("distance_m", 2.0))
    fps = int(params.get("fps", 24))
    total_frames = max(16, int(round(duration_s * fps)))

    action_name = "WALK_01"
    action = bpy.data.actions.get(action_name) or bpy.data.actions.new(action_name)
    if not rig.animation_data:
        rig.animation_data_create()
    rig.animation_data.action = action

    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='POSE')

    # Ensure feet IK active
    for side in [".L", ".R"]:
        thigh_p = rig.pose.bones.get(f"thigh_parent{side}")
        if thigh_p and "IK_FK" in thigh_p:
            thigh_p["IK_FK"] = 0.0
            thigh_p.keyframe_insert(data_path='["IK_FK"]', frame=1)

    root = rig.pose.bones.get("root")
    torso = rig.pose.bones.get("torso")
    foot_l = rig.pose.bones.get("foot_ik.L")
    foot_r = rig.pose.bones.get("foot_ik.R")

    foot_x_l = foot_l.location.x if foot_l else 0.1
    foot_x_r = foot_r.location.x if foot_r else -0.1

    step_height = 0.06
    # 2 full gait strides (4 steps)
    cycles = 2.0

    for f in range(1, total_frames + 1):
        t = (f - 1) / (total_frames - 1)
        current_forward_y = -distance_m * t

        # Torso vertical bobbing (twice per stride cycle)
        bob = math.sin(t * cycles * 4 * math.pi) * 0.025

        # Foot L gait phase
        phase_l = (t * cycles * 2 * math.pi) % (2 * math.pi)
        # Foot R gait phase (offset by pi)
        phase_r = (phase_l + math.pi) % (2 * math.pi)

        lift_l = max(0.0, math.sin(phase_l)) * step_height
        lift_r = max(0.0, math.sin(phase_r)) * step_height

        stride_l = current_forward_y + math.cos(phase_l) * 0.2
        stride_r = current_forward_y + math.cos(phase_r) * 0.2

        if root:
            root.location = Vector((0.0, current_forward_y, 0.0))
            root.keyframe_insert(data_path="location", frame=f)

        if torso:
            torso.location = Vector((0.0, 0.0, bob))
            torso.keyframe_insert(data_path="location", frame=f)

        if foot_l:
            foot_l.location = Vector((foot_x_l, stride_l, lift_l))
            foot_l.keyframe_insert(data_path="location", frame=f)

        if foot_r:
            foot_r.location = Vector((foot_x_r, stride_r, lift_r))
            foot_r.keyframe_insert(data_path="location", frame=f)

    bpy.ops.object.mode_set(mode='OBJECT')

    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = total_frames

    return {
        "action": action_name,
        "frame_start": 1,
        "frame_end": total_frames,
        "distance_m": distance_m,
        "duration_s": duration_s,
        "fps": fps
    }
