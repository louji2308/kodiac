"""Hint tests: one per blame class, plus the honesty properties (derived only from facts)."""

from __future__ import annotations

from typing import Any

import pytest

from Kodiac_robotics.blame.hint import make_hint
from Kodiac_robotics.contracts.core import Event, FactTable, Verdict


def _ft(
    facts: dict[str, dict[str, Any]],
    literal: str,
    transition: str = "T->F",
    step_index: int = 1,
) -> FactTable:
    return FactTable(
        t_star_s=3.8,
        frame=114,
        fps=30.0,
        sigma_frames=1.0,
        step_index=step_index,
        step_name="place",
        literal=literal,
        transition=transition,  # type: ignore[arg-type]
        facts=facts,
    )


def _fact(value: float, sigma: float, unit: str, **extra: float) -> dict[str, Any]:
    return {"value": value, "sigma": sigma, "unit": unit, **extra}


def test_release_before_approach_hint_is_order() -> None:
    ft = _ft(
        {"dt_before_reference_s": _fact(0.9, 0.1, "s"), "xy_offset_cm": _fact(6.0, 0.3, "cm")},
        "moves_with(gripper, cubeA)",
    )
    h = make_hint(ft)
    assert h is not None
    assert h.variable == "release_order" and h.unit == "s"
    assert h.delta == pytest.approx(1.0)  # dt + sigma = 0.9 + 0.1, nothing invented
    assert "move_to(place)" in (h.move or "")
    assert "0.9 \u00b1 0.1 s" in h.basis and "reaching the place target" in h.basis


def test_order_hint_names_target_object_when_facts_provide_it() -> None:
    ft = _ft(
        {
            "dt_before_reference_s": _fact(0.9, 0.1, "s"),
            "target_object": {"value": "cubeB"},
        },
        "moves_with(gripper, cubeA)",
    )
    h = make_hint(ft)
    assert h is not None and "reaching cubeB" in h.basis


def test_xy_offset_hint_moves_toward_target_with_cm_unit() -> None:
    ft = _ft(
        {"xy_offset_cm": _fact(5.0, 0.3, "cm", threshold=3.33)},
        "on(cubeA, cubeB, align_xy_cm<=3.33, gap_cm<=0.5)",
        transition="unmet",
    )
    h = make_hint(ft)
    assert h is not None and h.variable == "place_xy_offset" and h.unit == "cm"
    # need offset <= 3.33 - 0.3 = 3.03  ->  delta = 3.03 - 5.0 = -1.97 (flips margin to +sigma)
    assert h.delta == pytest.approx(-1.97)
    assert "toward cubeB" in (h.move or "")
    assert "5.0 \u00b1 0.3" in h.basis and "3.33" in h.basis


def test_z_gap_hint_lowers_release() -> None:
    ft = _ft(
        {
            "xy_offset_cm": _fact(0.2, 0.3, "cm", threshold=3.33),
            "gap_cm": _fact(11.0, 0.4, "cm", threshold=0.5),
        },
        "on(cubeA, cubeB)",
    )
    h = make_hint(ft)
    assert h is not None and h.variable == "release_height" and h.unit == "cm"
    assert h.delta == pytest.approx(0.5 - 0.4 - 11.0)


def test_lift_hint_is_positive_and_uses_min_cm() -> None:
    ft = _ft(
        {"lift_cm": _fact(0.5, 0.2, "cm", threshold=2.0)},
        "lifted(cubeA, min_cm=2.0)",
        transition="unmet",
    )
    h = make_hint(ft)
    assert h is not None and h.variable == "lift_distance"
    assert h.delta == pytest.approx(2.0 + 0.2 - 0.5)


def test_dwell_hint_in_seconds() -> None:
    ft = _ft(
        {"dwell_s": _fact(0.27, 0.03, "s", threshold=0.5)},
        "dwell(cubeA, cubeB, for_s=0.5)",
        transition="unmet",
    )
    h = make_hint(ft)
    assert h is not None and h.variable == "dwell_s" and h.unit == "s"
    assert h.delta == pytest.approx(0.5 + 0.03 - 0.27)


def test_margin_field_substitutes_for_threshold() -> None:
    # margin = limit - value for an upper-bounded component: limit = 5.0 + (-1.67) = 3.33
    ft = _ft({"xy_offset_cm": _fact(5.0, 0.3, "cm", margin=-1.67)}, "on(cubeA, cubeB)")
    h = make_hint(ft)
    assert h is not None and h.delta == pytest.approx(-1.97)


def test_applying_delta_flips_margin_to_at_least_sigma() -> None:
    value, sigma, limit = 5.0, 0.3, 3.33
    ft = _ft({"xy_offset_cm": _fact(value, sigma, "cm", threshold=limit)}, "on(cubeA, cubeB)")
    h = make_hint(ft)
    assert h is not None and isinstance(h.delta, float)
    assert limit - (value + h.delta) >= sigma - 1e-9


def test_insufficient_facts_return_none() -> None:
    assert make_hint(_ft({}, "moves_with(gripper, cubeA)")) is None
    # no threshold, no margin, no demo reference: never invent a target
    assert make_hint(_ft({"xy_offset_cm": _fact(5.0, 0.3, "cm")}, "on(cubeA, cubeB)")) is None
    # non-numeric value
    assert make_hint(_ft({"xy_offset_cm": {"value": "big", "threshold": 3.33}}, "on(a, b)")) is None
    # release did not precede approach (dt <= 0) and nothing else is known
    assert make_hint(_ft({"dt_before_reference_s": _fact(-0.2, 0.1, "s")}, "moves_with(g, a)")) is None


def test_no_hint_when_margin_already_satisfied() -> None:
    ft = _ft({"xy_offset_cm": _fact(1.0, 0.3, "cm", threshold=3.33)}, "on(cubeA, cubeB)")
    assert make_hint(ft) is None


def test_demo_event_supplies_reference_when_fact_has_no_threshold() -> None:
    demo = Event(
        step=1,
        step_name="place",
        kind="settled",
        predicate="on",
        args=["cubeA", "cubeB"],
        t_s=3.0,
        frame=90,
        fps=30.0,
        measurements={"on.align_xy": (0.8, 0.2)},
        source="demo",
        verdict=Verdict.PASS,
    )
    ft = _ft({"xy_offset_cm": _fact(5.0, 0.3, "cm")}, "on(cubeA, cubeB)")
    h = make_hint(ft, [demo])
    assert h is not None
    assert h.delta == pytest.approx(0.8 - 5.0)
    assert "demo value" in h.basis


def test_hint_is_deterministic_and_does_not_mutate_facts() -> None:
    ft = _ft({"xy_offset_cm": _fact(5.0, 0.3, "cm", threshold=3.33)}, "on(cubeA, cubeB)")
    before = ft.model_dump()
    assert make_hint(ft) == make_hint(ft)
    assert ft.model_dump() == before


def test_t01_fact_schema_gap_z_op_and_objects() -> None:
    """facts.py shape: gap_z_cm, `op`, `objects`, `blame_class` (place_z class)."""
    ft = _ft(
        {
            "xy_offset_cm": {
                "value": 0.2, "sigma": 0.3, "unit": "cm", "threshold": 3.33, "op": "<=",
                "margin": 3.13, "objects": ["cubeA", "cubeB"],
            },
            "gap_z_cm": {
                "value": 11.0, "sigma": 0.4, "unit": "cm", "threshold": 0.5, "op": "<=",
                "margin": -10.5, "objects": ["cubeA", "cubeB"],
            },
            "blame_class": {"value": "place_z", "unit": "class", "basis": "x"},
        },
        "moves_with(gripper, cubeA)",
    )
    h = make_hint(ft)
    assert h is not None and h.variable == "release_height"
    assert h.delta == pytest.approx(0.5 - 0.4 - 11.0)
    assert "z gap 11.0 \u00b1 0.4 cm" in h.basis


def test_t01_release_before_place_uses_dt_objects_for_target_name() -> None:
    ft = _ft(
        {
            "xy_offset_cm": _fact(9.0, 0.3, "cm", threshold=3.33),
            "dt_before_reference_s": {
                "value": 1.2, "sigma": 0.07, "unit": "s", "objects": ["gripper", "cubeB"],
            },
            "blame_class": {"value": "release_before_place"},
        },
        "moves_with(gripper, cubeA)",
    )
    h = make_hint(ft)
    assert h is not None and h.variable == "release_order"
    assert h.delta == pytest.approx(1.27) and "reaching cubeB" in h.basis


def test_op_in_fact_overrides_default_direction() -> None:
    # a '>=' op on the xy component flips the bound: need value >= threshold + sigma
    ft = _ft(
        {"xy_offset_cm": _fact(1.0, 0.5, "cm", threshold=3.0, op=">=")}, "on(cubeA, cubeB)"
    )
    h = make_hint(ft)
    assert h is not None and h.delta == pytest.approx(3.0 + 0.5 - 1.0)


def test_blame_class_without_numbers_returns_none() -> None:
    assert make_hint(_ft({"blame_class": {"value": "grasp"}}, "moves_with(gripper, cubeA)")) is None
    assert make_hint(_ft({"blame_class": {"value": "near"}}, "near(gripper, cubeA)")) is None