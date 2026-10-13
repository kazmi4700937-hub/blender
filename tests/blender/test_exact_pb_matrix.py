import bpy
import os
from mathutils import Vector, Matrix

bpy.ops.wm.open_mainfile(filepath=os.path.abspath("assets/base_character.blend"))
metarig = bpy.data.objects["metarig"]

bpy.context.view_layer.objects.active = metarig
bpy.ops.object.mode_set(mode='POSE')
pb = metarig.pose.bones["upper_arm.L"]

target_head = Vector((0.2, 0.0, 1.5))
target_tail = Vector((0.5, 0.0, 1.5))

# If we want pb.head = target_head and pb.tail = target_tail:
# Notice that pb.matrix is in armature space.
# For any pose bone pb, in armature space:
# pb.head is pb.matrix.translation
# pb.tail is pb.matrix @ Vector((0, pb.bone.length, 0)) if unscaled,
# or pb.matrix @ Vector((0, pb.bone.length, 0)) when scaled!
print("Original pb.bone.length:", pb.bone.length)
print("Original pb.matrix:\n", pb.matrix)

# If pb.matrix is:
# col 0: x axis * sx
# col 1: (target_tail - target_head) / pb.bone.length
# col 2: z axis * sz
# col 3: target_head
axis_y = (target_tail - target_head) / pb.bone.length
axis_x = Vector((0, 1, 0)).cross(axis_y).normalized()
axis_z = axis_y.cross(axis_x).normalized()

mat = Matrix.Identity(4)
mat.col[0] = axis_x.to_4d()
mat.col[1] = axis_y.to_4d()
mat.col[2] = axis_z.to_4d()
mat.col[3] = target_head.to_4d()
mat[3][3] = 1.0

pb.matrix = mat
bpy.context.view_layer.update()

print("\nResulting pb.head:", pb.head)
print("Resulting pb.tail:", pb.tail)
print("Expected head:   ", target_head)
print("Expected tail:   ", target_tail)
