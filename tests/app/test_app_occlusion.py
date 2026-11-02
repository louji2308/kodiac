"""Occlusion brush: pixel blackout on all frames, and mask emulation on cached tracks."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from Kodiac_robotics.app.occlusion import (
    apply_rects,
    normalize_rects,
    occlude_tracks,
    occlude_video,
)
from Kodiac_robotics.io.clip import open_clip
from Kodiac_robotics.segment.fixture import FixtureBackend

REPO_ROOT = Path(__file__).resolve().parents[2]
B01 = REPO_ROOT / "tests" / "fixtures" / "clips" / "b01_early_release.mp4"


def test_apply_rects_blackens_every_frame_and_copies() -> None:
    frames = np.full((5, 40, 60, 3), 200, dtype=np.uint8)
    out = apply_rects(frames, [(10, 5, 30, 20)])
    assert out.shape == frames.shape
    assert (out[:, 5:20, 10:30, :] == 0).all()
    assert (out[:, :5] == 200).all() and (out[:, :, 30:] == 200).all()
    assert (frames == 200).all(), "input must not be mutated"


def test_apply_rects_single_frame_and_clipping() -> None:
    frame = np.full((20, 20, 3), 9, dtype=np.uint8)
    out = apply_rects(frame, [(15, 15, 99, 99), (-5, -5, 2, 2)])
    assert (out[15:, 15:] == 0).all() and (out[:2, :2] == 0).all()
    assert out[10, 10, 0] == 9


def test_normalize_rects_orders_corners_and_drops_empty() -> None:
    assert normalize_rects([(30, 20, 10, 5), (4, 4, 4, 9)], 60, 40) == [(10, 5, 30, 20)]
    with pytest.raises(ValueError):
        normalize_rects([[1, 2, 3]], 10, 10)


def test_occlude_video_blackens_decoded_frames(tmp_path: Path) -> None:
    dst = occlude_video(B01, tmp_path / "occ.mp4", [(0, 0, 320, 240)], fps=30.0)
    cap = cv2.VideoCapture(str(dst))
    n = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        n += 1
        assert frame[10:230, 10:310].mean() < 8.0
    cap.release()
    assert n == 90


def test_occlude_tracks_removes_covered_masks_and_reports_fraction() -> None:
    clip = open_clip(B01)
    tracks = FixtureBackend(REPO_ROOT / "tests" / "fixtures" / "tracks")._load_tracks(clip)
    full, worst = occlude_tracks(tracks, [(380, 280, 500, 360)], (clip.height, clip.width))
    assert worst["cube_b"] == pytest.approx(1.0)
    assert full["cube_b"].frames == {}
    assert worst["cube_a"] < 1.0

    none, worst0 = occlude_tracks(tracks, [], (clip.height, clip.width))
    assert all(v == 0.0 for v in worst0.values())
    assert none["cube_b"].frames.keys() == tracks["cube_b"].frames.keys()


def test_occlude_tracks_partial_cover_shrinks_area() -> None:
    clip = open_clip(B01)
    tracks = FixtureBackend(REPO_ROOT / "tests" / "fixtures" / "tracks")._load_tracks(clip)
    out, worst = occlude_tracks(tracks, [(400, 300, 440, 342)], (clip.height, clip.width))
    f0 = min(tracks["cube_b"].frames)
    assert out["cube_b"].frames[f0].area_px < tracks["cube_b"].frames[f0].area_px
    assert 0.0 < worst["cube_b"] < 1.0
