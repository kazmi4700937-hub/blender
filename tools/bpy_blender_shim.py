#!/usr/bin/env python3
"""Optional: lets the tests that start Blender run without the Blender program.

It accepts the same arguments the tests pass to Blender
(`-b --python script.py -- extra args`, and an optional .blend file to open) and
runs them with the `bpy` Python module instead.

Use it on Linux or macOS where only `pip install bpy==4.2.0` (Python 3.11) is installed:

    export BLENDER_EXE=/full/path/to/tools/bpy_blender_shim.py
    chmod +x tools/bpy_blender_shim.py
    # run it with the virtual environment that has bpy installed activated, so that
    # `python3` in the first line below is that environment's Python.

It is a development convenience. The real Blender program remains the reference.
"""

import os
import runpy
import sys

import bpy

args = sys.argv[1:]
blend_file = None
script = None
extra = []
i = 0
while i < len(args):
    arg = args[i]
    if arg == "--":
        extra = args[i + 1:]
        break
    if arg == "--python":
        script = args[i + 1]
        i += 2
        continue
    if arg in ("-b", "--background"):
        i += 1
        continue
    if arg.endswith(".blend"):
        blend_file = arg
    i += 1

if script is None:
    sys.exit("bpy_blender_shim: no --python script given")

if blend_file:
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(blend_file))

sys.argv = ["blender", "--"] + extra
sys.path.insert(0, os.getcwd())
runpy.run_path(script, run_name="__main__")
