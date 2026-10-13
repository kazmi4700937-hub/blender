import bpy
import math
import os
import json
from mathutils import Vector

print("--- Rendering Ground Truth Reference Images ---")
blend_path = os.path.abspath("assets/base_character.blend")
bpy.ops.wm.open_mainfile(filepath=blend_path)

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT' if hasattr(bpy.types, 'RenderEngine') and 'BLENDER_EEVEE_NEXT' in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE'
scene.render.resolution_x = 1024
scene.render.resolution_y = 1024
scene.render.film_transparent = True
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'

# Create simple sun light
light_data = bpy.data.lights.new(name="Sun", type='SUN')
light_data.energy = 3.0
light_obj = bpy.data.objects.new(name="Sun", object_data=light_data)
scene.collection.objects.link(light_obj)
light_obj.rotation_euler = (math.radians(45), math.radians(30), math.radians(45))

# Camera settings
cam_data = bpy.data.cameras.new("OrthoCam")
cam_data.type = 'ORTHO'
cam_data.ortho_scale = 2.2  # 2.2m view height covers 1.98m character with margins
cam_obj = bpy.data.objects.new("OrthoCam", cam_data)
scene.collection.objects.link(cam_obj)
scene.camera = cam_obj

os.makedirs("assets/test_images", exist_ok=True)

# 1. Front Camera: at (0, -4, 1.0), looking at +Y
cam_obj.location = (0, -4.0, 1.0)
cam_obj.rotation_euler = (math.radians(90), 0, 0)
front_render_path = os.path.abspath("assets/test_images/front.png")
scene.render.filepath = front_render_path
bpy.ops.render.render(write_still=True)
print("Rendered front view to:", front_render_path)

# 2. Side Camera: at (4, 0, 1.0), looking at -X (so -Y is right edge of image)
cam_obj.location = (4.0, 0, 1.0)
cam_obj.rotation_euler = (math.radians(90), 0, math.radians(90))
side_render_path = os.path.abspath("assets/test_images/side.png")
scene.render.filepath = side_render_path
bpy.ops.render.render(write_still=True)
print("Rendered side view to:", side_render_path)

# Extract ground truth 3D joints and project to 2D image coordinates
metarig = bpy.data.objects["metarig"]
bones = metarig.data.bones

ground_truth = {
    "version": 1,
    "units": "m",
    "height_m": float(metarig.dimensions.z),
    "joints": {}
}

# Project 3D world coord to 2D image pixels for front and side
# Ortho bounds: center=(0, 1.0), scale=2.2
# x_px = 512 + (world_x / 2.2) * 1024
# y_px = 512 - ((world_z - 1.0) / 2.2) * 1024
def project_front(wx, wz):
    px = 512 + (wx / 2.2) * 1024
    py = 512 - ((wz - 1.0) / 2.2) * 1024
    return [int(round(px)), int(round(py))]

# For side view: facing right means front of body (-Y) is to the right (+image_x)
# px = 512 + (-wy / 2.2) * 1024
# py = 512 - ((wz - 1.0) / 2.2) * 1024
def project_side(wy, wz):
    px = 512 + (-wy / 2.2) * 1024
    py = 512 - ((wz - 1.0) / 2.2) * 1024
    return [int(round(px)), int(round(py))]

front_landmarks = {}
side_landmarks = {}

# Map metarig bones to Section 6 landmarks
landmark_bone_mapping = {
    "head_top": bones["spine.006"].tail_local,
    "chin": bones["spine.005"].head_local,
    "neck_base": bones["spine.004"].head_local,
    "shoulder_L": bones["upper_arm.L"].head_local,
    "shoulder_R": bones["upper_arm.R"].head_local,
    "elbow_L": bones["forearm.L"].head_local,
    "elbow_R": bones["forearm.R"].head_local,
    "wrist_L": bones["hand.L"].head_local,
    "wrist_R": bones["hand.R"].head_local,
    "hand_tip_L": bones["f_middle.03.L"].tail_local if "f_middle.03.L" in bones else bones["hand.L"].tail_local,
    "hand_tip_R": bones["f_middle.03.R"].tail_local if "f_middle.03.R" in bones else bones["hand.R"].tail_local,
    "hip_L": bones["thigh.L"].head_local,
    "hip_R": bones["thigh.R"].head_local,
    "knee_L": bones["shin.L"].head_local,
    "knee_R": bones["shin.R"].head_local,
    "ankle_L": bones["foot.L"].head_local,
    "ankle_R": bones["foot.R"].head_local,
    "toe_L": bones["toe.L"].tail_local,
    "toe_R": bones["toe.R"].tail_local,
    "crotch": bones["spine"].head_local
}

for name, pt in landmark_bone_mapping.items():
    ground_truth["joints"][name] = [round(float(pt.x), 4), round(float(pt.y), 4), round(float(pt.z), 4)]
    front_landmarks[name] = project_front(pt.x, pt.z)

# Side landmarks
side_landmark_pts = {
    "head_top": bones["spine.006"].tail_local,
    "chin": bones["spine.005"].head_local,
    "nose_tip": Vector((0, -0.15, bones["spine.006"].head_local.z)),
    "neck_base": bones["spine.004"].head_local,
    "shoulder": bones["upper_arm.L"].head_local,
    "elbow": bones["forearm.L"].head_local,
    "wrist": bones["hand.L"].head_local,
    "hip": bones["thigh.L"].head_local,
    "knee": bones["shin.L"].head_local,
    "ankle": bones["foot.L"].head_local,
    "toe": bones["toe.L"].tail_local,
    "heel": bones["foot.L"].tail_local,
    "chest_front": Vector((0, -0.16, bones["spine.003"].head_local.z)),
    "chest_back": Vector((0, 0.16, bones["spine.003"].head_local.z)),
    "belly_front": Vector((0, -0.14, bones["spine.001"].head_local.z)),
    "belly_back": Vector((0, 0.14, bones["spine.001"].head_local.z)),
    "buttock_back": Vector((0, 0.16, bones["spine"].head_local.z))
}

for name, pt in side_landmark_pts.items():
    side_landmarks[name] = project_side(pt.y, pt.z)

landmarks_json = {
    "version": 1,
    "image_size": { "front": [1024, 1024], "side": [1024, 1024] },
    "front": front_landmarks,
    "side": side_landmarks,
    "source": "ground_truth",
    "confirmed": True
}

with open("assets/test_images/expected_character_spec.json", "w", encoding="utf-8") as f:
    json.dump(ground_truth, f, indent=2)

with open("assets/test_images/ground_truth_landmarks.json", "w", encoding="utf-8") as f:
    json.dump(landmarks_json, f, indent=2)

print("Generated expected_character_spec.json and ground_truth_landmarks.json")
