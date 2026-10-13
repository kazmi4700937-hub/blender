import pytest
import subprocess
import socket
import time
import json
import sys
import os

from orchestrator.bridge_client import (
    BridgeClient,
    BridgeCommandError,
    BridgeConnectionError,
    BridgeTimeoutError
)

TEST_PORT = 9877

@pytest.fixture(scope="module")
def blender_server(blender_exe):
    """Start Blender in background running bridge server on TEST_PORT."""
    cmd = [
        blender_exe,
        "-b",
        "--python",
        "tools/run_headless_server.py",
        "--",
        str(TEST_PORT)
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=os.path.abspath(".")
    )
    
    # Wait for server to be responsive
    client = BridgeClient(host="127.0.0.1", port=TEST_PORT, timeout=5.0)
    connected = False
    start_time = time.time()
    
    while time.time() - start_time < 15.0:
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            raise RuntimeError(f"Blender exited prematurely with code {proc.returncode}:\n{stdout}\n{stderr}")
        try:
            client.connect()
            res = client.ping()
            if res.get("blender_version"):
                connected = True
                break
        except Exception:
            time.sleep(0.3)
            
    if not connected:
        proc.terminate()
        stdout, stderr = proc.communicate()
        raise TimeoutError(f"Blender bridge server failed to start within 15s:\n{stdout}\n{stderr}")
        
    yield client
    
    client.close()
    proc.terminate()
    try:
        proc.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_ping(blender_server):
    """Acceptance test 1: ping returns Blender version and addon version."""
    res = blender_server.ping()
    assert "blender_version" in res
    assert "4.2" in res["blender_version"]
    assert res.get("addon_version") == "1.0.0"


def test_create_cube_and_get_scene_info(blender_server):
    """Acceptance test 2: create a cube through a command and read it back with get_scene_info."""
    blender_server.clear_scene()
    
    # Create cube
    res_cube = blender_server.send_command("create_cube", {"name": "AcceptanceCube", "size": 1.5})
    assert res_cube.get("created") == "AcceptanceCube"
    
    # Read back scene info
    info = blender_server.get_scene_info()
    obj_names = [obj["name"] for obj in info.get("objects", [])]
    assert "AcceptanceCube" in obj_names


def test_malformed_request_error_handling(blender_server):
    """Acceptance test 3: malformed request returns error response and does not crash Blender."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", TEST_PORT))
    try:
        # Send non-JSON junk
        sock.sendall(b"{this is not valid json}\n")
        reply = sock.recv(4096).decode("utf-8")
        assert "\n" in reply
        parsed = json.loads(reply.strip())
        assert parsed["status"] == "error"
        assert parsed["error"]["code"] == "MALFORMED_JSON"
    finally:
        sock.close()
        
    # Verify server is still alive and responsive
    ping_res = blender_server.ping()
    assert "blender_version" in ping_res


def test_100_sequential_commands(blender_server):
    """Acceptance test 4: 100 sequential commands complete without a deadlock or crash."""
    for i in range(50):
        ping_res = blender_server.ping()
        assert "blender_version" in ping_res
        
        info = blender_server.get_scene_info()
        assert "objects" in info
