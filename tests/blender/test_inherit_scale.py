import bpy
import os

bpy.ops.wm.open_mainfile(filepath=os.path.abspath("assets/base_character.blend"))
metarig = bpy.data.objects["metarig"]

print("Inherit scale options for bone:")
b = metarig.data.bones["forearm.L"]
print("b.inherit_scale:", getattr(b, "inherit_scale", None))
print("b.use_inherit_scale:", getattr(b, "use_inherit_scale", None))
