"""Unit tests for LeRobot dataset episode ingest and AV1-to-H.264 CFR transcoding.

Verifies:
- URI parsing and parameter resolution.
- Constant Frame Rate (CFR) H.264 yuv420p transcoding via ffmpeg.
- Video stream metadata extraction.
- Offline fixture mocking and cache re-use.
- Clip contract conformance per ARCHITECTURE.md §0.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from Kodiac_robotics.contracts.core import Clip
from Kodiac_robotics.io.lerobot import (
    compute_file_sha256,
    get_video_metadata,
    load_lerobot_episode,
    parse_lerobot_uri,
    transcode_to_h264_cfr,
)

FIXTURES_DIR = Path("tests/fixtures/clips")
CORRECT_RUN = FIXTURES_DIR / "correct_run.mp4"


def test_parse_lerobot_uri_full():
    repo, ep, cam = parse_lerobot_uri("lerobot://alexander-soare/droid_100/42/exterior_1")
    assert repo == "alexander-soare/droid_100"
    assert ep == 42
    assert cam == "exterior_1"


def test_parse_lerobot_uri_without_camera():
    repo, ep, cam = parse_lerobot_uri("lerobot://lerobot/so100_pick_place/7")
    assert repo == "lerobot/so100_pick_place"
    assert ep == 7
    assert cam is None


def test_parse_lerobot_uri_explicit_args():
    repo, ep, cam = parse_lerobot_uri(
        "lerobot/so100_pick_place", episode_index=15, camera="laptop"
    )
    assert repo == "lerobot/so100_pick_place"
    assert ep == 15
    assert cam == "laptop"


def test_parse_lerobot_uri_invalid_missing_episode():
    with pytest.raises(ValueError, match="episode_index is required"):
        parse_lerobot_uri("lerobot/so100_pick_place")


def test_compute_file_sha256():
    assert CORRECT_RUN.exists(), f"Fixture missing: {CORRECT_RUN}"
    expected = hashlib.sha256(CORRECT_RUN.read_bytes()).hexdigest()
    computed = compute_file_sha256(CORRECT_RUN)
    assert computed == expected


def test_get_video_metadata():
    assert CORRECT_RUN.exists()
    meta = get_video_metadata(CORRECT_RUN)
    assert meta["width"] == 640
    assert meta["height"] == 480
    assert meta["fps"] == pytest.approx(30.0, abs=0.5)
    assert meta["n_frames"] >= 80
    assert meta["duration"] == pytest.approx(3.0, abs=0.5)
    assert meta["codec_name"] == "h264"


def test_transcode_to_h264_cfr(tmp_path: Path):
    out_file = tmp_path / "transcoded_15fps.mp4"
    result = transcode_to_h264_cfr(CORRECT_RUN, out_file, target_fps=15.0)
    assert result == out_file
    assert out_file.exists()
    assert out_file.stat().st_size > 0

    meta = get_video_metadata(out_file)
    assert meta["codec_name"] == "h264"
    assert meta["pix_fmt"] == "yuv420p"
    assert meta["fps"] == pytest.approx(15.0, abs=0.5)


def test_load_lerobot_episode_mock_fallback(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    clip = load_lerobot_episode(
        repo_id="lerobot://alexander-soare/droid_100/14/exterior_1",
        target_fps=15.0,
        cache_dir=cache_dir,
        mock_ok=True,
    )

    assert isinstance(clip, Clip)
    assert clip.ref.source_kind == "real"
    assert clip.ref.dataset == "alexander-soare/droid_100"
    assert clip.ref.episode_index == 14
    assert clip.ref.camera == "exterior_1"
    assert clip.width == 640
    assert clip.height == 480
    assert clip.fps == pytest.approx(15.0, abs=0.5)
    assert Path(clip.path_h264).exists()
    assert clip.sha256 == compute_file_sha256(clip.path_h264)


def test_load_lerobot_episode_cache_reuse(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    # First call - transcodes into cache
    clip1 = load_lerobot_episode(
        repo_id="lerobot/so100_pick_place",
        episode_index=1,
        camera="laptop",
        target_fps=30.0,
        cache_dir=cache_dir,
        mock_ok=True,
    )
    mtime1 = Path(clip1.path_h264).stat().st_mtime_ns

    # Second call - must hit cache directly without altering file
    clip2 = load_lerobot_episode(
        repo_id="lerobot/so100_pick_place",
        episode_index=1,
        camera="laptop",
        target_fps=30.0,
        cache_dir=cache_dir,
        mock_ok=True,
    )
    mtime2 = Path(clip2.path_h264).stat().st_mtime_ns

    assert clip1.sha256 == clip2.sha256
    assert clip1.path_h264 == clip2.path_h264
    assert mtime1 == mtime2


def test_load_lerobot_episode_raises_when_mock_disabled(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    # Ensure offline non-fixture without mock raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        load_lerobot_episode(
            repo_id="nonexistent_repo/nonexistent_dataset_xyz",
            episode_index=999999,
            cache_dir=cache_dir,
            mock_ok=False,
        )
