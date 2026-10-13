import bpy
import math
from typing import Dict, Any
from mathutils import Vector

def apply_motion_jump(rig: bpy.types.Object, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Applies parameterized jump animation with parabolic flight, crouch, launch, and landing absorption.
    Parameters:
      start_height_m: float >= 0 (default 0.0)
      end_height_m: float >= 0 (default 0.0)
      forward_distance_m: float (default 1.5)
      duration_s: float >= 0.3 (default 1.2)
      fps: int (default 24)
    """
    start_height_m = float(params.get("start_height_m", 0.0))
    end_height_m = float(params.get("end_height_m", 0.0))
    forward_distance_m = float(params.get("forward_distance_m", 1.5))
    duration_s = float(params.get("duration_s", 1.2))
    fps = int(params.get("fps", 24))

    # Parameter Range Validation
    if start_height_m < 0:
        raise ValueError(f"start_height_m cannot be negative: {start_height_m}")
    if end_height_m < 0:
        raise ValueError(f"end_height_m cannot be negative: {end_height_m}")
    if duration_s < 0.3:
        raise ValueError(f"duration_s must be at least 0.3s, got {duration_s}")

    total_frames = max(10, int(round(duration_s * fps)))

    action_name = "JUMP_01"
    action = bpy.data.actions.get(action_name) or bpy.data.actions.new(action_name)
    if not rig.animation_data:
        rig.animation_data_create()
    rig.animation_data.action = action

    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='POSE')

    # Ensure feet IK are active
    for side in [".L", ".R"]:
        thigh_p = rig.pose.bones.get(f"thigh_parent{side}")
        if thigh_p and "IK_FK" in thigh_p:
            thigh_p["IK_FK"] = 0.0
            thigh_p.keyframe_insert(data_path='["IK_FK"]', frame=1)

    root = rig.pose.bones.get("root")
    torso = rig.pose.bones.get("torso")
    foot_ik_l = rig.pose.bones.get("foot_ik.L")
    foot_ik_r = rig.pose.bones.get("foot_ik.R")

    # Record foot lateral resting X coordinates
    foot_x_l = foot_ik_l.location.x if foot_ik_l else 0.1
    foot_x_r = foot_ik_r.location.x if foot_ik_r else -0.1

    # Animation timing phases (percentages of total duration):
    # 0.0 - 0.20: Crouch / Preparation
    # 0.20 - 0.80: Flight (parabola)
    # 0.80 - 0.90: Impact absorption
    # 0.90 - 1.00: Recovery to standing
    crouch_end_t = 0.20
    flight_end_t = 0.80
    absorb_end_t = 0.90

    # Apex jump boost above the higher of the two elevations
    apex_boost = 0.35

    for f in range(1, total_frames + 1):
        t = (f - 1) / (total_frames - 1)

        if t <= crouch_end_t:
            # Phase 1: Crouch
            phase_t = t / crouch_end_t
            # Crouch depth up to 0.12m
            crouch_amount = math.sin(phase_t * math.pi) * 0.12

            # Root stays at start position
            root_y = 0.0
            root_z = start_height_m
            torso_z = -crouch_amount

            # Feet stay firmly planted on platform surface
            foot_z = start_height_m
            foot_y = 0.0

        elif t <= flight_end_t:
            # Phase 2: Parabolic flight
            tau = (t - crouch_end_t) / (flight_end_t - crouch_end_t)
            # Smooth forward travel along -Y (character faces -Y)
            root_y = -forward_distance_m * tau

            # Parabolic trajectory peaking above start_height_m
            linear_z = start_height_m * (1.0 - tau) + end_height_m * tau
            # Lift boost ensures character leaps above platform before descending
            height_diff = max(0.0, start_height_m - end_height_m)
            apex_lift = (apex_boost + height_diff * 0.5 * (1.0 - tau)) * math.sin(tau * math.pi)
            root_z = linear_z + apex_lift

            # Torso extends then tucks slightly in mid-air
            torso_z = math.sin(tau * math.pi) * 0.05

            # Feet follow root in flight
            foot_y = root_y
            foot_z = root_z

        elif t <= absorb_end_t:
            # Phase 3: Landing impact absorption
            phase_t = (t - flight_end_t) / (absorb_end_t - flight_end_t)
            absorb_amount = math.sin(phase_t * math.pi) * 0.14

            root_y = -forward_distance_m
            root_z = end_height_m
            torso_z = -absorb_amount

            # Feet planted firmly on ground surface at end_height_m
            foot_y = -forward_distance_m
            foot_z = end_height_m

        else:
            # Phase 4: Recovery to standing
            phase_t = (t - absorb_end_t) / (1.0 - absorb_end_t)
            root_y = -forward_distance_m
            root_z = end_height_m
            torso_z = 0.0

            # Feet remain on ground
            foot_y = -forward_distance_m
            foot_z = end_height_m

        # Insert keyframes on control bones
        if root:
            root.location = Vector((0.0, root_y, root_z))
            root.keyframe_insert(data_path="location", frame=f)

        if torso:
            torso.location = Vector((0.0, 0.0, torso_z))
            torso.keyframe_insert(data_path="location", frame=f)

        # Foot IK bones are children of root, so local position = target_world - root_world
        local_foot_y = foot_y - root_y
        local_foot_z = foot_z - root_z

        if foot_ik_l:
            foot_ik_l.location = Vector((foot_x_l, local_foot_y, local_foot_z))
            foot_ik_l.keyframe_insert(data_path="location", frame=f)

        if foot_ik_r:
            foot_ik_r.location = Vector((foot_x_r, local_foot_y, local_foot_z))
            foot_ik_r.keyframe_insert(data_path="location", frame=f)

    bpy.ops.object.mode_set(mode='OBJECT')

    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = total_frames

    return {
        "action": action_name,
        "frame_start": 1,
        "frame_end": total_frames,
        "start_height_m": start_height_m,
        "end_height_m": end_height_m,
        "forward_distance_m": forward_distance_m,
        "duration_s": duration_s,
        "fps": fps
    }
