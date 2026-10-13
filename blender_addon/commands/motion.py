import bpy
from typing import Dict, Any

from ..motions.idle import apply_motion_idle
from ..motions.wave import apply_motion_wave
from ..motions.jump import apply_motion_jump
from ..motions.walk import apply_motion_walk

MOTIONS = {
    "idle": apply_motion_idle,
    "wave": apply_motion_wave,
    "jump": apply_motion_jump,
    "walk": apply_motion_walk,
}

def cmd_apply_motion(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Applies named motion to Rigify character.
    params:
      name: 'idle' | 'wave' | 'jump' | 'walk'
      params: motion-specific parameters dict
      rig_name: optional armature name (default 'rig')
    """
    name = params.get("name")
    if not name:
        raise ValueError("Missing 'name' in apply_motion parameters")

    motion_fn = MOTIONS.get(name.lower())
    if not motion_fn:
        available = list(MOTIONS.keys())
        raise ValueError(f"Unknown motion '{name}'. Available motions: {available}")

    rig_name = params.get("rig_name", "rig")
    rig = bpy.data.objects.get(rig_name)
    if not rig:
        raise RuntimeError(f"Armature object '{rig_name}' not found")

    sub_params = params.get("params", {})
    res = motion_fn(rig, sub_params)

    # Set scene frame range
    if "frame_start" in res and "frame_end" in res:
        bpy.context.scene.frame_start = res["frame_start"]
        bpy.context.scene.frame_end = res["frame_end"]

    return res
