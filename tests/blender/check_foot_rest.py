import bpy
import os

bpy.ops.wm.open_mainfile(filepath=os.path.abspath("assets/rigged_character.blend"))
rig = bpy.data.objects["rig"]
foot_l = rig.pose.bones["foot_ik.L"]
print("foot_ik.L head_local Z:", foot_l.bone.head_local.z)
print("foot_ik.L matrix translation Z in rest pose:", (rig.matrix_world @ foot_l.matrix).to_translation().z)
