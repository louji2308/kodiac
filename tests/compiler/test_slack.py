"""Unit tests for compiler/slack.py.

Tests two-pass metric extraction via Kinematic Phase Segmentation (apex detection &
settled terminal window), certified slack derivation (margin >= 2σ), and hard physical
sanity caps (ADR-0013) per ARCHITECTURE.md §6.1-§6.3 and RULING.md.
"""

from __future__ import annotations

import pytest

from Kodiac_robotics.compiler.slack import (
    derive_thresholds,
    measure_demo_metrics,
)
from Kodiac_robotics.contracts.core import (
    Atom,
    Clip,
    Expr,
    GreenTest,
    ObjectDecl,
    Param,
    Provenance,
    Step,
)
from Kodiac_robotics.io.clip import open_clip


@pytest.fixture
def correct_clip() -> Clip:
    return open_clip("tests/fixtures/clips/correct_run.mp4")


@pytest.fixture
def skeleton_test() -> GreenTest:
    prov = Provenance(source="compiler-default")
    return GreenTest(
        version="0.1",
        name="stack_test",
        objects=[
            ObjectDecl(name="gripper", role="effector"),
            ObjectDecl(name="cube_a", role="rigid", size_cm=4.0),
            ObjectDecl(name="cube_b", role="rigid", size_cm=4.0),
        ],
        steps=[
            Step(
                index=1,
                name="grasp",
                expr=Expr(
                    op="and",
                    children=[
                        Expr(
                            op="atom",
                            atom=Atom(kind="pred", name="moves_with", args=["gripper", "cube_a"]),
                        ),
                        Expr(
                            op="atom",
                            atom=Atom(
                                kind="pred",
                                name="lifted",
                                args=["cube_a"],
                                params=[Param(name="min_cm", op="=", value=-1.0)],
                            ),
                        ),
                    ],
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
                        args=["cube_a", "cube_b"],
                        params=[
                            Param(name="align_xy_cm", op="<=", value=-1.0),
                            Param(name="gap_cm", op="<=", value=-1.0),
                        ],
                    ),
                ),
                provenance=prov,
            ),
            Step(
                index=3,
                name="release",
                expr=Expr(
                    op="atom",
                    atom=Atom(
                        kind="pred",
                        name="dwell",
                        args=["cube_a", "cube_b"],
                        params=[
                            Param(name="for_s", op=">=", value=0.5),
                            Param(name="max_speed_cm_s", op="<=", value=-1.0),
                        ],
                    ),
                ),
                provenance=prov,
            ),
        ],
    )


def test_kinematic_phase_segmentation_correct_clip(
    correct_clip: Clip,
    skeleton_test: GreenTest,
) -> None:
    """Kinematic Phase Segmentation accurately extracts apex elevation and terminal settled metrics."""
    metrics = measure_demo_metrics(correct_clip, skeleton_test)

    # Apex Detection: Global maximum of elevation h(t)
    assert "h_max" in metrics
    assert metrics["h_max"] >= 7.0  # Measured apex around ~7.9cm

    # Settled Terminal Window: Stationary plateau
    assert "delta_xy" in metrics
    assert "z_gap" in metrics
    assert "v_settle" in metrics
    assert "sigma" in metrics

    # Settling velocity must be <= 2.5 cm/s on canonical correct run
    assert metrics["v_settle"] <= 2.5
    assert metrics["sigma"] > 0.0


def test_derive_thresholds_nominal(skeleton_test: GreenTest) -> None:
    """derive_thresholds calculates certified slack margins under nominal profile."""
    demo_metrics = {
        "h_max": 7.5,
        "delta_xy": 1.3,
        "z_gap": 0.4,
        "v_settle": 0.2,
        "sigma": 0.3,
    }

    calibrated_test, slack_summary = derive_thresholds(
        skeleton_test,
        demo_metrics,
        profile="nominal",
    )

    # align_xy_cm = max(1.5, round(1.3 + 2.5*0.3, 1)) = max(1.5, 2.05 -> 2.0) = 2.0
    # gap_cm = max(0.5, round(0.4 + 2.5*0.3, 1)) = max(0.5, 1.15 -> 1.1) = 1.1
    # min_cm = max(1.0, floor(0.6 * 7.5)) = max(1.0, 4.0) = 4.0
    thresh = slack_summary["thresholds"]
    assert thresh["align_xy_cm"] == 2.0
    assert thresh["gap_cm"] == 1.1
    assert thresh["min_cm"] == 4.0
    assert thresh["max_speed_cm_s"] <= 2.5

    # Check that AST parameters are updated from placeholders (-1.0)
    lifted_param = calibrated_test.steps[0].expr.children[1].atom.params[0]
    assert lifted_param.name == "min_cm"
    assert lifted_param.value == 4.0

    on_params = {p.name: p.value for p in calibrated_test.steps[1].expr.atom.params}
    assert on_params["align_xy_cm"] == 2.0
    assert on_params["gap_cm"] == 1.1


def test_derive_thresholds_strict_vs_loose(skeleton_test: GreenTest) -> None:
    """Strict (2.0σ) derives tighter bounds than loose (3.0σ)."""
    demo_metrics = {
        "h_max": 6.0,
        "delta_xy": 1.4,
        "z_gap": 0.3,
        "v_settle": 0.1,
        "sigma": 0.4,
    }

    _, strict_summary = derive_thresholds(skeleton_test, demo_metrics, profile="strict")
    _, loose_summary = derive_thresholds(skeleton_test, demo_metrics, profile="loose")

    strict_align = strict_summary["thresholds"]["align_xy_cm"]
    loose_align = loose_summary["thresholds"]["align_xy_cm"]
    assert strict_align <= loose_align


@pytest.mark.parametrize(
    "bad_metrics,expected_violation",
    [
        (
            {"h_max": 7.0, "delta_xy": 4.5, "z_gap": 0.5, "v_settle": 0.1, "sigma": 0.2},
            "align_xy_cm",
        ),
        (
            {"h_max": 7.0, "delta_xy": 1.0, "z_gap": 2.5, "v_settle": 0.1, "sigma": 0.2},
            "gap_cm",
        ),
        (
            {"h_max": 16.0, "delta_xy": 1.0, "z_gap": 0.5, "v_settle": 0.1, "sigma": 0.2},
            "min_cm",
        ),
        (
            {"h_max": 7.0, "delta_xy": 1.0, "z_gap": 0.5, "v_settle": 3.8, "sigma": 0.2},
            "v_settle",
        ),
    ],
)
def test_physical_sanity_caps_rejection_e005(
    skeleton_test: GreenTest,
    bad_metrics: dict[str, float],
    expected_violation: str,
) -> None:
    """Demonstrations exceeding physical sanity caps are strictly rejected with E005 (ADR-0013)."""
    with pytest.raises(ValueError, match="E005") as exc_info:
        derive_thresholds(skeleton_test, bad_metrics, profile="nominal")

    assert "physical sanity cap" in str(exc_info.value)
    assert expected_violation in str(exc_info.value)
