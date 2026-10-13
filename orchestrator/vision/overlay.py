import os
from typing import Dict, Any, List, Tuple, Optional
import cv2
import numpy as np
from PIL import Image

FRONT_CONNECTIONS = [
    ("head_top", "chin"),
    ("chin", "neck_base"),
    ("neck_base", "shoulder_L"),
    ("neck_base", "shoulder_R"),
    ("shoulder_L", "elbow_L"),
    ("elbow_L", "wrist_L"),
    ("wrist_L", "hand_tip_L"),
    ("shoulder_R", "elbow_R"),
    ("elbow_R", "wrist_R"),
    ("wrist_R", "hand_tip_R"),
    ("neck_base", "crotch"),
    ("crotch", "hip_L"),
    ("crotch", "hip_R"),
    ("hip_L", "knee_L"),
    ("knee_L", "ankle_L"),
    ("ankle_L", "toe_L"),
    ("hip_R", "knee_R"),
    ("knee_R", "ankle_R"),
    ("ankle_R", "toe_R")
]

SIDE_CONNECTIONS = [
    ("head_top", "nose_tip"),
    ("nose_tip", "chin"),
    ("chin", "neck_base"),
    ("neck_base", "shoulder"),
    ("shoulder", "elbow"),
    ("elbow", "wrist"),
    ("neck_base", "chest_front"),
    ("chest_front", "belly_front"),
    ("neck_base", "chest_back"),
    ("chest_back", "belly_back"),
    ("belly_back", "buttock_back"),
    ("buttock_back", "hip"),
    ("hip", "knee"),
    ("knee", "ankle"),
    ("ankle", "heel"),
    ("ankle", "toe")
]

def draw_landmarks_overlay(
    image_path: str,
    landmarks: Dict[str, List[int]],
    view: str = "front",
    output_path: Optional[str] = None
) -> np.ndarray:
    """
    Draws landmarks, skeleton connections, and labels onto the image.
    Saves the overlay to output_path if provided.
    """
    img = Image.open(image_path).convert("RGB")
    cv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    connections = FRONT_CONNECTIONS if view == "front" else SIDE_CONNECTIONS

    # Draw connection lines
    for p1_name, p2_name in connections:
        if p1_name in landmarks and p2_name in landmarks:
            pt1 = tuple(landmarks[p1_name])
            pt2 = tuple(landmarks[p2_name])
            cv2.line(cv_img, pt1, pt2, (0, 255, 255), 2, cv2.LINE_AA)

    # Draw landmark dots and labels
    for name, pt in landmarks.items():
        x, y = int(pt[0]), int(pt[1])
        # Color coding: cyan for _L, magenta for _R, green for center/side
        if name.endswith("_L"):
            color = (255, 255, 0)   # Cyan in BGR
        elif name.endswith("_R"):
            color = (255, 0, 255)   # Magenta in BGR
        else:
            color = (0, 255, 0)     # Green in BGR

        cv2.circle(cv_img, (x, y), 5, color, -1, cv2.LINE_AA)
        cv2.circle(cv_img, (x, y), 6, (0, 0, 0), 1, cv2.LINE_AA)

        # Label
        cv2.putText(
            cv_img,
            name,
            (x + 7, y + 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (0, 0, 0),
            2,
            cv2.LINE_AA
        )
        cv2.putText(
            cv_img,
            name,
            (x + 7, y + 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (255, 255, 255),
            1,
            cv2.LINE_AA
        )

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        cv2.imwrite(output_path, cv_img)

    return cv_img
