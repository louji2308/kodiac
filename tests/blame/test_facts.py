"""Fact table: every number traces to a measured component; derived facts follow their stated formula."""

from __future__ import annotations

import pytest

from Kodiac_robotics.blame.facts import build_fact_table, classify, component_op, parse_atom_key
from Kodiac_robotics.blame.transitions import Transition, find_transition
from Kodiac_robotics.blame.tstar import TStar, refine_tstar
from Kodiac_robotics.blame.validate import blame_from_run
from Kodiac_robotics.contracts.core import (
    CodeLocation,
    Component,
    ReasonCode,
    StepResult,
    Tri,
    Verdict,
)

from .test_transitions import FPS, atom_expr, mk_test, run_result, scenario, series


def _blame(name: str, **kw):
    sc = scenario(name)
    b = blame_from_run(sc.result, sc.test, sc.frames, FPS, reference_frames=sc.reference, **kw)
    assert b is not None
    return sc, b


def _component_values(sc) -> dict[str, set[float]]:
    out: dict[str, set[float]] = {}
    for lst in list(sc.frames.values()) + [sc.reference]:
        for pf in lst:
            for c in pf.components:
                out.setdefault(pf.trace_id, set()).update({c.value, c.sigma, c.threshold})
    return out


def test_release_facts_b01_trace_to_components() -> None:
    sc, b = _blame("b01_early_release")
    ft = b.facts
    assert ft.transition == "T->F"
    assert ft.frame == sc.release_frame + 1
    assert ft.t_star_s == pytest.approx(ft.frame / FPS, abs=1e-4)
    assert ft.sigma_frames > 0
    values = _component_values(sc)
    for name, fact in ft.facts.items():
        if fact.get("role") in ("cause", "context"):
            (tid,) = fact["trace_ids"]
            assert tid in ft.trace_ids
            assert fact["value"] in values[tid], name
            assert fact["sigma"] in values[tid], name
    xy = ft.facts["xy_offset_cm"]
    assert xy["frame"] == sc.release_frame  # release pose = last attached frame
    assert xy["value"] == pytest.approx(9.0, abs=0.1)
    assert xy["op"] == "<=" and xy["objects"] == ["cubeA", "cubeB"]
    assert ft.facts["slip_cm"]["role"] == "cause"


def test_dt_before_reference_formula_b01() -> None:
    sc, b = _blame("b01_early_release")
    ft = b.facts
    dt = ft.facts["dt_before_reference_s"]
    # the gripper reaches cubeB in xy at frame 60 (by construction of the synthetic trajectory)
    assert dt["t_ref_frame"] == 60
    assert dt["value"] == pytest.approx((60 - ft.frame) / FPS)
    assert 0 < dt["sigma"] < 0.1
    assert ft.facts["reference_xy_cm"]["frame"] == 60
    assert ft.facts["blame_class"]["value"] == "release_before_place"


def test_blame_classes_for_offset_and_high_place() -> None:
    _, b02 = _blame("b02_xy_offset")
    assert b02.facts.facts["blame_class"]["value"] == "xy_offset"
    assert "dt_before_reference_s" not in b02.facts.facts  # the gripper never got closer to cubeB
    assert b02.facts.facts["xy_offset_cm"]["value"] == pytest.approx(4.5, abs=0.1)
    _, b10 = _blame("b10_place_high")
    assert b10.facts.facts["blame_class"]["value"] == "place_z"
    assert b10.facts.facts["gap_z_cm"]["value"] == pytest.approx(3.0, abs=0.1)


def test_unmet_lift_is_never_true_with_lift_fact() -> None:
    _, b = _blame("b09_low_lift")
    ft = b.facts
    assert ft.transition == "never_T"
    assert ft.literal == "lifted(cubeA)"
    assert ft.facts["lift_cm"]["role"] == "cause"
    assert ft.facts["lift_cm"]["value"] == pytest.approx(1.0, abs=0.1)
    assert ft.facts["lift_cm"]["op"] == ">="
    assert ft.facts["blame_class"]["value"] == "lift_height"
    assert "dt_before_reference_s" not in ft.facts


def test_code_location_licenses_aperture_and_indices_propagate() -> None:
    sc = scenario("b01_early_release")
    loc = CodeLocation(file="examples/sim/pick_place.py", line=12, code="robot.gripper.open()", span_id=5)
    b = blame_from_run(sc.result, sc.test, sc.frames, FPS, code_location=loc, dataset_index=7, action_chunk=3)
    assert b is not None
    ft = b.facts
    assert ft.code_location == loc
    assert ft.dataset_index == 7 and ft.action_chunk == 3
    assert ft.facts["aperture_open_event"]["value"] is True
    assert ft.facts["aperture_open_event"]["source"] == "sim_span"


def test_unreliable_components_are_not_promoted() -> None:
    n = 30
    on = series("on(cubeA, cubeB)", "on.align_xy", "cm", [6.0] * n, 3.33, upper=True)
    for pf in on:
        gap = Component(name="on.gap", value=2.0, threshold=0.5, margin=-1.5, sigma=0.1, unit="cm", tri=Tri.U,
                        reason=ReasonCode.DEPTH_AMBIGUOUS)
        pf.components.append(gap)
    test = mk_test([("place", atom_expr("on", "cubeA", "cubeB"))])
    result = run_result(test, Verdict.FAIL, [StepResult(index=0, name="place", verdict=Verdict.FAIL, frame=29)])
    tr = find_transition(result, {"on(cubeA, cubeB)": on}, test, FPS)
    assert tr is not None and tr.component == "on.align_xy"
    ts = refine_tstar(tr, on, FPS, (0, n - 1), n_boot=50)
    ft = build_fact_table(result, tr, ts, on, fps=FPS)
    assert "gap_z_cm" not in ft.facts
    assert ft.facts["xy_offset_cm"]["value"] == 6.0
    assert ft.facts["blame_class"]["value"] == "xy_offset"


def test_build_fact_table_direct_contract() -> None:
    lift = series("lifted(cubeA)", "lifted.height", "cm", [0.5] * 20, 2.0, upper=False)
    test = mk_test([("lift", atom_expr("lifted", "cubeA"))])
    result = run_result(test, Verdict.FAIL, [StepResult(index=0, name="lift", verdict=Verdict.FAIL, frame=19)])
    tr = Transition(cls="unmet", step_index=0, step_name="lift", literal="lifted(cubeA)", t_frame=4,
                    component="lifted.height")
    ts = TStar(frame=4, t_s=4 / FPS, sigma_frames=2.0, method="softscore_argmax")
    ft = build_fact_table(result, tr, ts, lift, fps=FPS)
    assert ft.frame == 4 and ft.sigma_frames == 2.0 and ft.transition == "never_T"
    assert ft.facts["lift_cm"]["trace_ids"] == ["tr_lifted.height_4"]
    assert any("t* method softscore_argmax" in e for e in ft.evidence)


def test_helpers() -> None:
    assert parse_atom_key("not moves_with(gripper, cubeA)") == ("moves_with", ["gripper", "cubeA"])
    c = Component(name="x.y", value=5.0, threshold=2.0, margin=3.0, sigma=0.1, unit="cm", tri=Tri.T)
    assert component_op(c) == ">="
    tr = Transition(cls="order_violation", step_index=1, step_name="p", literal="on(a, b)", t_frame=3)
    assert classify(tr, {}, None)["value"] == "order"
