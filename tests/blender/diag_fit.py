import bpy
import json
import os
import sys
from mathutils import Vector

sys.path.insert(0, os.path.abspath("."))

print("--- Diagnostic: Inspecting bone chains in fit_template ---")
bpy.ops.wm.read_homefile(use_empty=True)
bpy.ops.preferences.addon_enable(module="rigify")

blend_path = os.path.abspath("assets/base_character.blend")
with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
    for obj_name in ["metarig", "base_character"]:
        if obj_name in data_from.objects:
            data_to.objects.append(obj_name)
for obj in data_to.objects:
    bpy.context.collection.objects.link(obj)

metarig = bpy.data.objects["metarig"]

with open("assets/test_images/expected_character_spec.json", "r") as f:
    spec = json.load(f)

joints = spec["joints"]
print("Target shoulder_L:", joints["shoulder_L"])
print("Target elbow_L:   ", joints["elbow_L"])
print("Target wrist_L:   ", joints["wrist_L"])

print("\nRest bones before fit:")
bones = metarig.data.bones
print("upper_arm.L head:", bones["upper_arm.L"].head_local, "tail:", bones["upper_arm.L"].tail_local)
print("forearm.L head:  ", bones["forearm.L"].head_local, "tail:", bones["forearm.L"].tail_local)

# Let's inspect pose bones
bpy.context.view_layer.objects.active = metarig
bpy.ops.object.mode_set(mode='POSE')

pbs = metarig.pose.bones
print("\nPose bone relationships:")
print("forearm.L parent:", pbs["forearm.L"].parent.name if pbs["forearm.L"].parent else None)
print("forearm.L bone use_connect:", metarig.data.bones["forearm.L"].use_connect)

# Test setting matrix on upper_arm.L
from blender_addon.commands.fit import cmd_fit_template
cmd_fit_template({"spec": spec})

print("\nRest bones AFTER cmd_fit_template:")
bones = metarig.data.bones
print("upper_arm.L head:", bones["upper_arm.L"].head_local, "tail:", bones["upper_arm.L"].tail_local)
print("forearm.L head:  ", bones["forearm.L"].head_local, "tail:", bones["forearm.L"].tail_local)
print("hand.L head:     ", bones["hand.L"].head_local, "tail:", bones["hand.L"].tail_local)
