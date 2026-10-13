import os
import json
import math
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

class LandmarkOrderError(ValueError):
    """Raised when left/right landmark ordering violates convention."""
    pass

class UnconfirmedLandmarksError(ValueError):
    """Raised when attempting to measure without user confirmation."""
    pass

def compute_row_span(mask: np.ndarray, y: int) -> int:
    """Computes the horizontal width (span in pixels) of the mask at row y."""
    h, w = mask.shape[:2]
    if y < 0 or y >= h:
        return 0
    row = mask[y, :]
    nonzeros = np.where(row > 0)[0]
    if len(nonzeros) == 0:
        return 0
    return int(nonzeros[-1] - nonzeros[0] + 1)

def compute_measurements(
    landmarks_data: Dict[str, Any],
    front_mask: Optional[np.ndarray] = None,
    side_mask: Optional[np.ndarray] = None,
    height_m: float = 1.75
) -> Dict[str, Any]:
    """
    Converts 2D landmarks and masks into 3D character_spec.json.
    Strictly follows Section 6 conventions.
    """
    if not landmarks_data.get("confirmed", False):
        raise UnconfirmedLandmarksError(
            "Cannot compute measurements: landmarks have not been confirmed by user (confirmed must be true)."
        )

    front = landmarks_data["front"]
    side = landmarks_data["side"]
    warnings: List[str] = []

    # 1. Sanity Check: Left/Right Ordering
    # In front image, character's left is image right (higher x).
    # Character's right is image left (lower x).
    if front["shoulder_L"][0] <= front["shoulder_R"][0]:
        raise LandmarkOrderError(
            f"Left/Right ordering violation: shoulder_L x ({front['shoulder_L'][0]}) "
            f"must be greater than shoulder_R x ({front['shoulder_R'][0]}). "
            "Character's left is on the image's right."
        )

    if front["hip_L"][0] <= front["hip_R"][0]:
        raise LandmarkOrderError(
            f"Left/Right ordering violation: hip_L x ({front['hip_L'][0]}) "
            f"must be greater than hip_R x ({front['hip_R'][0]})."
        )

    if front["wrist_L"][0] <= front["wrist_R"][0]:
        raise LandmarkOrderError(
            f"Left/Right ordering violation: wrist_L x ({front['wrist_L'][0]}) "
            f"must be greater than wrist_R x ({front['wrist_R'][0]})."
        )

    # 2. Sanity Check: Landmarks inside mask
    if front_mask is not None:
        h_f, w_f = front_mask.shape[:2]
        for name, pt in front.items():
            x, y = int(pt[0]), int(pt[1])
            if 0 <= y < h_f and 0 <= x < w_f:
                if front_mask[y, x] == 0:
                    warnings.append(f"Front landmark '{name}' [{x}, {y}] falls outside the silhouette mask.")

    if side_mask is not None:
        h_s, w_s = side_mask.shape[:2]
        for name, pt in side.items():
            x, y = int(pt[0]), int(pt[1])
            if 0 <= y < h_s and 0 <= x < w_s:
                if side_mask[y, x] == 0:
                    warnings.append(f"Side landmark '{name}' [{x}, {y}] falls outside the silhouette mask.")

    # 3. Ground line and total height calculation
    # Feet rest on Z = 0
    if front_mask is not None:
        y_indices_f = np.where(front_mask > 0)[0]
        ground_y_front = int(np.max(y_indices_f)) if len(y_indices_f) > 0 else max(front["toe_L"][1], front["toe_R"][1])
        top_y_front = int(np.min(y_indices_f)) if len(y_indices_f) > 0 else front["head_top"][1]
        char_height_px_front = max(1, ground_y_front - top_y_front + 1)
    else:
        ground_y_front = max(front["toe_L"][1], front["toe_R"][1], front["ankle_L"][1], front["ankle_R"][1])
        top_y_front = front["head_top"][1]
        char_height_px_front = max(1, ground_y_front - top_y_front + 1)

    if side_mask is not None:
        y_indices_s = np.where(side_mask > 0)[0]
        ground_y_side = int(np.max(y_indices_s)) if len(y_indices_s) > 0 else max(side["toe"][1], side["heel"][1])
        top_y_side = int(np.min(y_indices_s)) if len(y_indices_s) > 0 else side["head_top"][1]
        char_height_px_side = max(1, ground_y_side - top_y_side + 1)
    else:
        ground_y_side = max(side.get("toe", [0, 0])[1], side.get("heel", [0, 0])[1], side["ankle"][1])
        top_y_side = side["head_top"][1]
        char_height_px_side = max(1, ground_y_side - top_y_side + 1)

    # Use average or front character height
    char_height_px = (char_height_px_front + char_height_px_side) / 2.0
    scale = height_m / char_height_px

    # Symmetry and limb length sanity check
    arm_len_L = math.dist(front["shoulder_L"], front["elbow_L"]) + math.dist(front["elbow_L"], front["wrist_L"])
    arm_len_R = math.dist(front["shoulder_R"], front["elbow_R"]) + math.dist(front["elbow_R"], front["wrist_R"])
    if arm_len_L <= 0 or arm_len_R <= 0:
        raise ValueError("Calculated arm lengths must be positive")
    arm_sym_diff = abs(arm_len_L - arm_len_R) / max(arm_len_L, arm_len_R)
    if arm_sym_diff > 0.10:
        warnings.append(f"Arm length asymmetry is {arm_sym_diff*100:.1f}% (exceeds 10%).")

    leg_len_L = math.dist(front["hip_L"], front["knee_L"]) + math.dist(front["knee_L"], front["ankle_L"])
    leg_len_R = math.dist(front["hip_R"], front["knee_R"]) + math.dist(front["knee_R"], front["ankle_R"])
    if leg_len_L <= 0 or leg_len_R <= 0:
        raise ValueError("Calculated leg lengths must be positive")
    leg_sym_diff = abs(leg_len_L - leg_len_R) / max(leg_len_L, leg_len_R)
    if leg_sym_diff > 0.10:
        warnings.append(f"Leg length asymmetry is {leg_sym_diff*100:.1f}% (exceeds 10%).")

    # Front center X (midpoint between shoulders or hips)
    center_x_front = (front["shoulder_L"][0] + front["shoulder_R"][0]) / 2.0

    # Side center X (character's body center axis in side view)
    center_x_side = (side["shoulder"][0] + side["hip"][0]) / 2.0

    # Z-agreement check for shared landmarks
    shared_landmarks = [
        ("head_top", front["head_top"], side["head_top"]),
        ("chin", front["chin"], side["chin"]),
        ("neck_base", front["neck_base"], side["neck_base"]),
        ("shoulder", front["shoulder_L"], side["shoulder"]),
        ("hip", front["hip_L"], side["hip"]),
        ("knee", front["knee_L"], side["knee"]),
        ("ankle", front["ankle_L"], side["ankle"]),
    ]
    for name, pt_f, pt_s in shared_landmarks:
        z_f = (ground_y_front - pt_f[1]) * scale
        z_s = (ground_y_side - pt_s[1]) * scale
        z_diff = abs(z_f - z_s)
        if z_diff / height_m > 0.03:
            warnings.append(
                f"Z discrepancy for '{name}': front={z_f:.3f}m, side={z_s:.3f}m "
                f"(diff {z_diff:.3f}m > 3% of height)."
            )

    # 4. Compute 3D Joint positions in meters
    joints: Dict[str, List[float]] = {}

    def pt_3d(img_pt_f, side_x, side_y=None):
        # image x -> world X
        # side x -> world -Y (character faces right, so front is -Y)
        # ground - image y -> world Z
        wx = (img_pt_f[0] - center_x_front) * scale
        # If side_x is specified: offset relative to side center
        wy = - (side_x - center_x_side) * scale
        wz = (ground_y_front - img_pt_f[1]) * scale
        return [round(float(wx), 4), round(float(wy), 4), round(float(wz), 4)]

    # Central joints
    joints["head_top"] = [0.0, round(- (side["head_top"][0] - center_x_side) * scale, 4), round((ground_y_front - front["head_top"][1]) * scale, 4)]
    joints["chin"] = [0.0, round(- (side["chin"][0] - center_x_side) * scale, 4), round((ground_y_front - front["chin"][1]) * scale, 4)]
    joints["neck_base"] = [0.0, round(- (side["neck_base"][0] - center_x_side) * scale, 4), round((ground_y_front - front["neck_base"][1]) * scale, 4)]
    joints["crotch"] = [0.0, round(- (side["hip"][0] - center_x_side) * scale, 4), round((ground_y_front - front["crotch"][1]) * scale, 4)]

    # Limbs
    # Shoulders
    sh_y = side["shoulder"][0]
    joints["shoulder_L"] = pt_3d(front["shoulder_L"], sh_y)
    joints["shoulder_R"] = pt_3d(front["shoulder_R"], sh_y)

    el_y = side.get("elbow", [sh_y, 0])[0]
    joints["elbow_L"] = pt_3d(front["elbow_L"], el_y)
    joints["elbow_R"] = pt_3d(front["elbow_R"], el_y)

    wr_y = side.get("wrist", [sh_y, 0])[0]
    joints["wrist_L"] = pt_3d(front["wrist_L"], wr_y)
    joints["wrist_R"] = pt_3d(front["wrist_R"], wr_y)

    ht_y = wr_y
    if "hand_tip_L" in front:
        joints["hand_tip_L"] = pt_3d(front["hand_tip_L"], ht_y)
    if "hand_tip_R" in front:
        joints["hand_tip_R"] = pt_3d(front["hand_tip_R"], ht_y)

    hip_y = side["hip"][0]
    joints["hip_L"] = pt_3d(front["hip_L"], hip_y)
    joints["hip_R"] = pt_3d(front["hip_R"], hip_y)

    kn_y = side.get("knee", [hip_y, 0])[0]
    joints["knee_L"] = pt_3d(front["knee_L"], kn_y)
    joints["knee_R"] = pt_3d(front["knee_R"], kn_y)

    ank_y = side.get("ankle", [hip_y, 0])[0]
    joints["ankle_L"] = pt_3d(front["ankle_L"], ank_y)
    joints["ankle_R"] = pt_3d(front["ankle_R"], ank_y)

    toe_y = side.get("toe", [ank_y, 0])[0]
    joints["toe_L"] = pt_3d(front["toe_L"], toe_y)
    joints["toe_R"] = pt_3d(front["toe_R"], toe_y)

    # 5. Compute Widths and Depths
    # Default widths from joints if masks are absent
    sh_w_landmark = abs(front["shoulder_L"][0] - front["shoulder_R"][0]) * scale
    hip_w_landmark = abs(front["hip_L"][0] - front["hip_R"][0]) * scale

    if front_mask is not None:
        sh_row_y = int((front["shoulder_L"][1] + front["shoulder_R"][1]) / 2.0)
        hip_row_y = int((front["hip_L"][1] + front["hip_R"][1]) / 2.0)
        chest_row_y = int(front["neck_base"][1] + 0.35 * (front["crotch"][1] - front["neck_base"][1]))
        waist_row_y = int(front["neck_base"][1] + 0.65 * (front["crotch"][1] - front["neck_base"][1]))

        sh_w = max(sh_w_landmark, compute_row_span(front_mask, sh_row_y) * scale)
        hip_w = max(hip_w_landmark, compute_row_span(front_mask, hip_row_y) * scale)
        chest_w = compute_row_span(front_mask, chest_row_y) * scale
        waist_w = compute_row_span(front_mask, waist_row_y) * scale
    else:
        sh_w = sh_w_landmark
        hip_w = hip_w_landmark
        chest_w = sh_w * 0.85
        waist_w = hip_w * 0.8

    widths = {
        "shoulder_width": round(float(sh_w), 4),
        "chest_width": round(float(chest_w), 4),
        "waist_width": round(float(waist_w), 4),
        "hip_width": round(float(hip_w), 4)
    }

    if side_mask is not None:
        head_row_y = int((side["head_top"][1] + side["chin"][1]) / 2.0)
        sh_row_y = int(side["shoulder"][1])
        hip_row_y = int(side["hip"][1])
        chest_row_y = int(side["neck_base"][1] + 0.35 * (side["hip"][1] - side["neck_base"][1]))

        head_d = compute_row_span(side_mask, head_row_y) * scale
        chest_d = compute_row_span(side_mask, chest_row_y) * scale
        hip_d = compute_row_span(side_mask, hip_row_y) * scale
    else:
        head_d = 0.22
        chest_d = 0.24
        hip_d = 0.22

    depths = {
        "head_depth": round(float(head_d), 4),
        "chest_depth": round(float(chest_d), 4),
        "hip_depth": round(float(hip_d), 4)
    }

    spec = {
        "version": 1,
        "units": "m",
        "height_m": round(float(height_m), 4),
        "joints": joints,
        "widths": widths,
        "depths": depths,
        "warnings": warnings
    }
    return spec
