"""Unit tests for compiler/selftest.py.

Tests demo self-test read-only evaluation pass, margin >= 2σ verification,
and failure/inconclusive handling (E005, W103) per ARCHITECTURE.md §6.1-§6.3 and RULING.md.
"""

from __future__ import annotations

import pytest

from Kodiac_robotics.compiler.selftest import run_demo_selftest
from Kodiac_robotics.contracts.core import (
    Atom,
    Clip,
    Expr,
    GreenTest,
    ObjectDecl,
    Param,
    Provenance,
    Step,
    Verdict,
)
from Kodiac_robotics.io.clip import open_clip


@pytest.fixture
def correct_clip() -> Clip:
    return open_clip("tests/fixtures/clips/correct_run.mp4")


@pytest.fixture
def b01_clip() -> Clip:
    return open_clip("tests/fixtures/clips/b01_early_release.mp4")


@pytest.fixture
def occluded_clip() -> Clip:
    return open_clip("tests/fixtures/clips/occluded_clip.mp4")


@pytest.fixture
def calibrated_pass_test() -> GreenTest:
    prov = Provenance(source="compiler-default")
    return GreenTest(
        version="0.1",
        name="calibrated_lift",
        objects=[
            ObjectDecl(name="gripper", role="effector"),
            ObjectDecl(name="cube_a", role="rigid", size_cm=4.0),
        ],
        steps=[
            Step(
                index=1,
                name="lift",
                expr=Expr(
                    op="atom",
                    atom=Atom(
                        kind="pred",
                        name="lifted",
                        args=["cube_a"],
                        params=[Param(name="min_cm", op="=", value=1.0)],
                    ),
                ),
                provenance=prov,
            ),
        ],
    )


@pytest.fixture
def multi_step_stackcube_test() -> GreenTest:
    prov = Provenance(source="compiler-default")
    return GreenTest(
        version="0.1",
        name="stackcube_test",
        objects=[
            ObjectDecl(name="gripper", role="effector"),
            ObjectDecl(name="cubeA", role="rigid", size_cm=4.0),
            ObjectDecl(name="cubeB", role="rigid", size_cm=4.0),
        ],
        steps=[
            Step(
                index=1,
                name="grasp",
                expr=Expr(
                    op="atom",
                    atom=Atom(
                        kind="pred",
                        name="moves_with",
                        args=["gripper", "cubeA"],
                    ),
                ),
                provenance=prov,
            ),
            Step(
                index=2,
                name="place",
                expr=Expr(
                    op="atom",
                    atom=Atom(
                        kind="pred",
                        name="on",
                        args=["cubeA", "cubeB"],
                    ),
                ),
                provenance=prov,
            ),
        ],
    )


def test_selftest_pass_on_calibrated_demo(
    calibrated_pass_test: GreenTest,
    correct_clip: Clip,
) -> None:
    """Calibrated demonstration self-test achieves Verdict == PASS with no E005 errors."""
    passed, run_result, diagnostics = run_demo_selftest(calibrated_pass_test, correct_clip)

    assert passed is True
    assert run_result.verdict == Verdict.PASS
    assert not any(d.severity == "error" for d in diagnostics)

    # Confirm decisive margin satisfies >= 2*sigma
    decisive_comps = run_result.steps[0].decisive
    assert len(decisive_comps) > 0
    comp = decisive_comps[0]
    assert comp.margin >= 2.0 * comp.sigma


def test_selftest_fail_on_broken_demonstration(
    multi_step_stackcube_test: GreenTest,
    b01_clip: Clip,
) -> None:
    """Failing demonstration produces passed=False, Verdict.FAIL, and E005 diagnostic."""
    passed, run_result, diagnostics = run_demo_selftest(multi_step_stackcube_test, b01_clip)

    assert passed is False
    assert run_result.verdict == Verdict.FAIL
    assert any(d.code == "E005" for d in diagnostics)


def test_selftest_inconclusive_on_occluded_clip(
    multi_step_stackcube_test: GreenTest,
    occluded_clip: Clip,
) -> None:
    """Occluded demonstration produces passed=False, Verdict.CANT_TELL, and E005 diagnostic."""
    passed, run_result, diagnostics = run_demo_selftest(multi_step_stackcube_test, occluded_clip)

    assert passed is False
    assert run_result.verdict == Verdict.CANT_TELL
    assert any(d.code == "E005" for d in diagnostics)


def test_selftest_w103_warning_on_tight_margin(correct_clip: Clip) -> None:
    """Demonstration component margin < 2*sigma generates W103 warning diagnostic."""
    # min_cm set close to actual apex (~2.75cm) so margin < 2*sigma
    prov = Provenance(source="compiler-default")
    tight_test = GreenTest(
        version="0.1",
        name="tight_lift",
        objects=[
            ObjectDecl(name="gripper", role="effector"),
            ObjectDecl(name="cube_a", role="rigid", size_cm=4.0),
        ],
        steps=[
            Step(
                index=1,
                name="lift",
                expr=Expr(
                    op="atom",
                    atom=Atom(
                        kind="pred",
                        name="lifted",
                        args=["cube_a"],
                        params=[Param(name="min_cm", op="=", value=7.0)],
                    ),
                ),
                provenance=prov,
            ),
        ],
    )

    passed, run_result, diagnostics = run_demo_selftest(tight_test, correct_clip)
    # Check that W103 was recorded
    assert any(d.code == "W103" for d in diagnostics)
