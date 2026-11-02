"""Corrective hint: the single variable change that flips the blamed margin to >= +sigma.

ARCHITECTURE.md sections 5.4 and 9. Every number is computed from FactTable values (or, when a
fact carries no threshold, from the demonstration event's measurement of the same component).
When the facts do not contain what is needed, `make_hint` returns None instead of guessing.
"""

from __future__ import annotations

import math
import re
from typing import Any, Literal

from Kodiac_robotics.blame.codeloc import component_for_facts
from Kodiac_robotics.contracts.core import Event, FactTable, Hint

_Bound = Literal["upper", "lower"]

# fact keys (blame/facts.py names first), demo-event component, default bound direction
_SPEC: dict[str, tuple[tuple[str, ...], str, _Bound]] = {
    "on.align_xy": (("xy_offset_cm",), "on.align_xy", "upper"),
    "on.gap": (("gap_z_cm", "gap_cm"), "on.gap", "upper"),
    "lifted.height": (("lift_cm",), "lifted.height", "lower"),
    "dwell.duration": (("dwell_s",), "dwell.duration", "lower"),
}


class _Fact:
    __slots__ = ("value", "sigma", "threshold", "margin")

    def __init__(self, value: float, sigma: float, threshold: float | None, margin: float | None):
        self.value, self.sigma, self.threshold, self.margin = value, sigma, threshold, margin


def _num(x: object) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        return None
    return float(x)


def _read(ft: FactTable, *keys: str) -> tuple[str, _Fact, dict[str, Any]] | None:
    for key in keys:
        entry = ft.facts.get(key)
        if not isinstance(entry, dict):
            continue
        value = _num(entry.get("value"))
        if value is None:
            continue
        fact = _Fact(
            value,
            max(_num(entry.get("sigma")) or 0.0, 0.0),
            _num(entry.get("threshold")),
            _num(entry.get("margin")),
        )
        return key, fact, entry
    return None


def _demo_reference(
    demo_events: list[Event] | None, comp: str, step_index: int
) -> tuple[float, float] | None:
    """Demo measurement (value, sigma) of `comp`, preferring the blamed step."""
    if not demo_events:
        return None
    same = [e for e in demo_events if e.step == step_index and comp in e.measurements]
    anywhere = [e for e in demo_events if comp in e.measurements]
    pick = (same or anywhere or [None])[0]
    return pick.measurements[comp] if pick is not None else None


def _target_name(ft: FactTable, entry: dict[str, Any] | None = None) -> str:
    """Name of the destination object: from the fact's `objects`, else the literal, else generic."""
    if entry is not None:
        objs = entry.get("objects")
        if isinstance(objs, list) and len(objs) >= 2 and isinstance(objs[1], str):
            return objs[1]
    named = ft.facts.get("target_object")
    if isinstance(named, dict) and isinstance(named.get("value"), str):
        return str(named["value"])
    if ft.literal.lstrip().startswith("moves_with"):
        return "the place target"  # the literal names the carried object, not the destination
    m = re.match(r"\s*\w+\(\s*([^,)]+)\s*,\s*([^,)]+)", ft.literal)
    return m.group(2).strip() if m else "the target"


def _order_hint(ft: FactTable) -> Hint | None:
    got = _read(ft, "dt_before_reference_s")
    if got is None or got[1].value <= 0:
        return None
    _, dt, entry = got
    delta = dt.value + dt.sigma
    return Hint(
        variable="release_order",
        delta=round(delta, 2),
        unit="s",
        move=f"move gripper.open() after move_to(place): delay the release by >= {delta:.2f} s",
        basis=(
            f"released {dt.value:.1f} \u00b1 {dt.sigma:.1f} s before reaching "
            f"{_target_name(ft, entry)} (dt_before_reference_s at frame {ft.frame})"
        ),
    )


# component -> (variable, label for the basis, unit, move template)
_PRESENTATION: dict[str, tuple[str, str, str, str]] = {
    "on.align_xy": ("place_xy_offset", "xy offset", "cm", "shift the place target {mag:.2f} cm toward {obj}"),
    "on.gap": ("release_height", "z gap", "cm", "lower the place pose {mag:.2f} cm before opening the gripper"),
    "lifted.height": ("lift_distance", "lift", "cm", "lift {mag:.2f} cm higher"),
    "dwell.duration": ("dwell_s", "dwell", "s", "hold {mag:.2f} s longer after release before retracting"),
}


def make_hint(ft: FactTable, demo_events: list[Event] | None = None) -> Hint | None:
    """Single-variable change that flips the blamed margin to >= +sigma, or None."""
    comp = component_for_facts(ft)
    if comp == "moves_with.slip":
        return _order_hint(ft)
    spec = _SPEC.get(comp)
    if spec is None:
        return None
    fact_keys, demo_comp, default_bound = spec
    got = _read(ft, *fact_keys)
    if got is None:
        return None
    _, fact, entry = got
    op = entry.get("op")
    bound: _Bound = "upper" if op == "<=" else "lower" if op == ">=" else default_bound

    threshold = fact.threshold
    source = "limit"
    if threshold is None and fact.margin is not None:
        threshold = fact.value + fact.margin if bound == "upper" else fact.value - fact.margin
    if threshold is None:
        ref = _demo_reference(demo_events, demo_comp, ft.step_index)
        if ref is None:
            return None
        threshold, source = ref[0], "demo value"
        target = threshold  # match the demo's own measurement; no extra sigma headroom
    else:
        target = threshold - fact.sigma if bound == "upper" else threshold + fact.sigma

    delta = target - fact.value
    if (bound == "upper" and delta >= 0) or (bound == "lower" and delta <= 0):
        return None  # margin is already >= +sigma: nothing to correct
    delta = round(delta, 2)
    variable, label, unit, move = _PRESENTATION[comp]
    return Hint(
        variable=variable,
        delta=delta,
        unit=unit,
        move=move.format(mag=abs(delta), obj=_target_name(ft, entry)),
        basis=(
            f"{label} {fact.value:.1f} \u00b1 {fact.sigma:.1f} {unit} vs {source} "
            f"{threshold:.2f} {unit}; need {'<=' if bound == 'upper' else '>='} {target:.2f} {unit}"
        ),
    )