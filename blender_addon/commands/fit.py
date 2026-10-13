import bpy
import json
import os
import math
from typing import Dict, Any, Tuple, Optional
from mathutils import Vector, Matrix, Quaternion

def cmd_import_base_character(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Appends template mesh and metarig from assets/base_character.blend into the current scene.
    """
    blend_path = params.get("blend_path", "assets/base_character.blend")
    abs_blend_path = os.path.abspath(blend_path)
    if not os.path.exists(abs_blend_path):
        raise FileNotFoundError(f"Base character asset not found at '{abs_blend_path}'")

    with bpy.data.libraries.load(abs_blend_path, link=False) as (data_from, data_to):
        for obj_name in ["metarig", "base_character"]:
            if obj_name in data_from.objects:
                data_to.objects.append(obj_name)

    coll = bpy.context.collection
    imported = []
    for obj in data_to.objects:
        if obj is not None:
            coll.objects.link(obj)
            imported.append(obj.name)

    return {"imported": imported, "path": abs_blend_path}


def cmd_fit_template(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deforms the template mesh and metarig so they match character_spec.json.
    Computes exact bone affine transformations from rest to target joints,
    deforms the mesh using linear blend skinning across vertex groups,
    and positions edit bones exactly on target joint coordinates.
    """
    spec_path = params.get("spec_path")
    spec_data = params.get("spec")

    if not spec_data:
        if not spec_path:
            raise ValueError("Either 'spec_path' or 'spec' must be provided to fit_template")
        abs_spec_path = os.path.abspath(spec_path)
        if not os.path.exists(abs_spec_path):
            raise FileNotFoundError(f"character_spec.json not found at '{abs_spec_path}'")
        with open(abs_spec_path, "r", encoding="utf-8") as f:
            spec_data = json.load(f)

    joints = spec_data.get("joints", {})
    widths = spec_data.get("widths", {})
    depths = spec_data.get("depths", {})
    target_height_m = spec_data.get("height_m", 1.75)

    metarig = bpy.data.objects.get("metarig")
    body = bpy.data.objects.get("base_character")

    if not metarig or not body:
        raise RuntimeError("Scene must contain 'metarig' and 'base_character' to fit template")

    # Record original rest bone positions
    bones_orig = {}
    for b in metarig.data.bones:
        bones_orig[b.name] = (Vector(b.head_local), Vector(b.tail_local))

    # Construct target bone endpoints
    target_endpoints: Dict[str, Tuple[Vector, Vector]] = {}

    # Torso & Spine Chain
    crotch = Vector(joints.get("crotch", [0, 0, 0.9]))
    neck_base = Vector(joints.get("neck_base", [0, 0, 1.45]))
    chin = Vector(joints.get("chin", [0, 0, 1.55]))
    head_top = Vector(joints.get("head_top", [0, 0, target_height_m]))

    spine_vec = neck_base - crotch
    sp1 = crotch + spine_vec * 0.25
    sp2 = crotch + spine_vec * 0.50
    sp3 = crotch + spine_vec * 0.75

    target_endpoints["spine"] = (crotch, sp1)
    target_endpoints["spine.001"] = (sp1, sp2)
    target_endpoints["spine.002"] = (sp2, sp3)
    target_endpoints["spine.003"] = (sp3, neck_base)
    target_endpoints["spine.004"] = (neck_base, chin)

    head_mid = chin + (head_top - chin) * 0.5
    target_endpoints["spine.005"] = (chin, head_mid)
    target_endpoints["spine.006"] = (head_mid, head_top)

    # Limbs (Left and Right)
    for side, sgn in [(".L", 1.0), (".R", -1.0)]:
        sfx = "_L" if side == ".L" else "_R"
        sh_head = Vector(joints.get(f"shoulder{sfx}", [sgn * 0.2, 0, neck_base.z]))
        el_head = Vector(joints.get(f"elbow{sfx}", [sgn * 0.45, 0, neck_base.z]))
        wr_head = Vector(joints.get(f"wrist{sfx}", [sgn * 0.65, 0, neck_base.z]))
        ht_head = Vector(joints.get(f"hand_tip{sfx}", [sgn * 0.72, 0, neck_base.z]))

        clav_head = Vector((sgn * 0.02, 0, neck_base.z - 0.05))
        # Ensure elbow has slight backward bend (+Y) for Rigify IK pole vector calculation
        if abs(el_head.y - sh_head.y) < 0.005:
            el_head.y = sh_head.y + 0.01

        target_endpoints[f"shoulder{side}"] = (clav_head, sh_head)
        target_endpoints[f"upper_arm{side}"] = (sh_head, el_head)
        target_endpoints[f"forearm{side}"] = (el_head, wr_head)
        target_endpoints[f"hand{side}"] = (wr_head, ht_head)

        hip_pt = Vector(joints.get(f"hip{sfx}", [sgn * 0.1, 0, crotch.z]))
        kn_pt = Vector(joints.get(f"knee{sfx}", [sgn * 0.1, 0, crotch.z * 0.5]))
        ank_pt = Vector(joints.get(f"ankle{sfx}", [sgn * 0.1, 0, 0.08]))
        toe_pt = Vector(joints.get(f"toe{sfx}", [sgn * 0.1, -0.1, 0.02]))

        # Ensure knee has slight forward bend (-Y) for Rigify IK pole vector calculation
        if abs(kn_pt.y - hip_pt.y) < 0.005:
            kn_pt.y = hip_pt.y - 0.01

        target_endpoints[f"thigh{side}"] = (hip_pt, kn_pt)
        target_endpoints[f"shin{side}"] = (kn_pt, ank_pt)
        target_endpoints[f"foot{side}"] = (ank_pt, toe_pt)
        target_endpoints[f"toe{side}"] = (toe_pt, toe_pt + Vector((0, -0.06, 0)))

    # Compute affine transformation for each bone
    chest_scale_x = widths.get("chest_width", 0.3) / 0.3
    chest_scale_z = depths.get("chest_depth", 0.24) / 0.24
    cross_scale_torso = (max(0.5, min(2.0, chest_scale_x)), max(0.5, min(2.0, chest_scale_z)))

    bone_transforms = {}
    for b_name, (h0, t0) in bones_orig.items():
        if b_name not in target_endpoints:
            continue
        h1, t1 = target_endpoints[b_name]
        v0 = t0 - h0
        v1 = t1 - h1
        len0 = v0.length
        len1 = v1.length
        if len0 < 1e-5 or len1 < 1e-5:
            continue

        dir0 = v0.normalized()
        dir1 = v1.normalized()
        rot = dir0.rotation_difference(dir1)
        scale_y = len1 / len0

        scale_cross = cross_scale_torso if "spine" in b_name else (1.0, 1.0)
        bone_transforms[b_name] = (h0, h1, rot, scale_y, dir0, scale_cross)

    # Deform mesh vertices using Linear Blend Skinning
    mesh = body.data
    vgroup_names = {g.index: g.name for g in body.vertex_groups}

    for v in mesh.vertices:
        total_w = sum(g.weight for g in v.groups if vgroup_names.get(g.group) in bone_transforms)
        if total_w < 1e-5:
            continue

        p_orig = v.co.copy()
        p_new = Vector((0, 0, 0))

        for g in v.groups:
            b_name = vgroup_names.get(g.group)
            if b_name not in bone_transforms:
                continue
            w = g.weight / total_w
            h0, h1, rot, scale_y, dir0, scale_cross = bone_transforms[b_name]

            d = p_orig - h0
            d_par = dir0 * d.dot(dir0)
            d_perp = d - d_par

            d_par_scaled = d_par * scale_y
            d_perp_scaled = d_perp * scale_cross[0]

            v_disp = rot @ (d_par_scaled + d_perp_scaled)
            p_new += (h1 + v_disp) * w

        v.co = p_new

    mesh.update()

    # Update edit bones of metarig to match target_endpoints exactly
    bpy.context.view_layer.objects.active = metarig
    bpy.ops.object.mode_set(mode='EDIT')
    ebones = metarig.data.edit_bones

    for b_name, (h1, t1) in target_endpoints.items():
        eb = ebones.get(b_name)
        if eb:
            eb.head = h1
            eb.tail = t1

    bpy.ops.object.mode_set(mode='OBJECT')

    # Ensure outward consistent normals
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')

    return {
        "fitted": True,
        "height_m": target_height_m,
        "joints_count": len(joints),
        "mesh_vertices": len(mesh.vertices)
    }
