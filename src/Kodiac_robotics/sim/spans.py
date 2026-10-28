"""Simulation span logger and causal blame attribution.

Implements zero-overhead AST/frame span tracking via sys._getframe(1)
and causal lookback window (Δt <= 1.0s) for physical actuation delay.
Per ARCHITECTURE.md §4, §5.7, ADR-0005, and P02 RULING.
"""

from __future__ import annotations

import functools
import linecache
import sys
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel

ActuationClass = Literal[
    "gripper.open",
    "gripper.close",
    "arm.move_to",
    "arm.lift",
    "arm.retract",
    "wait",
]


class SimSpan(BaseModel):
    """Execution span of a high-level robot actuation command."""

    span_id: int
    func: str
    file: str  # Repo-relative forward-slash path, e.g. "examples/sim/pick_place.py"
    line: int  # 1-based caller line number
    code: str  # Exact statement, e.g. "robot.gripper.open()"
    actuation_class: ActuationClass
    step_start: int  # Simulation control step index (0-based)
    step_end: int
    t_start_s: float
    t_end_s: float


# Context variable for thread/task active robot controller
_ACTIVE_ROBOT: ContextVar[Any | None] = ContextVar("_ACTIVE_ROBOT", default=None)


def set_active_robot(robot: Any | None) -> None:
    """Set the currently active robot context."""
    _ACTIVE_ROBOT.set(robot)


def get_active_robot() -> Any | None:
    """Get the currently active robot context."""
    return _ACTIVE_ROBOT.get()


def _find_repo_root() -> Path:
    """Locate repository root by walking upwards looking for pyproject.toml."""
    cur = Path(__file__).resolve().parent
    for parent in [cur, *cur.parents]:
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd().resolve()


_REPO_ROOT = _find_repo_root()


def _normalize_repo_path(filepath: str) -> str:
    """Convert absolute path to repo-relative forward-slash path."""
    try:
        p = Path(filepath).resolve()
        rel = p.relative_to(_REPO_ROOT)
        return rel.as_posix()
    except Exception:
        # Fallback to posix format
        return filepath.replace("\\", "/")


def span(actuation_class: ActuationClass) -> Callable[..., Any]:
    """Decorator capturing caller line, file, code, and simulation step interval."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 1. Inspect caller frame outside sim infrastructure
            frame = sys._getframe(1)
            # Walk back if caller is an internal wrapper inside this file
            while frame and frame.f_code.co_filename == __file__:
                frame = frame.f_back

            caller_file = frame.f_code.co_filename if frame else "unknown"
            caller_line = frame.f_lineno if frame else 0
            rel_file = _normalize_repo_path(caller_file)

            # Retrieve exact code line
            raw_line = linecache.getline(caller_file, caller_line).strip()
            if not raw_line:
                raw_line = f"robot.{actuation_class}()"

            # 2. Resolve robot controller reference
            robot = None
            if args:
                first = args[0]
                if hasattr(first, "_record_span"):
                    robot = first
                elif hasattr(first, "robot") and hasattr(first.robot, "_record_span"):
                    robot = first.robot
            if robot is None:
                robot = get_active_robot()

            # If no robot controller found, invoke without span recording
            if robot is None:
                return fn(*args, **kwargs)

            # 3. Capture interval
            step_start = getattr(robot, "current_step", 0)
            t_start_s = getattr(robot, "current_time_s", 0.0)

            result = fn(*args, **kwargs)

            step_end = getattr(robot, "current_step", step_start)
            t_end_s = getattr(robot, "current_time_s", t_start_s)

            span_id = len(getattr(robot, "spans", []))
            sim_span = SimSpan(
                span_id=span_id,
                func=fn.__name__,
                file=rel_file,
                line=caller_line,
                code=raw_line,
                actuation_class=actuation_class,
                step_start=step_start,
                step_end=step_end,
                t_start_s=round(t_start_s, 4),
                t_end_s=round(t_end_s, 4),
            )
            robot._record_span(sim_span)
            return result

        return wrapper

    return decorator


def find_blame_span(
    spans: list[SimSpan],
    frame_idx: int,
    broken_predicate: str | None = None,
    causal_window_s: float = 1.0,
    fps: float = 30.0,
) -> SimSpan | None:
    """Find the causal actuation span that triggered a failure at frame_idx.

    Implements a backward causal lookback window (Delta t <= causal_window_s,
    default 1.0s) to map physical event lag (e.g. cube separation, dropping,
    or toppling) back to the commanding actuation (e.g. gripper.open),
    rather than mistakenly blaming subsequent statements like arm.move_to or wait.
    """
    if not spans:
        return None

    t_star = frame_idx / fps
    t_min = max(0.0, t_star - causal_window_s)
    # Allow a minor epsilon tolerance (e.g. 1 frame = ~0.033s)
    t_max = t_star + (1.0 / fps)

    # Filter candidate spans whose execution interval overlaps [t_min, t_max]
    # and began at or before t_max
    candidates = [
        s
        for s in spans
        if s.t_start_s <= t_max and s.t_end_s >= t_min
    ]

    if not candidates:
        # Fallback to the latest span that started before or at frame_idx
        preceding = [s for s in spans if s.t_start_s <= t_max]
        return preceding[-1] if preceding else spans[0]

    # Domain causality mapping based on failed predicate
    if broken_predicate == "moves_with":
        # moves_with breaking means the held object parted from the gripper.
        # Primary causal trigger: gripper.open preceding or concurrent with the drop.
        open_spans = [s for s in candidates if s.actuation_class == "gripper.open"]
        if open_spans:
            return open_spans[-1]
        # Secondary: arm.lift / arm.move_to (e.g., dropped during sudden motion)
        motion_spans = [
            s for s in candidates if s.actuation_class in ("arm.lift", "arm.move_to")
        ]
        if motion_spans:
            return motion_spans[-1]

    elif broken_predicate == "lifted":
        # Failed to lift: gripper failed to grasp or arm failed to lift
        lift_spans = [
            s for s in candidates if s.actuation_class in ("arm.lift", "gripper.close")
        ]
        if lift_spans:
            return lift_spans[-1]

    elif broken_predicate in ("on", "inside"):
        # Misplacement: dropped from improper height, offset placement, or failed release
        placement_spans = [
            s
            for s in candidates
            if s.actuation_class in ("gripper.open", "arm.move_to", "arm.retract")
        ]
        if placement_spans:
            return placement_spans[-1]

    elif broken_predicate == "dwell":
        # Failed to dwell or premature disturbance
        dwell_spans = [
            s for s in candidates if s.actuation_class in ("arm.retract", "wait", "gripper.open")
        ]
        if dwell_spans:
            return dwell_spans[-1]

    elif broken_predicate == "near":
        nav_spans = [s for s in candidates if s.actuation_class == "arm.move_to"]
        if nav_spans:
            return nav_spans[-1]

    # General preference: pick the latest non-wait actuation span that started before t_star
    active_non_wait = [
        s for s in candidates if s.actuation_class != "wait" and s.t_start_s <= t_star
    ]
    if active_non_wait:
        return active_non_wait[-1]

    # Fallback to the span covering frame_idx, or the latest candidate
    for s in reversed(candidates):
        if s.step_start <= frame_idx <= s.step_end:
            return s

    return candidates[-1]
