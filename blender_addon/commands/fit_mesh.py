"""Place a Rigify metarig on a mesh that already exists, then rig and bind it.

Unlike fit_template, nothing deforms the mesh. The mesh is whatever a service generated (or an
artist made). Only the metarig moves, to the joints in a character spec. The spec can come from
landmarks found in the reference images, or from a skeleton the service returned.

Steps of cmd_rig_generated_mesh:
  1. append the metarig from the template file (the template body is not imported)
  2. refine each joint's depth (Y) to the middle of the mesh at that point
  3. move the metarig bones to the joints; bones with no joint of their own (fingers, face, pelvis,
     breasts, heels) follow their nearest ancestor that has one
  4. generate the Rigify rig and bind the mesh to it with automatic weights
  5. report what could trouble animation: joints outside the mesh, bones that got no vertices,
     vertices with no weight
"""

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from .fit import build_target_endpoints, cmd_import_base_character
from .rig import cmd_bind_mesh, cmd_generate_rig

# Joints whose depth (Y) is moved to the middle of the mesh at that point.
REFINE_JOINTS = [
    "crotch", "neck_base",
    "shoulder_L", "shoulder_R", "elbow_L", "elbow_R", "wrist_L", "wrist_R",
    "hip_L", "hip_R", "knee_L", "knee_R", "ankle_L", "ankle_R",
]
MAX_REFINE_SHIFT_M = 0.12     # never move a joint further than this
OUTSIDE_TOLERANCE_M = 0.02    # a joint this close to the surface is not reported as outside

# Deform bones that must receive vertices for a body to animate. A bone with none usually means
# its joint was placed outside the mesh.
KEY_DEFORM_BONES = [
    "DEF-spine", "DEF-spine.003", "DEF-spine.006",
    "DEF-upper_arm.L", "DEF-forearm.L", "DEF-hand.L", "DEF-upper_arm.R", "DEF-forearm.R", "DEF-hand.R",
    "DEF-thigh.L", "DEF-shin.L", "DEF-foot.L", "DEF-thigh.R", "DEF-shin.R", "DEF-foot.R",
]
MIN_VERTICES_PER_KEY_BONE = 3


def _bvh(mesh_obj) -> BVHTree:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return BVHTree.FromObject(mesh_obj, depsgraph)


def _is_inside(bvh: BVHTree, p: Vector) -> bool:
    """Majority vote of three ray directions (needs a mostly closed mesh)."""
    votes = 0
    for d in (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))):
        hits = 0
        origin = p.copy()
        for _ in range(64):
            loc, _n, _i, _dist = bvh.ray_cast(origin, d)
            if loc is None:
                break
            hits += 1
            origin = loc + d * 1e-4
        votes += hits % 2
    return votes >= 2


def refine_joint_depths(bvh: BVHTree, joints: Dict[str, List[float]]) -> Tuple[Dict[str, List[float]], List[str]]:
    """Move each listed joint's Y to the middle between the mesh surface in front of and behind it."""
    refined = {k: list(v) for k, v in joints.items()}
    unrefined = []
    for name in REFINE_JOINTS:
        if name not in joints:
            continue
        p = Vector(joints[name])
        front, _n, _i, d_front = bvh.ray_cast(p, Vector((0, -1, 0)))
        back, _n2, _i2, d_back = bvh.ray_cast(p, Vector((0, 1, 0)))
        if front is None or back is None:
            unrefined.append(name)
            continue
        new_y = (front.y + back.y) / 2
        shift = new_y - p.y
        if abs(shift) > MAX_REFINE_SHIFT_M:
            unrefined.append(name)
            continue
        refined[name][1] = new_y
    return refined, unrefined


def _nearest_target_ancestor(bone, targets) -> Optional[str]:
    cur = bone
    while cur is not None:
        if cur.name in targets:
            return cur.name
        cur = cur.parent
    return None


def place_metarig(metarig, target_endpoints: Dict[str, Tuple[Vector, Vector]]) -> Dict[str, int]:
    """Move every metarig bone. Returns counts of bones placed directly and bones that followed an ancestor."""
    rest = {b.name: (Vector(b.head_local), Vector(b.tail_local)) for b in metarig.data.bones}
    parents = {b.name: _nearest_target_ancestor(b, target_endpoints) for b in metarig.data.bones}

    # Rigid motion plus uniform scale for each bone that has a target: rotate the rest direction onto
    # the target direction, scale by the length ratio.
    motion = {}
    for name, (h1, t1) in target_endpoints.items():
        if name not in rest:
            continue
        h0, t0 = rest[name]
        if name.startswith("hand."):
            # The template's finger bones do not lie along its hand bone, so the finger group moves as
            # one piece: from the wrist to its farthest fingertip, mapped onto wrist -> hand tip.
            kids = [rest[b.name][1] for b in metarig.data.bones
                    if b.name not in target_endpoints and _nearest_target_ancestor(b, target_endpoints) == name]
            if kids:
                t0 = max(kids, key=lambda p: (p - h0).length)
        v0, v1 = t0 - h0, t1 - h1
        if v0.length < 1e-6 or v1.length < 1e-6:
            continue
        motion[name] = (h0, h1, v0.normalized().rotation_difference(v1.normalized()), v1.length / v0.length)

    def follow(p: Vector, anc: str) -> Vector:
        h0, h1, rot, scale = motion[anc]
        return h1 + rot @ ((p - h0) * scale)

    bpy.context.view_layer.objects.active = metarig
    bpy.ops.object.mode_set(mode="EDIT")
    ebones = metarig.data.edit_bones
    direct = followed = 0
    for _pass in range(2):   # second pass settles connected bones whose heads follow their parent's tail
        for name, (h0, t0) in rest.items():
            eb = ebones.get(name)
            if eb is None:
                continue
            if name in target_endpoints:
                eb.head, eb.tail = target_endpoints[name]
                direct += 1 if _pass == 0 else 0
            else:
                anc = parents.get(name)
                if anc in motion:
                    eb.head, eb.tail = follow(h0, anc), follow(t0, anc)
                    followed += 1 if _pass == 0 else 0
    bpy.ops.object.mode_set(mode="OBJECT")
    return {"bones_placed_directly": direct, "bones_following_an_ancestor": followed}


def _bone_vertex_counts(mesh_obj, bone_names: List[str]) -> Dict[str, int]:
    group_names = {g.index: g.name for g in mesh_obj.vertex_groups}
    counts = {n: 0 for n in bone_names}
    for v in mesh_obj.data.vertices:
        for g in v.groups:
            name = group_names.get(g.group)
            if name in counts and g.weight > 0.3:
                counts[name] += 1
    return counts


def cmd_rig_generated_mesh(params: Dict[str, Any]) -> Dict[str, Any]:
    mesh_name = params.get("mesh_name")
    mesh = bpy.data.objects.get(mesh_name) if mesh_name else None
    if mesh is None or mesh.type != "MESH":
        raise ValueError(f"Mesh object '{mesh_name}' not found. Import the generated model first.")

    spec = params.get("spec")
    if spec is None:
        spec_path = params.get("spec_path")
        if not spec_path or not os.path.isfile(spec_path):
            raise ValueError("Give either 'spec' or a 'spec_path' that exists.")
        with open(spec_path, "r", encoding="utf-8") as f:
            spec = json.load(f)
    joints = spec.get("joints")
    if not joints:
        raise ValueError("The spec has no joints.")
    height = float(spec.get("height_m", 1.75))

    warnings: List[str] = []
    bvh = _bvh(mesh)
    if params.get("refine_depth", True):
        joints, unrefined = refine_joint_depths(bvh, joints)
        if unrefined:
            warnings.append("Depth could not be refined (no mesh in front of or behind the joint, or too far off) for: "
                            + ", ".join(unrefined))

    outside = []
    for name, p in joints.items():
        pt = Vector(p)
        if not _is_inside(bvh, pt):
            _loc, _n, _i, dist = bvh.find_nearest(pt)
            if dist is not None and dist > OUTSIDE_TOLERANCE_M:
                outside.append(f"{name} ({dist * 100:.1f} cm outside)")
    if outside:
        warnings.append("These joints are outside the mesh, so their bones may get no vertices: " + ", ".join(outside)
                        + ". The reference-image landmarks may not match the generated model.")

    for name in ("metarig", "rig"):   # start clean if a previous attempt left a rig behind
        old = bpy.data.objects.get(name)
        if old is not None:
            bpy.data.objects.remove(old, do_unlink=True)
    cmd_import_base_character({"blend_path": params.get("blend_path", "assets/base_character.blend"),
                               "objects": ["metarig"]})
    metarig = bpy.data.objects["metarig"]

    targets = build_target_endpoints(joints, height)
    placement = place_metarig(metarig, targets)

    gen = cmd_generate_rig({})
    bind = cmd_bind_mesh({"mesh_name": mesh.name, "rig_name": gen["rig_name"]})

    counts = _bone_vertex_counts(mesh, KEY_DEFORM_BONES)
    empty = [n for n, c in counts.items() if c < MIN_VERTICES_PER_KEY_BONE]
    if empty:
        warnings.append("These deform bones control almost no vertices: " + ", ".join(empty)
                        + ". Check the joint positions against the mesh.")
    if bind["unweighted_count"] > 0:
        warnings.append(f"{bind['unweighted_count']} vertices have no weight and will not move with the rig.")

    return {
        "mesh": mesh.name,
        "rig": gen["rig_name"],
        "bone_count": gen["bone_count"],
        **placement,
        "vertex_count": bind["vertex_count"],
        "unweighted_count": bind["unweighted_count"],
        "key_bone_vertex_counts": counts,
        "joints_used": joints,
        "warnings": warnings,
    }
