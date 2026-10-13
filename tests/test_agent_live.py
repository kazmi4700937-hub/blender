"""
Live end-to-end integration test for Phase 7 Natural-Language Agent.
Boots headless Blender with assets/rigged_character.blend and the bridge server,
sends natural language instructions, executes them through the validator,
and verifies Blender scene state and preview renders.
"""

import pytest
import subprocess
import os
import time

from orchestrator.bridge_client import BridgeClient
from orchestrator.agent.run import run_agent_command

LIVE_PORT = 9878

@pytest.fixture(scope="module")
def live_rigged_blender(blender_exe):
    """Start Blender with rigged character and bridge server on LIVE_PORT."""
    cmd = [
        blender_exe,
        "assets/rigged_character.blend",
        "-b",
        "--python",
        "tools/run_headless_server.py",
        "--",
        str(LIVE_PORT)
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=os.path.abspath(".")
    )

    client = BridgeClient(host="127.0.0.1", port=LIVE_PORT, timeout=30.0)
    connected = False
    start_time = time.time()

    while time.time() - start_time < 20.0:
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
            time.sleep(0.4)

    if not connected:
        proc.terminate()
        stdout, stderr = proc.communicate()
        raise TimeoutError(f"Blender bridge server failed to start within 20s:\n{stdout}\n{stderr}")

    yield client

    # Cleanup
    try:
        proc.terminate()
        proc.wait(timeout=3.0)
    except Exception:
        proc.kill()


def test_live_agent_jump_from_platform(live_rigged_blender):
    """Test full pipeline: natural language prompt -> tool calls -> validator -> bridge -> render."""
    client = live_rigged_blender
    preview_file = "output/previews/live_jump_test.png"
    if os.path.exists(preview_file):
        os.remove(preview_file)

    prompt = "Make the character jump from a 3 meter high ground"
    res = run_agent_command(
        prompt,
        bridge_client=client,
        render_preview=True,
        preview_output_path=preview_file
    )

    assert res.success is True
    assert len(res.bridge_commands) == 2
    assert os.path.exists(preview_file)
    assert os.path.getsize(preview_file) > 1000

    # Query scene state via bridge
    scene_info = client.get_scene_info()
    obj_names = [o["name"] for o in scene_info["objects"]]
    assert "Platform_Box" in obj_names
    assert "Ground_Plane" in obj_names
    assert "rig" in obj_names


def test_live_agent_unsupported_motion_no_blender_calls(live_rigged_blender):
    """Test unsupported prompt does not affect Blender scene."""
    client = live_rigged_blender
    prompt = "make him dance the tango"

    res = run_agent_command(
        prompt,
        bridge_client=client,
        render_preview=False
    )

    assert res.success is True
    assert len(res.bridge_commands) == 0
    assert "idle, wave, jump, walk" in res.message


def test_live_agent_wave_motion(live_rigged_blender):
    """Test wave motion application via natural language prompt."""
    client = live_rigged_blender
    preview_file = "output/previews/live_wave_test.png"

    prompt = "Make the character wave hello"
    res = run_agent_command(
        prompt,
        bridge_client=client,
        render_preview=True,
        preview_output_path=preview_file
    )

    assert res.success is True
    assert len(res.bridge_commands) == 1
    assert res.bridge_commands[0]["params"]["name"] == "wave"
    assert os.path.exists(preview_file)
    assert os.path.getsize(preview_file) > 1000
