import sys
import os

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath("."))

from blender_addon import server

port = 9876
if len(sys.argv) > 1 and sys.argv[-1].isdigit():
    port = int(sys.argv[-1])

print(f"Starting headless bridge server on port {port}...")
server.start_server(host="127.0.0.1", port=port, allow_exec=False)
server.run_server_loop()
