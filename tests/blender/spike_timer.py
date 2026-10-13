import bpy
import time
import sys

count = 0
def tick():
    global count
    count += 1
    print(f"Timer tick {count}")
    if count >= 3:
        return None
    return 0.1

bpy.app.timers.register(tick)

print("Starting loop...")
# In background mode, if script finishes, Blender exits.
# To keep Blender alive while processing timers:
# Can we do a loop that yields to Blender or processes events?
# Or does time.sleep block the main thread?
for i in range(5):
    time.sleep(0.1)
print("Finished. Timer count:", count)
