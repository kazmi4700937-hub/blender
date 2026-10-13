import bpy

bpy.ops.wm.read_homefile(use_empty=True)
bpy.ops.preferences.addon_enable(module="rigify")
bpy.ops.object.armature_human_metarig_add()
metarig = bpy.context.active_object

print("Metarig name:", metarig.name)
print("Metarig dimensions:", metarig.dimensions)
print("Metarig location:", metarig.location)

# List main bone head and tail coordinates
bones = metarig.data.bones
key_bones = [
    "spine", "spine.001", "spine.002", "spine.003", "spine.004", "spine.005", "spine.006",
    "shoulder.L", "upper_arm.L", "forearm.L", "hand.L",
    "thigh.L", "shin.L", "foot.L", "toe.L"
]
print("\n--- Metarig Key Bone Locations (Edit/Rest) ---")
for b_name in key_bones:
    b = bones.get(b_name)
    if b:
        print(f"{b_name:15}: head={tuple(round(v, 4) for v in b.head_local)}, tail={tuple(round(v, 4) for v in b.tail_local)}")
