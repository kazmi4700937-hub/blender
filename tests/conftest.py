"""Shared pytest setup.

- Runs every test from the project root, because the tests use relative paths
  such as assets/test_images/front.png.
- Provides the `blender_exe` fixture. Tests that start Blender are skipped, with a
  clear message, when Blender cannot be found. Set the BLENDER_EXE environment
  variable to the Blender program, or edit paths.blender_exe in config.yaml.
- Skips the tests that need the generated reference images when those images do not
  exist yet, and says how to create them.
"""

import os
from pathlib import Path

import pytest

from orchestrator.settings import PROJECT_ROOT, get_blender_exe

TEST_IMAGES = Path("assets/test_images")
NEEDS_TEST_IMAGES = {
    "test_measure.py": None,  # every test in the file
    "test_vision.py": {"test_rendered_reference_images"},
}


@pytest.fixture(autouse=True, scope="session")
def _run_from_project_root():
    previous = os.getcwd()
    os.chdir(PROJECT_ROOT)
    yield
    os.chdir(previous)


@pytest.fixture(scope="session")
def blender_exe():
    exe = get_blender_exe()
    if not exe:
        pytest.skip(
            "Blender was not found. Set the BLENDER_EXE environment variable to the Blender "
            "program (for example the blender.exe of Blender 4.2 LTS) and run again."
        )
    return exe


def pytest_collection_modifyitems(config, items):
    images_ready = (PROJECT_ROOT / TEST_IMAGES / "front.png").is_file() and (
        PROJECT_ROOT / TEST_IMAGES / "ground_truth_landmarks.json"
    ).is_file()
    if images_ready:
        return
    skip_marker = pytest.mark.skip(
        reason=(
            "assets/test_images/ has not been generated. Run: python tools/run_all_tests.py "
            "(it renders the reference images first), or run "
            "tools/render_test_reference_images.py inside Blender."
        )
    )
    for item in items:
        file_name = Path(str(item.fspath)).name
        if file_name in NEEDS_TEST_IMAGES:
            only = NEEDS_TEST_IMAGES[file_name]
            if only is None or item.name in only:
                item.add_marker(skip_marker)
