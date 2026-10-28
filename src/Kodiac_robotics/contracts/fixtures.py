"""Synthetic test doubles and factory functions for Kodiac data models.

Provides canonical, deterministic mock fixtures for offline testing and CI.
Per IP-P01-D1-1 and ARCHITECTURE.md §4.
"""

from __future__ import annotations

import secrets
import time

from Kodiac_robotics.contracts.core import (
    Atom,
    Blame,
    Clip,
    ClipRef,
    CodeLocation,
    Component,
    Event,
    Expr,
    FactTable,
    GreenLock,
    GreenTest,
    Hint,
    ObjectDecl,
    ObjMask,
    Param,
    Provenance,
    ReasonCode,
    RunResult,
    Step,
    StepResult,
    Track,
    Tri,
    Verdict,
)


def make_dummy_clip(
    uri: str = "file://examples/clips/stack_blocks.mp4",
    fps: float = 30.0,
    n_frames: int = 150,
    width: int = 640,
    height: int = 480,
    sha256: str = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    source_kind: str = "demo",
) -> Clip:
    """Create a canonical Clip test double."""
    return Clip(
        ref=ClipRef(uri=uri, source_kind=source_kind),  # type: ignore[arg-type]
        path_h264="examples/clips/stack_blocks.mp4",
        fps=fps,
        n_frames=n_frames,
        width=width,
        height=height,
        sha256=sha256,
    )


def make_dummy_greentest(
    name: str = "stack_blocks",
    version: str = "0.1",
) -> GreenTest:
    """Create a canonical GreenTest test double."""
    prov = Provenance(
        quote="Stack the red block on top of the green block.",
        t_start=0.0,
        t_end=3.5,
        source="voice",
    )
    objects = [
        ObjectDecl(name="gripper", role="effector"),
        ObjectDecl(name="red_block", role="rigid", prompt="red cube on table"),
        ObjectDecl(name="green_block", role="rigid", prompt="green cube on table"),
    ]
    step1 = Step(
        index=1,
        name="lift_red",
        expr=Expr(
            op="atom",
            atom=Atom(
                kind="pred",
                name="lifted",
                args=["red_block"],
                params=[Param(name="min_cm", op=">=", value=5.0)],
            ),
        ),
        provenance=prov,
    )
    step2 = Step(
        index=2,
        name="stack_on_green",
        expr=Expr(
            op="atom",
            atom=Atom(
                kind="pred",
                name="on",
                args=["red_block", "green_block"],
                params=[Param(name="align_xy", op="<=", value=1.5)],
            ),
        ),
        provenance=prov,
    )
    return GreenTest(
        version="0.1",
        name=name,
        objects=objects,
        steps=[step1, step2],
        header_comment="Canonical stack blocks fixture test",
    )


def make_dummy_blame(
    step_index: int = 2,
    step_name: str = "stack_on_green",
    t_star_s: float = 3.8,
    frame: int = 114,
    fps: float = 30.0,
) -> Blame:
    """Create a canonical Blame causal attribution double."""
    facts = FactTable(
        t_star_s=t_star_s,
        frame=frame,
        fps=fps,
        sigma_frames=1.2,
        step_index=step_index,
        step_name=step_name,
        literal="on(red_block, green_block)",
        transition="T->F",
        facts={
            "align_xy": {
                "value": 3.4,
                "sigma": 0.2,
                "unit": "cm",
                "threshold": 1.5,
                "ref": "green_block",
            },
            "contact": {"value": 0.0, "sigma": 0.0, "unit": "ratio"},
        },
        code_location=CodeLocation(
            file="policies/pick_and_place.py",
            line=48,
            code="gripper.open()",
            span_id=102,
        ),
        evidence=["runs/run_001/evidence/f0114_overlay.png"],
        trace_ids=["tr_blame_001"],
    )
    hint = Hint(
        variable="target_xy",
        delta=[-1.9, 0.0],
        unit="cm",
        move="shift approach backward along X",
        basis="align_xy exceeded threshold by 1.9 cm at release onset",
    )
    return Blame(
        facts=facts,
        summary="Released red_block 1.9 cm off-center from green_block at frame 114 (t=3.80s).",
        summary_source="muse-spark",
        hint=hint,
        warnings=[],
    )


def make_dummy_runresult(
    verdict: Verdict = Verdict.FAIL,
    is_fixture: bool = True,
    run_id: str = "run_dummy_001",
    test_name: str = "stack_blocks",
    nonce: str | None = None,
) -> RunResult:
    """Create a canonical RunResult test double."""
    if nonce is None:
        nonce = secrets.token_hex(8)  # 16 characters lowercase hex

    reasons: list[ReasonCode] = []
    if verdict == Verdict.CANT_TELL:
        reasons.append(ReasonCode.OCCLUDED)

    blame_obj = make_dummy_blame() if verdict == Verdict.FAIL else None
    exit_code: int = 0 if verdict == Verdict.PASS else (1 if verdict == Verdict.FAIL else 2)

    step_results = [
        StepResult(
            index=1,
            name="lift_red",
            verdict=Verdict.PASS,
            t_s=1.5,
            frame=45,
            decisive=[
                Component(
                    name="lifted.min_cm",
                    value=7.2,
                    threshold=5.0,
                    margin=2.2,
                    sigma=0.3,
                    unit="cm",
                    tri=Tri.T,
                )
            ],
            evidence=["runs/run_001/evidence/f0045_overlay.png"],
        ),
        StepResult(
            index=2,
            name="stack_on_green",
            verdict=verdict,
            t_s=3.8 if verdict != Verdict.PASS else 4.0,
            frame=114 if verdict != Verdict.PASS else 120,
            decisive=[
                Component(
                    name="on.align_xy",
                    value=3.4 if verdict != Verdict.PASS else 0.8,
                    threshold=1.5,
                    margin=-1.9 if verdict != Verdict.PASS else 0.7,
                    sigma=0.2,
                    unit="cm",
                    tri=Tri.F if verdict == Verdict.FAIL else (Tri.T if verdict == Verdict.PASS else Tri.U),
                    reason=reasons[0] if reasons else None,
                )
            ],
            reasons=reasons,
            evidence=["runs/run_001/evidence/f0114_overlay.png"],
        ),
    ]

    return RunResult(
        run_id=run_id,
        test_name=test_name,
        test_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        config_sha256="cbf29ce484222325000000000000000000000000000000000000000000000000",
        clip=ClipRef(uri="file://examples/clips/stack_blocks.mp4", source_kind="demo"),
        verdict=verdict,
        exit_code=exit_code,  # type: ignore[arg-type]
        steps=step_results,
        reasons=reasons,
        blame=blame_obj,
        diff_text="--- demo: stack_on_green passed at t=3.5s\n+++ attempt: released at t=3.8s align_xy=3.4cm (thresh 1.5cm)",
        events=[
            Event(
                step=1,
                step_name="lift_red",
                kind="lifted",
                t_s=1.5,
                frame=45,
                fps=30.0,
                source="attempt",
                verdict=Verdict.PASS,
            ),
            Event(
                step=2,
                step_name="stack_on_green",
                kind="released",
                t_s=3.8,
                frame=114,
                fps=30.0,
                source="attempt",
                verdict=verdict,
            ),
        ],
        manual_checks=[],
        timings_ms={"ingest": 120, "segment": 450, "predicates": 35, "blame": 85},
        backends={"sam": "fixture", "judge": "fixture"},
        badges=["FIXTURE", "SIM"],
        nonce=nonce,
        is_fixture=is_fixture,
        card_path="runs/run_001/card.png",
        trace_path="runs/run_001/trace.jsonl",
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


def make_dummy_lock(
    test_sha256: str = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
) -> GreenLock:
    """Create a canonical GreenLock test double."""
    return GreenLock(
        test_sha256=test_sha256,
        transcript=[{"startMs": 0, "endMs": 3500, "text": "Stack the red block"}],
        object_baselines={
            "red_block": {"A0": 4200, "k0": 0.85, "scores": [0.95, 0.94]},
            "green_block": {"A0": 4150, "k0": 0.84, "scores": [0.96, 0.95]},
        },
        demo_events=[
            Event(
                step=1,
                step_name="lift_red",
                kind="lifted",
                t_s=1.4,
                frame=42,
                fps=30.0,
                source="demo",
                verdict=Verdict.PASS,
            ),
            Event(
                step=2,
                step_name="stack_on_green",
                kind="achieved",
                t_s=3.4,
                frame=102,
                fps=30.0,
                source="demo",
                verdict=Verdict.PASS,
            ),
        ],
        geometry_tier="B",
        model_ids={"sam": "sam-3.1", "spark": "muse-spark-1.3"},
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


def make_dummy_track(
    obj: str = "red_block",
    n_frames: int = 5,
    trace_id: str = "tr_track_001",
) -> Track:
    """Create a canonical Track test double."""
    frames: dict[int, ObjMask] = {}
    for i in range(n_frames):
        frames[i] = ObjMask(
            obj=obj,
            frame=i,
            score=0.98,
            bbox_xyxy=(100.0 + i, 120.0 + i, 150.0 + i, 170.0 + i),
            rle="dummy_rle_data",
            area_px=2500,
            rle_size=(480, 640),
        )
    return Track(
        obj=obj,
        frames=frames,
        backend="fixture",
        direction="forward",
        trace_id=trace_id,
    )
