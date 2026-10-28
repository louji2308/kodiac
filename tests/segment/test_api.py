"""Tests for hosted SAM 3.1 streaming backend adapter.

Validates prompt isolation, streaming parsing, disk caching, and tenacity retry.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import numpy as np
import pytest

from Kodiac_robotics.contracts.core import Clip, ClipRef
from Kodiac_robotics.segment.api import HostedSamBackend
from Kodiac_robotics.segment.rle import mask_to_rle


def _make_dummy_clip() -> Clip:
    return Clip(
        ref=ClipRef(uri="file://test.mp4", source_kind="sim"),
        path_h264="test.mp4",
        fps=30.0,
        n_frames=90,
        width=640,
        height=480,
        sha256="aabbccddeeff11223344",
    )


def test_prompt_isolation_segment_frames_rejects_boxes():
    """Verify segment_frames rejects non-string prompts."""
    backend = HostedSamBackend(api_key="mock_key")
    clip = _make_dummy_clip()

    # Pass dict containing box instead of list of strings
    with pytest.raises(ValueError, match="Prompt isolation violation"):
        backend.segment_frames(clip, [0], {"cube": [{"bbox": [10, 10, 20, 20]}]})  # type: ignore[dict-item]


def test_prompt_isolation_track_rejects_text_prompts():
    """Verify track rejects text prompts instead of ObjMask seeds."""
    backend = HostedSamBackend(api_key="mock_key")
    clip = _make_dummy_clip()

    with pytest.raises(ValueError, match="Prompt isolation violation"):
        backend.track(clip, 0, 10, {"cube": "red cube"}, direction="forward")  # type: ignore[dict-item]


def test_missing_api_key_raises(monkeypatch):
    """Verify error when api_key is missing."""
    monkeypatch.delenv("KODIAC_MODEL_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    backend = HostedSamBackend(api_key=None)
    backend.api_key = None
    clip = _make_dummy_clip()

    with pytest.raises(ValueError, match="MODEL_API_KEY is not set"):
        backend.segment_frames(clip, [0], {"cube": ["red cube"]})


def test_streaming_sse_parsing_and_caching(tmp_path: Path):
    """Verify streaming response parsing, coordinate alignment, and disk caching."""
    clip = _make_dummy_clip()
    call_count = 0

    # Local mask 40x50 at box [100, 50, 150, 90]
    local_mask = np.ones((40, 50), dtype=np.uint8)
    local_rle = mask_to_rle(local_mask)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1

        sse_body = (
            f"data: {json.dumps({'frame_index': 0, 'objects': [{'label': 'cube_a', 'score': 0.98, 'bbox': [100, 50, 150, 90], 'mask': {'counts': local_rle, 'size': [40, 50]}}]})}\n\n"
            f"data: {json.dumps({'frame_index': 5, 'objects': [{'label': 'cube_a', 'score': 0.95, 'bbox': [110, 50, 160, 90], 'mask': {'counts': local_rle, 'size': [40, 50]}}]})}\n\n"
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=sse_body)

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    backend = HostedSamBackend(
        api_key="mock_key",
        client=mock_client,
        cache_dir=tmp_path / "cache",
    )

    # First call - hits handler
    tracks = backend.segment_frames(clip, [0, 5], {"cube_a": ["red cube"]})
    assert call_count == 1
    assert "cube_a" in tracks
    assert 0 in tracks["cube_a"].frames
    assert 5 in tracks["cube_a"].frames

    # Check coordinate alignment contract
    mask0 = tracks["cube_a"].frames[0]
    assert mask0.rle_size == (clip.height, clip.width)
    assert mask0.bbox_xyxy == (100.0, 50.0, 150.0, 90.0)
    assert mask0.area_px == 40 * 50

    # Second call with identical arguments - hits disk cache, no network!
    tracks_cached = backend.segment_frames(clip, [0, 5], {"cube_a": ["red cube"]})
    assert call_count == 1
    assert tracks_cached["cube_a"].frames[0].rle == mask0.rle


def test_tenacity_retry_on_429(tmp_path: Path):
    """Verify tenacity retries on 429 status code and succeeds."""
    clip = _make_dummy_clip()
    attempts = 0

    local_mask = np.ones((20, 20), dtype=np.uint8)
    local_rle = mask_to_rle(local_mask)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, text="Rate limit exceeded")
        sse_body = (
            f"data: {json.dumps({'frame_index': 0, 'objects': [{'label': 'gripper', 'score': 0.9, 'bbox': [10, 10, 30, 30], 'rle': local_rle}]})}\n\n"
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=sse_body)

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    backend = HostedSamBackend(
        api_key="mock_key",
        client=mock_client,
        cache_dir=tmp_path / "cache",
    )

    tracks = backend.segment_frames(clip, [0], {"gripper": ["robot gripper"]})
    assert attempts == 2
    assert "gripper" in tracks
    assert tracks["gripper"].frames[0].rle_size == (clip.height, clip.width)
