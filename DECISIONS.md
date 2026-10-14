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


## Phase 9a: Gradient backgrounds and turnaround sheets

Date: 13 Oct 2026. Trigger: a real test character (front, side and back turnaround on a grey gradient
backdrop with floor shadows) was rejected as a "busy" background, and the rembg default model (about 1 GB)
ran out of memory when tried.

- R9a.1 Spec Section 3 still rejects busy backgrounds by default. A new option accepts them:
  `validate-images --allow-busy-background` (`allow_busy_background=True` in code). Accepted images get a
  warning in the result and in the console, because the cut-out is a model estimate.
- R9a.2 The rembg model is now a setting: `SEGMENTATION_MODEL` environment variable, then
  `vision.segmentation_model` in config.yaml, then `isnet-general-use`. That model is about 179 MB and
  is downloaded once. The rembg 2.0.85 default is about 1 GB. Checked on the test sheet: it cut out all
  three views cleanly, excluded the floor shadows and kept fine edges. Not yet checked on other art styles.
- R9a.3 Tried and dropped: modelling the gradient from the image border (polynomial and per-row) with a
  shadow-brightness rule. Dark clothing and floor shadows have the same brightness range, so it left holes
  in the clothing and included parts of the backdrop.
- R9a.4 `tools/split_turnaround.py` cuts a sheet into equal columns (front, side, back). It assumes even spacing.
- R9a.5 Still open: the arms are in an A-pose (about 30 degrees), not a T-pose, and two rods behind the waist
  show beside the body in the front view. Both belong to phases 10 to 13 (feature inventory, pose, parts).

## Decisions confirmed by the owner (13 Oct 2026)

- D8 Base body height: standard is 1.75 m. The current base_character.blend is 1.98 m, so it must be
  scaled or regenerated and the fitted and rigged .blend files rebuilt from one spec. Not done yet.
- D1 Geometry route: hybrid, the template body plus separately built parts. Tested first on the turnaround test character.
- D2 Hardware: a hosted image-to-3D service is allowed for the geometry phase, chosen after the Phase 9 tool comparison.

## Phase 9: Geometry service comparison (checked 13 Oct 2026)

Goal: replace the fixed template body as the main route with a service that builds a 3D model from any
character image, so nothing in the app is tied to one character. The service sits behind one switch
(`geometry.provider` in config.yaml, or the `GEOMETRY_PROVIDER` environment variable). Sources are the
vendors' own docs and repositories. Prices and licences change, so re-check before paying.

| Option | What it covers | Cost found | Licence | Runs on a CPU-only PC |
|---|---|---|---|---|
| Tripo API | Image to 3D, multiview, rig check, auto rig (biped, quadruped and more; Mixamo or Tripo bone names; GLB or FBX), segmentation, retopology, format conversion | Image to 3D 20 credits (no texture) or 30 (standard texture), auto rig 25, rig check free. The pricing page showed 1 credit = 0.07 CNY (China site); international price and free credits NOT confirmed | Commercial service, API terms apply (not read) | Yes, it is a web API |
| Meshy API | Image to 3D, auto rig, animation | Image to 3D 20 to 35 credits by model and texture size, auto rig 5, animation 3 per action. API credit price and any free API credits NOT confirmed (free web plan: 100 credits a month) | Commercial service (not read) | Yes |
| Hunyuan3D 2.1 (self-hosted) | Shape and PBR texture | Free, but needs about 10 GB VRAM for shape, 29 GB for shape plus texture | Tencent licence: not valid in the EU, UK and South Korea; extra licence above 1 million monthly users; outputs may not be used to improve other AI models | No |
| TripoSR (self-hosted) | Shape only (vertex colours, optional texture bake) | Free, about 6 GB VRAM | MIT | Not documented for CPU; needs a GPU in practice |

Findings:
- R9.1 Tripo is the only option found that covers the whole chain (generate, check riggability, rig,
  split into parts) in one API. Recommendation: use Tripo first, behind the provider switch, and keep
  Meshy as the second provider to add if Tripo's quality or price disappoints.
- R9.2 Self-hosting is not possible on the owner's CPU-only PC. Keep Hunyuan3D 2.1 and TripoSR as options
  for a rented GPU later. Check the Hunyuan licence territory rule before any use.
- R9.3 Tripo's rig is Tripo's own skeleton (Mixamo-style names), not a Rigify rig. The app therefore has two
  rig routes: the provider's rig (fast, fixed skeleton) and the app's Rigify route (more controls, needs
  joint landmarks on the new mesh). Rig profiles in spec v3 Phase 14 choose between them.
- R9.4 The multi-image option helps: Tripo's CLI page says front and back images together give more detail.
  The API endpoint for it (multiview) is not wired yet.
- R9.5 NOT verified: the exact body of Tripo's image-to-model request (the docs pages could not be read),
  the international price, free credits, and quality on the test character. `geometry.tripo.generation_body`
  in config.yaml holds the guess `{"input": "{file_token}"}`. The first real call will show the API's own
  error message if it is wrong. Fix the body from https://developers.tripo3d.com/en/docs.
- R9.6 Implemented: `orchestrator/geometry/` (base interface, registry, `manual` provider that imports a model
  you already have, `tripo` provider), the `geometry-generate` CLI command, 10 tests with a fake API. No
  real Tripo call has been made.

- R9.7 New bridge command `import_generated_mesh` (logged here as required by spec Section 1): imports .glb/.gltf/.fbx/.obj,
  scales to the stated height, stands the model on Z = 0 and centres it, bakes the transforms, merges seam duplicates
  and reports counts and warnings (open edges, separate pieces, heavy mesh, lying down, existing armature).
- R9.8 Found while testing: glTF import splits vertices at UV and shading seams (a 482-vertex test sphere arrived
  as 1,984 vertices, 512 pieces and 1,984 open edges). Without merging, every seam looks like a hole and auto weights
  can tear the seam. The import now merges vertices closer than 0.01 mm (`weld_distance_m`). Merging drops custom
  split normals, so shading may look slightly different; this is accepted for rigging.
- R9.9 Tests: `tests/blender/test_phase9.py` builds its own models (no network). Not yet run on a real AI-generated
  character, which is the next check.

## Phase 9c: Rigging an arbitrary imported mesh (14 Oct 2026)
New bridge commands (logged as the spec requires): `skeleton_to_spec` and `rig_generated_mesh`. CLI: `skeleton-to-spec`, `rig-generated-mesh`.
- R9c.1 Joints come from one of two places: the 2D landmarks (character spec, needs the vision model) or a Mixamo style skeleton that
  came with the model (`skeleton_to_spec`; names are matched with or without the `mixamorig:` prefix, left/right swapped skeletons
  are corrected and reported, unknown names are refused with the missing names listed).
- R9c.2 `rig_generated_mesh` moves each target Rigify metarig bone to its joint, refines every joint's depth (Y) by casting rays
  to the mesh front and back, and generates the rig. Metarig bones with no joint of their own (face, pelvis, toes, spine
  details) move with their nearest ancestor that has one. Fingers move as one group from the wrist to the hand tip, because the
  template's finger bones do not lie along its hand bone.
- R9c.3 Checks: every vertex weighted, key deform bones control vertices, and a knee bend moves only the left leg. Tested on a
  tall, thin variant of the base body exported as a bare .glb (no weights, no armature). NOT yet tested on a real AI-generated
  character; joints that fall outside the mesh are reported as warnings, not hidden.
- R9c.4 `fit.py` was refactored (`build_target_endpoints`, `objects` parameter); phases 4, 5, 6 and 9 still pass.
- R9c.5 Known limits: finger and face bones are placed by following the hand/head, not measured; the crotch depth cannot be
  refined on some meshes (reported as a warning); the 706-bone rig and A-pose handling are unchanged open items.
