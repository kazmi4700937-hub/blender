import os
import json
import base64
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

FRONT_LANDMARK_NAMES = [
    "head_top", "chin", "eye_L", "eye_R", "neck_base",
    "shoulder_L", "shoulder_R", "elbow_L", "elbow_R",
    "wrist_L", "wrist_R", "hand_tip_L", "hand_tip_R",
    "hip_L", "hip_R", "knee_L", "knee_R",
    "ankle_L", "ankle_R", "toe_L", "toe_R", "crotch"
]

SIDE_LANDMARK_NAMES = [
    "head_top", "chin", "nose_tip", "neck_base",
    "shoulder", "elbow", "wrist",
    "hip", "knee", "ankle", "toe", "heel",
    "chest_front", "chest_back", "belly_front", "belly_back", "buttock_back"
]

def validate_landmarks_json(data: Dict[str, Any]) -> None:
    """Validates landmarks data against Section 7.1 specification."""
    if not isinstance(data, dict):
        raise ValueError("Landmarks data must be a JSON object")
    if data.get("version") != 1:
        raise ValueError(f"Expected version 1, got {data.get('version')}")
    if "front" not in data or "side" not in data:
        raise ValueError("Landmarks data must contain 'front' and 'side' keys")
    if not isinstance(data.get("confirmed"), bool):
        raise ValueError("'confirmed' field must be a boolean")

    for k in ["shoulder_L", "shoulder_R", "hip_L", "hip_R", "head_top"]:
        if k not in data["front"]:
            raise ValueError(f"Missing essential front landmark: {k}")

    for k in ["head_top", "shoulder", "hip", "ankle"]:
        if k not in data["side"]:
            raise ValueError(f"Missing essential side landmark: {k}")

def encode_image_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def propose_landmarks_vlm(
    front_image_path: str,
    side_image_path: str,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calls Anthropic Claude vision model to propose landmarks for front and side views.
    Returns the parsed and validated landmarks dictionary with confirmed=False.
    """
    import anthropic
    from PIL import Image

    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")

    from ..settings import get_model_name
    model = model_name or get_model_name()

    front_img = Image.open(front_image_path)
    side_img = Image.open(side_image_path)
    w_front, h_front = front_img.size
    w_side, h_side = side_img.size

    client = anthropic.Anthropic(api_key=api_key)

    front_b64 = encode_image_base64(front_image_path)
    side_b64 = encode_image_base64(side_image_path)

    system_prompt = (
        "You are an expert 3D computer vision and rigging specialist. "
        "Your task is to detect precise anatomical joint and landmark positions in pixels on humanoid character reference images. "
        "Strictly follow the coordinate system: pixel coordinates [x, y] with [0,0] at the top-left, x to the right, y downward. "
        "Important Left/Right rule: the character's left (_L) is on the right side of the front image (higher x). "
        "The character's right (_R) is on the left side of the front image (lower x). "
        "Return ONLY raw JSON with no markdown formatting or commentary."
    )

    user_prompt = f"""Given these two images:
Image 1: Front T-pose view (size {w_front}x{h_front}).
Image 2: Side view facing right (size {w_side}x{h_side}).

Return a JSON object conforming exactly to this structure:
{{
  "version": 1,
  "image_size": {{
    "front": [{w_front}, {h_front}],
    "side": [{w_side}, {h_side}]
  }},
  "front": {{
    "head_top": [x, y],
    "chin": [x, y],
    "eye_L": [x, y],
    "eye_R": [x, y],
    "neck_base": [x, y],
    "shoulder_L": [x, y],
    "shoulder_R": [x, y],
    "elbow_L": [x, y],
    "elbow_R": [x, y],
    "wrist_L": [x, y],
    "wrist_R": [x, y],
    "hand_tip_L": [x, y],
    "hand_tip_R": [x, y],
    "hip_L": [x, y],
    "hip_R": [x, y],
    "knee_L": [x, y],
    "knee_R": [x, y],
    "ankle_L": [x, y],
    "ankle_R": [x, y],
    "toe_L": [x, y],
    "toe_R": [x, y],
    "crotch": [x, y]
  }},
  "side": {{
    "head_top": [x, y],
    "chin": [x, y],
    "nose_tip": [x, y],
    "neck_base": [x, y],
    "shoulder": [x, y],
    "elbow": [x, y],
    "wrist": [x, y],
    "hip": [x, y],
    "knee": [x, y],
    "ankle": [x, y],
    "toe": [x, y],
    "heel": [x, y],
    "chest_front": [x, y],
    "chest_back": [x, y],
    "belly_front": [x, y],
    "belly_back": [x, y],
    "buttock_back": [x, y]
  }},
  "source": "vlm_proposed",
  "confirmed": false
}}"""

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Front view:"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": front_b64
                        }
                    },
                    {"type": "text", "text": "Side view:"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": side_b64
                        }
                    },
                    {"type": "text", "text": user_prompt}
                ]
            }
        ]
    )

    resp_text = response.content[0].text.strip()
    if resp_text.startswith("```json"):
        resp_text = resp_text[7:]
    if resp_text.startswith("```"):
        resp_text = resp_text[3:]
    if resp_text.endswith("```"):
        resp_text = resp_text[:-3]
    resp_text = resp_text.strip()

    data = json.loads(resp_text)
    validate_landmarks_json(data)
    return data
