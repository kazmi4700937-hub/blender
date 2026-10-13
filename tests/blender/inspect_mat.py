import bpy
import os

bpy.ops.wm.open_mainfile(filepath=os.path.abspath("assets/base_character.blend"))
metarig = bpy.data.objects["metarig"]
b = metarig.data.bones["upper_arm.L"]
print("matrix_local col lengths:", [b.matrix_local.to_3x3().col[i].length for i in range(3)])
print("b.length:", b.length)

bpy.context.view_layer.objects.active = metarig
bpy.ops.object.mode_set(mode='POSE')
pb = metarig.pose.bones["upper_arm.L"]
print("pb.matrix col lengths in rest pose:", [pb.matrix.to_3x3().col[i].length for i in range(3)])
print("pb.head:", pb.head)
print("pb.tail:", pb.tail)
print("vector tail - head:", pb.tail - pb.head)
print("length of (pb.tail - pb.head):", (pb.tail - pb.head).length)
