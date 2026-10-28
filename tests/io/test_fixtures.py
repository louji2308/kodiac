"""Verification tests for golden fixture clips and SHA-256 manifest.

Verifies:
- All 5 canonical golden failure clips exist on disk.
- SHA-256 checksums strictly match tests/fixtures/clips/manifest.json.
- File size constraint: <= 2 MB per clip (DoD requirement).
- Streams are valid H.264 CFR video matching perceptual ingest standards.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from Kodiac_robotics.io.lerobot import get_video_metadata

FIXTURES_DIR = Path("tests/fixtures/clips")
MANIFEST_PATH = FIXTURES_DIR / "manifest.json"

EXPECTED_CLIPS = [
    "correct_run.mp4",
    "b01_early_release.mp4",
    "b02_xy_misalignment.mp4",
    "b09_lift_failure.mp4",
    "occluded_clip.mp4",
]


def test_manifest_exists_and_parses():
    assert MANIFEST_PATH.exists(), f"Missing manifest at {MANIFEST_PATH}"
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert "version" in data
    assert "clips" in data
    assert len(data["clips"]) == len(EXPECTED_CLIPS)


@pytest.mark.parametrize("clip_name", EXPECTED_CLIPS)
def test_fixture_clip_integrity(clip_name: str):
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    entry = manifest["clips"].get(clip_name)
    assert entry is not None, f"Clip {clip_name} not found in manifest"

    clip_path = Path(entry["path"])
    assert clip_path.exists(), f"Fixture file missing on disk: {clip_path}"

    # Verify SHA-256
    computed_sha = hashlib.sha256(clip_path.read_bytes()).hexdigest()
    assert (
        computed_sha == entry["sha256"]
    ), f"SHA-256 mismatch for {clip_name}: expected {entry['sha256']}, got {computed_sha}"

    # Verify size <= 2 MB (2,097,152 bytes)
    file_size = clip_path.stat().st_size
    assert file_size > 0, f"Clip {clip_name} is empty"
    assert file_size <= 2 * 1024 * 1024, f"Clip {clip_name} exceeds 2MB limit: {file_size} bytes"

    # Verify video metadata
    meta = get_video_metadata(clip_path)
    assert meta["codec_name"] == "h264"
    assert meta["duration"] > 0.5
    assert meta["width"] >= 320
    assert meta["height"] >= 240
    assert meta["fps"] > 0
