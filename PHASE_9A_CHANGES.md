# Phase 9a patch: gradient backgrounds and turnaround sheets

Apply from the project root (it overwrites the files listed below):

    tar -xf C:\Users\abbas\Downloads\phase9a_patch.zip
    .venv\Scripts\activate
    python -m pytest -q
    python tools\split_turnaround.py private\ninja_sheet.webp --out private\ninja
    python -m orchestrator.cli validate-images --front private\ninja\front.png --side private\ninja\side.png --allow-busy-background
    python -m orchestrator.cli extract-silhouettes --front private\ninja\front.png --side private\ninja\side.png --output-dir private\ninja\out

Put your character image in a `private` folder first (it is git-ignored). The first run downloads a
179 MB model. Open `private\ninja\out\front_mask.png` and `side_mask.png` and check them by eye.

Changed: orchestrator/settings.py, orchestrator/vision/silhouette.py, orchestrator/vision/validate.py,
orchestrator/cli.py, config.yaml, tests/test_vision.py, README.md, DECISIONS.md.
New: tools/split_turnaround.py, PHASE_9A_CHANGES.md.
