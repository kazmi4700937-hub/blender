import os
from typing import Tuple, Dict, Any, Optional
import numpy as np
import cv2
from PIL import Image

from .validate import detect_background_type

def extract_silhouette_mask(
    image_path: str,
    output_mask_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Extracts a binary silhouette mask (0 or 255) from an image.
    Uses alpha channel if present, color distance thresholding for flat solid backgrounds,
    or rembg as fallback. Keeps the largest connected component.
    Computes bounding box, total character height in px, and ground line.
    """
    img = Image.open(image_path)
    bg_info = detect_background_type(img)
    arr = np.array(img)
    
    if bg_info["type"] == "transparent":
        # Extract from alpha channel
        alpha = arr[:, :, 3] if arr.ndim == 3 else arr[:, :, 1]
        raw_mask = (alpha > 128).astype(np.uint8) * 255
    elif bg_info["type"] == "flat":
        # Threshold against flat background color
        rgb = arr[:, :, :3] if arr.ndim == 3 else np.stack([arr]*3, axis=-1)
        bg_col = np.array(bg_info["bg_color"], dtype=np.float32)
        # Euclidean color distance
        diff = np.linalg.norm(rgb.astype(np.float32) - bg_col, axis=-1)
        # Threshold: if diff > 25, it's character
        raw_mask = (diff > 25.0).astype(np.uint8) * 255
    else:
        # Fallback to rembg (imported here so images with an alpha channel or a flat
        # background work even when rembg is not installed)
        try:
            import rembg
        except ImportError as exc:
            raise RuntimeError(
                "This image needs background removal, which requires the 'rembg' package. "
                "Install it with: pip install rembg onnxruntime"
            ) from exc
        no_bg = rembg.remove(img)
        no_bg_arr = np.array(no_bg)
        alpha = no_bg_arr[:, :, 3]
        raw_mask = (alpha > 128).astype(np.uint8) * 255

    # Morphological clean up to remove small pinhole noise and soften anti-aliasing
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    cleaned = cv2.morphologyEx(raw_mask, cv2.MORPH_OPEN, kernel)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel)

    # Keep only the largest connected component (removes stray floating artifacts)
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(cleaned, connectivity=8)
    if num_labels > 1:
        # stat[cv2.CC_STAT_AREA]: index 0 is background
        areas = stats[1:, cv2.CC_STAT_AREA]
        largest_label = 1 + np.argmax(areas)
        mask = (labels == largest_label).astype(np.uint8) * 255
    else:
        mask = cleaned

    # Compute bounding box, height, ground line
    y_indices, x_indices = np.where(mask > 0)
    if len(y_indices) == 0:
        min_x, max_x, min_y, max_y = 0, 0, 0, 0
        height_px = 0
        ground_y = 0
    else:
        min_x = int(np.min(x_indices))
        max_x = int(np.max(x_indices))
        min_y = int(np.min(y_indices))
        max_y = int(np.max(y_indices))
        height_px = int(max_y - min_y + 1)
        ground_y = int(max_y)

    # Save mask PNG if requested
    if output_mask_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_mask_path)), exist_ok=True)
        cv2.imwrite(output_mask_path, mask)

    return {
        "mask": mask,
        "bbox": [min_x, min_y, max_x, max_y],
        "height_px": height_px,
        "ground_y": ground_y,
        "mask_path": output_mask_path
    }
