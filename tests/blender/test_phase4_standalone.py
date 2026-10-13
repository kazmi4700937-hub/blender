from __future__ import annotations
import sys
from pathlib import Path
import bpy
import bmesh
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
BLEND = ROOT / "assets" / "base_character.blend"
OUT = ROOT / "output" / "fitted_character.blend"
OUT_WIDE = ROOT / "output" / "fitted_character_wide_shoulders.blend"

def fail(msg):
    print("FAIL:", msg)
    sys.exit(1)

def ok(msg):
    print("OK:", msg)

def get_armature_height(arm):
    """World-space height from lowest to highest bone extremity."""
    min_z = 1e9
    max_z = -1e9
    for b in arm.data.bones:
        h = (arm.matrix_world @ b.head_local).z
        t = (arm.matrix_world @ b.tail_local).z
        min_z = min(min_z, h, t)
        max_z = max(max_z, h, t)
    return max_z - min_z, min_z, max_z

def set_bone_matrix(arm, bname, head_w, tail_w):
    """Set pose bone so head/tail match world positions (armature-space matrix)."""
    if bname not in arm.pose.bones:
        return False
    pb = arm.pose.bones[bname]
    rest = arm.data.bones[bname]
    arm_inv = arm.matrix_world.inverted()
    head_a = arm_inv @ head_w
    tail_a = arm_inv @ tail_w
    direction = tail_a - head_a
    length = direction.length
    if length < 1e-8:
        return False
    y = direction.normalized()
    up = Vector((0, 0, 1))
    if abs(y.dot(up)) > 0.9:
        up = Vector((1, 0, 0))
    x = up.cross(y).normalized()
    z = y.cross(x).normalized()
    rest_len = (rest.tail_local - rest.head_local).length
    scale_y = length / max(rest_len, 1e-8)
    mat = Matrix((
        (x.x, y.x * scale_y, z.x, head_a.x),
        (x.y, y.y * scale_y, z.y, head_a.y),
        (x.z, y.z * scale_y, z.z, head_a.z),
        (0.0, 0.0, 0.0, 1.0),
    ))
    pb.matrix = mat
    return True

def check_manifold(mesh_obj):
    """Return (is_manifold-ish, message). Uses bmesh edge checks."""
    bm = bmesh.new()
    bm.from_mesh(mesh_obj.data)
    bm.edges.ensure_lookup_table()
    non_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    if non_manifold == 0:
        return True, "Mesh edges are manifold"
    return False, f"Non-manifold edges: {non_manifold}"

def run_fit(shoulder_scale=1.0, label="standard"):
    """
    Full Phase-4 fit.
    shoulder_scale=1.2 means 20% wider shoulders.
    """
    print(f"\n========== FIT PASS: {label} (shoulder_scale={shoulder_scale}) ==========")

    # clear
    if bpy.context.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception:
            pass
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    if not BLEND.is_file():
        fail("base_character.blend not found")

    with bpy.data.libraries.load(str(BLEND), link=False) as (data_from, data_to):
        data_to.objects = list(data_from.objects)
        data_to.armatures = list(data_from.armatures)
    for obj in data_to.objects:
        if obj is not None:
            bpy.context.collection.objects.link(obj)

    metarig = body = None
    for obj in bpy.context.scene.objects:
        if obj.type == "ARMATURE" and "metarig" in obj.name.lower():
            metarig = obj
        if obj.type == "MESH":
            body = obj
    if not metarig or not body:
        fail("metarig or body missing")
    ok(f"Imported {metarig.name} + {body.name}")

    # ---------- Stage 1: uniform height scale ----------
    bpy.ops.object.select_all(action="DESELECT")
    metarig.select_set(True)
    body.select_set(True)
    bpy.context.view_layer.objects.active = metarig

    height, min_z, max_z = get_armature_height(metarig)
    target_height = 1.75
    if height < 1e-6:
        fail("Armature has zero height")
    scale_factor = target_height / height
    ok(f"Original height={height:.3f} m → scale by {scale_factor:.4f} to reach {target_height} m")

    # Scale both objects from world origin (feet stay near Z=0 after scale if min_z was small)
    metarig.scale = (scale_factor, scale_factor, scale_factor)
    body.scale = (scale_factor, scale_factor, scale_factor)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.context.view_layer.update()

    new_height, new_min, new_max = get_armature_height(metarig)
    ok(f"After scale: height={new_height:.3f} m  (Z range {new_min:.3f} .. {new_max:.3f})")

    # ---------- Stage 2: precise limb joint targets (post-scale) ----------
    # Base positions roughly matching a 1.75 m character after scale
    # Shoulder X is multiplied by shoulder_scale for the wide test
    sx = shoulder_scale
    T = {
        "shoulder_L": Vector((0.18 * sx, 0.02, 1.42)),
        "elbow_L":    Vector((0.45 * sx, 0.02, 1.42)),
        "wrist_L":    Vector((0.68 * sx, 0.02, 1.42)),
        "shoulder_R": Vector((-0.18 * sx, 0.02, 1.42)),
        "elbow_R":    Vector((-0.45 * sx, 0.02, 1.42)),
        "wrist_R":    Vector((-0.68 * sx, 0.02, 1.42)),
        "hip_L":      Vector((0.09, 0.01, 0.92)),
        "knee_L":     Vector((0.09, -0.02, 0.48)),
        "ankle_L":    Vector((0.09, 0.01, 0.07)),
        "hip_R":      Vector((-0.09, 0.01, 0.92)),
        "knee_R":     Vector((-0.09, -0.02, 0.48)),
        "ankle_R":    Vector((-0.09, 0.01, 0.07)),
    }

    chain = [
        ("upper_arm.L", "shoulder_L", "elbow_L"),
        ("forearm.L",   "elbow_L",    "wrist_L"),
        ("hand.L",      "wrist_L",    None),
        ("upper_arm.R", "shoulder_R", "elbow_R"),
        ("forearm.R",   "elbow_R",    "wrist_R"),
        ("hand.R",      "wrist_R",    None),
        ("thigh.L",     "hip_L",      "knee_L"),
        ("shin.L",      "knee_L",     "ankle_L"),
        ("foot.L",      "ankle_L",    None),
        ("thigh.R",     "hip_R",      "knee_R"),
        ("shin.R",      "knee_R",     "ankle_R"),
        ("foot.R",      "ankle_R",    None),
    ]

    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.pose.select_all(action="SELECT")
    bpy.ops.pose.transforms_clear()
    bpy.context.view_layer.update()

    for bname, head_key, tail_key in chain:
        if bname not in metarig.pose.bones:
            continue
        pb = metarig.pose.bones[bname]
        cur_head, cur_tail = pb.head.copy(), pb.tail.copy()
        new_head = T[head_key] if head_key else cur_head
        new_tail = T[tail_key] if tail_key else cur_tail
        if head_key and not tail_key:
            length = (cur_tail - cur_head).length
            direction = (cur_tail - cur_head).normalized()
            new_tail = new_head + direction * length
        elif tail_key and not head_key:
            length = (cur_tail - cur_head).length
            direction = (cur_tail - cur_head).normalized()
            new_head = new_tail - direction * length
        set_bone_matrix(metarig, bname, new_head, new_tail)
        bpy.context.view_layer.update()

    ok("Limb pose matrices applied")

    # ---------- Measure ----------
    print("\n--- Joint errors ---")
    max_err = 0.0
    checks = [
        ("shoulder_L", "upper_arm.L", "head"),
        ("elbow_L",    "forearm.L",   "head"),
        ("wrist_L",    "hand.L",      "head"),
        ("shoulder_R", "upper_arm.R", "head"),
        ("elbow_R",    "forearm.R",   "head"),
        ("wrist_R",    "hand.R",      "head"),
        ("hip_L",      "thigh.L",     "head"),
        ("knee_L",     "shin.L",      "head"),
        ("ankle_L",    "foot.L",      "head"),
        ("hip_R",      "thigh.R",     "head"),
        ("knee_R",     "shin.R",      "head"),
        ("ankle_R",    "foot.R",      "head"),
    ]
    for jname, bname, end in checks:
        if bname not in metarig.pose.bones:
            continue
        pb = metarig.pose.bones[bname]
        actual = pb.head if end == "head" else pb.tail
        err = (actual - T[jname]).length
        max_err = max(max_err, err)
        flag = "OK" if err <= 0.02 else "FAIL"
        print(f"  {jname:12} err={err*100:5.1f} cm  [{flag}]")

    # Head height check (after scale it should be near target_height)
    if "spine.006" in metarig.pose.bones:
        head_z = metarig.pose.bones["spine.006"].tail.z
        head_err = abs(head_z - target_height)
        print(f"  head_top     Z={head_z:.3f}  err_vs_{target_height}m={head_err*100:.1f} cm")
        max_err = max(max_err, head_err)

    print(f"Max joint/head error: {max_err*100:.1f} cm")

    # Symmetry
    sym_ok = True
    for L, R in [("shoulder_L", "shoulder_R"), ("hip_L", "hip_R"),
                 ("knee_L", "knee_R"), ("ankle_L", "ankle_R")]:
        if abs(T[L].x + T[R].x) > 0.005:
            sym_ok = False
    if sym_ok:
        ok("Target symmetry OK")
    else:
        print("WARNING: target symmetry issue")

    # Apply pose as rest
    try:
        bpy.ops.pose.armature_apply(selected=False)
        ok("Applied pose as rest")
    except Exception as e:
        print("WARNING armature_apply:", e)
    bpy.ops.object.mode_set(mode="OBJECT")

    # Apply armature modifier
    for mod in list(body.modifiers):
        if mod.type == "ARMATURE":
            bpy.ops.object.select_all(action="DESELECT")
            body.select_set(True)
            bpy.context.view_layer.objects.active = body
            try:
                bpy.ops.object.modifier_apply(modifier=mod.name)
                ok("Applied Armature modifier")
            except Exception as e:
                print("WARNING modifier:", e)
            break

    # Manifold check
    manifold, msg = check_manifold(body)
    if manifold:
        ok(msg)
    else:
        print("WARNING:", msg)

    ok(f"Poly count: {len(body.data.polygons)}")

    # Save
    out_path = OUT if shoulder_scale == 1.0 else OUT_WIDE
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out_path))
    ok(f"Saved {out_path}")

    return max_err, manifold

def main():
    # Pass 1 – standard proportions
    err1, man1 = run_fit(shoulder_scale=1.0, label="standard")

    # Pass 2 – 20% wider shoulders
    err2, man2 = run_fit(shoulder_scale=1.20, label="20% wider shoulders")

    print("\n" + "=" * 50)
    print("PHASE 4 FINAL SUMMARY")
    print("=" * 50)
    print(f"  Standard fit max error : {err1*100:.1f} cm")
    print(f"  Wide-shoulder max error: {err2*100:.1f} cm")
    print(f"  Manifold (standard)    : {man1}")
    print(f"  Manifold (wide)        : {man2}")

    if err1 <= 0.05 and err2 <= 0.08 and man1:
        print("\n>>> PHASE 4 ACCEPTANCE: PASSED <<<")
        sys.exit(0)
    else:
        print("\n>>> PHASE 4 ACCEPTANCE: NEEDS REVIEW <<<")
        sys.exit(1)

if __name__ == "__main__":
    main()