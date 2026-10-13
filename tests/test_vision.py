import pytest
import numpy as np
import cv2
from PIL import Image
import os

from orchestrator.vision.validate import (
    validate_input_images,
    detect_background_type,
    ImageValidationError
)
from orchestrator.vision.silhouette import extract_silhouette_mask

def create_synthetic_humanoid(height=400, bg="black", img_size=(512, 512)):
    """Creates a synthetic humanoid figure on a given background."""
    w, h = img_size
    if bg == "transparent":
        img_arr = np.zeros((h, w, 4), dtype=np.uint8)
        color = (255, 255, 255, 255)
    elif bg == "black":
        img_arr = np.zeros((h, w, 3), dtype=np.uint8)
        color = (255, 255, 255)
    elif bg == "white":
        img_arr = np.ones((h, w, 3), dtype=np.uint8) * 255
        color = (50, 50, 50)
    elif bg == "busy":
        # Random noise background with high variance
        np.random.seed(42)
        img_arr = np.random.randint(0, 256, (h, w, 3), dtype=np.uint8)
        color = (255, 255, 255)
    else:
        raise ValueError(f"Unknown bg: {bg}")

    # Draw humanoid figure with known dimensions:
    # Head top at y = 50, Feet at y = 450 (total height = 401 px)
    top_y = 50
    head_r = 30
    head_center = (w // 2, top_y + head_r)
    cv2.circle(img_arr, head_center, head_r, color, -1)
    
    # Torso
    torso_top = top_y + 2 * head_r
    torso_bottom = torso_top + 160
    cv2.rectangle(img_arr, (w // 2 - 40, torso_top), (w // 2 + 40, torso_bottom), color, -1)
    
    # Arms (T-pose)
    arm_top = torso_top + 10
    arm_bottom = arm_top + 30
    cv2.rectangle(img_arr, (w // 2 - 140, arm_top), (w // 2 + 140, arm_bottom), color, -1)
    
    # Legs down to y = 450
    leg_bottom = top_y + height
    cv2.rectangle(img_arr, (w // 2 - 35, torso_bottom), (w // 2 - 10, leg_bottom), color, -1)
    cv2.rectangle(img_arr, (w // 2 + 10, torso_bottom), (w // 2 + 35, leg_bottom), color, -1)
    
    return Image.fromarray(img_arr), (top_y, leg_bottom, height + 1)


def test_synthetic_mask_accuracy(tmp_path):
    """Acceptance test 1: mask matches synthetic shape within 1% of pixels and height within 2px."""
    height = 400
    img, (top_y, bottom_y, expected_height) = create_synthetic_humanoid(height=height, bg="black")
    img_path = str(tmp_path / "synthetic_humanoid.png")
    mask_out_path = str(tmp_path / "mask_out.png")
    img.save(img_path)

    res = extract_silhouette_mask(img_path, output_mask_path=mask_out_path)
    mask = res["mask"]
    
    # Ground truth mask (white figure is > 0 in grayscale)
    gray = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
    gt_mask = (gray > 128).astype(np.uint8) * 255
    
    # Pixel mismatch ratio
    diff_pixels = np.count_nonzero(mask != gt_mask)
    total_pixels = mask.size
    mismatch_ratio = diff_pixels / total_pixels
    
    assert mismatch_ratio < 0.01, f"Mismatch ratio {mismatch_ratio:.4f} exceeds 1%"
    assert abs(res["height_px"] - expected_height) <= 2, f"Height {res['height_px']} vs expected {expected_height}"
    assert os.path.exists(mask_out_path)


def test_mismatched_heights_fail(tmp_path):
    """Acceptance test 2a: images with mismatched heights fail with readable message."""
    front_img, _ = create_synthetic_humanoid(height=400, bg="black", img_size=(512, 512))
    side_img, _ = create_synthetic_humanoid(height=300, bg="black", img_size=(512, 650))
    
    front_path = str(tmp_path / "front.png")
    side_path = str(tmp_path / "side.png")
    front_img.save(front_path)
    side_img.save(side_path)

    with pytest.raises(ImageValidationError) as exc_info:
        validate_input_images(front_path, side_path)
    assert "Image heights do not match" in str(exc_info.value)


def test_busy_background_fails(tmp_path):
    """Acceptance test 2b: busy background fails with readable message."""
    front_img, _ = create_synthetic_humanoid(height=400, bg="busy", img_size=(512, 512))
    side_img, _ = create_synthetic_humanoid(height=400, bg="black", img_size=(512, 512))
    
    front_path = str(tmp_path / "front_busy.png")
    side_path = str(tmp_path / "side.png")
    front_img.save(front_path)
    side_img.save(side_path)

    with pytest.raises(ImageValidationError) as exc_info:
        validate_input_images(front_path, side_path)
    assert "busy or non-uniform background" in str(exc_info.value)


def test_transparent_and_flat_backgrounds(tmp_path):
    """Verifies transparent and flat solid white/black backgrounds work seamlessly."""
    trans_img, _ = create_synthetic_humanoid(height=400, bg="transparent")
    trans_path = str(tmp_path / "trans.png")
    trans_img.save(trans_path)
    
    res = extract_silhouette_mask(trans_path)
    assert res["height_px"] > 390
    
    white_img, _ = create_synthetic_humanoid(height=400, bg="white")
    white_path = str(tmp_path / "white.png")
    white_img.save(white_path)
    
    res_white = extract_silhouette_mask(white_path)
    assert res_white["height_px"] > 390


def test_rendered_reference_images():
    """Validates the rendered reference images from base character."""
    front_path = "assets/test_images/front.png"
    side_path = "assets/test_images/side.png"
    
    val = validate_input_images(front_path, side_path)
    assert val["front"]["size"] == [1024, 1024]
    assert val["side"]["size"] == [1024, 1024]
    assert val["front"]["background"]["type"] in ("transparent", "flat")
    assert val["side"]["background"]["type"] in ("transparent", "flat")

    front_mask = extract_silhouette_mask(front_path)
    side_mask = extract_silhouette_mask(side_path)

    assert front_mask["height_px"] > 800
    assert side_mask["height_px"] > 800
    # Heights should match within 2%
    diff_ratio = abs(front_mask["height_px"] - side_mask["height_px"]) / front_mask["height_px"]
    assert diff_ratio < 0.02



def test_busy_background_allowed_with_flag(tmp_path):
    """With allow_busy_background=True a busy image passes and a warning is returned."""
    front_img, _ = create_synthetic_humanoid(height=400, bg="busy", img_size=(512, 512))
    side_img, _ = create_synthetic_humanoid(height=400, bg="black", img_size=(512, 512))
    front_path = str(tmp_path / "front_busy.png")
    side_path = str(tmp_path / "side.png")
    front_img.save(front_path)
    side_img.save(side_path)

    res = validate_input_images(front_path, side_path, allow_busy_background=True)
    assert len(res["warnings"]) == 1
    assert "Front" in res["warnings"][0]


def test_segmentation_model_setting(monkeypatch):
    """SEGMENTATION_MODEL overrides config.yaml, which overrides the built-in default."""
    from orchestrator.settings import get_segmentation_model, FALLBACK_SEGMENTATION_MODEL

    monkeypatch.delenv("SEGMENTATION_MODEL", raising=False)
    assert get_segmentation_model({}) == FALLBACK_SEGMENTATION_MODEL
    assert get_segmentation_model({"vision": {"segmentation_model": "u2net"}}) == "u2net"
    monkeypatch.setenv("SEGMENTATION_MODEL", "u2netp")
    assert get_segmentation_model({"vision": {"segmentation_model": "u2net"}}) == "u2netp"


def test_busy_background_uses_configured_rembg_model(tmp_path, monkeypatch):
    """A busy-background image goes to rembg, with a session made from the configured model."""
    import sys
    import types
    import numpy as np
    from PIL import Image
    from orchestrator.vision import silhouette

    calls = {}

    def fake_new_session(name):
        calls["model"] = name
        return "session"

    def fake_remove(img, session=None):
        calls["session"] = session
        arr = np.zeros((img.height, img.width, 4), dtype=np.uint8)
        arr[100:300, 200:300] = 255  # a white block counts as the character
        return Image.fromarray(arr, "RGBA")

    fake = types.SimpleNamespace(new_session=fake_new_session, remove=fake_remove)
    monkeypatch.setitem(sys.modules, "rembg", fake)
    monkeypatch.setenv("SEGMENTATION_MODEL", "test-seg-model")
    silhouette._SESSIONS.clear()

    img, _ = create_synthetic_humanoid(height=400, bg="busy", img_size=(512, 512))
    path = str(tmp_path / "busy.png")
    img.save(path)
    res = silhouette.extract_silhouette_mask(path)

    assert calls["model"] == "test-seg-model"
    assert calls["session"] == "session"
    assert res["height_px"] == 200
    silhouette._SESSIONS.clear()
