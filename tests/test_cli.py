import subprocess
import time
import os
import sys


def test_cli_ping(blender_exe):
    # Start server
    proc = subprocess.Popen(
        [blender_exe, "-b", "--python", "tools/run_headless_server.py", "--", "9876"],
        cwd=os.path.abspath(".")
    )
    time.sleep(1.0)
    try:
        res = subprocess.run(
            [sys.executable, "-m", "orchestrator.cli", "ping"],
            capture_output=True,
            text=True,
            cwd=os.path.abspath(".")
        )
        assert res.returncode == 0, f"CLI ping failed: {res.stderr}"
        assert "Bridge connected successfully!" in res.stdout
        assert "Blender Version:" in res.stdout
        assert "4.2" in res.stdout
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
