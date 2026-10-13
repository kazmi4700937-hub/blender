# 2D-to-3D Character Rigging Assistant for Blender

An autonomous MVP pipeline taking 2D reference images of a humanoid character (front T-pose and side view), extracting silhouette masks and anatomical landmarks, fitting a 3D base mesh and Rigify metarig, generating a full IK/FK rig, and animating the character via natural-language commands and parameterized motions in Blender.

## Tech Stack
- **Blender**: 4.2 LTS (bundled with Rigify)
- **Python**: 3.11
- **Orchestrator**: Typer CLI, Bridge Client, Anthropic SDK
- **Vision**: Pillow, OpenCV, NumPy, rembg, onnxruntime
- **Bridge Protocol**: Local TCP Socket (127.0.0.1:9876), newline-delimited JSON with `bpy.app.timers` queue dispatch

## Project Structure
```
blender_rig_assistant/
  config.yaml              # Global settings
  DECISIONS.md             # Architecture and design decisions log
  requirements.txt         # Pinned Python package dependencies
  .gitignore
  assets/
    base_character.blend   # Calibrated template mesh + metarig
    fitted_character.blend # Output of the phase 4 test (kept for reference)
    rigged_character.blend # Output of the phase 5 test (used by the live agent test)
    test_images/           # Reference images and expected values (generated, small)
  blender_addon/
    __init__.py            # Addon entrypoint & server lifecycle
    server.py              # Socket server & timer execution queue
    commands/              # scene, rig, fit, environment, motion
    motions/               # jump, walk, wave, idle
  orchestrator/
    settings.py            # Config, model name, API key and Blender path (one place)
    cli.py                 # Main CLI entrypoint
    geometry/              # Providers that turn images into a 3D model (manual, tripo)
    bridge_client.py       # Robust JSON socket client
    vision/                # validate, silhouette, landmarks, overlay
    measure/               # landmarks -> character_spec.json
    agent/                 # tools, validator, run
  tests/
    conftest.py            # Shared test setup (project root, Blender lookup)
    test_*.py              # Pytest test suite for orchestrator
    blender/               # Blender headless test scripts (test_phase0/4/5/6 are the acceptance tests)
  tools/
    run_all_tests.py       # Runs everything and saves the output to docs/test_runs/
    render_test_reference_images.py
    run_headless_server.py
    split_turnaround.py    # Cut a front/side/back sheet into separate images
    bpy_blender_shim.py    # Optional: run Blender tests with the bpy module instead of Blender
  docs/
    rigify_bones.txt
    test_runs/             # Saved output of the last full test run
```

## Settings
- **LLM model**: set the `LLM_MODEL` environment variable, or `llm.default_model` in `config.yaml`. The code never hard-codes a model name. Check the current vision-capable model name before using it.
- **API key**: set `ANTHROPIC_API_KEY`. Without it, the agent uses the offline parser and landmark proposals use the template reference.
- **Blender program**: set the `BLENDER_EXE` environment variable. If it is not set, the tests use `paths.blender_exe` from `config.yaml`, then `blender` on PATH, then common install locations. Tests that start Blender are skipped, with a message, if Blender is not found.

## Quick Start
1. Install Blender 4.2 LTS (it includes Rigify).
2. Create a virtual environment and install the packages.

   Windows (PowerShell):
   ```powershell
   uv venv .venv --python 3.11
   .venv\Scripts\activate
   uv pip install -r requirements.txt
   ```
   Linux or macOS:
   ```bash
   uv venv .venv --python 3.11
   source .venv/bin/activate
   uv pip install -r requirements.txt
   ```
3. Tell the project where Blender is (skip if Blender is on PATH or at the default Windows location).

   Windows (PowerShell):
   ```powershell
   $env:BLENDER_EXE = "C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"
   ```
   Linux or macOS:
   ```bash
   export BLENDER_EXE=/path/to/blender
   ```
4. Run every test and save the output to `docs/test_runs/`:
   ```
   python tools/run_all_tests.py
   ```
   This renders `assets/test_images/` if it is missing, runs pytest, then runs the Blender phase scripts 0, 4, 5 and 6. Use `--skip-blender` to run only the tests that do not need Blender.

### Running the tests one by one
```
pytest -v
blender -b --python tests/blender/test_phase0.py
blender -b --python tests/blender/test_phase4.py
blender -b --python tests/blender/test_phase5.py
blender -b --python tests/blender/test_phase6.py
```
Replace `blender` with the full path to your Blender program if it is not on PATH. Run these from the project root.

### No Blender program? Use the bpy module
On Python 3.11, `pip install bpy==4.2.0` provides Blender as a Python module. `python tools/run_all_tests.py` uses it automatically when no Blender program is found. To also run the bridge, CLI and live-agent tests this way, point `BLENDER_EXE` at `tools/bpy_blender_shim.py` (see the notes at the top of that file). A script run this way may crash while Python shuts down after printing its pass line. This is a known effect of the module and `run_all_tests.py` allows for it.

## CLI Usage Workflow
Run these from the project root.

1. **Validate reference images**:
   ```
   python -m orchestrator.cli validate-images --front assets/test_images/front.png --side assets/test_images/side.png
   ```
2. **Extract silhouettes**:
   ```
   python -m orchestrator.cli extract-silhouettes
   ```
3. **Propose and review landmarks**:
   ```
   python -m orchestrator.cli propose-landmarks
   # Inspect overlays in output/landmarks_front_overlay.png and output/landmarks_side_overlay.png
   ```
4. **Confirm landmarks**:
   ```
   python -m orchestrator.cli confirm-landmarks
   ```
5. **Compute measurements**:
   ```
   python -m orchestrator.cli measure --height-m 1.75
   ```
6. **Natural Language Animation Agent**:
   ```
   python -m orchestrator.cli agent "Make the character jump from a 3 meter high ground"
   python -m orchestrator.cli agent "Make the character wave hello"
   ```

## Characters on gradient backgrounds, and turnaround sheets
If the reference image has a gradient or busy background (spec Section 3 normally rejects it), allow it and let rembg cut the character out:
```
python tools/split_turnaround.py private/sheet.png --out private/views     # only if the views are on one sheet
python -m orchestrator.cli validate-images --front private/views/front.png --side private/views/side.png --allow-busy-background
python -m orchestrator.cli extract-silhouettes --front private/views/front.png --side private/views/side.png
```
The first run downloads the segmentation model (about 179 MB, `vision.segmentation_model` in `config.yaml`). Always check the mask before trusting measurements.

## Getting a 3D model for the character (geometry providers)
The service that builds the 3D model is a setting (`geometry.provider` in `config.yaml`, or `GEOMETRY_PROVIDER`).
```
# No account: import a model you made elsewhere (for example in a web tool)
python -m orchestrator.cli geometry-generate --image private/views/front.png --provider manual --model path\to\model.glb

# Tripo web API (set TRIPO_API_KEY first; see DECISIONS.md Phase 9 for what is not yet verified)
python -m orchestrator.cli geometry-generate --image private/views/front.png --provider tripo --rig
```
Results are saved in `output/geometry/`. To bring the model into Blender (with the Blender add-on server running), scale it to the character's real height, stand it on the ground and check the mesh:
```
python -m orchestrator.cli import-generated-mesh output/geometry/generated.glb --height-m 1.75 --save output/generated_scene.blend
``` A Tripo rig is Tripo's own skeleton, not a Rigify rig.

## Notes
- Do not commit third-party artwork (for example game character images) to a public repository. Keep private test images in a `private/` folder, which `.gitignore` excludes.
- See `DECISIONS.md` for design decisions and open questions.
