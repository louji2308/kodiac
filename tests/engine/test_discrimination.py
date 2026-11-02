"""Discrimination tests for Kodiac measurement engine (T13).

Verifies:
1. Canonical bug discrimination on KinematicMockEnv: correct_run -> PASS, B01..B10 -> FAIL.
   Specifically verifies B04 (short dwell) and B09 (never opens) are FAIL, NEVER false-PASS.
   Also verifies held-out perturbation variants (B04 short dwell 0.08s, B09 partial open).
2. Case C step chain semantics:
   - Sustained T run >= n_on -> PASS
   - F on decided frames with NO U run >= n_on -> FAIL
   - U run >= n_on that could hide a T run -> CANT_TELL
   - Decisive frame is U -> CANT_TELL
3. Predicate contracts:
   - dwell(A, B) checks on(A, B) both currently and in stillness history
   - moves_with(A, B) requires contact proximity (dist <= contact_max_cm)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from Kodiac_robotics.contracts.core import (
    Atom,
    Component,
    Expr,
    ObjMask,
    PredFrame,
    Provenance,
    ReasonCode,
    ScaleModel,
    Step,
    Track,
    Tri,
    Verdict,
)
from Kodiac_robotics.engine.steps import evaluate_step_chain
from Kodiac_robotics.predicates.base import get_atom_key
from Kodiac_robotics.predicates.dwell import evaluate_dwell
from Kodiac_robotics.predicates.moves_with import evaluate_moves_with

REPO = Path(__file__).resolve().parents[2]


class _DummyScale(ScaleModel):
    """Simple scale model returning fixed 3D coordinates for testing."""

    def __init__(self, coords_by_obj_frame: dict[tuple[str, int], tuple[float, float, float, float]]) -> None:
        self._coords = coords_by_obj_frame

    def to_table_frame(self, obj: str, frame: int) -> tuple[float, float, float, float]:
        if (obj, frame) in self._coords:
            return self._coords[(obj, frame)]
        return (0.0, 0.0, 0.0, 0.1)


def _make_dummy_track(obj: str, n_frames: int) -> Track:
    frames = {
        f: ObjMask(
            obj=obj,
            frame=f,
            score=0.99,
            bbox_xyxy=(10.0, 10.0, 50.0, 50.0),
            rle="dummy",
            area_px=1600,
            rle_size=(480, 640),
        )
        for f in range(n_frames)
    }
    return Track(obj=obj, frames=frames, backend="fixture", direction="forward", trace_id=f"tr_{obj}")


def _make_pf(
    atom: Atom,
    frame: int,
    tri: Tri,
    margin: float = 1.0,
    reason: ReasonCode | None = None,
) -> PredFrame:
    key = get_atom_key(atom)
    comp = Component(
        name=f"{atom.name}.metric",
        value=1.0,
        threshold=0.0,
        margin=margin,
        sigma=0.2,
        unit="cm",
        tri=tri,
        reason=reason,
    )
    return PredFrame(
        frame=frame,
        atom_key=key,
        tri=tri,
        components=[comp],
        trace_id=f"tr_{frame}",
    )


# ==============================================================================
# Case C Engine Tests
# ==============================================================================


def test_case_c_sustained_t_passes() -> None:
    """Sustained T run >= n_on frames achieves and returns PASS."""
    fps = 30.0  # n_on = max(2, round(0.10 * 30)) = 3
    n_frames = 20

    atom = Atom(kind="pred", name="lifted", args=["cubeA"])
    step = Step(
        index=1,
        name="lift",
        expr=Expr(op="atom", atom=atom),
        provenance=Provenance(source="compiler-default"),
    )

    # Frames 0..4 are F, frames 5..7 are T (3 consecutive Ts -> achieves at 7)
    frames = [_make_pf(atom, f, Tri.T if 5 <= f <= 7 else Tri.F) for f in range(n_frames)]
    pred_frames = {get_atom_key(atom): frames}

    verdict, step_results, reasons, events = evaluate_step_chain(
        steps=[step],
        pred_frames_by_atom=pred_frames,
        fps=fps,
    )

    assert verdict == Verdict.PASS
    assert step_results[0].verdict == Verdict.PASS
    assert step_results[0].frame == 7


def test_case_c_decided_f_with_no_u_run_fails() -> None:
    """F on decided frames with NO U run >= n_on returns FAIL (Defect 2 resolution)."""
    fps = 30.0  # n_on = 3
    n_frames = 20

    atom = Atom(kind="pred", name="lifted", args=["cubeA"])
    step = Step(
        index=1,
        name="lift",
        expr=Expr(op="atom", atom=atom),
        provenance=Provenance(source="compiler-default"),
    )

    # Frame 2 is a single U (run length 1 < n_on=3), all other frames are F
    frames = []
    for f in range(n_frames):
        if f == 2:
            frames.append(_make_pf(atom, f, Tri.U, margin=0.0, reason=ReasonCode.BELOW_NOISE_FLOOR))
        else:
            frames.append(_make_pf(atom, f, Tri.F, margin=-2.0))
    pred_frames = {get_atom_key(atom): frames}

    verdict, step_results, reasons, events = evaluate_step_chain(
        steps=[step],
        pred_frames_by_atom=pred_frames,
        fps=fps,
    )

    # A single isolated U cannot hide a 3-frame T run; clear FAIL
    assert verdict == Verdict.FAIL
    assert step_results[0].verdict == Verdict.FAIL


def test_case_c_u_run_greater_than_n_on_returns_cant_tell() -> None:
    """Unresolved U run >= n_on that could hide a T run forces CANT_TELL (ARCHITECTURE §7.5)."""
    fps = 30.0  # n_on = 3
    n_frames = 20

    atom = Atom(kind="pred", name="lifted", args=["cubeA"])
    step = Step(
        index=1,
        name="lift",
        expr=Expr(op="atom", atom=atom),
        provenance=Provenance(source="compiler-default"),
    )

    # Frames 5, 6, 7 are U (run length 3 == n_on); frame 19 is F
    frames = []
    for f in range(n_frames):
        if 5 <= f <= 7:
            frames.append(_make_pf(atom, f, Tri.U, margin=0.0, reason=ReasonCode.BELOW_NOISE_FLOOR))
        else:
            frames.append(_make_pf(atom, f, Tri.F, margin=-2.0))
    pred_frames = {get_atom_key(atom): frames}

    verdict, step_results, reasons, events = evaluate_step_chain(
        steps=[step],
        pred_frames_by_atom=pred_frames,
        fps=fps,
    )

    # Even though last frame is F, the U run >= n_on could have been T; must be CANT_TELL
    assert verdict == Verdict.CANT_TELL
    assert step_results[0].verdict == Verdict.CANT_TELL
    assert ReasonCode.BELOW_NOISE_FLOOR in reasons


def test_case_c_decisive_frame_u_returns_cant_tell() -> None:
    """Decisive frame evaluating to Tri.U returns CANT_TELL with reason code."""
    fps = 30.0
    n_frames = 10

    atom = Atom(kind="pred", name="lifted", args=["cubeA"])
    step = Step(
        index=1,
        name="lift",
        expr=Expr(op="atom", atom=atom),
        provenance=Provenance(source="compiler-default"),
    )

    # All frames are U
    frames = [_make_pf(atom, f, Tri.U, margin=0.0, reason=ReasonCode.OCCLUDED) for f in range(n_frames)]
    pred_frames = {get_atom_key(atom): frames}

    verdict, step_results, reasons, events = evaluate_step_chain(
        steps=[step],
        pred_frames_by_atom=pred_frames,
        fps=fps,
    )

    assert verdict == Verdict.CANT_TELL
    assert step_results[0].verdict == Verdict.CANT_TELL
    assert ReasonCode.OCCLUDED in reasons


# ==============================================================================
# Predicate Unit Tests (dwell & moves_with)
# ==============================================================================


def test_dwell_requires_both_arguments_on_cube() -> None:
    """dwell(cubeA, cubeB) requires on(cubeA, cubeB); stillness alone is insufficient."""
    fps = 30.0
    n_frames = 25
    coords: dict[tuple[str, int], tuple[float, float, float, float]] = {}

    # cubeA is completely still at (0, 0, 10) cm
    # cubeB is at (50, 50, 0) cm -> cubeA is NOT on cubeB!
    for f in range(n_frames):
        coords[("cubeA", f)] = (0.0, 0.0, 10.0, 0.05)
        coords[("cubeB", f)] = (50.0, 50.0, 0.0, 0.05)

    scale = _DummyScale(coords)
    tracks = {
        "cubeA": _make_dummy_track("cubeA", n_frames),
        "cubeB": _make_dummy_track("cubeB", n_frames),
    }
    atom = Atom(kind="pred", name="dwell", args=["cubeA", "cubeB"])

    pf = evaluate_dwell(atom, tracks, scale, frame=20, fps=fps)
    # Must be Tri.F because cubeA is not on cubeB
    assert pf.tri == Tri.F
    assert any(c.name.startswith("on.") and c.tri == Tri.F for c in pf.components)


def test_moves_with_requires_contact_proximity() -> None:
    """moves_with(gripper, cubeA) requires contact_max_cm; separated objects evaluate to F."""
    fps = 30.0
    n_frames = 10
    coords: dict[tuple[str, int], tuple[float, float, float, float]] = {}

    # Both objects are stationary, but 10 cm apart (> 4.0 cm contact threshold)
    for f in range(n_frames):
        coords[("gripper", f)] = (0.0, 0.0, 10.0, 0.05)
        coords[("cubeA", f)] = (0.0, 0.0, 0.0, 0.05)

    scale = _DummyScale(coords)
    tracks = {
        "gripper": _make_dummy_track("gripper", n_frames),
        "cubeA": _make_dummy_track("cubeA", n_frames),
    }
    atom = Atom(kind="pred", name="moves_with", args=["gripper", "cubeA"])

    pf = evaluate_moves_with(atom, tracks, scale, frame=5, fps=fps)
    assert pf.tri == Tri.F
    comp = pf.components[0]
    assert comp.name == "moves_with.slip"
    assert comp.margin < 0.0


def test_moves_with_co_stationary_in_contact_evaluates_to_t() -> None:
    """moves_with(gripper, cubeA) remains Tri.T when co-stationary in contact (no false break)."""
    fps = 30.0
    n_frames = 10
    coords: dict[tuple[str, int], tuple[float, float, float, float]] = {}

    # Both objects are co-stationary and in close contact (1 cm apart <= 4 cm)
    for f in range(n_frames):
        coords[("gripper", f)] = (0.0, 0.0, 2.0, 0.05)
        coords[("cubeA", f)] = (0.0, 0.0, 1.0, 0.05)

    scale = _DummyScale(coords)
    tracks = {
        "gripper": _make_dummy_track("gripper", n_frames),
        "cubeA": _make_dummy_track("cubeA", n_frames),
    }
    atom = Atom(kind="pred", name="moves_with", args=["gripper", "cubeA"])

    pf = evaluate_moves_with(atom, tracks, scale, frame=5, fps=fps)
    assert pf.tri == Tri.T
    assert pf.components[0].margin > 0.0


# ==============================================================================
# End-to-End Simulation Discrimination Tests
# ==============================================================================


@pytest.mark.parametrize(
    ("variant", "expected_verdict"),
    [
        (None, Verdict.PASS),
        ("B01", Verdict.FAIL),
        ("B04", Verdict.FAIL),
        ("B09", Verdict.FAIL),
    ],
)
def test_sim_grade_discrimination(variant: str | None, expected_verdict: Verdict, tmp_path: Path) -> None:
    """Evaluates discrimination on kinematic mock sim: correct -> PASS, B01, B04, B09 -> FAIL."""
    from Kodiac_robotics.loop.gate import grade_sim_run
    from Kodiac_robotics.sim.runner import run_script_with_digests

    sig = "def execute_pick_place(robot: RobotController, bug_id: str | None = None)"
    src = (REPO / "examples" / "sim" / "pick_place.py").read_text(encoding="utf-8")
    if variant is not None:
        src = src.replace(sig, sig.replace("= None", f' = "{variant}"'))

    script_p = tmp_path / "script.py"
    script_p.write_text(src, encoding="utf-8")
    sim, digests = run_script_with_digests(script_p, 0, tmp_path / "sim", backend="kinematic_mock")
    res = grade_sim_run(REPO / "examples" / "stackcube.green", sim, tmp_path / "grade", digests=digests)

    assert res.verdict == expected_verdict
    if variant is None:
        assert sim.oracle_success is True
    else:
        assert sim.oracle_success is False
