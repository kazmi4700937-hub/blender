import os
from typing import Tuple, Dict, Any, Optional
import numpy as np
from PIL import Image

class ImageValidationError(Exception):
    """Raised when an input image violates requirements."""
    pass

def check_image_exists(path: str, view_name: str) -> None:
    if not path or not os.path.exists(path):
        raise ImageValidationError(f"{view_name} image does not exist: '{path}'")

def detect_background_type(img: Image.Image) -> Dict[str, Any]:
    """
    Determines if the image has a transparent background, a flat solid background,
    or a busy/unsupported background.
    """
    arr = np.array(img)
    
    # 1. Check for alpha channel
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        alpha = arr[:, :, 3] if arr.ndim == 3 else arr[:, :, 1]
        transparent_ratio = np.mean(alpha < 128)
        # Check if corners are transparent
        corners = [alpha[0, 0], alpha[0, -1], alpha[-1, 0], alpha[-1, -1]]
        if transparent_ratio > 0.05 and any(c < 128 for c in corners):
            return {
                "type": "transparent",
                "transparent_ratio": float(transparent_ratio)
            }
            
    # 2. Check RGB border variance for flat background
    rgb = arr[:, :, :3] if arr.ndim == 3 else np.stack([arr]*3, axis=-1)
    h, w = rgb.shape[:2]
    
    # Sample border pixels (top, left, right borders)
    top_border = rgb[0:max(1, int(h * 0.02)), :]
    left_border = rgb[:, 0:max(1, int(w * 0.02))]
    right_border = rgb[:, -max(1, int(w * 0.02)):]
    
    border_pixels = np.concatenate([
        top_border.reshape(-1, 3),
        left_border.reshape(-1, 3),
        right_border.reshape(-1, 3)
    ], axis=0)
    
    border_std = np.std(border_pixels, axis=0)
    mean_std = float(np.mean(border_std))
    
    # If border color is very consistent (mean std dev < 18.0)
    if mean_std < 18.0:
        bg_color = np.median(border_pixels, axis=0).astype(int).tolist()
        return {
            "type": "flat",
            "bg_color": bg_color,
            "border_std": mean_std
        }
    else:
        return {
            "type": "busy",
            "border_std": mean_std
        }

def validate_input_images(
    front_path: str,
    side_path: str,
    max_height_diff_ratio: float = 0.05,
    allow_busy_background: bool = False,
) -> Dict[str, Any]:
    """
    Validates front and side images according to Section 3 of the specification.
    Returns metadata if valid, otherwise raises ImageValidationError.

    By default a busy or gradient background is rejected (spec Section 3). With
    allow_busy_background=True such an image is accepted and the silhouette step cuts the
    character out with rembg instead. The result then lists a warning for each such view,
    because the cut-out is a model estimate and should be checked on the overlay.
    """
    check_image_exists(front_path, "Front")
    check_image_exists(side_path, "Side")
    
    try:
        front_img = Image.open(front_path)
    except Exception as e:
        raise ImageValidationError(f"Failed to open front image '{front_path}': {e}") from e
        
    try:
        side_img = Image.open(side_path)
    except Exception as e:
        raise ImageValidationError(f"Failed to open side image '{side_path}': {e}") from e

    w_front, h_front = front_img.size
    w_side, h_side = side_img.size
    
    # Check heights match within tolerance
    height_diff = abs(h_front - h_side)
    if height_diff / max(h_front, h_side) > max_height_diff_ratio:
        raise ImageValidationError(
            f"Image heights do not match: front is {h_front}px, side is {h_side}px. "
            f"Both views must be rendered or scaled to the same pixel height."
        )

    # Check backgrounds
    front_bg = detect_background_type(front_img)
    side_bg = detect_background_type(side_img)
    
    warnings = []
    if allow_busy_background:
        for name, bg in (("Front", front_bg), ("Side", side_bg)):
            if bg["type"] == "busy":
                warnings.append(
                    f"{name} image has a busy or gradient background; the silhouette will be "
                    "cut out with rembg. Check the mask before trusting measurements."
                )
    if front_bg["type"] == "busy" and not allow_busy_background:
        raise ImageValidationError(
            f"Front image has a busy or non-uniform background (border variance {front_bg['border_std']:.1f}). "
            "Please use a transparent PNG or a flat solid background."
        )
        
    if side_bg["type"] == "busy" and not allow_busy_background:
        raise ImageValidationError(
            f"Side image has a busy or non-uniform background (border variance {side_bg['border_std']:.1f}). "
            "Please use a transparent PNG or a flat solid background."
        )
        
    return {
        "warnings": warnings,
        "front": {
            "path": front_path,
            "size": [w_front, h_front],
            "background": front_bg
        },
        "side": {
            "path": side_path,
            "size": [w_side, h_side],
            "background": side_bg
        }
    }
