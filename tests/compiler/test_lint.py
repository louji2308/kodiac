"""Tests for compile-time spec linter (E001-E005, W101-W105)."""

from __future__ import annotations

from Kodiac_robotics.compiler.lint import lint_green
from Kodiac_robotics.compiler.parser import parse_green
from Kodiac_robotics.contracts.core import (
    ClipRef,
    Component,
    RunResult,
    StepResult,
    Tri,
    Verdict,
)


def _make_dummy_run_result(
    verdict: Verdict = Verdict.PASS,
    decisive: list[Component] | None = None,
    badges: list[str] | None = None,
) -> RunResult:
    return RunResult(
        run_id="run-test",
        test_name="test",
        test_sha256="abc",
        config_sha256="def",
        clip=ClipRef(uri="test.mp4", source_kind="demo"),
        verdict=verdict,
        exit_code=0 if verdict == Verdict.PASS else (1 if verdict == Verdict.FAIL else 2),
        steps=[
            StepResult(
                index=0,
                name="step1",
                verdict=verdict,
                decisive=decisive or [],
            )
        ]
        if verdict != Verdict.CANT_TELL
        else [],
        reasons=[] if verdict != Verdict.CANT_TELL else ["not_visible"],  # type: ignore[arg-type]
        badges=badges or [],
        nonce="0123456789abcdef",
        trace_path="trace.json",
        created_at="2026-10-31T00:00:00Z",
    )


def test_lint_e001_missing_object() -> None:
    """E001: Reference to undeclared object."""
    text = """# E001 Test
objects: [gripper, blockA]
1. pick: moves_with(gripper, phantom_block)
"""
    test = parse_green(text)
    diags = lint_green(test)
    e001 = [d for d in diags if d.code == "E001"]
    assert len(e001) == 1
    assert "phantom_block" in e001[0].message


def test_lint_e002_duplicate_and_ambiguous_objects() -> None:
    """E002: Duplicate object names or identical visual prompts."""
    # Duplicate name
    text_dup = """# E002 Dup
objects: [gripper, block, block]
1. pick: moves_with(gripper, block)
"""
    test_dup = parse_green(text_dup)
    diags_dup = lint_green(test_dup)
    assert any(d.code == "E002" and "Duplicate" in d.message for d in diags_dup)

    # Ambiguous prompt
    text_amb = """# E002 Ambiguous
objects: [
  gripper,
  cubeA(prompt="red cube", size_cm=5),
  cubeB(prompt="red cube", size_cm=5)
]
1. pick: moves_with(gripper, cubeA)
"""
    test_amb = parse_green(text_amb)
    diags_amb = lint_green(test_amb)
    assert any(d.code == "E002" and "Ambiguous" in d.message for d in diags_amb)


def test_lint_e003_arity_role_and_parameter_errors() -> None:
    """E003: Arity mismatch, invalid predicate parameter, and invalid object roles."""
    # Arity mismatch (lifted expects 1 object)
    text_arity = """# E003 Arity
objects: [gripper, cubeA, cubeB]
1. lift: lifted(cubeA, cubeB)
"""
    test_arity = parse_green(text_arity)
    diags_arity = lint_green(test_arity)
    assert any(d.code == "E003" and "expects 1" in d.message for d in diags_arity)

    # Invalid parameter for predicate
    text_param = """# E003 Param
objects: [gripper, cubeA, cubeB]
1. place: on(cubeA, cubeB, min_cm=2.0)
"""
    test_param = parse_green(text_param)
    diags_param = lint_green(test_param)
    assert any(d.code == "E003" and "min_cm" in d.message for d in diags_param)

    # Role constraint (inside expects container as arg 2)
    text_role = """# E003 Role
objects: [gripper, cubeA(role=rigid), cubeB(role=rigid)]
1. place: inside(cubeA, cubeB)
"""
    test_role = parse_green(text_role)
    diags_role = lint_green(test_role)
    assert any(d.code == "E003" and "container" in d.message for d in diags_role)


def test_lint_e004_comparator_direction() -> None:
    """E004: Parameter operator contradicts expected normative direction."""
    # min_cm expects >=, got <=
    text = """# E004 Test
objects: [gripper, cubeA]
1. lift: lifted(cubeA, min_cm<=2.0)
"""
    test = parse_green(text)
    diags = lint_green(test)
    e004 = [d for d in diags if d.code == "E004"]
    assert len(e004) == 1
    assert "min_cm" in e004[0].message
    assert ">=" in e004[0].message


def test_lint_e005_physical_sanity_caps_and_demo_failure() -> None:
    """E005: Out-of-bounds demonstration parameters exceeding physical sanity caps."""
    # align_xy_cm > 4.0 cm cap
    text_cap = """# E005 Cap
objects: [gripper, cubeA, cubeB]
1. place: on(cubeA, cubeB, align_xy_cm<=5.0)
"""
    test_cap = parse_green(text_cap)
    diags_cap = lint_green(test_cap)
    assert any(d.code == "E005" and "align_xy_cm" in d.message for d in diags_cap)

    # Demonstration failed self-test
    text_demo = """# E005 Demo Fail
objects: [gripper, cubeA]
1. pick: moves_with(gripper, cubeA)
"""
    test_demo = parse_green(text_demo)
    fail_run = _make_dummy_run_result(verdict=Verdict.FAIL)
    diags_fail = lint_green(test_demo, context=fail_run)
    assert any(d.code == "E005" and "fails its own test" in d.message for d in diags_fail)


def test_lint_w101_tactile_keywords() -> None:
    """W101: Tactile words in provenance quotes trigger MANUAL(...) warning."""
    text = """# W101 Test
objects: [gripper, block]
1. place: moves_with(gripper, block) # "place it gently" [0:01-0:04]
"""
    test = parse_green(text)
    diags = lint_green(test)
    w101 = [d for d in diags if d.code == "W101"]
    assert len(w101) == 1
    assert "gently" in w101[0].message
    assert "MANUAL" in w101[0].message


def test_lint_w102_missing_provenance() -> None:
    """W102: Step without quote and timestamp grounding."""
    text = """# W102 Test
objects: [gripper, block]
1. ungrounded: moves_with(gripper, block)
"""
    test = parse_green(text)
    diags = lint_green(test)
    assert any(d.code == "W102" for d in diags)


def test_lint_w103_margin_tighter_than_2sigma() -> None:
    """W103: Decisive component margin < 2σ."""
    text = """# W103 Test
objects: [gripper, cubeA]
1. pick: moves_with(gripper, cubeA) # "pick" [0:01-0:04]
"""
    test = parse_green(text)
    # Component with margin 0.5 and sigma 0.4 -> 2*sigma = 0.8 > 0.5
    comp = Component(
        name="on.align_xy",
        value=1.4,
        threshold=1.5,
        margin=0.5,
        sigma=0.4,
        unit="cm",
        tri=Tri.T,
    )
    run_res = _make_dummy_run_result(verdict=Verdict.PASS, decisive=[comp])
    diags = lint_green(test, context=run_res)
    assert any(d.code == "W103" and "2σ" in d.message for d in diags)


def test_lint_w104_depth_critical_on_tier_c() -> None:
    """W104: Depth-critical checks evaluated under Tier C geometry."""
    text = """# W104 Test
objects: [gripper, cube(role=rigid), cup(role=container)]
1. place: inside(cube, cup) # "put inside" [0:01-0:04]
"""
    test = parse_green(text)
    run_tier_c = _make_dummy_run_result(
        verdict=Verdict.PASS,
        badges=["[GEOMETRY: TIER C · UNCALIBRATED CAMERA]"],
    )
    diags = lint_green(test, context=run_tier_c)
    assert any(d.code == "W104" for d in diags)


def test_lint_w105_or_branching() -> None:
    """W105: Use of non-canonical 'or' branching logic."""
    text = """# W105 Test
objects: [gripper, cubeA, cubeB]
1. branch: on(cubeA, cubeB) or dwell(cubeA) # "either" [0:01-0:04]
"""
    test = parse_green(text)
    diags = lint_green(test)
    assert any(d.code == "W105" for d in diags)
