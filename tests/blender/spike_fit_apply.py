import bpy
import os

print("--- Testing Armature Apply Pose as Rest Pose in Blender 4.2 ---")
bpy.ops.wm.open_mainfile(filepath=os.path.abspath("assets/base_character.blend"))

metarig = bpy.data.objects["metarig"]
body = bpy.data.objects["base_character"]

bpy.context.view_layer.objects.active = metarig
bpy.ops.object.mode_set(mode='POSE')

# Move upper arm pose bone
p_uarm = metarig.pose.bones["upper_arm.L"]
p_uarm.location = (0.05, 0, 0)
p_uarm.scale = (1.2, 1.0, 1.0)

# Check if apply pose as rest pose exists
print("Available operators in bpy.ops.pose:")
print([op for op in dir(bpy.ops.pose) if "armature" in op or "apply" in op])

# Apply modifier on mesh
bpy.context.view_layer.objects.active = body
bpy.ops.object.mode_set(mode='OBJECT')
for m in body.modifiers:
    if m.type == 'ARMATURE':
        bpy.ops.object.modifier_apply(modifier=m.name)
        print("Applied armature modifier successfully!")

# Apply pose as rest pose on armature
bpy.context.view_layer.objects.active = metarig
bpy.ops.object.mode_set(mode='POSE')
bpy.ops.pose.armature_apply(selected=False)
print("Applied pose as rest pose successfully!")
bpy.ops.object.mode_set(mode='OBJECT')

print("Spike completed successfully.")
