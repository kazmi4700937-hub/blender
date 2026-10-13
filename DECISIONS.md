# Project Architectural Decisions & Log

This log records every non-obvious decision, library choice, workaround, or deviation from the specification with a clear rationale.

## Initial Decisions (Section 12)
- **D1. Art Style**: Stylized humanoid with roughly realistic proportions. Chosen to balance clear anatomical landmark identification with accessible template deformation.
- **D2. Operating System & Compute**: Windows 11 on x86_64, CPU inference default. Configured `rembg` with `onnxruntime` CPU execution provider so no external CUDA GPU setup is required for the MVP.
- **D3. LLM API Access**: Anthropic Claude API (`anthropic` SDK). Model name read from `LLM_MODEL` environment variable (default: `claude-3-7-sonnet-20250219` or `claude-3-5-sonnet-20241022`), API key read from `ANTHROPIC_API_KEY`.
- **D4. Base Character Mesh & License**: Procedurally generated stylized humanoid mesh in `assets/base_character.blend` created under CC0 1.0 Universal (Public Domain Dedication). Topologically structured with clean quad/tri layout aligned to the Blender 4.2 Rigify human metarig, with pre-calibrated vertex weights and zero unweighted vertices.
- **D5. Interface**: Command-line interface via Python `typer` for Phase 0–7 MVP execution.

## Technical Findings & Workarounds
- **T0.1: Blender 4.2 Add-on Enabling**: In Blender 4.2 headless mode (`blender -b`), add-ons like Rigify must be activated via `bpy.ops.preferences.addon_enable(module="rigify")` rather than raw `addon_utils.enable()` to ensure preference dictionaries and operator registries initialize properly.
- **T0.2: Rigify Bone Names in Blender 4.2 LTS**: Confirmed root control is `root`, torso controls are `torso`, `chest`, `hips`, IK hand controls are `hand_ik.L` / `hand_ik.R`, IK feet controls are `foot_ik.L` / `foot_ik.R`, and IK/FK switch property is `IK_FK` on `thigh_parent.{L/R}` and `upper_arm_parent.{L/R}`.
- **T0.3: rembg CPU Provider**: `rembg` requires an explicit backend runtime on Windows; installed `onnxruntime` CPU provider.
- **T1.1: Bridge Server Main Thread Execution**: For GUI mode, requests are processed via `bpy.app.timers.register`. For headless mode (`blender -b`), `server.run_server_loop` allows synchronous main thread event processing without crashing Blender.
- **T1.2: Python Module Discovery**: Added `pytest.ini` with `pythonpath = .` for clean orchestrator imports during automated testing.
- **T2.1: Silhouette Extraction & Noise Suppression**: Morphological opening/closing and 8-connectivity connected component filtering are applied to isolate the largest connected component and remove stray floating artifacts.
- **T2.2: Background Variance Classification**: Border pixel standard deviation thresholding (threshold < 18.0) robustly detects flat solid backgrounds while rejecting complex/busy scene images.
- **T3.1: Strict Left/Right Sanity Validation**: Enforces image-space X ordering for Left and Right landmarks (`x_L > x_R`) to prevent inverted skeletal deformation.
- **T3.2: Human Confirmation Gatekeeper**: Enforces that `landmarks.json` has `confirmed: true` before allowing measurement extraction to proceed, preventing unverified VLM pixel hallucinations from propagating downstream.
- **T3.3: Offline/Mock Proposal Fallback**: When `ANTHROPIC_API_KEY` is not present, CLI propose command falls back to template reference landmarks with `confirmed=False` to enable full local inspection and testing.
- **T4.1: Direct LBS Mesh & Metarig Fitting**: Avoids pose bone scale inheritance multiplication artifacts by computing affine transformations from rest to target bones and displacing mesh vertices via linear blend skinning across vertex groups, while edit bones are positioned directly in edit mode.
- **T4.2: Outward Normals Validation**: Verified using signed mesh volume (`bm.calc_volume(signed=True) > 0`) in combination with `normals_make_consistent(inside=False)` to prevent inverted face normals.
- **T5.1: Rigify Limb Pole Vector Bend**: Added non-zero natural limb bend offsets (+Y for elbows, -Y for knees) in `fit_template` so the Rigify generator's pole angle vector computation never receives collinear or zero-length vectors.
- **T5.2: Deformation Isolation Verification**: Confirmed via evaluated dependency graph vertex inspection that rotating the knee moves 103 left-leg vertices while producing exactly 0 moved vertices on the opposing leg and torso.
- **T6.1: Rigify Foot IK Offset Calculation**: Since `foot_ik.L` and `foot_ik.R` inherit the `root` bone's transform, local target coordinates are keyframed as `target_world - root_world` while preserving resting ankle height (`0.0852m`) to place foot soles on the ground or platform with sub-centimeter accuracy.
- **T6.2: Ballistic Jump Arc Dynamics**: Added an asymmetric apex boost to the parabolic trajectory for platform drops, ensuring the root ascends above the takeoff platform before transitioning into parabolic freefall.
- **T7.1: Anthropic Tool Calling with Offline Deterministic Fallback**: Integrated Anthropic Claude tool calling schemas for LLM-driven planning while maintaining a strict deterministic offline regex parser for offline and local test execution.
- **T7.2: Parameter Validation & Default Reporting**: Validator validates numeric bounds before dispatching any command over the socket bridge, rejects unsupported motions politely with the available motion list, and tracks default assignments in `applied_defaults`.
- **T7.3: Fast Workbench Preview Engine**: Switched `render_preview` to the Workbench render engine at 640x480 resolution to produce instant viewport snapshot previews in ~0.05s on CPU without Cycles/EEVEE shader compilation overhead.

## Phase 8a Repairs (11 Oct 2026)
These changes follow the Handoff & Problem Report and Spec v3 Section 3. No behaviour of the pipeline was changed.

- **R8a.1: One settings module.** `orchestrator/settings.py` now holds config loading, the model name, the API key and the Blender path. The model name was repeated in four places before, so changing it needed code edits.
- **R8a.2: Default model changed to `claude-sonnet-5-5`** in `config.yaml`. VERIFY: it was not tested against the live API here because no API key was available. `LLM_MODEL` overrides it. `FALLBACK_MODEL` in `settings.py` is used only when `config.yaml` is missing.
- **R8a.3: Blender path from the `BLENDER_EXE` environment variable**, then `paths.blender_exe` in `config.yaml`, then `blender` on PATH, then common install locations. The three tests that start Blender use a `blender_exe` fixture (in `tests/conftest.py`) and are skipped with a clear message if Blender is not found.
- **R8a.4: `rembg` is imported only when background removal is needed** (`orchestrator/vision/silhouette.py`). Images with an alpha channel or a flat background no longer need `rembg` installed.
- **R8a.5: `tests/conftest.py`** runs every test from the project root, and skips the tests that need `assets/test_images/` when it has not been generated, with the command to create it.
- **R8a.6: `tools/run_all_tests.py`** runs everything and saves the output to `docs/test_runs/`. `.gitignore` added.
- **R8a.7: `tools/bpy_blender_shim.py`** is an optional development aid that lets the Blender-starting tests run with the `bpy` module on Linux or macOS. The real Blender program remains the reference.
- **R8a.8: The extra bridge command `create_cube`** (`blender_addon/server.py`) is not in the spec v2 command set. It stays only because the Phase 1 acceptance test requires creating a cube through a command (`tests/test_bridge.py`). It is test-only and must not be used by the orchestrator.
- **R8a.9: Landmark fallback tag.** With no API key, `propose-landmarks` uses the template's own landmarks, writes `source: "reference_proposal"` and `confirmed: false`, and prints a warning (already in `orchestrator/cli.py`; recorded here as T3.3 follow-up). They must never be treated as real detections.
- **R8a.10: Phase test scripts.** The project folder already keeps `test_phase0.py`, `test_phase4.py`, `test_phase5.py` and `test_phase6.py` (and the standalone and helper scripts) in `tests/blender/`, where the README expects them. The GitHub repository only has flat copies in its root, so push the whole project folder to make the repository match.
- **R8a.11: Test runs are saved.** `docs/test_runs/` holds the output of the last full run, so another person or AI can see what passed. These runs used the `bpy` 4.2.0 module through the shim; repeat them with the Blender 4.2 program on your machine.

### Open decisions (not changed in Phase 8a)
- **D8:** the base body is 1.98 m tall, the spec default is 1.75 m. Decide which is standard, then regenerate `fitted_character.blend` and `rigged_character.blend` from one spec (they currently come from different test specs).
- The generated Rigify rig has 706 bones including face and breast controls. Spec v2 asked for a face-free head.
- The GitHub repository still needs the full project pushed from your computer.
