import sys
import os
import time

# Add project root to sys.path so blender_addon can be imported
sys.path.insert(0, os.path.abspath("."))

from blender_addon import server

server.start_server(host="127.0.0.1", port=9876, allow_exec=False)
print("Bridge server started in headless test script.")

# Run for 2 seconds processing queue
start = time.time()
while time.time() - start < 2.0:
    server._process_queue_timer()
    time.sleep(0.01)

server.stop_server()
print("Bridge server stopped cleanly.")
