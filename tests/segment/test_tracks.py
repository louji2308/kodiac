"""Unit tests for spatio-temporal track assembler and track_many dispatcher.

Tests:
- Multi-window temporal track stitching
- Forward-backward cyclic consistency validation (IoU < 0.70 degradation flag)
- Maximum 16 objects API limit enforcement
- Batch track_many dispatcher functionality
Per ARCHITECTURE.md §3.1, §4.3, IMPLEMENTATION_PLAN.md P03.S06, and P03 RULING.
"""

from __future__ import annotations

import numpy as np
import pytest

from Kodiac_robotics.contracts.core import Clip, ClipRef, ObjMask, Track
from Kodiac_robotics.segment.tracks import (
    assemble_tracks,
    compute_bbox_iou,
    compute_mask_iou,
    track_many,
)


def _make_dummy_clip(n_frames: int = 90) -> Clip:
    return Clip(
        ref=ClipRef(uri="test_clip.mp4", source_kind="sim"),
        path_h264="test_clip.mp4",
        fps=30.0,
        n_frames=n_frames,
        width=640,
        height=480,
        sha256="test_sha_1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
    )


def test_compute_iou_metrics() -> None:
    """Verify mask and bbox IoU calculation accuracy."""
    # Bbox IoU
    box1 = (0.0, 0.0, 10.0, 10.0)
    box2 = (0.0, 0.0, 10.0, 10.0)
    assert compute_bbox_iou(box1, box2) == 1.0

    box3 = (10.0, 10.0, 20.0, 20.0)
    assert compute_bbox_iou(box1, box3) == 0.0

    box4 = (5.0, 0.0, 15.0, 10.0)  # half overlap
    assert np.isclose(compute_bbox_iou(box1, box4), 50.0 / 150.0)

    # Mask IoU
    m1 = np.zeros((10, 10), dtype=np.uint8)
    m2 = np.zeros((10, 10), dtype=np.uint8)
    m1[0:5, 0:5] = 1
    m2[0:5, 0:5] = 1
    assert compute_mask_iou(m1, m2) == 1.0

    m3 = np.zeros((10, 10), dtype=np.uint8)
    m3[5:10, 5:10] = 1
    assert compute_mask_iou(m1, m3) == 0.0


def test_assemble_tracks_multi_window_stitching() -> None:
    """Verify assembling multiple window cuts produces continuous tracks."""
    # Window 1: frames 0..49
    frames_w1 = {
        i: ObjMask(
            obj="cube",
            frame=i,
            score=0.96,
            bbox_xyxy=(10.0 + i, 20.0, 50.0 + i, 60.0),
            rle="",
            area_px=1600,
            rle_size=(480, 640),
        )
        for i in range(50)
    }
    t1 = Track(
        obj="cube",
        frames=frames_w1,
        backend="modal",
        direction="forward",
        trace_id="w1",
    )

    # Window 2: frames 45..89
    frames_w2 = {
        i: ObjMask(
            obj="cube",
            frame=i,
            score=0.96,
            bbox_xyxy=(10.0 + i, 20.0, 50.0 + i, 60.0),
            rle="",
            area_px=1600,
            rle_size=(480, 640),
        )
        for i in range(45, 90)
    }
    t2 = Track(
        obj="cube",
        frames=frames_w2,
        backend="modal",
        direction="forward",
        trace_id="w2",
    )

    assembled = assemble_tracks(window_cuts=[], raw_tracks=[{"cube": t1}, {"cube": t2}])

    assert "cube" in assembled
    cube_track = assembled["cube"]
    assert len(cube_track.frames) == 90
    assert min(cube_track.frames.keys()) == 0
    assert max(cube_track.frames.keys()) == 89


def test_assemble_tracks_cyclic_consistency_degradation_tripwire() -> None:
    """Verify that cyclic IoU < 0.70 flags score as degraded (< 0.50)."""
    # Overlapping frame 25: Forward and backward tracks agree
    fwd_m_agree = ObjMask(
        obj="cube",
        frame=25,
        score=0.95,
        bbox_xyxy=(100.0, 100.0, 150.0, 150.0),
        rle="",
        area_px=2500,
        rle_size=(480, 640),
    )
    bwd_m_agree = ObjMask(
        obj="cube",
        frame=25,
        score=0.95,
        bbox_xyxy=(100.0, 100.0, 150.0, 150.0),
        rle="",
        area_px=2500,
        rle_size=(480, 640),
    )

    # Overlapping frame 30: Forward and backward tracks severely disagree (divergent tracking)
    fwd_m_diverge = ObjMask(
        obj="cube",
        frame=30,
        score=0.95,
        bbox_xyxy=(100.0, 100.0, 150.0, 150.0),
        rle="",
        area_px=2500,
        rle_size=(480, 640),
    )
    bwd_m_diverge = ObjMask(
        obj="cube",
        frame=30,
        score=0.95,
        bbox_xyxy=(300.0, 300.0, 350.0, 350.0),  # Disjoint
        rle="",
        area_px=2500,
        rle_size=(480, 640),
    )

    t_fwd = Track(
        obj="cube",
        frames={25: fwd_m_agree, 30: fwd_m_diverge},
        backend="modal",
        direction="forward",
        trace_id="fwd",
    )
    t_bwd = Track(
        obj="cube",
        frames={25: bwd_m_agree, 30: bwd_m_diverge},
        backend="modal",
        direction="backward",
        trace_id="bwd",
    )

    assembled = assemble_tracks(window_cuts=[], raw_tracks=[{"cube": t_fwd}, {"cube": t_bwd}])

    cube_track = assembled["cube"]
    assert cube_track.direction == "both"

    # Frame 25 agreed: score is high
    assert cube_track.frames[25].score >= 0.90

    # Frame 30 diverged: score is degraded (< 0.50) per tripwire TR-03
    assert cube_track.frames[30].score < 0.50


def test_assemble_tracks_max_objects_enforcement() -> None:
    """Verify that exceeding 16 objects raises ValueError."""
    tracks_dict = {
        f"obj_{i}": Track(
            obj=f"obj_{i}",
            frames={0: ObjMask(
                obj=f"obj_{i}",
                frame=0,
                score=0.95,
                bbox_xyxy=(0.0, 0.0, 10.0, 10.0),
                rle="",
                area_px=100,
                rle_size=(480, 640),
            )},
            backend="modal",
            direction="forward",
            trace_id=f"t_{i}",
        )
        for i in range(17)
    }
    with pytest.raises(ValueError, match="maximum allowable object limit of 16"):
        assemble_tracks(window_cuts=[], raw_tracks=[tracks_dict])


def test_track_many_dispatcher() -> None:
    """Verify batch track_many executes on multiple jobs."""
    clip = _make_dummy_clip(n_frames=30)
    jobs = [
        {"clip": clip, "f0": 0, "f1": 15, "direction": "forward", "prompts": {"gripper": ["gripper"]}},
        {"clip": clip, "f0": 15, "f1": 30, "direction": "forward", "prompts": {"gripper": ["gripper"]}},
    ]
    results = track_many(jobs, backend="modal")
    assert len(results) == 2
    assert "gripper" in results[0]
    assert "gripper" in results[1]
    assert len(results[0]["gripper"].frames) == 15
    assert len(results[1]["gripper"].frames) == 15
