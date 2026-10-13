"""Phase 9 acceptance test: import a generated model, normalize it, and check the mesh.

Run with:  blender -b --python tests/blender/test_phase9.py
The test builds its own small models and exports them as .glb, so it needs no network
and no files from any 3D service.
"""

import math
import os
import sys
import tempfile

import bpy

print("=== RUNNING PHASE 9 ACCEPTANCE TESTS ===")

sys.path.insert(0, os.path.abspath("."))
from blender_addon.commands.geometry import cmd_import_generated_mesh

TMP = tempfile.mkdtemp(prefix="phase9_")


def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)


def check(cond, msg):
    if not cond:
        fail(msg)
    print("PASS:", msg)


def empty_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_closed_character(height=2.2, location=(3.0, -2.0, 5.0)):
    """One closed piece: a tall ellipsoid standing roughly like a body."""
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1.0, location=location)
    obj = bpy.context.active_object
    obj.scale = (0.25 * height / 2, 0.15 * height / 2, height / 2)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return obj


def export_glb(name):
    path = os.path.join(TMP, name)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB")
    return path


# -------------------------------------------------------------
print("\n--- Test 1: clean closed model is scaled to 1.75 m, stood on the ground and centred ---")
empty_scene()
make_closed_character(height=2.2, location=(3.0, -2.0, 5.0))
glb = export_glb("clean.glb")
empty_scene()
res = cmd_import_generated_mesh({"path": glb, "target_height_m": 1.75})
print(res)
check(abs(res["height_m"] - 1.75) < 1e-3, f"height is 1.75 m (got {res['height_m']})")
check(abs(res["min_z"]) < 1e-4, f"feet are on the ground (min z {res['min_z']})")
mesh = bpy.data.objects[res["mesh_objects"][0]]
xs = [(mesh.matrix_world @ v.co).x for v in mesh.data.vertices]
ys = [(mesh.matrix_world @ v.co).y for v in mesh.data.vertices]
check(abs((max(xs) + min(xs)) / 2) < 1e-3 and abs((max(ys) + min(ys)) / 2) < 1e-3, "model is centred on X and Y")
check(all(abs(s - 1.0) < 1e-6 for s in mesh.scale) and all(abs(v) < 1e-6 for v in mesh.location),
      "scale and location are baked into the mesh (object transform is identity)")
check(res["vertices_before_weld"] > res["vertices"],
      f"seam duplicates were merged ({res['vertices_before_weld']} -> {res['vertices']} vertices)")
check(res["non_manifold_edges"] == 0 and res["pieces"] == 1, "clean mesh reports 0 open edges and 1 piece")
check(res["warnings"] == [], f"clean mesh gives no warnings (got {res['warnings']})")

# -------------------------------------------------------------
print("\n--- Test 2: an open mesh is reported ---")
empty_scene()
bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.3, depth=1.8, end_fill_type="NOTHING", location=(0, 0, 0.9))
glb = export_glb("open.glb")
empty_scene()
res = cmd_import_generated_mesh({"path": glb})
check(res["non_manifold_edges"] > 0, f"open edges counted ({res['non_manifold_edges']})")
check(any("non-manifold" in w for w in res["warnings"]), "a warning names the open edges")
check(abs(res["height_m"] - 1.75) < 1e-3, "default target height is 1.75 m")

# -------------------------------------------------------------
print("\n--- Test 3: separate pieces are reported ---")
empty_scene()
make_closed_character(height=1.8, location=(0, 0, 0.9))
bpy.ops.mesh.primitive_cube_add(size=0.2, location=(0.8, 0, 0.9))
glb = export_glb("two_pieces.glb")
empty_scene()
res = cmd_import_generated_mesh({"path": glb})
check(res["pieces"] == 2, f"two pieces counted (got {res['pieces']})")
check(any("separate pieces" in w for w in res["warnings"]), "a warning names the separate pieces")

# -------------------------------------------------------------
print("\n--- Test 4: a model lying on its side is flagged ---")
empty_scene()
obj = make_closed_character(height=1.8, location=(0, 0, 0))
obj.rotation_euler = (0, math.radians(90), 0)
bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
glb = export_glb("lying.glb")
empty_scene()
res = cmd_import_generated_mesh({"path": glb})
check(any("lying down" in w for w in res["warnings"]), "a warning says the model may be lying down")

# -------------------------------------------------------------
print("\n--- Test 5: bad input is rejected with a readable error ---")
for params, text in (
    ({"path": os.path.join(TMP, "missing.glb")}, "not found"),
    ({"path": glb, "target_height_m": 10.0}, "outside"),
):
    try:
        cmd_import_generated_mesh(params)
        fail(f"{params} was accepted")
    except ValueError as e:
        check(text in str(e), f"rejected: {e}")

bad = os.path.join(TMP, "model.txt")
open(bad, "w").write("x")
try:
    cmd_import_generated_mesh({"path": bad})
    fail("unsupported file type was accepted")
except ValueError as e:
    check("Unsupported" in str(e), f"rejected: {e}")

print("\n=== ACCEPTANCE TESTS PASSED ===")
