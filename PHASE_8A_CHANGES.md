# Phase 8a repairs: what changed

How to apply: unzip this file **into your `blender_rig_assistant` folder** and let it overwrite the files it lists. Your `assets/*.blend` files, `.venv` and `output` folder are not touched.

Then run (from the project folder, with your virtual environment active):

    python tools/run_all_tests.py

It saves the output to `docs/test_runs/`. On your Windows machine it finds Blender at the default path, or set `BLENDER_EXE` first (see README.md).

## Changed files
- `orchestrator/cli.py`, `orchestrator/agent/run.py`: use the new `orchestrator/settings.py` instead of their own copies of the config loader and model default.
- `orchestrator/vision/landmarks.py`: reads the model name from settings.
- `orchestrator/vision/silhouette.py`: `rembg` is imported only when background removal is needed.
- `config.yaml`: default model is now `claude-sonnet-5-5` (VERIFY; set `LLM_MODEL` to override). Comment added on the Blender path.
- `tests/test_bridge.py`, `tests/test_cli.py`, `tests/test_agent_live.py`: no hard-coded Windows path; they use the `blender_exe` fixture.
- `tests/test_validator.py`: no longer hard-codes the old model name.
- `README.md`: Windows and Linux/macOS commands, settings section, `run_all_tests.py`.
- `DECISIONS.md`: new "Phase 8a Repairs" section (R8a.1 to R8a.11) and open decisions.

## New files
- `orchestrator/settings.py`: one place for config, model name, API key and the Blender path.
- `tests/conftest.py`: runs tests from the project root, finds Blender, skips tests with a clear message when Blender or the reference images are missing.
- `tools/run_all_tests.py`: runs every test and saves the output.
- `tools/bpy_blender_shim.py`: optional, lets the Blender-starting tests run with the `bpy` module on Linux or macOS.
- `.gitignore`.
- `assets/test_images/`: the generated reference images and expected values (1.3 MB, your own synthetic renders).
- `docs/test_runs/`: output of the full run described below.

## Test result of these changes
30 of 30 pytest tests pass, and Blender phases 0, 4, 5 and 6 pass. These runs used the `bpy` 4.2.0 module, not the Blender program, so please repeat them with Blender 4.2 on your machine. Each Blender script ended with a crash at shutdown after printing its pass line, which is a known effect of the module; `run_all_tests.py` allows for it only in that mode.

## Not changed (needs you)
- Push the full project folder to GitHub (the repository only has flat test scripts).
- Decide the standard height (1.98 m base body or 1.75 m spec), then regenerate `fitted_character.blend` and `rigged_character.blend` from one spec.
- Decide whether to keep face and breast controls in the Rigify rig (706 bones now).
- Verify the default model name against the live API with your key.
