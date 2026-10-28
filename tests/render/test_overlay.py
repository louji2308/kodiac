"""Unit tests for Perception Debug Overlay Renderer.

Tests single-frame mask rendering, contours, centroid crosshairs, bottom anchors,
top banner watermark, and full video overlay generation.
"""

from __future__ import annotations

import numpy as np
import pytest

from Kodiac_robotics.contracts.core import Clip, ObjMask, Track
from Kodiac_robotics.io.clip import open_clip
from Kodiac_robotics.io.transcode import probe_video
from Kodiac_robotics.render.overlay import OverlayRenderer
from Kodiac_robotics.segment.rle import mask_to_rle


@pytest.fixture
def golden_clip() -> Clip:
    return open_clip("tests/fixtures/clips/correct_run.mp4")


def _create_synthetic_box_mask(
    h: int,
    w: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
) -> tuple[np.ndarray, str]:
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[y0:y1, x0:x1] = 1
    rle = mask_to_rle(mask)
    return mask, rle


def test_render_frame_single_and_pixel_modification():
    """Verify render_frame produces correct shape and alters mask, bbox, and centroid pixels."""
    h, w = 480, 640
    blank_frame = np.full((h, w, 3), 128, dtype=np.uint8)
    renderer = OverlayRenderer(alpha=0.5, line_width=2)

    _, rle_gripper = _create_synthetic_box_mask(h, w, 100, 100, 200, 200)
    _, rle_target = _create_synthetic_box_mask(h, w, 300, 300, 400, 400)

    masks = {
        "gripper": ObjMask(
            obj="gripper",
            frame=0,
            score=0.95,
            bbox_xyxy=(100.0, 100.0, 200.0, 200.0),
            rle=rle_gripper,
            area_px=10000,
            rle_size=(h, w),
        ),
        "target": ObjMask(
            obj="target",
            frame=0,
            score=0.88,
            bbox_xyxy=(300.0, 300.0, 400.0, 400.0),
            rle=rle_target,
            area_px=10000,
            rle_size=(h, w),
        ),
    }

    out = renderer.render_frame(blank_frame, masks)

    assert isinstance(out, np.ndarray)
    assert out.shape == (h, w, 3)
    # Mask interior pixels should not equal original blank grey (128, 128, 128)
    assert not np.array_equal(out[150, 150], [128, 128, 128])
    assert not np.array_equal(out[350, 350], [128, 128, 128])
    # Outside background pixels should remain unmodified
    assert np.array_equal(out[50, 50], [128, 128, 128])


def test_render_frame_watermark():
    """Verify render_frame renders high-contrast text banner across top when watermark is provided."""
    h, w = 480, 640
    blank_frame = np.full((h, w, 3), 128, dtype=np.uint8)
    renderer = OverlayRenderer()

    out_no_watermark = renderer.render_frame(blank_frame, {})
    out_with_watermark = renderer.render_frame(
        blank_frame, {}, watermark="[SIM · ManiSkill3] frame 0"
    )

    # Top banner area should be modified
    assert not np.array_equal(out_with_watermark[:25, :], out_no_watermark[:25, :])
    # Lower area should remain identical
    assert np.array_equal(out_with_watermark[100:, :], out_no_watermark[100:, :])


def test_render_frame_custom_color_palette():
    """Verify custom color palette maps directly to object overlays."""
    h, w = 480, 640
    blank_frame = np.zeros((h, w, 3), dtype=np.uint8)
    renderer = OverlayRenderer(alpha=1.0)  # full opacity for deterministic pixel match

    _, rle = _create_synthetic_box_mask(h, w, 50, 50, 150, 150)
    masks = {
        "custom_cube": ObjMask(
            obj="custom_cube",
            frame=0,
            score=0.99,
            bbox_xyxy=(50.0, 50.0, 150.0, 150.0),
            rle=rle,
            area_px=10000,
            rle_size=(h, w),
        )
    }
    custom_color = (12, 34, 56)
    out = renderer.render_frame(
        blank_frame,
        masks,
        color_palette={"custom_cube": custom_color},
    )

    # Pixel inside mask away from crosshair should match custom_color
    assert tuple(out[80, 80]) == custom_color
    # Centroid dot at (100, 100) has white center highlight
    assert tuple(out[100, 100]) == (255, 255, 255)


def test_render_frame_explicit_bottom_anchors():
    """Verify bottom_anchors parameter explicitly places anchor marker."""
    h, w = 480, 640
    blank_frame = np.full((h, w, 3), 128, dtype=np.uint8)
    renderer = OverlayRenderer()

    _, rle = _create_synthetic_box_mask(h, w, 50, 50, 150, 150)
    masks = {
        "gripper": ObjMask(
            obj="gripper",
            frame=0,
            score=0.95,
            bbox_xyxy=(50.0, 50.0, 150.0, 150.0),
            rle=rle,
            area_px=10000,
            rle_size=(h, w),
        )
    }

    out = renderer.render_frame(
        blank_frame,
        masks,
        bottom_anchors={"gripper": (200.0, 250.0)},
    )

    # Pixel at explicit bottom anchor (200, 250) must be modified
    assert not np.array_equal(out[250, 200], [128, 128, 128])


def test_render_video_end_to_end(golden_clip, tmp_path):
    """Verify render_video processes all frames and encodes CFR H.264 video at native resolution."""
    renderer = OverlayRenderer(alpha=0.35, line_width=2)
    h, w = golden_clip.height, golden_clip.width

    # Generate synthetic tracks for first 10 frames
    _, rle = _create_synthetic_box_mask(h, w, 200, 200, 300, 300)
    frames_dict = {
        i: ObjMask(
            obj="red_block",
            frame=i,
            score=0.92,
            bbox_xyxy=(200.0, 200.0, 300.0, 300.0),
            rle=rle,
            area_px=10000,
            rle_size=(h, w),
        )
        for i in range(10)
    }

    tracks = {
        "red_block": Track(
            obj="red_block",
            frames=frames_dict,
            backend="fixture",
            direction="forward",
            trace_id="test_trace_001",
        )
    }

    out_video = tmp_path / "overlay_output.mp4"
    result_path = renderer.render_video(
        clip=golden_clip,
        tracks=tracks,
        output_path=out_video,
        watermark="[FIXTURE · OVERLAY DEMO]",
    )

    assert result_path.exists()
    assert result_path == out_video

    meta = probe_video(result_path)
    assert meta["width"] == golden_clip.width
    assert meta["height"] == golden_clip.height
    assert meta["fps"] == golden_clip.fps
    assert meta["n_frames"] == golden_clip.n_frames
    assert meta["codec_name"] == "h264"
    assert meta["pix_fmt"] in ("yuv420p", "yuvj420p")
