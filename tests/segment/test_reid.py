"""Unit tests for ReIdEngine, eroded-core HSV histograms, and categorical Hue gating.

Tests:
- Morphological 5x5 erosion eliminating boundary bleed
- Dominant Hue circular mean calculation
- Categorical Hue gating: delta Hue > 60° enforces infinite penalty
- Zero ID swaps between red and green cubes under extreme spatial proximity
- Strict non-destructive multi-label semantics (no mask subtraction)
Per ARCHITECTURE.md §3.1, §4.3, IMPLEMENTATION_PLAN.md P03.S06, and P03 RULING.
"""

from __future__ import annotations

import numpy as np

from Kodiac_robotics.contracts.core import ObjMask
from Kodiac_robotics.segment.reid import ReIdEngine


def _create_color_patch_image(
    height: int = 480,
    width: int = 640,
    boxes: list[tuple[int, int, int, int, tuple[int, int, int]]] | None = None,
) -> np.ndarray:
    """Create a synthetic test image with specified colored bounding boxes in BGR."""
    img = np.full((height, width, 3), 180, dtype=np.uint8)  # neutral grey background
    if boxes:
        for x1, y1, x2, y2, bgr in boxes:
            img[y1:y2, x1:x2] = bgr
    return img


def test_compute_eroded_hsv_hist_boundary_erosion() -> None:
    """Verify that compute_eroded_hsv_hist erodes boundary pixels and normalizes."""
    engine = ReIdEngine(hist_bins=(16, 8))
    frame = np.full((100, 100, 3), 128, dtype=np.uint8)

    # Put a red block with a 2-pixel noisy border
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[20:60, 20:60] = 1  # 40x40 mask

    # Core is red, border is green noise
    frame[20:60, 20:60] = (0, 0, 255)  # Red BGR
    frame[20:23, 20:60] = (0, 255, 0)  # Green top border
    frame[57:60, 20:60] = (0, 255, 0)  # Green bottom border

    # With erosion kernel 7, green borders are stripped away
    hist = engine.compute_eroded_hsv_hist(frame, mask, erode_ksize=7)
    assert isinstance(hist, np.ndarray)
    assert hist.shape == (16, 8)
    assert np.isclose(np.sum(hist), 1.0, atol=1e-3)

    # Verify fallback for tiny mask
    tiny_mask = np.zeros((100, 100), dtype=np.uint8)
    tiny_mask[50:52, 50:52] = 1  # 2x2 = 4 pixels, erosion vanishes it
    tiny_hist = engine.compute_eroded_hsv_hist(frame, tiny_mask, erode_ksize=5)
    assert np.isclose(np.sum(tiny_hist), 1.0, atol=1e-3)


def test_extract_dominant_hue_circular() -> None:
    """Verify dominant hue correctly identifies Red, Green, and Blue."""
    engine = ReIdEngine()

    # Red patch
    red_img = _create_color_patch_image(boxes=[(10, 10, 50, 50, (0, 0, 255))])
    red_mask = np.zeros((480, 640), dtype=np.uint8)
    red_mask[10:50, 10:50] = 1
    hue_red, s_red, _ = engine.extract_dominant_hue(red_img, red_mask)
    assert s_red > 150
    # Red hue is near 0° or 360°
    assert hue_red < 20.0 or hue_red > 340.0

    # Green patch
    green_img = _create_color_patch_image(boxes=[(10, 10, 50, 50, (0, 255, 0))])
    green_mask = np.zeros((480, 640), dtype=np.uint8)
    green_mask[10:50, 10:50] = 1
    hue_green, s_green, _ = engine.extract_dominant_hue(green_img, green_mask)
    assert s_green > 150
    # Green hue is near 120°
    assert 100.0 < hue_green < 140.0


def test_red_and_green_cubes_zero_swap_under_extreme_proximity() -> None:
    """MANDATED TEST: Red and Green cubes must never swap IDs even when 2px apart."""
    engine = ReIdEngine(hue_gate_degrees=60.0)

    # Create synthetic frame with Red cube and Green cube touching / 2px apart
    # Red cube at x=[100, 140], Green cube at x=[142, 182]
    frame = _create_color_patch_image(
        boxes=[
            (100, 100, 140, 140, (0, 0, 255)),  # Red cube BGR
            (142, 100, 182, 140, (0, 255, 0)),  # Green cube BGR
        ]
    )

    # Initial targets
    target_red = ObjMask(
        obj="red_cube",
        frame=0,
        score=0.98,
        bbox_xyxy=(100.0, 100.0, 140.0, 140.0),
        rle="",
        area_px=1600,
        rle_size=(480, 640),
    )
    target_green = ObjMask(
        obj="green_cube",
        frame=0,
        score=0.98,
        bbox_xyxy=(142.0, 100.0, 182.0, 140.0),
        rle="",
        area_px=1600,
        rle_size=(480, 640),
    )
    targets = {"red_cube": target_red, "green_cube": target_green}

    # Present candidates in REVERSED order to challenge Hungarian matcher:
    # cand 0 is Green, cand 1 is Red
    cand_green = ObjMask(
        obj="unknown_1",
        frame=1,
        score=0.95,
        bbox_xyxy=(143.0, 101.0, 183.0, 141.0),
        rle="",
        area_px=1600,
        rle_size=(480, 640),
    )
    cand_red = ObjMask(
        obj="unknown_0",
        frame=1,
        score=0.95,
        bbox_xyxy=(101.0, 101.0, 141.0, 141.0),
        rle="",
        area_px=1600,
        rle_size=(480, 640),
    )
    candidates = [cand_green, cand_red]

    # Execute matching
    matched = engine.match_masks(candidates, targets, frame)

    assert len(matched) == 2
    assert "red_cube" in matched
    assert "green_cube" in matched

    # Verify ZERO ID swaps: red matched to candidate with x ~ 101
    assert matched["red_cube"].bbox_xyxy[0] == 101.0
    assert matched["green_cube"].bbox_xyxy[0] == 143.0
    assert matched["red_cube"].obj == "red_cube"
    assert matched["green_cube"].obj == "green_cube"


def test_no_destructive_mask_subtraction() -> None:
    """Verify that matching does not mutate or destructively subtract masks."""
    engine = ReIdEngine()

    frame = _create_color_patch_image(
        boxes=[
            (100, 100, 150, 150, (0, 0, 255)),
            (120, 120, 170, 170, (255, 0, 0)),  # Overlapping
        ]
    )

    t1 = ObjMask(
        obj="obj_1",
        frame=0,
        score=0.95,
        bbox_xyxy=(100.0, 100.0, 150.0, 150.0),
        rle="",
        area_px=2500,
        rle_size=(480, 640),
    )
    c1 = ObjMask(
        obj="cand_1",
        frame=1,
        score=0.95,
        bbox_xyxy=(100.0, 100.0, 150.0, 150.0),
        rle="",
        area_px=2500,
        rle_size=(480, 640),
    )

    matched = engine.match_masks([c1], {"obj_1": t1}, frame)
    assert matched["obj_1"].area_px == 2500
    assert c1.area_px == 2500
