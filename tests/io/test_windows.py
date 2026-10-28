"""Unit tests for Window padding, symmetric boundary expansion, and sparse keyframe packing.

Verifies SAM 3.1 50-frame minimum constraint, start/end clamping, and 3x keyframe replication.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from Kodiac_robotics.contracts.core import Clip
from Kodiac_robotics.io.clip import open_clip
from Kodiac_robotics.io.transcode import probe_video
from Kodiac_robotics.io.windows import cut_window, pack_frames


@pytest.fixture
def golden_clip() -> Clip:
    return open_clip("tests/fixtures/clips/correct_run.mp4")


def test_cut_window_short_symmetric_padding(golden_clip):
    """Verify window shorter than min_frames (50) is symmetrically padded to >= 50 frames."""
    # Requested 11 frames [30, 40]
    cut = cut_window(golden_clip, f0=30, f1=40, min_frames=50)

    assert cut.valid_f0 == 30
    assert cut.valid_f1 == 40
    # Symmetric pad: deficit=39 -> pad_left=19, pad_right=20 -> [11, 60]
    assert cut.padded_f0 == 11
    assert cut.padded_f1 == 60
    assert cut.n_frames == 50
    assert cut.n_frames >= 50
    assert cut.parent_sha256 == golden_clip.sha256
    assert Path(cut.path).exists()

    # Validate actual cut video file geometry and frame count
    meta = probe_video(cut.path)
    assert meta["n_frames"] == 50
    assert meta["fps"] == golden_clip.fps
    assert meta["width"] == golden_clip.width
    assert meta["height"] == golden_clip.height


def test_cut_window_clamp_at_start(golden_clip):
    """Verify window near start clamps padded_f0 at 0 and pushes remaining deficit forward."""
    # Requested 11 frames [5, 15]
    cut = cut_window(golden_clip, f0=5, f1=15, min_frames=50)

    assert cut.valid_f0 == 5
    assert cut.valid_f1 == 15
    assert cut.padded_f0 == 0
    # Deficit 39 -> left tries -14, clamped to 0 -> right takes 15 + 20 + 14 = 49
    assert cut.padded_f1 == 49
    assert cut.n_frames == 50
    assert Path(cut.path).exists()

    meta = probe_video(cut.path)
    assert meta["n_frames"] == 50


def test_cut_window_clamp_at_end(golden_clip):
    """Verify window near end clamps padded_f1 at n_frames - 1 and pushes deficit backward."""
    # Parent has 90 frames (0..89). Requested 11 frames [75, 85].
    cut = cut_window(golden_clip, f0=75, f1=85, min_frames=50)

    assert cut.valid_f0 == 75
    assert cut.valid_f1 == 85
    assert cut.padded_f1 == 89
    # Deficit 39 -> right tries 85 + 20 = 105 (>89) -> right takes 4 -> left takes remaining 35 -> 75 - 35 = 40
    assert cut.padded_f0 == 40
    assert cut.n_frames == 50
    assert Path(cut.path).exists()

    meta = probe_video(cut.path)
    assert meta["n_frames"] == 50


def test_cut_window_already_sufficient_length(golden_clip):
    """Verify windows already meeting min_frames threshold require zero padding."""
    cut = cut_window(golden_clip, f0=10, f1=70, min_frames=50)

    assert cut.valid_f0 == 10
    assert cut.valid_f1 == 70
    assert cut.padded_f0 == 10
    assert cut.padded_f1 == 70
    assert cut.n_frames == 61
    assert Path(cut.path).exists()


def test_cut_window_invalid_bounds(golden_clip):
    """Verify cut_window rejects f0 > f1."""
    with pytest.raises(ValueError, match="cannot be greater"):
        cut_window(golden_clip, f0=60, f1=20)


def test_pack_frames_structure_and_index_map(golden_clip):
    """Verify pack_frames duplicates keyframes 3 times at 10 fps and preserves index mapping."""
    keyframe_indices = [0, 15, 30, 45, 60]
    pack = pack_frames(golden_clip, indices=keyframe_indices)

    assert pack.original_indices == keyframe_indices
    # 5 keyframes * 3 = 15 total frames
    assert pack.n_frames == 15
    assert len(pack.index_map) == 15

    # Check bidirectional index map
    for k_idx, orig_f in enumerate(keyframe_indices):
        assert pack.index_map[k_idx * 3] == orig_f
        assert pack.index_map[k_idx * 3 + 1] == orig_f
        assert pack.index_map[k_idx * 3 + 2] == orig_f

    assert Path(pack.path).exists()
    meta = probe_video(pack.path)
    assert meta["fps"] == 10.0
    assert meta["n_frames"] == 15


def test_pack_frames_empty_indices_raises(golden_clip):
    """Verify pack_frames raises ValueError on empty indices list."""
    with pytest.raises(ValueError, match="cannot be empty"):
        pack_frames(golden_clip, [])


def test_pack_frames_out_of_range_raises(golden_clip):
    """Verify pack_frames raises ValueError when keyframe index is out of range."""
    with pytest.raises(ValueError, match="out of range"):
        pack_frames(golden_clip, [0, 999])
