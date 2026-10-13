import pytest
import json
import os
import math
import numpy as np

from orchestrator.measure.measure import (
    compute_measurements,
    UnconfirmedLandmarksError,
    LandmarkOrderError
)
from orchestrator.vision.silhouette import extract_silhouette_mask
from orchestrator.vision.overlay import draw_landmarks_overlay

def test_round_trip_measurement():
    """Acceptance test 1: Round-trip test against rendered template body."""
    landmarks_file = "assets/test_images/ground_truth_landmarks.json"
    expected_spec_file = "assets/test_images/expected_character_spec.json"
    front_img_file = "assets/test_images/front.png"
    side_img_file = "assets/test_images/side.png"

    with open(landmarks_file, "r", encoding="utf-8") as f:
        landmarks_data = json.load(f)

    with open(expected_spec_file, "r", encoding="utf-8") as f:
        expected_spec = json.load(f)

    front_res = extract_silhouette_mask(front_img_file)
    side_res = extract_silhouette_mask(side_img_file)

    target_height = expected_spec["height_m"]
    computed_spec = compute_measurements(
        landmarks_data,
        front_mask=front_res["mask"],
        side_mask=side_res["mask"],
        height_m=target_height
    )

    # 1. Height match within 3%
    assert abs(computed_spec["height_m"] - target_height) / target_height < 0.03

    # 2. Shoulder width match within 3%
    exp_sh_L = expected_spec["joints"]["shoulder_L"]
    exp_sh_R = expected_spec["joints"]["shoulder_R"]
    exp_sh_width = abs(exp_sh_L[0] - exp_sh_R[0])
    comp_sh_width = abs(computed_spec["joints"]["shoulder_L"][0] - computed_spec["joints"]["shoulder_R"][0])
    diff_sh = abs(comp_sh_width - exp_sh_width) / exp_sh_width
    assert diff_sh < 0.03, f"Shoulder width diff {diff_sh*100:.2f}% exceeds 3%"

    # 3. Arm length match within 3%
    exp_el_L = expected_spec["joints"]["elbow_L"]
    exp_wr_L = expected_spec["joints"]["wrist_L"]
    exp_arm_len = math.dist(exp_sh_L, exp_el_L) + math.dist(exp_el_L, exp_wr_L)

    comp_sh_L = computed_spec["joints"]["shoulder_L"]
    comp_el_L = computed_spec["joints"]["elbow_L"]
    comp_wr_L = computed_spec["joints"]["wrist_L"]
    comp_arm_len = math.dist(comp_sh_L, comp_el_L) + math.dist(comp_el_L, comp_wr_L)
    diff_arm = abs(comp_arm_len - exp_arm_len) / exp_arm_len
    assert diff_arm < 0.03, f"Arm length diff {diff_arm*100:.2f}% exceeds 3%"

    # 4. Leg length match within 3%
    exp_hip_L = expected_spec["joints"]["hip_L"]
    exp_kn_L = expected_spec["joints"]["knee_L"]
    exp_ank_L = expected_spec["joints"]["ankle_L"]
    exp_leg_len = math.dist(exp_hip_L, exp_kn_L) + math.dist(exp_kn_L, exp_ank_L)

    comp_hip_L = computed_spec["joints"]["hip_L"]
    comp_kn_L = computed_spec["joints"]["knee_L"]
    comp_ank_L = computed_spec["joints"]["ankle_L"]
    comp_leg_len = math.dist(comp_hip_L, comp_kn_L) + math.dist(comp_kn_L, comp_ank_L)
    diff_leg = abs(comp_leg_len - exp_leg_len) / exp_leg_len
    assert diff_leg < 0.03, f"Leg length diff {diff_leg*100:.2f}% exceeds 3%"


def test_pipeline_refuses_unconfirmed_landmarks():
    """Acceptance test 2: pipeline refuses to continue when confirmed is false."""
    landmarks_file = "assets/test_images/ground_truth_landmarks.json"
    with open(landmarks_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["confirmed"] = False

    with pytest.raises(UnconfirmedLandmarksError) as exc_info:
        compute_measurements(data)
    assert "landmarks have not been confirmed" in str(exc_info.value)


def test_swapped_left_right_detected():
    """Acceptance test 3: swapping left and right landmarks is detected by sanity check."""
    landmarks_file = "assets/test_images/ground_truth_landmarks.json"
    with open(landmarks_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Swap shoulder_L and shoulder_R
    data["front"]["shoulder_L"], data["front"]["shoulder_R"] = (
        data["front"]["shoulder_R"],
        data["front"]["shoulder_L"]
    )

    with pytest.raises(LandmarkOrderError) as exc_info:
        compute_measurements(data)
    assert "Left/Right ordering violation" in str(exc_info.value)


def test_overlay_generation(tmp_path):
    """Verifies overlay generation works cleanly and creates image."""
    landmarks_file = "assets/test_images/ground_truth_landmarks.json"
    with open(landmarks_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    out_front = str(tmp_path / "front_overlay.png")
    out_side = str(tmp_path / "side_overlay.png")

    img_f = draw_landmarks_overlay("assets/test_images/front.png", data["front"], view="front", output_path=out_front)
    img_s = draw_landmarks_overlay("assets/test_images/side.png", data["side"], view="side", output_path=out_side)

    assert os.path.exists(out_front)
    assert os.path.exists(out_side)
    assert img_f.shape == (1024, 1024, 3)
    assert img_s.shape == (1024, 1024, 3)
