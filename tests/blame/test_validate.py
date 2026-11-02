"""Validator (fabrication rejection) and the blame_from_run orchestrator, incl. the golden fixture drive.

Set ``KODIAC_WRITE_BLAME_REPORT=1`` to (re)write ``artifacts/p06/blame_core_report.json`` from
``test_fixture_and_synthetic_report``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from Kodiac_robotics.blame.summary import render_template_summary
from Kodiac_robotics.blame.transitions import load_trace_pred_frames
from Kodiac_robotics.blame.validate import blame_from_run, validate_summary
from Kodiac_robotics.contracts.core import CodeLocation, ReasonCode, StepResult, Verdict
from Kodiac_robotics.pipeline.loader import load_green_test
from Kodiac_robotics.sim.spans import SimSpan

from .test_transitions import FPS, run_result, scenario

REPO = Path(__file__).resolve().parents[2]
FIXTURE_CLIPS = ["b01_early_release", "b02_xy_misalignment", "b09_lift_failure", "correct_run"]


@pytest.fixture(scope="module")
def b01():
    sc = scenario("b01_early_release")
    b = blame_from_run(sc.result, sc.test, sc.frames, FPS, reference_frames=sc.reference)
    assert b is not None
    return sc, b.facts


@pytest.fixture(scope="module")
def b09():
    sc = scenario("b09_low_lift")
    b = blame_from_run(sc.result, sc.test, sc.frames, FPS)
    assert b is not None
    return sc, b.facts


# ------------------------------------------------------------------------------------------------
# Fabrication rejection
# ------------------------------------------------------------------------------------------------


def test_valid_template_passes(b01) -> None:
    sc, ft = b01
    assert validate_summary(render_template_summary(ft), ft, sc.test) == []


def test_injected_fabricated_number_is_rejected(b01) -> None:
    sc, ft = b01
    good = render_template_summary(ft)
    bad = good.replace("9.0 ± 0.1 cm", "7.3 ± 0.1 cm")
    assert bad != good
    v = validate_summary(bad, ft, sc.test)
    assert any("7.3" in x for x in v)
    loose = "blame: gripper released cubeA 9.0 ± 0.1 cm from cubeB after a 12.4 cm swing at 00:01.5, frame 46"
    assert any("12.4" in x for x in validate_summary(loose, ft, sc.test))


def test_mixed_value_and_sigma_from_different_facts_is_rejected(b01) -> None:
    sc, ft = b01
    other_sigma = f"{ft.facts['speed_cm_s']['sigma']:.1f}"
    assert other_sigma != "0.1"
    text = f"blame: gripper released cubeA 9.0 ± {other_sigma} cm from cubeB at 00:01.5, frame 46"
    assert any("not a value ± sigma pair" in x for x in validate_summary(text, ft, sc.test))


def test_fabricated_object_is_rejected(b01) -> None:
    sc, ft = b01
    for obj in ("blue_bowl", "the bowl", "mugB"):
        text = f"blame: gripper released cubeA 9.0 ± 0.1 cm from {obj} at 00:01.5, frame 46"
        assert validate_summary(text, ft, sc.test), obj


def test_generic_nouns_matching_declared_objects_are_allowed(b01) -> None:
    sc, ft = b01
    text = "blame: the gripper released the cube 9.0 ± 0.1 cm from cubeB at 00:01.5, frame 46"
    assert validate_summary(text, ft, sc.test) == []


def test_unlicensed_verbs_are_rejected(b01, b09) -> None:
    sc, ft = b01
    opened = "blame: gripper opened 9.0 ± 0.1 cm from cubeB at 00:01.5, frame 46"
    assert any("opened" in x for x in validate_summary(opened, ft, sc.test))
    hit = "blame: gripper hit cubeB, xy offset 9.0 ± 0.1 cm at 00:01.5, frame 46"
    assert any("contact is never measured" in x for x in validate_summary(hit, ft, sc.test))
    sc9, ft9 = b09
    released = "blame: gripper released cubeA with lift 1.0 ± 0.1 cm at 00:01.2, frame 37"
    assert any("no measured moves_with" in x for x in validate_summary(released, ft9, sc9.test))


def test_opened_is_licensed_by_a_sim_span() -> None:
    sc = scenario("b01_early_release")
    loc = CodeLocation(file="examples/sim/pick_place.py", line=12, code="robot.gripper.open()", span_id=5)
    b = blame_from_run(sc.result, sc.test, sc.frames, FPS, code_location=loc, reference_frames=sc.reference)
    assert b is not None
    text = "blame: gripper opened at line 12 and released cubeA 9.0 ± 0.1 cm from cubeB at 00:01.5, frame 46"
    assert validate_summary(text, b.facts, sc.test) == []


def test_shape_rules(b01) -> None:
    sc, ft = b01
    two = "blame: gripper released cubeA. It was 9.0 ± 0.1 cm from cubeB at 00:01.5, frame 46"
    assert any("one sentence" in x for x in validate_summary(two, ft, sc.test))
    long = "blame: " + "really " * 30 + "9.0 ± 0.1 cm"
    assert any("words" in x for x in validate_summary(long, ft, sc.test))
    nopm = "blame: gripper released cubeA 9.0 cm from cubeB at 00:01.5, frame 46"
    assert any("at least one" in x for x in validate_summary(nopm, ft, sc.test))
    assert validate_summary("", ft, sc.test) == ["empty summary"]


def test_units_times_and_frames_must_match(b01) -> None:
    sc, ft = b01
    unit = "blame: gripper released cubeA 9.0 ± 0.1 s from cubeB at 00:01.5, frame 46"
    assert validate_summary(unit, ft, sc.test)
    when = "blame: gripper released cubeA 9.0 ± 0.1 cm from cubeB at 00:02.7, frame 46"
    assert any("time" in x for x in validate_summary(when, ft, sc.test))
    frame = "blame: gripper released cubeA 9.0 ± 0.1 cm from cubeB at 00:01.5, frame 81"
    assert any("frame 81" in x for x in validate_summary(frame, ft, sc.test))


# ------------------------------------------------------------------------------------------------
# Orchestrator
# ------------------------------------------------------------------------------------------------


def test_pass_and_cant_tell_return_none() -> None:
    sc = scenario("correct")
    assert blame_from_run(sc.result, sc.test, sc.frames, FPS) is None
    ct = run_result(sc.test, Verdict.CANT_TELL, [StepResult(index=0, name="grasp", verdict=Verdict.CANT_TELL)],
                    reasons=[ReasonCode.OCCLUDED])
    assert blame_from_run(ct, sc.test, sc.frames, FPS) is None


def test_spans_disambiguate_release_before_place_and_inject_callbacks() -> None:
    sc = scenario("b01_early_release")

    def span(i: int, code: str, cls: str, s0: int, s1: int) -> SimSpan:
        return SimSpan(span_id=i, func=cls.split(".")[-1], file="examples/sim/pick_place.py", line=10 + i,
                       code=code, actuation_class=cls, step_start=s0, step_end=s1,
                       t_start_s=s0 / FPS, t_end_s=s1 / FPS)

    spans = [
        span(0, 'robot.arm.lift(0.10)', "arm.lift", 14, 30),
        span(1, "robot.gripper.open()", "gripper.open", 45, 46),
        span(2, 'robot.arm.move_to("place", "green_block")', "arm.move_to", 60, 70),
    ]
    seen: list[tuple[int, str]] = []

    def locator(frame: int, component: str) -> CodeLocation:
        seen.append((frame, component))
        return CodeLocation(file="examples/sim/pick_place.py", line=11, code="robot.gripper.open()", span_id=1)

    b = blame_from_run(sc.result, sc.test, sc.frames, FPS, spans=spans, code_locator=locator,
                       hint_fn=lambda ft: None, reference_frames=sc.reference)
    assert b is not None
    assert seen == [(46, "moves_with.slip")]
    bc = b.facts.facts["blame_class"]
    assert bc["value"] == "release_before_place" and bc["source"] == "sim_span"
    assert b.facts.facts["aperture_open_event"]["line"] == 11
    assert b.summary_source == "template"
    assert validate_summary(b.summary, b.facts, sc.test) == []


def _drive_fixture(clip: str, tmp_path: Path) -> dict:
    from Kodiac_robotics.pipeline.run import run

    test, _ = load_green_test(REPO / "examples" / "stackcube.green")
    res = run(test=REPO / "examples" / "stackcube.green", clip=REPO / "tests" / "fixtures" / "clips" / f"{clip}.mp4",
              output_dir=tmp_path / clip)
    frames = load_trace_pred_frames(res.trace_path)
    b = blame_from_run(res, test, frames, 30.0)
    entry: dict = {
        "clip": f"tests/fixtures/clips/{clip}.mp4",
        "evidence_type": "fixture_replay",
        "verdict": res.verdict.value,
        "steps": [{"name": s.name, "verdict": s.verdict.value if s.verdict else None, "frame": s.frame} for s in res.steps],
        "badges": res.badges,
        "backends": res.backends,
        "is_fixture": res.is_fixture,
        "blame": None,
    }
    if b is not None:
        ft = b.facts
        entry["blame"] = {
            "transition": ft.transition,
            "step": ft.step_name,
            "literal": ft.literal,
            "t_star_frame": ft.frame,
            "t_star_s": ft.t_star_s,
            "sigma_frames": ft.sigma_frames,
            "facts": {k: {kk: v[kk] for kk in ("value", "sigma", "unit", "threshold", "frame") if kk in v}
                      for k, v in ft.facts.items()},
            "summary": b.summary,
            "summary_source": b.summary_source,
            "summary_violations": validate_summary(b.summary, ft, test),
            "warnings": b.warnings,
        }
    return entry


@pytest.mark.parametrize("clip", ["b01_early_release", "b02_xy_misalignment", "b09_lift_failure"])
def test_golden_fixtures_yield_honest_blame(clip: str, tmp_path: Path) -> None:
    entry = _drive_fixture(clip, tmp_path)
    assert entry["verdict"] == "FAIL"
    blame = entry["blame"]
    assert blame is not None
    assert blame["summary_violations"] == []
    assert blame["summary_source"] == "template"
    assert any("fixture replay" in w for w in blame["warnings"])
    # Tier C fixtures: the engine cannot confirm moves_with (sigma == slip threshold), so the grasp step fails.
    assert blame["step"] == "grasp"
    if clip == "b09_lift_failure":
        # the cube never rises: the measured cause is the lift itself
        assert blame["literal"] == "lifted(cubeA)"
        assert blame["facts"]["lift_cm"]["value"] < blame["facts"]["lift_cm"]["threshold"]
    else:
        # the cube is carried but moves_with stays inside its noise band: blame must say "unresolved", not invent
        # a release story
        assert blame["literal"] == "moves_with(gripper, cubeA)"
        assert any("below the noise floor" in w for w in blame["warnings"])
        assert "never confirmed" in blame["summary"]


def test_fixture_and_synthetic_report(tmp_path: Path) -> None:
    report: dict = {
        "task": "P06/T01 blame core",
        "law1_note": (
            "fixture_replay rows: golden 640x480 clips replayed through recorded HSV-segmented tracks "
            "(no live SAM 3.1, no SAPIEN physics), Tier C geometry. synthetic_kinematic rows: hand-built "
            "gripper/cube trajectories with known release frames fed through the real predicates, gates and step "
            "engine via an exact (tier-A-like) fake scale model; they test the blame logic, not perception."
        ),
        "fixture_limitation": (
            "On every fixture clip, including correct_run.mp4, the engine returns FAIL at step grasp because Tier C "
            "sigma for moves_with.slip (1.0 cm) equals the slip threshold, so gate G3 holds the grasp at U. Blame "
            "reports this honestly as an unresolved grasp; these clips are not hero evidence."
        ),
        "fixture_replay": [_drive_fixture(c, tmp_path) for c in FIXTURE_CLIPS],
        "synthetic_kinematic": [],
    }
    for name in ("b01_early_release", "b02_xy_offset", "b10_place_high", "b09_low_lift"):
        sc = scenario(name)
        b = blame_from_run(sc.result, sc.test, sc.frames, FPS, reference_frames=sc.reference)
        assert b is not None
        ft = b.facts
        report["synthetic_kinematic"].append({
            "scenario": name,
            "evidence_type": "synthetic_kinematic",
            "ground_truth_detach_frame": sc.release_frame + 1 if ft.transition == "T->F" else None,
            "t_star_frame": ft.frame,
            "sigma_frames": ft.sigma_frames,
            "transition": ft.transition,
            "literal": ft.literal,
            "blame_class": ft.facts["blame_class"]["value"],
            "facts": {k: {kk: v[kk] for kk in ("value", "sigma", "unit", "threshold", "frame") if kk in v}
                      for k, v in ft.facts.items()},
            "summary": b.summary,
            "summary_source": b.summary_source,
        })
    for row in report["synthetic_kinematic"]:
        if row["ground_truth_detach_frame"] is not None:
            assert row["t_star_frame"] == row["ground_truth_detach_frame"], row["scenario"]
    text = json.dumps(report, indent=2, default=str)
    assert json.loads(text)["fixture_replay"][0]["evidence_type"] == "fixture_replay"
    if os.environ.get("KODIAC_WRITE_BLAME_REPORT") == "1":
        out = REPO / "artifacts" / "p06" / "blame_core_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
