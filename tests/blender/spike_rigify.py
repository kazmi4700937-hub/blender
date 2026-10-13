import bpy
import addon_utils
import sys
import os

print("Blender version:", bpy.app.version_string)
print("Python version:", sys.version)

# Check and enable rigify
installed_addons = [mod.__name__ for mod in addon_utils.modules()]
if "rigify" not in installed_addons:
    raise RuntimeError("Rigify is not installed in Blender!")

loaded_default, loaded_state = addon_utils.check("rigify")
if not loaded_state:
    bpy.ops.preferences.addon_enable(module="rigify")

# Empty scene
bpy.ops.wm.read_homefile(use_empty=True)
bpy.ops.object.armature_human_metarig_add()

metarig = bpy.context.active_object
print("Added metarig:", metarig.name)

# Generate rig
bpy.ops.pose.rigify_generate()
rig = bpy.data.objects.get("rig")
if not rig:
    raise RuntimeError("Failed to find generated rig 'rig'")

# Ensure docs directory exists
os.makedirs("docs", exist_ok=True)

# Collect all bone names
bone_names = [b.name for b in rig.data.bones]
bone_names.sort()

with open("docs/rigify_bones.txt", "w", encoding="utf-8") as f:
    for name in bone_names:
        f.write(name + "\n")

print(f"Saved {len(bone_names)} bone names to docs/rigify_bones.txt")

# Inspect key controls and IK/FK switch properties
print("\n--- Control Bones & Properties Analysis ---")
root_bones = [b for b in bone_names if "root" in b.lower()]
torso_bones = [b for b in bone_names if "torso" in b.lower() or "chest" in b.lower() or "spine" in b.lower() or "hips" in b.lower()]
ik_hand_bones = [b for b in bone_names if "hand" in b.lower() and "ik" in b.lower()]
ik_foot_bones = [b for b in bone_names if "foot" in b.lower() and "ik" in b.lower()]

print("Root bones:", root_bones)
print("Torso bones:", torso_bones)
print("IK Hand bones:", ik_hand_bones)
print("IK Foot bones:", ik_foot_bones)

# Check pose bone custom properties for IK/FK switches
print("\n--- Pose Bones with Custom Properties (IK/FK switches) ---")
ik_fk_switches = {}
for pb in rig.pose.bones:
    custom_props = [k for k in pb.keys() if not k.startswith("_")]
    if custom_props:
        for prop in custom_props:
            val = pb[prop]
            if "ik" in prop.lower() or "fk" in prop.lower() or "switch" in prop.lower():
                print(f"Bone: {pb.name} -> Prop: {prop} = {val}")
                ik_fk_switches[f"{pb.name}.{prop}"] = val

with open("docs/rigify_controls_summary.txt", "w", encoding="utf-8") as f:
    f.write("=== RIGIFY CONTROL BONES SUMMARY ===\n")
    f.write(f"Root: {root_bones}\n")
    f.write(f"Torso: {torso_bones}\n")
    f.write(f"IK Hands: {ik_hand_bones}\n")
    f.write(f"IK Feet: {ik_foot_bones}\n")
    f.write("\n=== IK/FK SWITCH PROPERTIES ===\n")
    for k, v in ik_fk_switches.items():
        f.write(f"{k} = {v}\n")

print("\nWrote summary to docs/rigify_controls_summary.txt")
print("Verification spike completed successfully.")
