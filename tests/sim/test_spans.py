"""Unit tests for @span decorator and causal blame attribution.

Per ARCHITECTURE.md §4, §5.7, ADR-0005, and P02 RULING.
"""

from __future__ import annotations

from Kodiac_robotics.sim.env import KinematicMockEnv
from Kodiac_robotics.sim.robot import RobotController
from Kodiac_robotics.sim.spans import SimSpan, find_blame_span


def test_span_decorator_metadata_capture() -> None:
    """Verify @span captures repo-relative paths, line numbers, and exact code statements."""
    env = KinematicMockEnv()
    robot = RobotController(env)
    robot.reset(seed=1)

    # Calling robot methods decorated with @span
    robot.arm.move_to([-0.10, 0.22, 0.15], steps=2)
    robot.gripper.close(steps=2)
    robot.arm.lift(distance=0.05)

    assert len(robot.spans) == 3

    span0 = robot.spans[0]
    assert span0.span_id == 0
    assert span0.actuation_class == "arm.move_to"
    assert span0.func == "move_to"
    assert "\\" not in span0.file
    assert span0.file.endswith("tests/sim/test_spans.py")
    assert span0.line > 0
    assert "robot.arm.move_to" in span0.code
    assert span0.step_start == 0
    assert span0.step_end == 2
    assert span0.t_start_s == 0.0

    span1 = robot.spans[1]
    assert span1.span_id == 1
    assert span1.actuation_class == "gripper.close"
    assert "robot.gripper.close" in span1.code
    assert span1.step_start == 2
    assert span1.step_end == 4


def test_find_blame_span_causal_lookback_moves_with() -> None:
    """SDM Ruling Invariant: moves_with failure at t=3.8s must map to gripper.open at t=3.33s.

    Physical lag test:
    - gripper.open executes at frame 100 (t = 3.33s), ends at frame 105 (t = 3.50s)
    - arm.move_to executes from frame 105 (t = 3.50s) to frame 120 (t = 4.00s)
    - Physical separation (moves_with: T -> F) occurs at frame 114 (t* = 3.80s)
    Naive point-in-time lookup wrongly blames arm.move_to;
    causal lookback window (<= 1.0s) must correctly blame gripper.open.
    """
    spans = [
        SimSpan(
            span_id=0,
            func="move_to",
            file="examples/sim/pick_place.py",
            line=45,
            code="robot.arm.move_to(place_pose)",
            actuation_class="arm.move_to",
            step_start=80,
            step_end=100,
            t_start_s=2.67,
            t_end_s=3.33,
        ),
        SimSpan(
            span_id=1,
            func="open",
            file="examples/sim/pick_place.py",
            line=50,
            code="robot.gripper.open(steps=5)",
            actuation_class="gripper.open",
            step_start=100,
            step_end=105,
            t_start_s=3.33,
            t_end_s=3.50,
        ),
        SimSpan(
            span_id=2,
            func="move_to",
            file="examples/sim/pick_place.py",
            line=55,
            code="robot.arm.move_to(retract_pose)",
            actuation_class="arm.move_to",
            step_start=105,
            step_end=120,
            t_start_s=3.50,
            t_end_s=4.00,
        ),
        SimSpan(
            span_id=3,
            func="wait",
            file="examples/sim/pick_place.py",
            line=60,
            code="robot.wait(0.5)",
            actuation_class="wait",
            step_start=120,
            step_end=135,
            t_start_s=4.00,
            t_end_s=4.50,
        ),
    ]

    # Separation detected at frame 114 (t* = 3.80s, during span 2: arm.move_to)
    blamed = find_blame_span(
        spans=spans,
        frame_idx=114,
        broken_predicate="moves_with",
        causal_window_s=1.0,
        fps=30.0,
    )

    assert blamed is not None
    assert blamed.actuation_class == "gripper.open"
    assert blamed.span_id == 1
    assert "robot.gripper.open" in blamed.code


def test_find_blame_span_lifted_predicate() -> None:
    """Verify lifted failure maps to arm.lift or gripper.close within causal window."""
    spans = [
        SimSpan(
            span_id=0,
            func="close",
            file="examples/sim/pick_place.py",
            line=30,
            code="robot.gripper.close()",
            actuation_class="gripper.close",
            step_start=20,
            step_end=35,
            t_start_s=0.67,
            t_end_s=1.17,
        ),
        SimSpan(
            span_id=1,
            func="lift",
            file="examples/sim/pick_place.py",
            line=35,
            code="robot.arm.lift(0.12)",
            actuation_class="arm.lift",
            step_start=35,
            step_end=55,
            t_start_s=1.17,
            t_end_s=1.83,
        ),
    ]

    blamed = find_blame_span(spans=spans, frame_idx=50, broken_predicate="lifted")
    assert blamed is not None
    assert blamed.actuation_class == "arm.lift"


def test_find_blame_span_causal_window_expiration() -> None:
    """If an action ended well outside causal window (> 1.0s), it is not blamed."""
    spans = [
        SimSpan(
            span_id=0,
            func="open",
            file="examples/sim/pick_place.py",
            line=20,
            code="robot.gripper.open()",
            actuation_class="gripper.open",
            step_start=10,
            step_end=20,
            t_start_s=0.33,
            t_end_s=0.67,
        ),
        SimSpan(
            span_id=1,
            func="move_to",
            file="examples/sim/pick_place.py",
            line=25,
            code="robot.arm.move_to(target)",
            actuation_class="arm.move_to",
            step_start=60,
            step_end=90,
            t_start_s=2.00,
            t_end_s=3.00,
        ),
    ]

    # frame 80 (t* = 2.67s). Span 0 ended at 0.67s (2.0s ago, outside 1.0s window)
    blamed = find_blame_span(
        spans=spans,
        frame_idx=80,
        broken_predicate="moves_with",
        causal_window_s=1.0,
        fps=30.0,
    )
    assert blamed is not None
    # Because gripper.open is expired (> 1.0s ago), it falls back to active motion span
    assert blamed.span_id == 1
