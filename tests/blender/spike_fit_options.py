import bpy
import json
from mathutils import Vector, Matrix, Quaternion
import os

print("--- Testing Template Fitting Strategies ---")
blend_path = os.path.abspath("assets/base_character.blend")
spec_path = os.path.abspath("assets/test_images/expected_character_spec.json")

with open(spec_path, "r", encoding="utf-8") as f:
    spec = json.load(f)

joints = spec["joints"]

bpy.ops.wm.open_mainfile(filepath=blend_path)
metarig = bpy.data.objects["metarig"]
body = bpy.data.objects["base_character"]

# Test direct edit bones adjustment vs pose deformation
# Let's inspect the edit bones:
bpy.context.view_layer.objects.active = metarig
bpy.ops.object.mode_set(mode='EDIT')
ebones = metarig.data.edit_bones

orig_sh_l = Vector(ebones["upper_arm.L"].head)
print("Original upper_arm.L head:", orig_sh_l)
print("Target shoulder_L:", joints["shoulder_L"])

bpy.ops.object.mode_set(mode='OBJECT')
print("Completed inspection.")
