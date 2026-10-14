"""Read the joints of a character from a skeleton that came with a generated model.

Some services (for example Tripo with spec "mixamo") return a rigged file. Its bones tell us
where the shoulders, elbows, hips and so on are, so no guessing from the picture is needed.
The result has the same shape as character_spec.json, so the rest of the pipeline does not care
whether the joints came from a skeleton or from landmarks found in the images.

Only Mixamo style bone names are understood. Any other naming is reported by name, not guessed.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

import bpy
from mathutils import Vector

# spec joint -> (bone whose HEAD is the joint, ...alternatives in order). Names are lower case,
# with any prefix such as "mixamorig:" removed.
_HEAD_OF = {
    "crotch": ["hips"],
    "neck_base": ["neck"],
    "chin": ["head"],
    "shoulder_L": ["leftarm"], "shoulder_R": ["rightarm"],
    "elbow_L": ["leftforearm"], "elbow_R": ["rightforearm"],
    "wrist_L": ["lefthand"], "wrist_R": ["righthand"],
    "hip_L": ["leftupleg"], "hip_R": ["rightupleg"],
    "knee_L": ["leftleg"], "knee_R": ["rightleg"],
    "ankle_L": ["leftfoot"], "ankle_R": ["rightfoot"],
    "toe_L": ["lefttoebase"], "toe_R": ["righttoebase"],
}
REQUIRED = sorted({name for names in _HEAD_OF.values() for name in names})


def normalize_bone_name(name: str) -> str:
    """'mixamorig:LeftArm', 'mixamorig_LeftArm', 'mixamorigLeftArm' and 'LeftArm' all become 'leftarm'."""
    n = name.lower()
    n = re.sub(r"^.*[:|]", "", n)            # drop everything up to a colon or pipe
    n = re.sub(r"^mixamorig[_.]?", "", n)    # drop the Mixamo prefix
    return n.replace("_", "").replace(".", "").replace(" ", "")


def joints_from_bones(bones: Dict[str, Tuple[Vector, Vector]], mesh_top_z: Optional[float] = None) -> Dict[str, Any]:
    """Build a character spec from {bone name: (head, tail)} in metres, Z up, character facing -Y."""
    by_name = {normalize_bone_name(n): (Vector(h), Vector(t)) for n, (h, t) in bones.items()}
    missing = [n for n in REQUIRED if n not in by_name]
    if missing:
        raise ValueError(
            "This skeleton does not use Mixamo bone names, so its joints cannot be read. "
            f"Missing: {', '.join(missing)}. Bones found include: {', '.join(sorted(bones)[:12])}"
        )

    joints: Dict[str, List[float]] = {}
    for joint, names in _HEAD_OF.items():
        head = by_name[names[0]][0]
        joints[joint] = [head.x, head.y, head.z]

    warnings = []
    swapped = False
    # The character's left is +X when it faces -Y. Fix a skeleton that was built the other way round.
    if joints["shoulder_L"][0] < joints["shoulder_R"][0]:
        swapped = True
        warnings.append("Left and right were swapped in the skeleton; corrected.")
        for base in ("shoulder", "elbow", "wrist", "hip", "knee", "ankle", "toe"):
            joints[base + "_L"], joints[base + "_R"] = joints[base + "_R"], joints[base + "_L"]

    # Top of the head: the end of a HeadTop bone if there is one, else the top of the mesh.
    top = None
    top_xy = None
    for key in ("headtopend", "headtop"):
        if key in by_name:
            p0 = by_name[key][0]      # the head of this end bone is the top of the head
            top, top_xy = p0.z, [p0.x, p0.y]
            break
    if top is None:
        if mesh_top_z is not None:
            top = mesh_top_z
        else:
            head_head, head_tail = by_name["head"]
            top = max(head_head.z, head_tail.z)
            warnings.append("No head-top bone and no mesh given; the head top is taken from the head bone.")
    xy = top_xy or [joints["chin"][0], joints["chin"][1]]
    joints["head_top"] = [xy[0], xy[1], top]

    # Fingertip: end of the middle finger chain if present, else a short extension of the forearm line.
    for side, sgn in (("L", "right" if swapped else "left"), ("R", "left" if swapped else "right")):
        wrist = Vector(joints[f"wrist_{side}"])
        if f"{sgn}handmiddle4" in by_name:
            tip = by_name[f"{sgn}handmiddle4"][0]    # head of the end bone is the fingertip
        elif f"{sgn}handmiddle3" in by_name:
            tip = by_name[f"{sgn}handmiddle3"][1]
        else:
            elbow = Vector(joints[f"elbow_{side}"])
            tip = wrist + (wrist - elbow) * 0.35
        joints[f"hand_tip_{side}"] = [tip.x, tip.y, tip.z]

    return {
        "version": 1,
        "units": "m",
        "height_m": top,
        "joints": {k: [round(float(c), 5) for c in v] for k, v in joints.items()},
        "source": "skeleton",
        "warnings": warnings,
    }


def cmd_skeleton_to_spec(params):
    """Read joints from an armature in the scene (a Mixamo style skeleton) and return a character spec."""
    name = params.get("armature_name")
    arm = bpy.data.objects.get(name) if name else next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
    if arm is None or arm.type != "ARMATURE":
        raise ValueError("No armature found in the scene. The model must have come with a skeleton.")

    bones = {}
    for b in arm.data.bones:
        bones[b.name] = (arm.matrix_world @ b.head_local, arm.matrix_world @ b.tail_local)

    mesh_top = None
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if meshes:
        mesh_top = max((o.matrix_world @ Vector(c)).z for o in meshes for c in o.bound_box)
    spec = joints_from_bones(bones, mesh_top)
    spec["armature"] = arm.name
    return spec
