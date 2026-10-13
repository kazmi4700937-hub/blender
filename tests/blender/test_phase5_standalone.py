"""
Phase 5 standalone test — Rigify generate + bind + deformation checks.

No hardcoded character proportions. Uses assets/base_character.blend
(or output/fitted_character.blend if present).

Run on Windows:
  "C:\\Program Files\\Blender Foundation\\Blender 4.2\\blender.exe" -b --python tests\\blender\\test_phase5_standalone.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy
from mathutils import Euler, Vector

ROOT = Path(__file__).resolve().parents[2]
BLEND_FITTED = ROOT / "output" / "fitted_character.blend"
BLEND_BASE = ROOT / "assets" / "base_character.blend"
OUT = ROOT / "output" / "rigged_character.blend"

EXPECTED_CONTROLS = [
    "root",
    "torso",
    "hand_ik.L",
    "hand_ik.R",
    "foot_ik.L",
    "foot_ik.R",
]


def fail(msg: str) -> None:
    print("FAIL:", msg)
    sys.exit(1)


def ok(msg: str) -> None:
    print("OK:", msg)


def ensure_object_mode() -> None:
    if bpy.context.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass


def clear_scene() -> None:
    ensure_object_mode()
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.armatures, bpy.data.actions):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def import_blend(path: Path) -> None:
    with bpy.data.libraries.load(str(path), link=False) as (data_from, data_to):
        data_to.objects = list(data_from.objects)
        data_to.armatures = list(data_from.armatures)
        data_to.materials = list(data_from.materials)
    for obj in data_to.objects:
        if obj is not None:
            bpy.context.collection.objects.link(obj)


def find_metarig():
    for obj in bpy.context.scene.objects:
        if obj.type == "ARMATURE" and "metarig" in obj.name.lower():
            return obj
    for obj in bpy.context.scene.objects:
        if obj.type == "ARMATURE":
            return obj
    return None


def find_body():
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            return obj
    return None


def find_generated_rig(metarig):
    for obj in bpy.context.scene.objects:
        if obj.type != "ARMATURE" or obj == metarig:
            continue
        name = obj.name.lower()
        if "metarig" in name:
            continue
        if "rig" in name:
            return obj
    for obj in bpy.context.scene.objects:
        if obj.type == "ARMATURE" and obj != metarig:
            return obj
    return None


def count_unweighted_vertices(mesh_obj, rig_obj) -> int:
    groups = mesh_obj.vertex_groups
    if not groups:
        return len(mesh_obj.data.vertices)
    unweighted = 0
    for v in mesh_obj.data.vertices:
        total = 0.0
        for g in v.groups:
            total += g.weight
        if total < 1e-4:
            unweighted += 1
    return unweighted


def find_bone_containing(rig, fragment: str):
    fragment = fragment.lower()
    for b in rig.pose.bones:
        if fragment in b.name.lower():
            return b.name
    return None


def main():
    print("=" * 50)
    print("PHASE 5 STANDALONE TEST — Rigify generate + bind")
    print("=" * 50)

    clear_scene()

    if BLEND_FITTED.is_file():
        src = BLEND_FITTED
        ok(f"Using fitted character: {src}")
    elif BLEND_BASE.is_file():
        src = BLEND_BASE
        ok(f"Using base character (no fitted blend found): {src}")
    else:
        fail(f"Neither {BLEND_FITTED} nor {BLEND_BASE} found")

    import_blend(src)

    metarig = find_metarig()
    body = find_body()
    if not metarig:
        fail("No metarig/armature found in blend")
    if not body:
        fail("No mesh found in blend")
    ok(f"Scene: metarig={metarig.name}, body={body.name}")

    try:
        bpy.ops.preferences.addon_enable(module="rigify")
        ok("Rigify enabled")
    except Exception as e:
        print("WARNING: could not enable Rigify:", e)

    ensure_object_mode()
    bpy.ops.object.select_all(action="DESELECT")
    metarig.select_set(True)
    bpy.context.view_layer.objects.active = metarig

    try:
        bpy.ops.pose.rigify_generate()
        ok("rigify_generate() completed")
    except Exception as e:
        fail(f"rigify_generate failed: {e}")

    rig = find_generated_rig(metarig)
    if not rig:
        fail("No generated rig found after rigify_generate")
    ok(f"Generated rig: {rig.name}  bones={len(rig.data.bones)}")

    print("Sample control/deform bones (first 40):")
    for i, b in enumerate(rig.data.bones):
        if i >= 40:
            print("  ...")
            break
        print(f"  {b.name}")

    print("\n--- Expected control presence ---")
    found_controls = {}
    for frag in EXPECTED_CONTROLS:
        name = find_bone_containing(rig, frag)
        found_controls[frag] = name
        status = "OK" if name else "MISSING"
        print(f"  {frag:12} → {name or '-'}  [{status}]")

    finger_frags = ["f_index", "f_middle", "f_ring", "f_pinky", "thumb"]
    finger_count = 0
    for frag in finger_frags:
        for b in rig.data.bones:
            if frag in b.name.lower():
                finger_count += 1
    ok(f"Finger-related bones found: {finger_count}")
    if finger_count < 5:
        print("WARNING: few finger bones — hand deformation may be limited")

    ensure_object_mode()
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig

    if body.parent:
        mw = body.matrix_world.copy()
        body.parent = None
        body.matrix_world = mw

    for mod in list(body.modifiers):
        if mod.type == "ARMATURE":
            body.modifiers.remove(mod)

    try:
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
        ok("Bound mesh with ARMATURE_AUTO")
    except Exception as e:
        fail(f"parent_set ARMATURE_AUTO failed: {e}")

    unweighted = count_unweighted_vertices(body, rig)
    print(f"Unweighted vertices: {unweighted} / {len(body.data.vertices)}")
    if unweighted == 0:
        ok("Zero unweighted vertices")
    elif unweighted < max(5, len(body.data.vertices) * 0.02):
        print(f"WARNING: {unweighted} unweighted vertices (small fraction — acceptable for MVP)")
    else:
        fail(f"Too many unweighted vertices: {unweighted}")

    knee_bone = (
        find_bone_containing(rig, "DEF-shin.L")
        or find_bone_containing(rig, "shin.L")
        or find_bone_containing(rig, "thigh.L")
    )
    if not knee_bone:
        print("WARNING: could not find left leg bone for pose test — skipping region check")
    else:
        ensure_object_mode()
        bpy.ops.object.select_all(action="DESELECT")
        rig.select_set(True)
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode="POSE")

        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        body_eval = body.evaluated_get(dg)
        coords_before = [v.co.copy() for v in body_eval.data.vertices]

        pb = rig.pose.bones[knee_bone]
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = Euler((1.57, 0, 0), "XYZ")
        bpy.context.view_layer.update()

        dg = bpy.context.evaluated_depsgraph_get()
        body_eval = body.evaluated_get(dg)
        coords_after = [v.co.copy() for v in body_eval.data.vertices]
        moved = []
        for i in range(len(coords_before)):
            if (coords_after[i] - coords_before[i]).length > 0.005:
                moved.append(i)

        pb.rotation_euler = Euler((0, 0, 0), "XYZ")
        bpy.context.view_layer.update()
        bpy.ops.object.mode_set(mode="OBJECT")

        ok(f"Knee pose test on '{knee_bone}': {len(moved)} vertices moved > 5 mm")
        if len(moved) == 0:
            print("WARNING: no vertices moved — weights may not be deforming this bone")
        else:
            avg_x = sum(coords_after[i].x for i in moved) / len(moved)
            print(f"  Average X of moved verts: {avg_x:.3f} (expect > 0 for left leg)")
            if avg_x < -0.05:
                print("WARNING: movement skewed to right side — possible weight mirror issue")
            else:
                ok("Left-knee bend affects primarily left-side geometry")

    print("\n--- IK/FK switch properties ---")
    ik_fk_found = 0
    for b in rig.pose.bones:
        if "IK_FK" in b.keys() or "ik_fk" in [k.lower() for k in b.keys()]:
            ik_fk_found += 1
            print(f"  {b.name} has IK_FK-like property")
        for k in b.keys():
            if "ik" in k.lower() and "fk" in k.lower():
                ik_fk_found += 1
                print(f"  {b.name}['{k}']")
                break
    if ik_fk_found > 0:
        ok(f"IK/FK-related properties found on {ik_fk_found} bones")
    else:
        for frag in ["IK_FK", "ik_fk", "thigh_parent", "upper_arm_parent"]:
            n = find_bone_containing(rig, frag)
            if n:
                ok(f"Found related bone: {n}")
                ik_fk_found += 1
        if ik_fk_found == 0:
            print("WARNING: no IK_FK properties detected — confirm manually in Blender UI")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT))
    ok(f"Saved {OUT}")

    print("\n" + "=" * 50)
    print("PHASE 5 SUMMARY")
    print("=" * 50)
    print(f"  Rig name           : {rig.name}")
    print(f"  Bone count         : {len(rig.data.bones)}")
    print(f"  Finger bones       : {finger_count}")
    print(f"  Unweighted verts   : {unweighted}")
    missing = [f for f, n in found_controls.items() if not n]
    if missing:
        print(f"  Missing controls   : {missing}")
    else:
        print("  Expected controls  : all fragments found")

    critical_ok = (
        rig is not None
        and unweighted < max(5, len(body.data.vertices) * 0.05)
        and finger_count >= 1
    )
    if critical_ok:
        print("\n>>> PHASE 5 SMOKE TEST: PASSED <<<")
        print("Next: full deformation/IK acceptance on your machine if needed.")
        sys.exit(0)
    else:
        print("\n>>> PHASE 5 SMOKE TEST: NEEDS REVIEW <<<")
        sys.exit(1)


if __name__ == "__main__":
    main()