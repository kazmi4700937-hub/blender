import bpy
import bmesh
import os

bpy.ops.wm.open_mainfile(filepath=os.path.abspath("assets/base_character.blend"))
body = bpy.data.objects["base_character"]

bm = bmesh.new()
bm.from_mesh(body.data)

volume = bm.calc_volume(signed=True)
print("Mesh signed volume:", volume)
print("Is signed volume positive?", volume > 0)
bm.free()
