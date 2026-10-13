import bpy
import os
import sys

print("=== RUNNING PHASE 0 ACCEPTANCE TEST ===")

blend_file = os.path.abspath("assets/base_character.blend")
if not os.path.exists(blend_file):
    print("FAIL: base_character.blend not found!")
    sys.exit(1)

bpy.ops.wm.open_mainfile(filepath=blend_file)
bpy.ops.preferences.addon_enable(module="rigify")

metarig = bpy.data.objects.get("metarig")
body = bpy.data.objects.get("base_character")

if not metarig:
    print("FAIL: metarig object not found in asset!")
    sys.exit(1)
if not body:
    print("FAIL: base_character object not found in asset!")
    sys.exit(1)

# Check unweighted vertices
unweighted = [v.index for v in body.data.vertices if len(v.groups) == 0]
if unweighted:
    print(f"FAIL: {len(unweighted)} unweighted vertices in base_character!")
    sys.exit(1)

print("PASS: Base character mesh has zero unweighted vertices.")

# Generate rig
bpy.context.view_layer.objects.active = metarig
metarig.select_set(True)
bpy.ops.pose.rigify_generate()

rig = bpy.data.objects.get("rig")
if not rig:
    print("FAIL: Rigify generate did not produce 'rig' object!")
    sys.exit(1)

print(f"PASS: Rigify successfully generated '{rig.name}' with {len(rig.data.bones)} bones.")

# Verify control bone names
rig_bones = {b.name for b in rig.data.bones}

required_controls = [
    "root",
    "torso",
    "chest",
    "hips",
    "hand_ik.L",
    "hand_ik.R",
    "foot_ik.L",
    "foot_ik.R"
]

missing = [b for b in required_controls if b not in rig_bones]
if missing:
    print(f"FAIL: Missing required control bones in generated rig: {missing}")
    sys.exit(1)

print("PASS: All required control bones verified in generated rig.")

# Check IK/FK switch properties
for limb in ["thigh_parent.L", "thigh_parent.R", "upper_arm_parent.L", "upper_arm_parent.R"]:
    pb = rig.pose.bones.get(limb)
    if not pb or "IK_FK" not in pb:
        print(f"FAIL: Missing IK_FK property on {limb}")
        sys.exit(1)

print("PASS: IK/FK switch properties verified on all limb parent bones.")
print("=== PHASE 0 ACCEPTANCE TESTS PASSED SUCCESSFULLY! ===")
