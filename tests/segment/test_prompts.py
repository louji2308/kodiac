"""Tests for prompt library, effector aliasing, and embodiment detection.

Validates Invariant I16 (gripper <-> hand aliasing) and confidence probing per P03.S05.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from Kodiac_robotics.contracts.core import Clip, ClipRef, ObjMask, Track
from Kodiac_robotics.segment.prompts import (
    detect_embodiment,
    get_prompt_set,
)


def _make_dummy_clip(uri: str = "file://dummy.mp4", dataset: str = "maniskill", source_kind: str = "sim") -> Clip:
    return Clip(
        ref=ClipRef(uri=uri, source_kind=source_kind, dataset=dataset),
        path_h264="dummy.mp4",
        fps=30.0,
        n_frames=90,
        width=640,
        height=480,
        sha256="dummy_sha256",
    )


def test_robot_prompt_set_roles():
    """Verify robot prompt set contains manipulator roles."""
    prompts = get_prompt_set("stack_cube", embodiment="robot")
    assert "gripper" in prompts
    assert "cube_a" in prompts
    assert "cube_b" in prompts
    assert "target" in prompts
    assert any("robot" in p for p in prompts["gripper"])


def test_human_prompt_set_effector_aliasing():
    """Verify Invariant I16: human embodiment aliases gripper role to hand prompts."""
    prompts = get_prompt_set("stack_cube", embodiment="human")
    assert "gripper" in prompts
    # 'gripper' key must contain human hand prompts for human embodiment
    assert any("hand" in p for p in prompts["gripper"])
    assert not any("robot" in p for p in prompts["gripper"])


def test_generic_task_returns_full_library():
    """Verify unknown or general task returns complete role library."""
    prompts = get_prompt_set("arbitrary_task", embodiment="robot")
    expected_roles = {"gripper", "fingers", "cube_a", "cube_b", "target", "container"}
    for role in expected_roles:
        assert role in prompts


def test_detect_embodiment_with_backend_probe():
    """Verify backend probe scoring human hand higher than robot gripper."""
    clip = _make_dummy_clip()
    mock_backend = MagicMock()

    # Frame 0 mask with higher human hand score
    hand_mask = ObjMask(
        obj="human_hand",
        frame=0,
        score=0.92,
        bbox_xyxy=(10.0, 10.0, 50.0, 50.0),
        rle="123",
        area_px=100,
        rle_size=(480, 640),
    )
    gripper_mask = ObjMask(
        obj="robot_gripper",
        frame=0,
        score=0.21,
        bbox_xyxy=(10.0, 10.0, 50.0, 50.0),
        rle="123",
        area_px=100,
        rle_size=(480, 640),
    )

    mock_backend.segment_frames.return_value = {
        "human_hand": Track(
            obj="human_hand",
            frames={0: hand_mask},
            backend="api",
            direction="forward",
            trace_id="test",
        ),
        "robot_gripper": Track(
            obj="robot_gripper",
            frames={0: gripper_mask},
            backend="api",
            direction="forward",
            trace_id="test",
        ),
    }

    embodiment = detect_embodiment(clip, [0], backend=mock_backend)
    assert embodiment == "human"


def test_detect_embodiment_metadata_fallback():
    """Verify metadata heuristics when backend is absent."""
    sim_clip = _make_dummy_clip(source_kind="sim")
    assert detect_embodiment(sim_clip, [0]) == "robot"

    droid_clip = _make_dummy_clip(uri="file://droid/run1.mp4", dataset="droid", source_kind="real")
    assert detect_embodiment(droid_clip, [0]) == "robot"

    human_clip = _make_dummy_clip(uri="file://ego4d/demo1.mp4", dataset="ego4d", source_kind="demo")
    assert detect_embodiment(human_clip, [0]) == "human"


def test_detect_embodiment_env_override(monkeypatch):
    """Verify KODIAC_EMBODIMENT environment variable override."""
    clip = _make_dummy_clip(source_kind="sim")
    monkeypatch.setenv("KODIAC_EMBODIMENT", "human")
    assert detect_embodiment(clip, [0]) == "human"
