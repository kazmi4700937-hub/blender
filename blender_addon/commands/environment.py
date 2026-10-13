import bpy
from typing import Dict, Any

def cmd_build_environment(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Creates ground plane and optional platform for platform_drop.
    params:
      kind: 'ground' | 'platform_drop'
      height_m: float (platform height)
      size_m: float (ground size)
    """
    kind = params.get("kind", "ground")
    height_m = float(params.get("height_m", 2.0))
    size_m = float(params.get("size_m", 10.0))

    if height_m < 0:
        raise ValueError(f"Platform height cannot be negative: {height_m}")
    if size_m <= 0:
        raise ValueError(f"Environment size must be positive: {size_m}")

    # Remove existing environment objects if any
    for obj_name in ["Ground_Plane", "Platform_Box"]:
        existing = bpy.data.objects.get(obj_name)
        if existing:
            bpy.data.objects.remove(existing, do_unlink=True)

    created_objects = []

    # 1. Ground Plane (at Z = 0)
    bpy.ops.mesh.primitive_plane_add(size=size_m, location=(0, -size_m * 0.25, 0))
    ground = bpy.context.active_object
    ground.name = "Ground_Plane"
    created_objects.append(ground.name)

    # Simple ground material
    mat_ground = bpy.data.materials.get("Mat_Ground")
    if not mat_ground:
        mat_ground = bpy.data.materials.new("Mat_Ground")
        mat_ground.diffuse_color = (0.3, 0.5, 0.3, 1.0)
    ground.data.materials.append(mat_ground)

    # 2. Platform (for platform_drop)
    platform_top_z = 0.0
    if kind == "platform_drop":
        platform_depth = 2.0
        platform_width = 2.0
        # Platform box: center is at Z = height_m / 2, so top is at height_m
        box_center_z = height_m / 2.0
        box_center_y = 0.0  # Character starts at (0, 0, height_m)
        bpy.ops.mesh.primitive_cube_add(
            size=1.0,
            location=(0, box_center_y, box_center_z)
        )
        platform = bpy.context.active_object
        platform.name = "Platform_Box"
        platform.scale = (platform_width, platform_depth, height_m)
        bpy.ops.object.transform_apply(scale=True)
        created_objects.append(platform.name)

        mat_plat = bpy.data.materials.get("Mat_Platform")
        if not mat_plat:
            mat_plat = bpy.data.materials.new("Mat_Platform")
            mat_plat.diffuse_color = (0.5, 0.4, 0.3, 1.0)
        platform.data.materials.append(mat_plat)
        platform_top_z = height_m

    return {
        "kind": kind,
        "created_objects": created_objects,
        "platform_top_z": platform_top_z,
        "height_m": height_m
    }
