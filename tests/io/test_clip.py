"""Unit tests for Universal Video IO and open_clip normalization.

Tests local fixtures, ClipRef models, synthetic odd-dimension transcoding,
file:// URI parsing, and error conditions.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from Kodiac_robotics.contracts.core import Clip, ClipRef
from Kodiac_robotics.io.clip import open_clip


@pytest.fixture
def manifest():
    manifest_path = Path("tests/fixtures/clips/manifest.json")
    assert manifest_path.exists(), "Manifest fixture missing"
    with open(manifest_path, encoding="utf-8") as f:
        return json.load(f)["clips"]


def test_open_clip_golden_fixture(manifest):
    """Verify open_clip loads canonical correct_run.mp4 with exact metadata."""
    clip_info = manifest["correct_run.mp4"]
    clip_path = Path(clip_info["path"])

    clip = open_clip(clip_path)

    assert isinstance(clip, Clip)
    assert clip.width == clip_info["width"]
    assert clip.height == clip_info["height"]
    assert clip.n_frames == clip_info["n_frames"]
    assert clip.fps == clip_info["fps"]
    assert clip.sha256 == clip_info["sha256"]
    assert Path(clip.path_h264).exists()
    assert clip.ref.uri == str(clip_path.resolve())


def test_open_clip_with_clipref():
    """Verify open_clip accepts an explicit ClipRef model and preserves metadata."""
    clip_ref = ClipRef(
        uri="tests/fixtures/clips/b01_early_release.mp4",
        source_kind="sim",
        episode_index=1,
    )
    clip = open_clip(clip_ref)

    assert isinstance(clip, Clip)
    assert clip.ref.source_kind == "sim"
    assert clip.ref.episode_index == 1
    assert clip.n_frames == 90
    assert clip.fps == 30.0
    assert clip.width == 640
    assert clip.height == 480


def test_open_clip_file_uri():
    """Verify open_clip parses file:// URIs correctly."""
    clip_path = Path("tests/fixtures/clips/b02_xy_misalignment.mp4").resolve()
    file_uri = clip_path.as_uri()

    clip = open_clip(file_uri)
    assert isinstance(clip, Clip)
    assert clip.n_frames == 90
    assert clip.width == 640
    assert clip.height == 480


def test_open_clip_odd_dimensions_and_transcoding(tmp_path):
    """Verify open_clip normalizes odd dimensions (e.g. 321x241) to even dimensions with H.264 CFR."""
    raw_odd_video = tmp_path / "odd_dim.mp4"
    # Generate a 30-frame synthetic video with odd dimensions: 321x241
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=1:size=321x241:rate=30",
        "-c:v",
        "mpeg4",
        "-q:v",
        "5",
        str(raw_odd_video),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    assert raw_odd_video.exists()

    clip = open_clip(raw_odd_video)

    assert isinstance(clip, Clip)
    # Output must have even dimensions
    assert clip.width % 2 == 0
    assert clip.height % 2 == 0
    assert clip.width >= 321
    assert clip.height >= 241
    assert clip.fps == 30.0
    assert clip.n_frames == 30
    assert Path(clip.path_h264).exists()
    assert len(clip.sha256) == 64


def test_open_clip_nonexistent_raises():
    """Verify open_clip raises FileNotFoundError for nonexistent paths."""
    with pytest.raises(FileNotFoundError):
        open_clip("tests/fixtures/clips/does_not_exist_xyz.mp4")


def test_open_clip_lerobot_uri():
    """Verify open_clip delegates lerobot:// URIs to the LeRobot loader with mock fallback."""
    uri = "lerobot://lerobot/aloha_sim_insertion_human/0"
    clip = open_clip(uri)
    assert isinstance(clip, Clip)
    assert clip.ref.uri.startswith("lerobot://")
    assert clip.n_frames > 0
    assert clip.fps > 0
    assert clip.width % 2 == 0
    assert clip.height % 2 == 0
