"""Unit tests for step-chain logic engine and carried literal persistence."""

from __future__ import annotations

import pytest

from Kodiac_robotics.contracts.core import (
    Atom,
    ClipRef,
    Component,
    Expr,
    PredFrame,
    Provenance,
    ReasonCode,
    RunResult,
    Step,
    Tri,
    Verdict,
)
from Kodiac_robotics.engine.steps import evaluate_step_chain
from Kodiac_robotics.predicates.base import get_atom_key


def _make_pf(atom: Atom, frame: int, tri: Tri, margin: float = 1.0, reason: ReasonCode | None = None) -> PredFrame:
    """Helper to create a PredFrame with a single Component."""
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


def test_step_chain_full_pass():
    """Verify clean 2-step sequence achieves and returns Verdict.PASS."""
    fps = 30.0
    n_frames = 40

    atom_grasp = Atom(kind="pred", name="moves_with", args=["gripper", "red_block"])
    atom_place = Atom(kind="pred", name="on", args=["red_block", "green_block"])

    step_1 = Step(
        index=1,
        name="grasp",
        expr=Expr(op="atom", atom=atom_grasp),
        provenance=Provenance(source="compiler-default"),
    )
    step_2 = Step(
        index=2,
        name="place",
        expr=Expr(op="atom", atom=atom_place),
        provenance=Provenance(source="compiler-default"),
    )

    # Step 1 achieves at frame 10 (3 consecutive Ts: frames 8, 9, 10)
    # Step 2 achieves at frame 25 (3 consecutive Ts: frames 23, 24, 25)
    key_grasp = get_atom_key(atom_grasp)
    key_place = get_atom_key(atom_place)

    frames_grasp = []
    frames_place = []
    for f in range(n_frames):
        # Grasp is T from frame 8 onward
        tri_g = Tri.T if f >= 8 else Tri.F
        frames_grasp.append(_make_pf(atom_grasp, f, tri_g))

        # Place is T from frame 23 onward
        tri_p = Tri.T if f >= 23 else Tri.F
        frames_place.append(_make_pf(atom_place, f, tri_p))

    pred_frames = {key_grasp: frames_grasp, key_place: frames_place}

    verdict, step_results, reasons, events = evaluate_step_chain(
        steps=[step_1, step_2],
        pred_frames_by_atom=pred_frames,
        fps=fps,
    )

    assert verdict == Verdict.PASS
    assert len(step_results) == 2
    assert step_results[0].verdict == Verdict.PASS
    assert step_results[0].frame == 10
    assert step_results[1].verdict == Verdict.PASS
    assert step_results[1].frame == 25
    assert reasons == []

    # Verify event generation
    event_kinds = [e.kind for e in events]
    assert "grasped" in event_kinds
    assert "settled" in event_kinds


def test_carried_literal_persistence_failure():
    """Verify Step 1 grasp state (moves_with) persists during Step 2 place and catches drops."""
    fps = 30.0
    n_frames = 40

    atom_grasp = Atom(kind="pred", name="moves_with", args=["gripper", "red_block"])
    atom_place = Atom(kind="pred", name="on", args=["red_block", "green_block"])

    step_1 = Step(
        index=1,
        name="grasp",
        expr=Expr(op="atom", atom=atom_grasp),
        provenance=Provenance(source="compiler-default"),
    )
    step_2 = Step(
        index=2,
        name="place",
        expr=Expr(op="atom", atom=atom_place),
        provenance=Provenance(source="compiler-default"),
    )

    key_grasp = get_atom_key(atom_grasp)
    key_place = get_atom_key(atom_place)

    frames_grasp = []
    frames_place = []
    for f in range(n_frames):
        # Grasp becomes T at frame 8, but DROPS at frame 18 (flips to F)
        if 8 <= f < 18:
            tri_g = Tri.T
        else:
            tri_g = Tri.F
        frames_grasp.append(_make_pf(atom_grasp, f, tri_g, margin=-1.5 if f >= 18 else 1.0))

        # Place would have achieved at frame 25, but object was already dropped at frame 18
        tri_p = Tri.T if f >= 23 else Tri.F
        frames_place.append(_make_pf(atom_place, f, tri_p))

    pred_frames = {key_grasp: frames_grasp, key_place: frames_place}

    verdict, step_results, reasons, events = evaluate_step_chain(
        steps=[step_1, step_2],
        pred_frames_by_atom=pred_frames,
        fps=fps,
    )

    # Overall verdict must be FAIL
    assert verdict == Verdict.FAIL
    assert step_results[0].verdict == Verdict.PASS
    assert step_results[0].frame == 10

    # Step 2 must fail at the drop frame (18)
    assert step_results[1].verdict == Verdict.FAIL
    assert step_results[1].frame == 18
    assert "carried invariant" in step_results[1].evidence[0]

    # Check that release event was generated
    event_kinds = [e.kind for e in events]
    assert "released" in event_kinds


def test_carried_literal_negation_in_release_step():
    """Verify that explicitly negated literals (e.g. not moves_with in release) do NOT cause failure."""
    fps = 30.0
    n_frames = 30

    atom_grasp = Atom(kind="pred", name="moves_with", args=["gripper", "red_block"])

    step_1 = Step(
        index=1,
        name="grasp",
        expr=Expr(op="atom", atom=atom_grasp),
        provenance=Provenance(source="compiler-default"),
    )
    # Step 2 is release: not moves_with
    step_2 = Step(
        index=2,
        name="release",
        expr=Expr(op="not", children=[Expr(op="atom", atom=atom_grasp)]),
        provenance=Provenance(source="compiler-default"),
    )

    key_grasp = get_atom_key(atom_grasp)
    frames_grasp = []
    for f in range(n_frames):
        # Grasp holds from frame 5 to 15, then releases (F from 16 onward)
        tri_g = Tri.T if 5 <= f <= 15 else Tri.F
        frames_grasp.append(_make_pf(atom_grasp, f, tri_g))

    pred_frames = {key_grasp: frames_grasp}

    verdict, step_results, reasons, events = evaluate_step_chain(
        steps=[step_1, step_2],
        pred_frames_by_atom=pred_frames,
        fps=fps,
    )

    assert verdict == Verdict.PASS
    assert step_results[0].verdict == Verdict.PASS
    assert step_results[0].frame == 7  # 3 confirmations (5, 6, 7)
    assert step_results[1].verdict == Verdict.PASS
    assert step_results[1].frame == 18  # 3 confirmations of not moves_with (16, 17, 18)


def test_cant_tell_bubbles_reason_codes_and_validates_schema():
    """CRITICAL INVARIANT: CANT_TELL bubbles ReasonCode so RunResult passes Pydantic model validation."""
    fps = 30.0
    n_frames = 20

    atom = Atom(kind="pred", name="inside", args=["red_block", "bin"])
    step = Step(
        index=1,
        name="contain",
        expr=Expr(op="atom", atom=atom),
        provenance=Provenance(source="compiler-default"),
    )

    # Atom frames are all UNKNOWN due to camera occlusion
    key = get_atom_key(atom)
    frames = [
        _make_pf(atom, f, Tri.U, margin=0.0, reason=ReasonCode.OCCLUDED)
        for f in range(n_frames)
    ]
    pred_frames = {key: frames}

    verdict, step_results, reasons, events = evaluate_step_chain(
        steps=[step],
        pred_frames_by_atom=pred_frames,
        fps=fps,
    )

    assert verdict == Verdict.CANT_TELL
    assert step_results[0].verdict == Verdict.CANT_TELL
    assert ReasonCode.OCCLUDED in reasons
    assert len(reasons) >= 1

    # Verify that RunResult validates cleanly under Pydantic schema
    run_result = RunResult(
        run_id="run_test_001",
        test_name="contain_test",
        test_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        config_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        clip=ClipRef(uri="file://test.mp4", source_kind="sim"),
        verdict=verdict,
        exit_code=2,
        steps=step_results,
        reasons=reasons,
        nonce="0123456789abcdef",
        trace_path="runs/test/trace.jsonl",
        created_at="2026-10-28T18:00:00Z",
    )
    assert run_result.verdict == Verdict.CANT_TELL
    assert run_result.reasons == [ReasonCode.OCCLUDED]

    # Verify that an empty reasons list on CANT_TELL raises ValueError per contract
    with pytest.raises(ValueError, match="Verdict.CANT_TELL requires at least one ReasonCode"):
        RunResult(
            run_id="run_invalid",
            test_name="contain_test",
            test_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            config_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            clip=ClipRef(uri="file://test.mp4", source_kind="sim"),
            verdict=Verdict.CANT_TELL,
            exit_code=2,
            steps=step_results,
            reasons=[],  # Empty should fail!
            nonce="0123456789abcdef",
            trace_path="runs/test/trace.jsonl",
            created_at="2026-10-28T18:00:00Z",
        )
