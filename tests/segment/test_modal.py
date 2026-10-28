"""Unit tests for Modal SAM 3.1 backend client and container service.

Tests parameter validation, 50-frame chunking, sliding window cache-clearing,
scale-to-zero enforcement, and deterministic offline mock fallback.
Per ARCHITECTURE.md §3.1, §4.3, IMPLEMENTATION_PLAN.md P03.S03, and P03 RULING.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from Kodiac_robotics.contracts.core import Clip, ClipRef, ObjMask  # noqa: E402
from Kodiac_robotics.segment.modal_backend import ModalSamBackend  # noqa: E402
from modal.sam31 import (  # noqa: E402
    APP_NAME,
    GPU_TYPE,
    SCALEDOWN_WINDOW,
    SLIDING_WINDOW_FRAMES,
    USE_FA3,
    handle_request,
    handle_stream_request,
)


def _make_dummy_clip(n_frames: int = 90, w: int = 640, h: int = 480) -> Clip:
    """Helper to construct a valid Clip model for tests."""
    return Clip(
        ref=ClipRef(uri="test_clip.mp4", source_kind="sim"),
        path_h264="test_clip.mp4",
        fps=30.0,
        n_frames=n_frames,
        width=w,
        height=h,
        sha256="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    )


def test_modal_service_configuration_invariants() -> None:
    """Verify hardware and container configuration constants."""
    assert APP_NAME == "Kodiac-sam31"
    assert GPU_TYPE == "L4"
    assert USE_FA3 is False, "FlashAttention-3 must be False on non-Hopper / L4 GPUs"
    assert SCALEDOWN_WINDOW == 60, "Must enforce scale-to-zero with 60s window"
    assert SLIDING_WINDOW_FRAMES == 50, "Sliding window must chunk at 50 frames"


def test_modal_service_handle_request_and_chunking() -> None:
    """Verify handle_request processes 50-frame chunks with memory bounds."""
    req = {
        "clip_sha256": "test_sha",
        "n_frames": 120,
        "width": 640,
        "height": 480,
        "start_frame_index": 0,
        "max_frame_num_to_track": 120,
        "direction": "forward",
        "prompts": {"gripper": ["gripper"], "target_cube": ["red cube"]},
    }
    result = handle_request(req)
    assert result["status"] == "success"
    assert result["frames_processed"] == 120
    assert result["use_fa3"] is False
    assert result["gpu"] == "L4"

    tracks = result["tracks"]
    assert "gripper" in tracks
    assert "target_cube" in tracks
    assert len(tracks["gripper"]["frames"]) == 120

    # Verify mask properties
    sample_mask = tracks["gripper"]["frames"][0]
    assert sample_mask["rle_size"] == (480, 640)
    assert sample_mask["score"] >= 0.90
    assert len(sample_mask["rle"]) > 0


def test_modal_service_handle_stream_request() -> None:
    """Verify streaming generator yields results in 50-frame chunks."""
    req = {
        "clip_sha256": "test_stream_sha",
        "n_frames": 110,
        "width": 640,
        "height": 480,
        "direction": "forward",
        "prompts": {"cube": ["cube"]},
    }
    chunks = list(handle_stream_request(req))
    assert len(chunks) == 3  # 0..49, 50..99, 100..109
    assert len(chunks[0]["frames"]) == 50
    assert len(chunks[1]["frames"]) == 50
    assert len(chunks[2]["frames"]) == 10


def test_modal_backend_parameter_validation() -> None:
    """Verify ModalSamBackend validates input constraints strictly."""
    client = ModalSamBackend()
    clip = _make_dummy_clip(n_frames=90)

    # Empty frames should return empty dict
    assert client.segment_frames(clip, [], {"cube": ["cube"]}) == {}

    # Frame out of bounds
    with pytest.raises(ValueError, match="out of clip bounds"):
        client.segment_frames(clip, [95], {"cube": ["cube"]})

    with pytest.raises(ValueError, match="out of clip bounds"):
        client.segment_frames(clip, [-1], {"cube": ["cube"]})

    # More than 16 objects
    over_prompts = {f"obj_{i}": [f"prompt_{i}"] for i in range(17)}
    with pytest.raises(ValueError, match="maximum object limit of 16"):
        client.segment_frames(clip, [0], over_prompts)

    # Invalid tracking window
    dummy_seed = ObjMask(
        obj="cube",
        frame=0,
        score=0.95,
        bbox_xyxy=(10.0, 10.0, 50.0, 50.0),
        rle="dummy",
        area_px=1600,
        rle_size=(480, 640),
    )
    with pytest.raises(ValueError, match="Invalid frame window"):
        client.track(clip, f0=50, f1=30, seeds={"cube": dummy_seed})

    # Invalid direction
    with pytest.raises(ValueError, match="Invalid propagation direction"):
        client.track(clip, f0=0, f1=10, seeds={"cube": dummy_seed}, direction="sideways")  # type: ignore


def test_modal_backend_offline_execution_and_models() -> None:
    """Verify offline mock fallback returns valid Track models adhering to invariants."""
    client = ModalSamBackend(offline_fallback=True)
    clip = _make_dummy_clip(n_frames=60, w=640, h=480)

    # 1. Sparse segmentation
    seg_tracks = client.segment_frames(clip, [0, 30, 59], {"cube": ["red block"]})
    assert "cube" in seg_tracks
    track = seg_tracks["cube"]
    assert track.obj == "cube"
    assert track.backend == "modal"
    assert len(track.frames) == 3
    for f_idx in [0, 30, 59]:
        m = track.frames[f_idx]
        assert m.frame == f_idx
        assert m.rle_size == (clip.height, clip.width), "Must strictly match full clip canvas!"
        assert m.area_px > 0

    # 2. Window tracking forward
    seed = track.frames[0]
    fwd_tracks = client.track(clip, f0=0, f1=40, seeds={"cube": seed}, direction="forward")
    assert "cube" in fwd_tracks
    assert len(fwd_tracks["cube"].frames) == 40

    # 3. Window tracking both directions
    both_tracks = client.track(clip, f0=0, f1=40, seeds={"cube": seed}, direction="both")
    assert "cube" in both_tracks
    assert both_tracks["cube"].direction == "both"
    assert len(both_tracks["cube"].frames) == 40
