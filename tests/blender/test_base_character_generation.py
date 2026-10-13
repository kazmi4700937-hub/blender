import bpy
import bmesh
import math
from mathutils import Vector, Matrix
import os

print("--- Generating Base Character Asset ---")
bpy.ops.wm.read_homefile(use_empty=True)
bpy.ops.preferences.addon_enable(module="rigify")

# Add the human metarig
bpy.ops.object.armature_human_metarig_add()
metarig = bpy.context.active_object
metarig.name = "metarig"

# For standard T-pose, metarig arms are slightly bent/angled.
# Let's align arms into a clean horizontal T-pose in edit mode for the metarig and mesh!
bpy.ops.object.mode_set(mode='EDIT')
ebones = metarig.data.edit_bones

# Ensure arms are horizontal in T-pose along X axis (Z and Y constant)
shoulder_l = ebones.get("shoulder.L")
upper_arm_l = ebones.get("upper_arm.L")
forearm_l = ebones.get("forearm.L")
hand_l = ebones.get("hand.L")

arm_z = upper_arm_l.head.z
arm_y = upper_arm_l.head.y

upper_arm_len = (upper_arm_l.tail - upper_arm_l.head).length
forearm_len = (forearm_l.tail - forearm_l.head).length
hand_len = (hand_l.tail - hand_l.head).length

# Straighten Left arm along +X
upper_arm_l.tail = Vector((upper_arm_l.head.x + upper_arm_len, arm_y, arm_z))
forearm_l.head = upper_arm_l.tail
forearm_l.tail = Vector((forearm_l.head.x + forearm_len, arm_y, arm_z))
hand_l.head = forearm_l.tail
hand_l.tail = Vector((hand_l.head.x + hand_len, arm_y, arm_z))

# Symmetrize Right arm to match (-X)
shoulder_r = ebones.get("shoulder.R")
upper_arm_r = ebones.get("upper_arm.R")
forearm_r = ebones.get("forearm.R")
hand_r = ebones.get("hand.R")

upper_arm_r.head = Vector((-upper_arm_l.head.x, upper_arm_l.head.y, upper_arm_l.head.z))
upper_arm_r.tail = Vector((-upper_arm_l.tail.x, upper_arm_l.tail.y, upper_arm_l.tail.z))
forearm_r.head = upper_arm_r.tail
forearm_r.tail = Vector((-forearm_l.tail.x, forearm_l.tail.y, forearm_l.tail.z))
hand_r.head = forearm_r.tail
hand_r.tail = Vector((-hand_l.tail.x, hand_l.tail.y, hand_l.tail.z))

# Adjust fingers to align horizontally along X
for prefix in ["thumb", "f_index", "f_middle", "f_ring", "f_pinky"]:
    for side in [".L", ".R"]:
        sign = 1.0 if side == ".L" else -1.0
        for i in range(1, 4):
            b_name = f"{prefix}.0{i}{side}"
            b = ebones.get(b_name)
            if b:
                # Keep them in palm/hand range
                pass

# Make sure feet rest on ground Z = 0
foot_l = ebones.get("foot.L")
toe_l = ebones.get("toe.L")
foot_r = ebones.get("foot.R")
toe_r = ebones.get("toe.R")

foot_l.tail.z = 0.05
toe_l.head.z = 0.05
toe_l.tail.z = 0.02
foot_r.tail.z = 0.05
toe_r.head.z = 0.05
toe_r.tail.z = 0.02

bpy.ops.object.mode_set(mode='OBJECT')

# Now build the base character mesh around these bone locations
mesh = bpy.data.meshes.new("base_character_mesh")
body_obj = bpy.data.objects.new("base_character", mesh)
bpy.context.collection.objects.link(body_obj)

bm = bmesh.new()

# Helper functions to build limbs and torso
def add_cylinder_between(bm, p1, p2, r1, r2, segs=12, rings=4):
    v_axis = p2 - p1
    length = v_axis.length
    if length < 1e-5:
        return []
    v_norm = v_axis.normalized()
    # Find perpendicular vector
    up = Vector((0, 0, 1)) if abs(v_norm.z) < 0.9 else Vector((0, 1, 0))
    radial1 = v_norm.cross(up).normalized()
    radial2 = v_norm.cross(radial1).normalized()
    
    ring_verts = []
    for ring in range(rings):
        t = ring / (rings - 1)
        center = p1 + v_axis * t
        r = r1 + (r2 - r1) * t
        current_ring = []
        for s in range(segs):
            theta = 2 * math.pi * s / segs
            pos = center + (radial1 * math.cos(theta) + radial2 * math.sin(theta)) * r
            current_ring.append(bm.verts.new(pos))
        ring_verts.append(current_ring)
        
    for ring in range(rings - 1):
        for s in range(segs):
            s_next = (s + 1) % segs
            bm.faces.new([
                ring_verts[ring][s],
                ring_verts[ring][s_next],
                ring_verts[ring + 1][s_next],
                ring_verts[ring + 1][s]
            ])
            
    # Caps
    cap_bot = bm.faces.new(reversed(ring_verts[0]))
    cap_top = bm.faces.new(ring_verts[-1])
    all_verts = [v for ring in ring_verts for v in ring]
    return all_verts

def add_capsule_between(bm, p1, p2, r, segs=12, rings=4):
    return add_cylinder_between(bm, p1, p2, r, r, segs=segs, rings=rings)

# Extract key coordinates from metarig
bones = metarig.data.bones
spine_head = bones["spine"].head_local
spine_tail = bones["spine"].tail_local
chest_head = bones["spine.002"].head_local
chest_tail = bones["spine.003"].tail_local
neck_head = bones["spine.004"].head_local
head_head = bones["spine.005"].head_local
head_tail = bones["spine.006"].tail_local

# Head: stylized humanoid head (icosphere / cube-sphere)
head_center = (head_head + head_tail) * 0.5
bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=12, radius=0.12, matrix=Matrix.Translation(head_center))

# Neck: cylinder
add_cylinder_between(bm, neck_head, head_head, 0.06, 0.055, segs=12, rings=3)

# Torso / Chest / Pelvis
# Pelvis / Hips
add_cylinder_between(bm, spine_head, spine_tail, 0.16, 0.14, segs=14, rings=3)
# Spine / Midsection
add_cylinder_between(bm, spine_tail, chest_head, 0.14, 0.17, segs=14, rings=3)
# Chest / Upper Torso
add_cylinder_between(bm, chest_head, neck_head, 0.17, 0.15, segs=14, rings=4)

# Limbs (Left and Right)
for side, sign in [(".L", 1.0), (".R", -1.0)]:
    # Clavicle / Shoulder connector
    sh_head = bones[f"shoulder{side}"].head_local
    sh_tail = bones[f"shoulder{side}"].tail_local
    add_cylinder_between(bm, sh_head, sh_tail, 0.07, 0.065, segs=10, rings=3)
    
    # Upper Arm
    uarm_head = bones[f"upper_arm{side}"].head_local
    uarm_tail = bones[f"upper_arm{side}"].tail_local
    add_cylinder_between(bm, uarm_head, uarm_tail, 0.065, 0.05, segs=12, rings=4)
    
    # Forearm
    farm_head = bones[f"forearm{side}"].head_local
    farm_tail = bones[f"forearm{side}"].tail_local
    add_cylinder_between(bm, farm_head, farm_tail, 0.05, 0.04, segs=12, rings=4)
    
    # Hand
    hand_head = bones[f"hand{side}"].head_local
    hand_tail = bones[f"hand{side}"].tail_local
    add_cylinder_between(bm, hand_head, hand_tail, 0.04, 0.035, segs=10, rings=3)
    
    # Fingers (Thumb, Index, Middle, Ring, Pinky)
    for finger in ["thumb", "f_index", "f_middle", "f_ring", "f_pinky"]:
        b1 = bones.get(f"{finger}.01{side}")
        b3 = bones.get(f"{finger}.03{side}")
        if b1 and b3:
            add_cylinder_between(bm, b1.head_local, b3.tail_local, 0.012, 0.009, segs=6, rings=3)
            
    # Thigh
    thigh_head = bones[f"thigh{side}"].head_local
    thigh_tail = bones[f"thigh{side}"].tail_local
    add_cylinder_between(bm, thigh_head, thigh_tail, 0.10, 0.07, segs=12, rings=4)
    
    # Shin
    shin_head = bones[f"shin{side}"].head_local
    shin_tail = bones[f"shin{side}"].tail_local
    add_cylinder_between(bm, shin_head, shin_tail, 0.07, 0.05, segs=12, rings=4)
    
    # Foot
    foot_head = bones[f"foot{side}"].head_local
    foot_tail = bones[f"foot{side}"].tail_local
    add_cylinder_between(bm, foot_head, foot_tail, 0.055, 0.045, segs=10, rings=3)
    
    # Toe
    toe_head = bones[f"toe{side}"].head_local
    toe_tail = bones[f"toe{side}"].tail_local
    add_cylinder_between(bm, toe_head, toe_tail, 0.045, 0.035, segs=10, rings=2)

# Finish bmesh
bm.to_mesh(mesh)
bm.free()

# Ensure normals face outward
bpy.context.view_layer.objects.active = body_obj
body_obj.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.object.mode_set(mode='OBJECT')

print(f"Base body created with {len(mesh.vertices)} vertices, {len(mesh.polygons)} polygons.")

# Parent mesh to metarig with automatic weights
body_obj.select_set(True)
metarig.select_set(True)
bpy.context.view_layer.objects.active = metarig
bpy.ops.object.parent_set(type='ARMATURE_AUTO')

print("Parented base body to metarig with ARMATURE_AUTO.")

# Check for unweighted vertices
armature_mod = next((m for m in body_obj.modifiers if m.type == 'ARMATURE'), None)
print("Armature modifier present on mesh:", armature_mod is not None)

unweighted = [v.index for v in body_obj.data.vertices if len(v.groups) == 0]
print(f"Unweighted vertices count: {len(unweighted)}")

# Add materials
mat_skin = bpy.data.materials.new(name="Mat_Skin")
mat_skin.diffuse_color = (0.85, 0.65, 0.55, 1.0)
mat_cloth = bpy.data.materials.new(name="Mat_Cloth")
mat_cloth.diffuse_color = (0.2, 0.4, 0.8, 1.0)
body_obj.data.materials.append(mat_skin)
body_obj.data.materials.append(mat_cloth)

# Save to assets/base_character.blend
os.makedirs("assets", exist_ok=True)
blend_path = os.path.abspath("assets/base_character.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
print("Saved base character asset to:", blend_path)
print("Base character generation completed successfully.")
