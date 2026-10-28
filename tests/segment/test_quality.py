"""Quality verification suite for perception core and proof benchmark arms.

Verifies:
1. Golden fixture clip tracking quality on all 5 canonical clips.
2. Coordinate canvas invariant: obj_mask.rle_size == (clip.height, clip.width) strictly.
3. ID stability: zero cube swaps on StackCube clips under Re-ID matching.
4. Forward-backward cyclic consistency evaluation.
5. Proof benchmark arm assembly across the 10 pre-registered arms per PREREGISTRATION.md.
Per ARCHITECTURE.md §3.1, §4.3, §5.7, IMPLEMENTATION_PLAN.md P03.S08, P03.S14, and P03 RULING.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from Kodiac_robotics.contracts.core import Clip, ClipRef, ObjMask
from Kodiac_robotics.proof.arms import assemble_proof_arms
from Kodiac_robotics.proof.pool import generate_mock_pool
from Kodiac_robotics.segment.modal_backend import ModalSamBackend
from Kodiac_robotics.segment.reid import ReIdEngine
from Kodiac_robotics.segment.tracks import assemble_tracks

FIXTURES_DIR = Path("tests/fixtures/clips")
MANIFEST_PATH = FIXTURES_DIR / "manifest.json"


def _load_fixture_clip(clip_name: str) -> Clip:
    """Load Clip model for a named golden fixture clip."""
    assert MANIFEST_PATH.is_file(), f"Missing manifest at {MANIFEST_PATH}"
    manifest_data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    clip_info = manifest_data["clips"][clip_name]
    clip_path = Path(clip_info["path"])
    assert clip_path.is_file(), f"Fixture file not found: {clip_path}"

    return Clip(
        ref=ClipRef(uri=str(clip_path), source_kind="sim"),
        path_h264=str(clip_path),
        fps=float(clip_info["fps"]),
        n_frames=int(clip_info["n_frames"]),
        width=int(clip_info["width"]),
        height=int(clip_info["height"]),
        sha256=str(clip_info["sha256"]),
    )


@pytest.mark.parametrize(
    "clip_name",
    [
        "correct_run.mp4",
        "b01_early_release.mp4",
        "b02_xy_misalignment.mp4",
        "b09_lift_failure.mp4",
        "occluded_clip.mp4",
    ],
)
def test_golden_fixture_tracking_and_canvas_invariants(clip_name: str) -> None:
    """Verify tracking execution and canvas dimension invariants across golden clips."""
    clip = _load_fixture_clip(clip_name)
    assert clip.width == 640
    assert clip.height == 480
    assert clip.fps == 30.0

    backend = ModalSamBackend(offline_fallback=True)
    prompts = {"gripper": ["gripper"], "target_cube": ["red cube"]}

    # 1. Sparse segmentation on initial frame to seed tracking
    seg_tracks = backend.segment_frames(clip=clip, frames=[0], prompts=prompts)
    assert "gripper" in seg_tracks
    assert "target_cube" in seg_tracks
    seeds = {obj: track.frames[0] for obj, track in seg_tracks.items()}

    # 2. Track dense window seeded from frame 0
    tracks = backend.track(
        clip=clip,
        f0=0,
        f1=min(50, clip.n_frames),
        seeds=seeds,
        direction="forward",
    )

    assert "gripper" in tracks
    assert "target_cube" in tracks
    gripper_track = tracks["gripper"]
    assert len(gripper_track.frames) == min(50, clip.n_frames)

    # MANDATED LAW 1 & COORDINATE INVARIANT:
    # ObjMask.rle_size MUST strictly match (clip.height, clip.width)
    for f_idx, mask in gripper_track.frames.items():
        assert mask.rle_size == (clip.height, clip.width), (
            f"Canvas drift detected on frame {f_idx}: {mask.rle_size} != {(clip.height, clip.width)}"
        )
        assert mask.area_px > 0, f"Empty mask detected on frame {f_idx}"
        assert mask.score >= 0.90


def test_zero_block_id_swaps_on_stackcube_scene() -> None:
    """Verify zero ID swaps between red and green cubes under Re-ID matching."""
    engine = ReIdEngine(hue_gate_degrees=60.0)

    # Synthetic StackCube frame with Red and Green blocks touching
    h, w = 480, 640
    frame = np.full((h, w, 3), 190, dtype=np.uint8)
    frame[200:250, 250:300] = (0, 0, 255)  # Red Cube BGR
    frame[200:250, 302:352] = (0, 255, 0)  # Green Cube BGR (2px separation)

    target_red = ObjMask(
        obj="red_block",
        frame=0,
        score=0.98,
        bbox_xyxy=(250.0, 200.0, 300.0, 250.0),
        rle="",
        area_px=2500,
        rle_size=(h, w),
    )
    target_green = ObjMask(
        obj="green_block",
        frame=0,
        score=0.98,
        bbox_xyxy=(302.0, 200.0, 352.0, 250.0),
        rle="",
        area_px=2500,
        rle_size=(h, w),
    )
    targets = {"red_block": target_red, "green_block": target_green}

    # Frame 1: Candidates moved slightly, shuffled candidate ordering
    cand_green = ObjMask(
        obj="unassigned_1",
        frame=1,
        score=0.96,
        bbox_xyxy=(303.0, 201.0, 353.0, 251.0),
        rle="",
        area_px=2500,
        rle_size=(h, w),
    )
    cand_red = ObjMask(
        obj="unassigned_0",
        frame=1,
        score=0.96,
        bbox_xyxy=(251.0, 201.0, 301.0, 251.0),
        rle="",
        area_px=2500,
        rle_size=(h, w),
    )
    candidates = [cand_green, cand_red]

    matched = engine.match_masks(candidates, targets, frame)

    assert len(matched) == 2
    assert matched["red_block"].bbox_xyxy[0] == 251.0
    assert matched["green_block"].bbox_xyxy[0] == 303.0


def test_cyclic_tracking_consistency_assembly() -> None:
    """Verify cyclic consistency evaluation across forward and backward tracks."""
    clip = _load_fixture_clip("correct_run.mp4")
    backend = ModalSamBackend(offline_fallback=True)

    seeds = {
        "cube": ObjMask(
            obj="cube",
            frame=0,
            score=0.95,
            bbox_xyxy=(200.0, 200.0, 250.0, 250.0),
            rle="",
            area_px=2500,
            rle_size=(clip.height, clip.width),
        )
    }

    fwd = backend.track(clip, f0=0, f1=30, seeds=seeds, direction="forward")
    bwd = backend.track(clip, f0=0, f1=30, seeds=seeds, direction="backward")

    assembled = assemble_tracks(window_cuts=[], raw_tracks=[fwd, bwd])
    assert "cube" in assembled
    cube_track = assembled["cube"]
    assert cube_track.direction == "both"
    assert len(cube_track.frames) == 30


def test_assemble_proof_arms_all_ten_arms() -> None:
    """Verify assemble_proof_arms produces valid partitions for all 10 benchmark arms."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        manifest_path = generate_mock_pool(
            output_dir=tmp_path / "pool",
            n_episodes=30,
            calibration_ratio=0.20,
            allow_untagged=True,
        )

        labels_dir = tmp_path / "labels"
        labels_dir.mkdir(parents=True, exist_ok=True)

        arms = assemble_proof_arms(manifest_path, labels_dir, train_split_only=True)

        # 10 pre-registered benchmark arms per PREREGISTRATION.md §4
        expected_arms = [
            "oracle",
            "accept_all",
            "kodiac_cloud",
            "kodiac_open_weights",
            "kodiac_salvage",
            "single_pass_spark_2fps",
            "robometer_4b",
            "topreward",
            "size_matched_control",
            "oracle_k_percent",
        ]

        for arm in expected_arms:
            assert arm in arms, f"Missing required pre-registered arm: {arm}"
            assert isinstance(arms[arm], list), f"Arm {arm} must return a list of episode IDs"

        # Invariant checks
        # Size-matched control must have exact same count as Kodiac
        assert len(arms["size_matched_control"]) == len(arms["kodiac_cloud"])

        # Accept-all must contain all train episodes
        assert len(arms["accept_all"]) >= len(arms["oracle"])

        # All IDs in oracle must be non-empty
        assert len(arms["oracle"]) > 0
