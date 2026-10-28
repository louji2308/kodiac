"""Unit tests for pixel jitter sigma estimation via second-difference MAD."""

from __future__ import annotations

import numpy as np

from Kodiac_robotics.contracts.core import ObjMask, Track
from Kodiac_robotics.segment.rle import mask_to_rle
from Kodiac_robotics.uncertainty.sigma import estimate_pixel_jitter


def _make_stationary_mask(frame: int, cx: float, cy: float, side=20) -> ObjMask:
    x1 = cx - side / 2
    y1 = cy - side / 2
    x2 = cx + side / 2
    y2 = cy + side / 2
    canvas = np.zeros((480, 640), dtype=np.uint8)
    canvas[int(y1) : int(y2), int(x1) : int(x2)] = 1
    return ObjMask(
        obj="cube",
        frame=frame,
        score=0.98,
        bbox_xyxy=(x1, y1, x2, y2),
        rle=mask_to_rle(canvas),
        area_px=int(np.sum(canvas)),
        rle_size=(480, 640),
    )


def test_estimate_pixel_jitter_floor():
    """Stationary object with zero jitter returns floor 0.5 px."""
    frames = {f: _make_stationary_mask(f, 320.0, 240.0) for f in range(16)}
    track = Track(obj="cube", frames=frames, backend="fixture", direction="forward", trace_id="tr1")

    sigma_px = estimate_pixel_jitter({"cube": track}, static_window=(0, 15))
    assert sigma_px == 0.5


def test_estimate_pixel_jitter_synthetic_noise():
    """Estimates synthetic jitter within statistical tolerance."""
    rng = np.random.default_rng(42)
    frames = {}
    true_sigma = 1.8
    for f in range(20):
        # Add normal jitter
        jitter_x = rng.normal(0.0, true_sigma)
        jitter_y = rng.normal(0.0, true_sigma)
        frames[f] = _make_stationary_mask(f, 320.0 + jitter_x, 240.0 + jitter_y)

    track = Track(obj="cube", frames=frames, backend="fixture", direction="forward", trace_id="tr1")
    est_sigma = estimate_pixel_jitter({"cube": track}, static_window=(0, 19))
    assert 1.0 <= est_sigma <= 2.8
