"""Tests for geometric anchor extraction."""

from __future__ import annotations

import numpy as np

from Kodiac_robotics.contracts.core import ObjMask
from Kodiac_robotics.geometry.anchors import compute_anchors
from Kodiac_robotics.segment.rle import mask_to_rle


def test_empty_mask_anchors():
    """Empty mask must return fallback centroid, bbox anchors, zero area, and honest occlusion."""
    mask = ObjMask(
        obj="cube",
        frame=0,
        score=0.9,
        bbox_xyxy=(10.0, 20.0, 30.0, 60.0),
        rle="",
        area_px=0,
        rle_size=(480, 640),
    )
    (cx, cy), bottom, top, area, occ = compute_anchors(mask, base_area_px=100)
    assert cx == 20.0
    assert cy == 40.0
    assert bottom == (20.0, 60.0)
    assert top == (20.0, 20.0)
    assert area == 0
    assert occ == 1.0


def test_rectangular_mask_anchors():
    """Rectangular mask must have bottom anchor at lowest row, top anchor at highest row."""
    canvas = np.zeros((100, 100), dtype=np.uint8)
    # Rectangle: rows 30..70, cols 40..60
    canvas[30:71, 40:61] = 1
    rle = mask_to_rle(canvas)

    mask = ObjMask(
        obj="block",
        frame=0,
        score=0.95,
        bbox_xyxy=(40.0, 30.0, 60.0, 70.0),
        rle=rle,
        area_px=int(np.sum(canvas)),
        rle_size=(100, 100),
    )
    total_px = int(np.sum(canvas))
    (cx, cy), bottom, top, area, occ = compute_anchors(mask, base_area_px=total_px)
    assert np.isclose(cx, 50.0)
    assert np.isclose(cy, 50.0)
    # Lowest row in image is y=70; median col across 40..60 is 50.0
    assert np.isclose(bottom[0], 50.0)
    assert bottom[1] == 70.0
    # Highest row in image is y=30; median col across 40..60 is 50.0
    assert np.isclose(top[0], 50.0)
    assert top[1] == 30.0
    assert area == total_px
    assert np.isclose(occ, 0.0)

    # Half occlusion test
    _, _, _, _, half_occ = compute_anchors(mask, base_area_px=total_px * 2)
    assert np.isclose(half_occ, 0.5)


def test_asymmetric_trapezoid_anchors():
    """Trapezoid wider at bottom must compute median column of bottom 5% correctly."""
    canvas = np.zeros((100, 100), dtype=np.uint8)
    # Top: row 10..20, col 48..52 (center ~50)
    canvas[10:21, 48:53] = 1
    # Bottom: row 80..90, col 20..80 (center ~50)
    canvas[80:91, 20:81] = 1

    rle = mask_to_rle(canvas)
    mask = ObjMask(
        obj="lamp",
        frame=5,
        score=0.98,
        bbox_xyxy=(20.0, 10.0, 80.0, 90.0),
        rle=rle,
        area_px=int(np.sum(canvas)),
        rle_size=(100, 100),
    )
    (cx, cy), bottom, top, area, occ = compute_anchors(mask)
    assert bottom[1] == 90.0
    assert np.isclose(bottom[0], 50.0)
    assert top[1] == 10.0
    assert np.isclose(top[0], 50.0)
    assert occ == 0.0
