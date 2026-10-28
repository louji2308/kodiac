"""Tests for pure-Python / NumPy COCO RLE codec.

Validates round-trip encoding/decoding, area calculation, and box-local
coordinate translation onto full-frame canvas per IP-P03-D1-1 and IP-P03-D3-2.
"""

from __future__ import annotations

import numpy as np
import pytest

from Kodiac_robotics.segment.rle import (
    box_local_to_full_frame_rle,
    mask_to_rle,
    rle_area,
    rle_to_mask,
)


def test_rle_empty_mask_roundtrip():
    """Verify empty mask encoding and decoding."""
    shape = (100, 100)
    empty_mask = np.zeros(shape, dtype=np.uint8)
    rle = mask_to_rle(empty_mask)
    decoded = rle_to_mask(rle, shape)

    assert np.array_equal(empty_mask, decoded)
    assert rle_area(rle, shape) == 0


def test_rle_full_mask_roundtrip():
    """Verify all-ones mask encoding and decoding."""
    shape = (60, 80)
    full_mask = np.ones(shape, dtype=np.uint8)
    rle = mask_to_rle(full_mask)
    decoded = rle_to_mask(rle, shape)

    assert np.array_equal(full_mask, decoded)
    assert rle_area(rle, shape) == 60 * 80


def test_rle_single_pixel_and_corners():
    """Verify single-pixel activations at first, middle, and last indices."""
    shape = (50, 50)
    mask = np.zeros(shape, dtype=np.uint8)
    mask[0, 0] = 1
    mask[25, 25] = 1
    mask[49, 49] = 1

    rle = mask_to_rle(mask)
    decoded = rle_to_mask(rle, shape)

    assert np.array_equal(mask, decoded)
    assert rle_area(rle, shape) == 3


def test_rle_random_masks_roundtrip():
    """Verify random binary masks roundtrip across various resolutions."""
    test_shapes = [(20, 20), (120, 160), (480, 640)]
    for idx, shape in enumerate(test_shapes):
        rng = np.random.default_rng(seed=100 + idx)
        mask = (rng.random(shape) > 0.85).astype(np.uint8)
        rle = mask_to_rle(mask)
        decoded = rle_to_mask(rle, shape)

        assert np.array_equal(mask, decoded), f"Mismatch for shape {shape}"
        assert rle_area(rle, shape) == int(np.sum(mask))


def test_box_local_to_full_frame_rle_translation():
    """Verify box-local RLE is properly placed at (x1, y1) on full-frame canvas."""
    full_shape = (480, 640)
    box_xyxy = (100.0, 50.0, 150.0, 90.0)  # w=50, h=40
    local_shape = (40, 50)

    # Local mask with a solid rectangle in center
    local_mask = np.ones(local_shape, dtype=np.uint8)
    local_rle = mask_to_rle(local_mask)

    # Translate to full frame
    full_rle = box_local_to_full_frame_rle(local_rle, box_xyxy, full_shape)
    full_mask = rle_to_mask(full_rle, full_shape)

    assert full_mask.shape == full_shape
    assert rle_area(full_rle, full_shape) == 40 * 50

    # Non-zero pixels must exist strictly inside [50:90, 100:150]
    assert np.all(full_mask[50:90, 100:150] == 1)
    # Outside must be strictly zero
    assert np.sum(full_mask[:50, :]) == 0
    assert np.sum(full_mask[90:, :]) == 0
    assert np.sum(full_mask[:, :100]) == 0
    assert np.sum(full_mask[:, 150:]) == 0


def test_box_local_already_full_frame():
    """Verify that an already full-frame mask passes through unchanged."""
    full_shape = (480, 640)
    mask = np.zeros(full_shape, dtype=np.uint8)
    mask[200:220, 300:320] = 1
    full_rle = mask_to_rle(mask)

    # Even if box_xyxy is given, if total pixels matches full frame, return as-is
    res = box_local_to_full_frame_rle(full_rle, (300.0, 200.0, 320.0, 220.0), full_shape)
    assert res == full_rle


def test_box_local_clamping():
    """Verify coordinate clamping when box boundaries extend beyond canvas."""
    full_shape = (100, 100)
    # Box extends past right and bottom edges
    box_xyxy = (80.0, 80.0, 120.0, 120.0)  # local 40x40
    local_shape = (40, 40)
    local_mask = np.ones(local_shape, dtype=np.uint8)
    local_rle = mask_to_rle(local_mask)

    full_rle = box_local_to_full_frame_rle(local_rle, box_xyxy, full_shape)
    full_mask = rle_to_mask(full_rle, full_shape)

    # Only 20x20 pixels should fit on the canvas [80:100, 80:100]
    assert rle_area(full_rle, full_shape) == 20 * 20
    assert np.all(full_mask[80:100, 80:100] == 1)


def test_invalid_mask_dimension():
    """Verify 3D array raises ValueError."""
    with pytest.raises(ValueError, match="Expected 2D mask"):
        mask_to_rle(np.zeros((10, 10, 3), dtype=np.uint8))
