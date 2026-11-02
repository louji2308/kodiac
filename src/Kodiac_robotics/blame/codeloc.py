"""Blamed frame -> source line (sim `/goal` loop input). ARCHITECTURE.md section 9, ADR-0005.

Blamed span = the latest span with `step_start <= frame + slack_frames` whose actuation
class can break the failed component (table below). When no span of an admissible class
exists, we fall back to `sim.spans.find_blame_span` (causal-window lookback) rather than
duplicating its logic.
"""

from __future__ import annotations

from Kodiac_robotics.contracts.core import CodeLocation, FactTable
from Kodiac_robotics.sim.spans import ActuationClass, SimSpan, find_blame_span

_RELEASE_OR_MOTION: tuple[ActuationClass, ...] = (
    "gripper.open",
    "arm.lift",
    "arm.move_to",
    "arm.retract",
)

# Failed component -> actuation classes able to break it (most specific first in docs, matched
# by recency at lookup time). Keys are Component.name values from predicates/*.
COMPONENT_CLASSES: dict[str, tuple[ActuationClass, ...]] = {
    "moves_with.slip": _RELEASE_OR_MOTION,
    "lifted.height": ("arm.lift", "gripper.close"),
    "on.align_xy": ("arm.move_to",),
    "on.gap": ("arm.move_to",),
    "on.scale_ratio": ("arm.move_to",),
    "inside.rim_margin": ("arm.move_to",),
    "inside.depth_consistency": ("arm.move_to",),
    "inside.front_occluder": ("arm.move_to",),
    "near.distance": ("arm.move_to",),
    "dwell.duration": ("wait",),
    "dwell.speed": ("wait", "arm.retract", "gripper.open"),
}

_PREDICATE_DEFAULTS: dict[str, tuple[ActuationClass, ...]] = {
    "moves_with": _RELEASE_OR_MOTION,
    "lifted": ("arm.lift", "gripper.close"),
    "on": ("arm.move_to",),
    "inside": ("arm.move_to",),
    "near": ("arm.move_to",),
    "dwell": ("wait", "arm.retract", "gripper.open"),
}


def classes_for_component(component: str) -> tuple[ActuationClass, ...]:
    """Admissible actuation classes for a failed component (exact name, else predicate prefix)."""
    if component in COMPONENT_CLASSES:
        return COMPONENT_CLASSES[component]
    return _PREDICATE_DEFAULTS.get(component.split(".", 1)[0], ())


def _spans_fps(spans: list[SimSpan]) -> float:
    for s in spans:
        if s.step_start > 0 and s.t_start_s > 0:
            return s.step_start / s.t_start_s
    return 30.0


def _to_location(s: SimSpan) -> CodeLocation:
    return CodeLocation(file=s.file, line=s.line, code=s.code, span_id=s.span_id)


def locate_code(
    spans: list[SimSpan],
    ft_frame: int,
    component: str,
    *,
    slack_frames: int = 3,
) -> CodeLocation | None:
    """Map blamed frame + broken component to the robot-API call line that caused it."""
    if not spans:
        return None
    classes = classes_for_component(component)
    candidates = [
        s for s in spans if s.actuation_class in classes and s.step_start <= ft_frame + slack_frames
    ]
    if candidates:
        return _to_location(max(candidates, key=lambda s: (s.step_start, s.span_id)))

    fallback = find_blame_span(
        spans,
        ft_frame,
        broken_predicate=component.split(".", 1)[0],
        fps=_spans_fps(spans),
    )
    return _to_location(fallback) if fallback is not None else None


def _fact_value(ft: FactTable, *keys: str) -> tuple[float, float, float | None] | None:
    """(value, sigma, threshold) of the first present fact among `keys`."""
    for key in keys:
        entry = ft.facts.get(key)
        if not isinstance(entry, dict) or not isinstance(entry.get("value"), (int, float)):
            continue
        sigma = entry.get("sigma")
        thr = entry.get("threshold")
        return (
            float(entry["value"]),
            float(sigma) if isinstance(sigma, (int, float)) else 0.0,
            float(thr) if isinstance(thr, (int, float)) else None,
        )
    return None


# facts["blame_class"]["value"] (blame/facts.py `classify`) -> broken component
_CLASS_TO_COMPONENT = {
    "release_before_place": "moves_with.slip",
    "release_before_approach": "moves_with.slip",
    "release_unclassified": "moves_with.slip",
    "grasp": "moves_with.slip",
    "xy_offset": "on.align_xy",
    "place_z": "on.gap",
    "z_gap": "on.gap",
    "lift_height": "lifted.height",
    "lift": "lifted.height",
    "near": "near.distance",
    "depth": "on.scale_ratio",
    "inside": "inside.rim_margin",
}


def component_for_facts(ft: FactTable) -> str:
    """Pick the broken component from the fact table (ARCHITECTURE section 9 disambiguation).

    An explicit `facts["blame_class"]["value"]` wins. Otherwise, for `moves_with` T->F: a release
    preceding the effector's approach to the target (`dt_before_reference_s` > sigma) blames the
    release; an xy-offset breach or a z gap blames `move_to(place)`.
    """
    explicit = ft.facts.get("blame_class")
    if isinstance(explicit, dict):
        cls = str(explicit.get("value"))
        if cls in _CLASS_TO_COMPONENT:
            return _CLASS_TO_COMPONENT[cls]
        if cls == "dwell":
            only_speed = "speed_cm_s" in ft.facts and "dwell_s" not in ft.facts
            return "dwell.speed" if only_speed else "dwell.duration"

    dt = _fact_value(ft, "dt_before_reference_s")
    if dt is not None and dt[0] > dt[1]:
        return "moves_with.slip"
    xy = _fact_value(ft, "xy_offset_cm")
    if xy is not None and xy[2] is not None and xy[0] > xy[2]:
        return "on.align_xy"
    gap = _fact_value(ft, "gap_z_cm", "gap_cm")
    if gap is not None and gap[2] is not None and gap[0] > gap[2]:
        return "on.gap"
    if _fact_value(ft, "lift_cm") is not None and "lifted" in ft.literal:
        return "lifted.height"
    if "dwell" in ft.literal:
        return "dwell.duration"
    if "on(" in ft.literal.replace(" ", ""):
        return "on.align_xy"
    return "moves_with.slip"

def locate_from_fact_table(spans: list[SimSpan], ft: FactTable) -> CodeLocation | None:
    """Convenience wrapper used by the CLI/loop: FactTable + span log -> CodeLocation."""
    return locate_code(spans, ft.frame, component_for_facts(ft))
