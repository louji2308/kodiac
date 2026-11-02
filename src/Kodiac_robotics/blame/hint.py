"""Corrective hint: the single variable change that flips the blamed margin to >= +sigma.

ARCHITECTURE.md sections 5.4 and 9. Every number is computed from FactTable values (or, when a
fact carries no threshold, from the demonstration event's measurement of the same component).
When the facts do not contain what is needed, `make_hint` returns None instead of guessing.
"""

from __future__ import annotations

import math
import re
from typing import Literal

from Kodiac_robotics.blame.codeloc import component_for_facts
from Kodiac_robotics.contracts.core import Event, FactTable, Hint

_Bound = Literal["upper", "lower"]

# fact key, demo-event component, bound direction
_SPEC: dict[str, tuple[str, str, _Bound]] = {
    "on.align_xy": ("xy_offset_cm", "on.align_xy", "upper"),
    "on.gap": ("gap_cm", "on.gap", "upper"),
    "lifted.height": ("lift_cm", "lifted.height", "lower"),
    "dwell.duration": ("dwell_s", "dwell.duration", "lower"),
}


class _Fact:
    __slots__ = ("value", "sigma", "threshold", "margin")

    def __init__(self, value: float, sigma: float, threshold: float | None, margin: float | None):
        self.value, self.sigma, self.threshold, self.margin = value, sigma, threshold, margin


def _num(x: object) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        return None
    return float(x)


def _read(ft: FactTable, key: str) -> _Fact | None:
    entry = ft.facts.get(key)
    if not isinstance(entry, dict):
        return None
    value = _num(entry.get("value"))
    if value is None:
        return None
    return _Fact(
        value,
        max(_num(entry.get("sigma")) or 0.0, 0.0),
        _num(entry.get("threshold")),
        _num(entry.get("margin")),
    )


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


def _target_name(ft: FactTable) -> str:
    named = ft.facts.get("target_object")
    if isinstance(named, dict) and isinstance(named.get("value"), str):
        return str(named["value"])
    if ft.literal.lstrip().startswith("moves_with"):
        return "the place target"  # the literal names the carried object, not the destination
    m = re.match(r"\s*\w+\(\s*([^,)]+)\s*,\s*([^,)]+)", ft.literal)
    return m.group(2).strip() if m else "the target"


def _order_hint(ft: FactTable) -> Hint | None:
    dt = _read(ft, "dt_before_reference_s")
    if dt is None or dt.value <= 0:
        return None
    delta = dt.value + dt.sigma
    target = _target_name(ft)
    return Hint(
        variable="release_order",
        delta=round(delta, 2),
        unit="s",
        move=f"move gripper.open() after move_to(place): delay the release by >= {delta:.2f} s",
        basis=(
            f"released {dt.value:.1f} \u00b1 {dt.sigma:.1f} s before reaching {target} "
            f"(dt_before_reference_s at frame {ft.frame})"
        ),
    )


def make_hint(ft: FactTable, demo_events: list[Event] | None = None) -> Hint | None:
    """Single-variable change that flips the blamed margin to >= +sigma, or None."""
    comp = component_for_facts(ft)
    if comp == "moves_with.slip":
        return _order_hint(ft)
    spec = _SPEC.get(comp)
    if spec is None:
        return None
    fact_key, demo_comp, bound = spec
    fact = _read(ft, fact_key)
    if fact is None:
        return None

    threshold = fact.threshold
    source = "limit"
    if threshold is None and fact.margin is not None:
        threshold = fact.value + fact.margin if bound == "upper" else fact.value - fact.margin
    if threshold is None:
        ref = _demo_reference(demo_events, demo_comp, ft.step_index)
        if ref is None:
            return None
        threshold, source = ref[0], "demo value"
        # the demo's own measurement is the reference to match, no extra sigma headroom
        target = threshold
    else:
        target = threshold - fact.sigma if bound == "upper" else threshold + fact.sigma

    delta = target - fact.value
    if (bound == "upper" and delta >= 0) or (bound == "lower" and delta <= 0):
        return None  # margin is already >= +sigma: nothing to correct
    delta = round(delta, 2)
    obj = _target_name(ft)
    mag = abs(delta)
    basis = (
        f"{fact_key} {fact.value:.1f} \u00b1 {fact.sigma:.1f} "
        f"vs {source} {threshold:.2f}; need {'<=' if bound == 'upper' else '>='} {target:.2f}"
    )
    if fact_key == "xy_offset_cm":
        return Hint(
            variable="place_xy_offset",
            delta=delta,
            unit="cm",
            move=f"shift the place target {mag:.2f} cm toward {obj}",
            basis=basis.replace("xy_offset_cm", "xy offset") + " cm",
        )
    if fact_key == "gap_cm":
        return Hint(
            variable="release_height",
            delta=delta,
            unit="cm",
            move=f"lower the place pose {mag:.2f} cm before opening the gripper",
            basis=basis.replace("gap_cm", "gap") + " cm",
        )
    if fact_key == "lift_cm":
        return Hint(
            variable="lift_distance",
            delta=delta,
            unit="cm",
            move=f"lift {mag:.2f} cm higher",
            basis=basis.replace("lift_cm", "lift") + " cm",
        )
    return Hint(
        variable="dwell_s",
        delta=delta,
        unit="s",
        move=f"hold {mag:.2f} s longer after release before retracting",
        basis=basis.replace("dwell_s", "dwell") + " s",
    )
