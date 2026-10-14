#!/usr/bin/env python3
"""Run every test in the project and save the output to docs/test_runs/.

Usage (from anywhere):
    python tools/run_all_tests.py
    python tools/run_all_tests.py --skip-blender      # only the tests that do not need Blender

What it does, in order:
  1. Writes docs/test_runs/environment.txt (Python, system, Blender or bpy versions).
  2. Renders assets/test_images/ (front and side reference images) if they are missing.
  3. Runs pytest and saves docs/test_runs/pytest.txt.
  4. Runs the Blender phase scripts 0, 4, 5, 6 and 9 and saves docs/test_runs/phase<N>.txt.
  5. Prints a summary and saves docs/test_runs/summary.txt.

Blender is found through the BLENDER_EXE environment variable, paths.blender_exe in
config.yaml, PATH, or a common install location. If no Blender program is found but the
`bpy` Python module is installed (pip install bpy==4.2.0 on Python 3.11), the scripts are
run with that instead.

Exit code: 0 if nothing failed, 1 if anything failed. Steps that could not run (no Blender)
are listed as SKIPPED and do not count as passes.
"""

import argparse
import datetime
import importlib.util
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from orchestrator.settings import get_blender_exe  # noqa: E402

OUT_DIR = ROOT / "docs" / "test_runs"
PHASES = [0, 4, 5, 6, 9, "9c"]
PASS_MARKER = "ACCEPTANCE TESTS PASSED"


def bpy_available() -> bool:
    return importlib.util.find_spec("bpy") is not None


def blender_command(exe, script: Path):
    """Command that runs a Blender script, or None if there is no way to run it."""
    if exe:
        return [exe, "-b", "--python", str(script)]
    if bpy_available():
        return [sys.executable, str(script)]
    return None


def run_logged(cmd, log_name: str, timeout: int):
    """Run a command from the project root, save its output, return (exit code, text)."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout, errors="replace"
        )
        text = (proc.stdout or "") + (proc.stderr or "")
        code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        text = f"TIMEOUT after {timeout}s\n{exc.stdout or ''}{exc.stderr or ''}"
        code = -1
    (OUT_DIR / log_name).write_text(text, encoding="utf-8")
    return code, text


def write_environment(exe, mode: str):
    lines = [
        f"date: {datetime.datetime.now().isoformat(timespec='seconds')}",
        f"python: {sys.version.split()[0]}",
        f"system: {platform.platform()}",
        f"blender program: {exe or 'not found'}",
        f"blender mode used for Blender scripts: {mode}",
    ]
    if exe:
        try:
            out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60)
            lines.append("blender version: " + (out.stdout.strip().splitlines() or ["unknown"])[0])
        except Exception as exc:  # noqa: BLE001
            lines.append(f"blender version: could not run ({exc})")
    if bpy_available():
        try:
            out = subprocess.run(
                [sys.executable, "-c", "import bpy; print(bpy.app.version_string)"],
                capture_output=True, text=True, timeout=120,
            )
            lines.append("bpy module version: " + out.stdout.strip().splitlines()[-1])
        except Exception as exc:  # noqa: BLE001
            lines.append(f"bpy module version: could not import ({exc})")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "environment.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all project tests and save the output.")
    parser.add_argument("--skip-blender", action="store_true",
                        help="Do not run anything that needs Blender (image rendering, phase scripts).")
    args = parser.parse_args()

    exe = None if args.skip_blender else get_blender_exe()
    can_run_blender = (not args.skip_blender) and (bool(exe) or bpy_available())
    mode = "program" if exe else ("bpy module" if can_run_blender else "none")
    write_environment(exe, mode)

    results = []  # (name, status, detail)

    # 1. reference images
    images_ready = (ROOT / "assets/test_images/front.png").is_file() and (
        ROOT / "assets/test_images/ground_truth_landmarks.json").is_file()
    if not images_ready:
        cmd = blender_command(exe, ROOT / "tools/render_test_reference_images.py") if can_run_blender else None
        if cmd is None:
            results.append(("render reference images", "SKIPPED", "Blender not found"))
        else:
            print("Rendering reference images (this takes a few minutes)...")
            code, text = run_logged(cmd, "render_reference_images.txt", timeout=1800)
            ok = (ROOT / "assets/test_images/front.png").is_file()
            results.append(("render reference images", "PASSED" if ok else "FAILED", f"exit code {code}"))
    else:
        results.append(("render reference images", "PASSED", "already present"))

    # 2. pytest
    print("Running pytest...")
    code, text = run_logged(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"],
        "pytest.txt", timeout=1800,
    )
    summary_line = (text.strip().splitlines() or ["no output"])[-1]
    results.append(("pytest", "PASSED" if code == 0 else "FAILED", summary_line))

    # 3. Blender phase scripts
    for n in PHASES:
        name = f"phase {n} (tests/blender/test_phase{n}.py)"
        script = ROOT / "tests" / "blender" / f"test_phase{n}.py"
        cmd = blender_command(exe, script) if can_run_blender else None
        if cmd is None or not script.is_file():
            reason = "Blender not found" if cmd is None else "script missing"
            results.append((name, "SKIPPED", reason))
            continue
        print(f"Running Blender phase {n}...")
        code, text = run_logged(cmd, f"phase{n}.txt", timeout=1800)
        marker_found = PASS_MARKER in text
        # With the bpy module (directly, or through tools/bpy_blender_shim.py) Python can crash
        # while shutting down after the tests finish (exit code 139, or -11, on Linux).
        # The pass marker is printed before that, so accept it in that case only.
        uses_bpy_module = mode == "bpy module" or str(exe or "").endswith("bpy_blender_shim.py")
        exit_ok = code == 0 or (uses_bpy_module and marker_found)
        status = "PASSED" if (marker_found and exit_ok) else "FAILED"
        results.append((name, status, f"exit code {code}, pass marker {'found' if marker_found else 'missing'}"))

    # summary
    width = max(len(r[0]) for r in results)
    lines = [f"{name.ljust(width)}  {status:8}  {detail}" for name, status, detail in results]
    failed = sum(1 for r in results if r[1] == "FAILED")
    skipped = sum(1 for r in results if r[1] == "SKIPPED")
    lines.append("")
    lines.append(f"{len(results) - failed - skipped} passed, {failed} failed, {skipped} skipped")
    summary = "\n".join(lines)
    print("\n" + summary)
    (OUT_DIR / "summary.txt").write_text(summary + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
