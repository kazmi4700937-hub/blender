"""Bring a generated 3D model into Blender and make it ready for rigging.

cmd_import_generated_mesh:
  1. imports a .glb, .gltf, .fbx or .obj file
  2. scales it uniformly so its height (Z) equals target_height_m
  3. stands it on the ground (lowest point at Z = 0) and centres it on X and Y
  4. applies the transforms, so the mesh data itself is at the right size
  5. merges duplicate vertices (seams) so the mesh is one connected surface
  6. measures the mesh and returns warnings about anything that would trouble rigging

Nothing here depends on which service made the model.
"""

import os

import bmesh
import bpy
from mathutils import Matrix, Vector

SUPPORTED = (".glb", ".gltf", ".fbx", ".obj")

# Warning thresholds. They are advice for the user, not hard limits.
HEAVY_TRIANGLES = 200_000
MIN_HEIGHT_TO_WIDTH = 0.6     # a standing character is rarely much wider than it is tall


def _import_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise ValueError(f"Unsupported model type '{ext}'. Use one of: {', '.join(SUPPORTED)}")


def _world_bounds(objects):
    """Combined world-space bounding box (min, max) of mesh objects."""
    lo = Vector((float("inf"),) * 3)
    hi = Vector((float("-inf"),) * 3)
    for obj in objects:
        for corner in obj.bound_box:
            p = obj.matrix_world @ Vector(corner)
            lo = Vector((min(lo[i], p[i]) for i in range(3)))
            hi = Vector((max(hi[i], p[i]) for i in range(3)))
    return lo, hi


def _count_pieces(bm):
    """Number of separate connected pieces of faces."""
    seen = set()
    pieces = 0
    for face in bm.faces:
        if face.index in seen:
            continue
        pieces += 1
        stack = [face]
        seen.add(face.index)
        while stack:
            f = stack.pop()
            for edge in f.edges:
                for other in edge.link_faces:
                    if other.index not in seen:
                        seen.add(other.index)
                        stack.append(other)
    return pieces


def weld_vertices(mesh_objects, distance):
    """Merge vertices closer than `distance` (metres). Returns (before, after) vertex counts.

    glTF and FBX files split vertices wherever the UV map or the shading has a seam, so the same
    point exists several times. Auto weights can give such twins different weights, which tears the
    seam when the character moves, and the mesh checks would count every seam as an open edge.
    """
    before = after = 0
    for obj in mesh_objects:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        before += len(bm.verts)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=distance)
        after += len(bm.verts)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
    return before, after


def measure_meshes(mesh_objects):
    """Counts and checks for the given mesh objects (evaluated as they are, no changes)."""
    verts = tris = non_manifold = loose = pieces = 0
    has_uv = False
    materials = set()
    for obj in mesh_objects:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        verts += len(bm.verts)
        tris += sum(len(f.verts) - 2 for f in bm.faces)
        non_manifold += sum(1 for e in bm.edges if e.is_boundary or len(e.link_faces) > 2)
        loose += sum(1 for v in bm.verts if not v.link_edges)
        pieces += _count_pieces(bm)
        bm.free()
        has_uv = has_uv or len(obj.data.uv_layers) > 0
        materials.update(m.name for m in obj.data.materials if m)
    return {
        "vertices": verts,
        "triangles": tris,
        "non_manifold_edges": non_manifold,
        "loose_vertices": loose,
        "pieces": pieces,
        "has_uv": has_uv,
        "materials": sorted(materials),
    }


def cmd_import_generated_mesh(params):
    path = params.get("path")
    if not path or not os.path.isfile(path):
        raise ValueError(f"Model file not found: '{path}'")
    target_height = float(params.get("target_height_m", 1.75))
    if not 0.2 <= target_height <= 4.0:
        raise ValueError(f"target_height_m {target_height} is outside 0.2 to 4.0 metres")

    before = set(bpy.data.objects.keys())
    _import_file(path)
    new_objects = [bpy.data.objects[n] for n in bpy.data.objects.keys() if n not in before]
    meshes = [o for o in new_objects if o.type == "MESH"]
    armatures = [o for o in new_objects if o.type == "ARMATURE"]
    if not meshes:
        raise ValueError("The file contains no mesh.")

    # Meshes that are children of the imported empties/armatures keep their world position, so
    # work in world space and bake it into the mesh at the end.
    bpy.context.view_layer.update()
    lo, hi = _world_bounds(meshes)
    size = hi - lo
    if size.z <= 1e-9:
        raise ValueError("The model has no height; it may be empty or flat.")
    factor = target_height / size.z

    roots = [o for o in new_objects if o.parent is None]
    # Scale every root about the world origin, then move so the feet touch Z = 0 and X, Y are centred.
    centre_x = (lo.x + hi.x) / 2 * factor
    centre_y = (lo.y + hi.y) / 2 * factor
    shift = Vector((-centre_x, -centre_y, -lo.z * factor))
    scale_m = Matrix.Scale(factor, 4)
    for obj in roots:
        obj.matrix_world = Matrix.Translation(shift) @ scale_m @ obj.matrix_world
    bpy.context.view_layer.update()

    # Bake the transforms into the mesh data.
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes + armatures:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    lo2, hi2 = _world_bounds(meshes)
    size2 = hi2 - lo2
    weld_distance = float(params.get("weld_distance_m", 1e-5))
    if weld_distance > 0:
        verts_before_weld, _ = weld_vertices(meshes, weld_distance)
    else:
        verts_before_weld = None
    stats = measure_meshes(meshes)

    warnings = []
    if size.z < MIN_HEIGHT_TO_WIDTH * max(size.x, size.y):
        warnings.append(
            "The model is much wider than it is tall before scaling; it may be lying down or rotated. "
            "Check the orientation before rigging."
        )
    if stats["triangles"] > HEAVY_TRIANGLES:
        warnings.append(f"The mesh is heavy ({stats['triangles']:,} triangles); rigging and weighting will be slow.")
    if stats["non_manifold_edges"] > 0:
        warnings.append(
            f"{stats['non_manifold_edges']} open or non-manifold edges; automatic weights may fail or leave holes."
        )
    if stats["pieces"] > 1:
        warnings.append(
            f"The mesh has {stats['pieces']} separate pieces (parts, props, or stray fragments); "
            "decide which pieces are the body and which are props."
        )
    if stats["loose_vertices"] > 0:
        warnings.append(f"{stats['loose_vertices']} loose vertices not attached to any face.")
    if armatures:
        warnings.append("The file already contains an armature; the app's own rig step will not use it unless you ask.")

    return {
        "path": path,
        "scale_factor": round(factor, 6),
        "height_m": round(size2.z, 4),
        "width_m": round(size2.x, 4),
        "depth_m": round(size2.y, 4),
        "min_z": round(lo2.z, 6),
        "vertices_before_weld": verts_before_weld,
        "mesh_objects": [o.name for o in meshes],
        "armature_objects": [o.name for o in armatures],
        **stats,
        "warnings": warnings,
    }
