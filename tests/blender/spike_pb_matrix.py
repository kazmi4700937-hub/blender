import bpy
import os
from mathutils import Vector, Matrix

print("--- Testing Pose Bone Matrix Assignment in Blender 4.2 ---")
bpy.ops.wm.open_mainfile(filepath=os.path.abspath("assets/base_character.blend"))
metarig = bpy.data.objects["metarig"]

bpy.context.view_layer.objects.active = metarig
bpy.ops.object.mode_set(mode='POSE')

pb = metarig.pose.bones["upper_arm.L"]
orig_mat = pb.matrix.copy()
print("Original pb.matrix translation:", orig_mat.to_translation())

# Test moving shoulder out by 0.1m and scaling along Y
target_head = orig_mat.to_translation() + Vector((0.1, 0, 0))
target_mat = orig_mat.copy()
target_mat.translation = target_head

pb.matrix = target_mat
bpy.context.view_layer.update()

print("New pb.matrix translation after update:", pb.matrix.to_translation())
print("pb.head:", pb.head)
bpy.ops.object.mode_set(mode='OBJECT')
print("Pose bone matrix assignment test finished.")
