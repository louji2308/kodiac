"""Unit tests for compiler/typecheck.py.

Tests keyframe grounding, embodiment aliasing (Invariant I16), container rim ellipse
fitting, and compile-time diagnostics (E001, E002) per ARCHITECTURE.md §6.1-§6.3.
"""

from __future__ import annotations

import os

import pytest

from Kodiac_robotics.compiler.typecheck import typecheck_and_ground_objects
from Kodiac_robotics.contracts.core import (
    Clip,
    ClipRef,
    GreenTest,
    ObjectDecl,
    ObjMask,
    Track,
)
from Kodiac_robotics.io.clip import open_clip


@pytest.fixture
def correct_clip() -> Clip:
    return open_clip("tests/fixtures/clips/correct_run.mp4")


@pytest.fixture
def stackcube_test() -> GreenTest:
    return GreenTest(
        version="0.1",
        name="test_stackcube",
        objects=[
            ObjectDecl(name="gripper", role="effector"),
            ObjectDecl(name="cube_a", role="rigid", size_cm=4.0),
            ObjectDecl(name="cube_b", role="rigid", size_cm=4.0),
        ],
        steps=[],
    )


def test_typecheck_robot_grounding(correct_clip: Clip, stackcube_test: GreenTest) -> None:
    """Robot clip correctly grounds gripper and objects to robot embodiment baselines."""
    test, baselines = typecheck_and_ground_objects(correct_clip, stackcube_test)

    # Gripper identifier remains canonically 'gripper' (Invariant I16)
    assert any(o.name == "gripper" for o in test.objects)
    assert "gripper" in baselines
    assert baselines["gripper"]["embodiment"] == "robot"
    assert "cube_a" in baselines
    assert "cube_b" in baselines

    for name in ("gripper", "cube_a", "cube_b"):
        info = baselines[name]
        assert info["k0"] > 0.0
        assert info["A0"] > 0
        assert info["score"] >= 0.40
        assert len(info["bbox"]) == 4


def test_typecheck_human_embodiment_aliasing(correct_clip: Clip, stackcube_test: GreenTest) -> None:
    """Invariant I16: When human embodiment is detected, 'gripper' aliases to human hand without changing AST name."""
    os.environ["KODIAC_EMBODIMENT"] = "human"
    try:
        test, baselines = typecheck_and_ground_objects(correct_clip, stackcube_test)
        assert any(o.name == "gripper" for o in test.objects)
        assert baselines["gripper"]["embodiment"] == "human"
    finally:
        os.environ.pop("KODIAC_EMBODIMENT", None)


def test_typecheck_missing_object_e001(correct_clip: Clip) -> None:
    """Undeclared or missing object in keyframe tracking raises E001 diagnostic."""
    test_missing = GreenTest(
        version="0.1",
        name="test_missing",
        objects=[
            ObjectDecl(name="gripper", role="effector"),
            ObjectDecl(name="nonexistent_block_xyz", role="rigid", size_cm=4.0),
        ],
        steps=[],
    )

    with pytest.raises(ValueError, match="E001"):
        typecheck_and_ground_objects(correct_clip, test_missing)


def test_typecheck_duplicate_object_e002(correct_clip: Clip) -> None:
    """Duplicate object declaration in objects list raises E002 diagnostic."""
    test_dup = GreenTest(
        version="0.1",
        name="test_dup",
        objects=[
            ObjectDecl(name="gripper", role="effector"),
            ObjectDecl(name="cubeA", role="rigid", size_cm=4.0),
            ObjectDecl(name="cubeA", role="rigid", size_cm=4.0),
        ],
        steps=[],
    )

    with pytest.raises(ValueError, match="E002"):
        typecheck_and_ground_objects(correct_clip, test_dup)


def test_typecheck_container_rim_fitting() -> None:
    """Container role triggers cv2.fitEllipse rim ellipse extraction."""
    # Synthetic clip & container track with an elliptical mask
    clip = Clip(
        ref=ClipRef(uri="synthetic_container.mp4", source_kind="sim"),
        path_h264="synthetic_container.mp4",
        fps=30.0,
        n_frames=10,
        width=640,
        height=480,
        sha256="synth_cont_sha",
    )

    import cv2
    import numpy as np
    canvas = np.zeros((480, 640), dtype=np.uint8)
    cv2.ellipse(canvas, (320, 240), (80, 40), 15, 0, 360, 1, -1)

    ys, xs = np.where(canvas > 0)
    x1, y1 = float(np.min(xs)), float(np.min(ys))
    x2, y2 = float(np.max(xs)), float(np.max(ys))

    # Simple run-length counts for RLE
    flat = canvas.flatten(order="F")
    diffs = np.diff(flat)
    change_indices = np.where(diffs != 0)[0] + 1
    split_indices = np.concatenate(([0], change_indices, [len(flat)]))
    runs = np.diff(split_indices).tolist()
    if flat[0] == 1:
        runs = [0] + runs

    import json
    rle_str = json.dumps(runs)

    mask = ObjMask(
        obj="bin",
        frame=0,
        score=0.95,
        bbox_xyxy=(x1, y1, x2, y2),
        rle=rle_str,
        area_px=int(len(ys)),
        rle_size=(480, 640),
    )
    track = Track(
        obj="bin",
        frames={0: mask},
        backend="fixture",
        direction="forward",
        trace_id="cont_tr",
    )

    class MockBackend:
        def segment_frames(self, clip, frames, prompts):
            return {"bin": track}

    test_container = GreenTest(
        version="0.1",
        name="test_container",
        objects=[ObjectDecl(name="bin", role="container", size_cm=15.0)],
        steps=[],
    )

    _, baselines = typecheck_and_ground_objects(clip, test_container, backend=MockBackend())

    assert "bin" in baselines
    assert "rim_ellipse" in baselines["bin"]
    rim = baselines["bin"]["rim_ellipse"]
    assert np.isclose(rim["center"][0], 320.0, atol=2.0)
    assert np.isclose(rim["center"][1], 240.0, atol=2.0)
    assert "axes" in rim
    assert "angle_deg" in rim
