"""Tests for deterministic perception FixtureBackend.

Validates Law 1 anti-fabrication compliance (backend="fixture", is_fixture=True),
exact frame slicing, and coordinate frame alignment per IP-P03-D3-5 and RULING.md §5.
"""

from __future__ import annotations

import pytest

from Kodiac_robotics.contracts.core import Clip, ClipRef
from Kodiac_robotics.segment.fixture import FixtureBackend


def _load_golden_clip() -> Clip:
    # correct_run.mp4
    sha256 = "6b28a831148885bfc67936b677fe5d0a0c1afef3fcb585500c427a97e0190b24"
    return Clip(
        ref=ClipRef(uri="tests/fixtures/clips/correct_run.mp4", source_kind="sim"),
        path_h264="tests/fixtures/clips/correct_run.mp4",
        fps=30.0,
        n_frames=90,
        width=640,
        height=480,
        sha256=sha256,
    )


def test_fixture_backend_segment_frames():
    """Verify segment_frames returns expected roles and slices exact frames."""
    backend = FixtureBackend()
    clip = _load_golden_clip()

    requested_frames = [0, 15, 30, 45]
    prompts = {
        "cube_a": ["red cube"],
        "cube_b": ["green cube"],
        "gripper": ["robot gripper"],
    }

    tracks = backend.segment_frames(clip, requested_frames, prompts)

    assert "cube_a" in tracks
    assert "cube_b" in tracks
    assert "gripper" in tracks

    for obj_name, track in tracks.items():
        # Law 1 watermark assertion
        assert track.backend == "fixture"
        assert set(track.frames.keys()) == set(requested_frames)

        for f in requested_frames:
            mask = track.frames[f]
            assert mask.rle_size == (clip.height, clip.width)
            assert mask.area_px > 0
            assert len(mask.bbox_xyxy) == 4


def test_fixture_backend_track_window():
    """Verify track returns exact window frame range [f0, f1]."""
    backend = FixtureBackend()
    clip = _load_golden_clip()

    # Get seed from frame 10
    key_tracks = backend.segment_frames(clip, [10], {"cube_a": ["red cube"]})
    seed_mask = key_tracks["cube_a"].frames[10]

    window_tracks = backend.track(clip, f0=10, f1=25, seeds={"cube_a": seed_mask}, direction="forward")
    assert "cube_a" in window_tracks
    track = window_tracks["cube_a"]

    assert track.backend == "fixture"
    expected_frames = set(range(10, 26))
    assert set(track.frames.keys()) == expected_frames


def test_fixture_backend_alias_resolution():
    """Verify synonyms like 'red cube' or 'green_cube' resolve properly."""
    backend = FixtureBackend()
    clip = _load_golden_clip()

    tracks = backend.segment_frames(clip, [0], {"red_cube": ["red rectangular block"]})
    assert "red_cube" in tracks
    assert 0 in tracks["red_cube"].frames
    assert tracks["red_cube"].backend == "fixture"


def test_fixture_missing_file_raises():
    """Verify missing fixture file raises FileNotFoundError."""
    backend = FixtureBackend()
    non_existent_clip = Clip(
        ref=ClipRef(uri="non_existent.mp4", source_kind="sim"),
        path_h264="non_existent.mp4",
        fps=30.0,
        n_frames=90,
        width=640,
        height=480,
        sha256="ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
    )

    with pytest.raises(FileNotFoundError, match="Fixture track not found"):
        backend.segment_frames(non_existent_clip, [0], {"cube_a": ["red cube"]})
