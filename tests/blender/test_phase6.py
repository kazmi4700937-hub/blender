import bpy
import json
import math
import os
import sys
from mathutils import Vector

print("=== RUNNING PHASE 6 ACCEPTANCE TESTS ===")

sys.path.insert(0, os.path.abspath("."))
from blender_addon.commands.environment import cmd_build_environment
from blender_addon.commands.motion import cmd_apply_motion
from blender_addon.commands.scene import cmd_render_preview

# Open scene with rigged character
bpy.ops.wm.open_mainfile(filepath=os.path.abspath("assets/rigged_character.blend"))
bpy.ops.preferences.addon_enable(module="rigify")

# -------------------------------------------------------------
# Test 1: Invalid parameters are rejected with an error
# -------------------------------------------------------------
print("\n--- Test 1: Parameter validation checks ---")
# Negative height
try:
    cmd_build_environment({"height_m": -2.0})
    print("FAIL: Negative platform height was not rejected!")
    sys.exit(1)
except ValueError as e:
    print("PASS: Rejected negative platform height:", e)

# Negative jump height
try:
    cmd_apply_motion({"name": "jump", "params": {"start_height_m": -1.0}})
    print("FAIL: Negative start_height_m was not rejected!")
    sys.exit(1)
except ValueError as e:
    print("PASS: Rejected negative jump start_height_m:", e)

# Jump duration under 0.3s
try:
    cmd_apply_motion({"name": "jump", "params": {"duration_s": 0.15}})
    print("FAIL: Duration < 0.3s was not rejected!")
    sys.exit(1)
except ValueError as e:
    print("PASS: Rejected short jump duration:", e)

# -------------------------------------------------------------
# Test 2: Platform drop jump trajectory and foot placement
# -------------------------------------------------------------
print("\n--- Test 2: Jump from 2m platform to ground ---")
bpy.ops.wm.open_mainfile(filepath=os.path.abspath("assets/rigged_character.blend"))
bpy.ops.preferences.addon_enable(module="rigify")

# Build 2m platform drop environment
env_res = cmd_build_environment({"kind": "platform_drop", "height_m": 2.0, "size_m": 12.0})
print("Environment built:", env_res)

# Apply jump from 2m platform to 0m ground
jump_res = cmd_apply_motion({
    "name": "jump",
    "params": {
        "start_height_m": 2.0,
        "end_height_m": 0.0,
        "forward_distance_m": 2.5,
        "duration_s": 1.2,
        "fps": 24
    }
})
print("Jump motion applied:", jump_res)

rig = bpy.data.objects["rig"]
total_frames = jump_res["frame_end"]

# Inspect keyframes across timeline
foot_l = rig.pose.bones["foot_ik.L"]
foot_r = rig.pose.bones["foot_ik.R"]
root = rig.pose.bones["root"]

root_z_history = []

for f in range(1, total_frames + 1):
    bpy.context.scene.frame_set(f)
    bpy.context.view_layer.update()

    # Get world space matrix of bones
    mat_l = rig.matrix_world @ foot_l.matrix
    mat_r = rig.matrix_world @ foot_r.matrix
    mat_root = rig.matrix_world @ root.matrix

    pos_l = mat_l.to_translation()
    pos_r = mat_r.to_translation()
    pos_root = mat_root.to_translation()

    root_z_history.append(pos_root.z)

    # Foot sole height rests on ground/platform surface
    rest_foot_z = foot_l.bone.head_local.z
    sole_l_z = pos_l.z - rest_foot_z
    sole_r_z = pos_r.z - rest_foot_z

    # Acceptance test 2a: Frame 1 feet on 2m platform surface within 2 cm
    if f == 1:
        print(f"Frame 1: sole_L Z = {sole_l_z:.4f}m, sole_R Z = {sole_r_z:.4f}m (Expected: 2.0m)")
        if abs(sole_l_z - 2.0) > 0.02 or abs(sole_r_z - 2.0) > 0.02:
            print("FAIL: Frame 1 feet are not within 2 cm of 2.0m platform surface!")
            sys.exit(1)

    # Acceptance test 2b: Last frame feet on 0m ground within 2 cm
    if f == total_frames:
        print(f"Frame {total_frames}: sole_L Z = {sole_l_z:.4f}m, sole_R Z = {sole_r_z:.4f}m (Expected: 0.0m)")
        if abs(sole_l_z - 0.0) > 0.02 or abs(sole_r_z - 0.0) > 0.02:
            print("FAIL: Last frame feet are not within 2 cm of 0.0m ground!")
            sys.exit(1)

    # Acceptance test 2c: No feet sinking through ground more than 2 cm
    if sole_l_z < -0.02 or sole_r_z < -0.02:
        print(f"FAIL: Feet sinking below ground at frame {f}: L={sole_l_z:.4f}m, R={sole_r_z:.4f}m")
        sys.exit(1)

print("PASS: Feet start on 2m platform at frame 1 and land on ground at last frame (within 2cm).")
print("PASS: Zero ground sinking (>2cm) throughout entire jump.")

# -------------------------------------------------------------
# Test 3: Root height follows smooth parabolic arc
# -------------------------------------------------------------
print("\n--- Test 3: Root height arc smoothness ---")
max_dz = 0.0
for i in range(len(root_z_history) - 1):
    dz = abs(root_z_history[i + 1] - root_z_history[i])
    if dz > max_dz:
        max_dz = dz

print(f"Maximum frame-to-frame root delta Z: {max_dz:.4f}m (limit: 0.25m)")
if max_dz > 0.25:
    print(f"FAIL: Root trajectory has sudden jump ({max_dz:.4f}m > 0.25m)!")
    sys.exit(1)

# Verify apex is higher than start height
apex_z = max(root_z_history)
print(f"Apex root height: {apex_z:.4f}m (start was 2.0m)")
if apex_z <= 2.0:
    print("FAIL: Jump trajectory did not reach an apex above start height!")
    sys.exit(1)

print("PASS: Root height follows smooth parabolic arc with no sudden jumps.")

# -------------------------------------------------------------
# Test 4: Idle, Wave, Walk motions execute and set actions
# -------------------------------------------------------------
print("\n--- Test 4: Idle, Wave, and Walk motions ---")
for mot_name in ["idle", "wave", "walk"]:
    res_m = cmd_apply_motion({"name": mot_name, "params": {}})
    print(f"Motion '{mot_name}' -> action: {res_m.get('action')}, frames: {res_m.get('frame_start')}-{res_m.get('frame_end')}")
    assert rig.animation_data.action.name.startswith(mot_name.upper())

# Restore Jump animation for preview render
cmd_apply_motion({
    "name": "jump",
    "params": {"start_height_m": 2.0, "end_height_m": 0.0, "forward_distance_m": 2.5, "duration_s": 1.2}
})

# Render preview frames
os.makedirs("output/previews", exist_ok=True)
cmd_render_preview({"path": "output/previews/jump_start.png", "frame": 1})
cmd_render_preview({"path": "output/previews/jump_apex.png", "frame": 14})
cmd_render_preview({"path": "output/previews/jump_land.png", "frame": total_frames})
print("Rendered preview keyframes to output/previews/")

print("\n=== PHASE 6 ACCEPTANCE TESTS PASSED SUCCESSFULLY! ===")
