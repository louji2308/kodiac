"""Fact table: the only input the blame sentence may draw on (ARCHITECTURE §9).

Every numeric fact is a ``{value, sigma, unit, ...}`` dict copied from a measured ``Component`` of a ``PredFrame``
(``trace_ids`` name the PredFrames it came from) or derived from such values by stated arithmetic
(``dt_before_reference_s``). Unreliable components (not visible, occluded, view blocked, appearance unresolved,
depth ambiguous) are never promoted to facts; their absence is recorded in ``evidence``.

Fact names: ``xy_offset_cm`` (on.align_xy), ``gap_z_cm`` (on.gap), ``depth_ratio`` (on.scale_ratio),
``lift_cm`` (lifted.height), ``slip_cm`` (moves_with.slip), ``distance_cm`` (near.distance),
``speed_cm_s`` (dwell.speed), ``dwell_s`` (dwell.duration), ``inside_*`` (inside.*),
``dt_before_reference_s`` (``t_ref - t*``, ``t_ref`` = the effector's closest xy approach to the target after t*),
``reference_xy_cm`` (that closest distance), ``aperture_open_event`` (sim span / aperture evidence only),
``occlusion`` (fraction of frames near t* where a blamed object was occluded or not visible) and
``blame_class`` (disambiguation for hint/code location; see ``classify``).

Context facts are taken at t*, except for a ``moves_with`` True->False release, where they are taken on the last
attached frame ``t* - 1`` (the release pose); each fact records its own ``frame``.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from Kodiac_robotics.blame.transitions import (
    FrameIndex,
    Transition,
    index_pred_frames,
    reliable_components,
    total_frames,
)
from Kodiac_robotics.blame.tstar import SIGMA_FLOOR_FRAMES, TStar
from Kodiac_robotics.contracts.core import (
    Atom,
    CodeLocation,
    Component,
    FactTable,
    PredFrame,
    ReasonCode,
    RunResult,
    ScaleModel,
    Track,
    Tri,
    Verdict,
)

FACT_NAMES: dict[str, str] = {
    "on.align_xy": "xy_offset_cm",
    "on.gap": "gap_z_cm",
    "on.scale_ratio": "depth_ratio",
    "lifted.height": "lift_cm",
    "moves_with.slip": "slip_cm",
    "near.distance": "distance_cm",
    "dwell.speed": "speed_cm_s",
    "dwell.duration": "dwell_s",
}
# Direction of each component's threshold (value must be <= or >= threshold to satisfy the predicate).
COMPONENT_OP: dict[str, str] = {
    "on.align_xy": "<=",
    "on.gap": "<=",
    "on.scale_ratio": "<=",
    "moves_with.slip": "<=",
    "near.distance": "<=",
    "dwell.speed": "<=",
    "lifted.height": ">=",
    "dwell.duration": ">=",
}
CLASS_BY_COMPONENT: dict[str, str] = {
    "on.align_xy": "xy_offset",
    "on.gap": "place_z",
    "on.scale_ratio": "depth",
    "lifted.height": "lift_height",
    "moves_with.slip": "grasp",
    "near.distance": "near",
    "dwell.speed": "dwell",
    "dwell.duration": "dwell",
}
BLAME_CLASSES = (
    "release_before_place",
    "place_z",
    "xy_offset",
    "release_unclassified",
    "lift_height",
    "grasp",
    "dwell",
    "near",
    "depth",
    "inside",
    "order",
    "unclassified",
)
_OCCLUSION_REASONS = {ReasonCode.OCCLUDED, ReasonCode.NOT_VISIBLE}


def fact_name(component: str) -> str:
    """Stable fact key for a component name."""
    if component in FACT_NAMES:
        return FACT_NAMES[component]
    return component.replace(".", "_")


def component_op(c: Component) -> str:
    """'<=' or '>=' for a component (static table, else inferred from the margin sign convention)."""
    if c.name in COMPONENT_OP:
        return COMPONENT_OP[c.name]
    upper = abs((c.threshold - c.value) - c.margin)
    lower = abs((c.value - c.threshold) - c.margin)
    return "<=" if upper <= lower else ">="


def parse_atom_key(key: str) -> tuple[str, list[str]]:
    """``'on(cubeA, cubeB)'`` -> ``('on', ['cubeA', 'cubeB'])``; a leading ``not `` is dropped."""
    key = key.strip().removeprefix("not ").strip()
    if "(" not in key or not key.endswith(")"):
        return key, []
    name, inner = key.split("(", 1)
    args = [a.strip() for a in inner[:-1].split(",") if a.strip()]
    return name.strip(), args


def _component_fact(pf: PredFrame, c: Component, role: str) -> dict[str, Any]:
    _, args = parse_atom_key(pf.atom_key)
    return {
        "value": float(c.value),
        "sigma": float(c.sigma),
        "unit": c.unit,
        "threshold": float(c.threshold),
        "op": component_op(c),
        "margin": float(c.margin),
        "tri": c.tri.value,
        "reason": c.reason.value if c.reason is not None else None,
        "component": c.name,
        "ref": pf.atom_key,
        "objects": args,
        "frame": pf.frame,
        "trace_ids": [pf.trace_id],
        "role": role,
    }


def _arrival_bootstrap(
    frames: list[int], values: list[float], sigmas: list[float], n_boot: int = 200, seed: int = 0
) -> float:
    """Seeded parametric-bootstrap std (frames) of the closest-approach arrival frame; floor 0.5 frame.

    Arrival = first frame whose distance is within its own sigma of the observed minimum (the minimum of the noisy
    replicates themselves would be biased low by extreme-value noise on a hover plateau).
    """
    if len(frames) < 2:
        return SIGMA_FLOOR_FRAMES
    rng = np.random.default_rng(seed)
    fr = np.asarray(frames, dtype=int)
    v = np.asarray(values, dtype=float)
    s = np.asarray(sigmas, dtype=float)
    draws = v[:, None] + rng.normal(0.0, 1.0, size=(len(v), n_boot)) * s[:, None]
    hit = draws <= float(v.min()) + s[:, None]
    hit[-1, :] |= ~hit.any(axis=0)
    picks = fr[np.argmax(hit, axis=0)]
    return float(max(SIGMA_FLOOR_FRAMES, float(np.std(picks.astype(float), ddof=1))))


def _target_of(index: FrameIndex, obj: str) -> str | None:
    """The place target B of object A: first ``on(A, B)`` / ``inside(A, B)`` atom in the evaluated frames."""
    for key in index:
        name, args = parse_atom_key(key)
        if name in ("on", "inside") and len(args) >= 2 and args[0] == obj:
            return args[1]
    return None


def _xy_series(index: FrameIndex, a: str, b: str, lo: int, hi: int) -> list[tuple[int, float, float, str]]:
    """(frame, xy distance, sigma, trace_id) between a and b from ``on(a, b)`` (align_xy) or ``near(a, b)``."""
    out: list[tuple[int, float, float, str]] = []
    for key, comp_name in ((f"on({a}, {b})", "on.align_xy"), (f"near({a}, {b})", "near.distance")):
        slot = index.get(key)
        if not slot:
            continue
        for f in range(lo, hi + 1):
            pf = slot.get(f)
            if pf is None:
                continue
            c = next((x for x in reliable_components(pf) if x.name == comp_name), None)
            if c is not None:
                out.append((f, float(c.value), float(c.sigma), pf.trace_id))
        if out:
            return out
    return out


def reference_pred_frames(
    effector: str,
    target: str,
    tracks: dict[str, Track],
    scale: ScaleModel,
    n_frames: int,
    fps: float,
) -> list[PredFrame]:
    """Measure the effector-target xy relation with the existing ``on`` predicate (``on(effector, target)``).

    These frames feed ``dt_before_reference_s``. They are measurements from the same tracks/scale model the run
    used; pass them alongside the run's PredFrames.
    """
    from Kodiac_robotics.predicates.dispatch import evaluate_atom_over_clip

    atom = Atom(kind="pred", name="on", args=[effector, target])
    return evaluate_atom_over_clip(atom, tracks, scale, n_frames, fps, context=None)


def _window_start(result: RunResult, step_index: int) -> int:
    last = -1
    for sr in result.steps:
        if sr.index == step_index:
            break
        if sr.verdict == Verdict.PASS and sr.frame is not None:
            last = int(sr.frame)
    return last + 1


def _was_ever_true(index: FrameIndex, literal: str, lo: int, hi: int) -> bool:
    slot = index.get(literal.removeprefix("not ").strip(), {})
    target = Tri.F if literal.startswith("not ") else Tri.T
    return any(pf.tri == target for f, pf in slot.items() if lo <= f <= hi)


def classify(transition: Transition, facts: dict[str, dict[str, Any]], cause: str | None) -> dict[str, Any]:
    """Measurement-based blame class (ARCHITECTURE §9 disambiguation; sim spans refine it in validate.py)."""
    pred, _ = parse_atom_key(transition.literal)
    if transition.cls == "order_violation":
        return {"value": "order", "unit": "class", "basis": "a later condition held before its predecessor"}
    if transition.cls == "broken_prerequisite" and pred == "moves_with":
        xy = facts.get("xy_offset_cm")
        gap = facts.get("gap_z_cm")
        dt = facts.get("dt_before_reference_s")
        if xy is not None:
            if xy["value"] <= xy["threshold"]:
                if gap is not None and gap["value"] > gap["threshold"]:
                    return {
                        "value": "place_z",
                        "unit": "class",
                        "basis": "released aligned in xy (xy_offset_cm <= align_xy) but above the gap tolerance "
                        "(gap_z_cm > gap_cm)",
                    }
                return {
                    "value": "release_unclassified",
                    "unit": "class",
                    "basis": "released aligned in xy; no measured z violation at t*",
                }
            if dt is not None:
                return {
                    "value": "release_before_place",
                    "unit": "class",
                    "basis": "released outside align_xy and the effector kept approaching the target afterwards "
                    "(dt_before_reference_s)",
                }
            return {
                "value": "xy_offset",
                "unit": "class",
                "basis": "released outside align_xy and the effector did not get closer to the target afterwards",
            }
        return {"value": "release_unclassified", "unit": "class", "basis": "no target relation measured at t*"}
    if cause is not None:
        if cause.startswith("inside."):
            return {"value": "inside", "unit": "class", "basis": f"cause component {cause}"}
        cls = CLASS_BY_COMPONENT.get(cause, "unclassified")
        return {"value": cls, "unit": "class", "basis": f"cause component {cause}"}
    return {"value": "unclassified", "unit": "class", "basis": "no cause component"}


def build_fact_table(
    result: RunResult,
    transition: Transition,
    tstar: TStar,
    pred_frames: list[PredFrame],
    *,
    code_location: CodeLocation | None = None,
    dataset_index: int | None = None,
    action_chunk: int | None = None,
    fps: float,
) -> FactTable:
    """Assemble the FactTable at t* from measured PredFrames only."""
    index = index_pred_frames(pred_frames)
    n_total = total_frames(index)
    f = int(tstar.frame)
    facts: dict[str, dict[str, Any]] = {}
    trace_ids: list[str] = []
    evidence: list[str] = []

    pred, lit_args = parse_atom_key(transition.literal)
    lit_key = transition.literal.removeprefix("not ").strip()
    if pred == "moves_with" and len(lit_args) >= 2:
        effector, obj = lit_args[0], lit_args[1]
    else:
        effector, obj = None, (lit_args[0] if lit_args else None)
    target = _target_of(index, obj) if obj else None
    blamed_objects = {o for o in (effector, obj, target) if o}

    def add(name: str, pf: PredFrame, c: Component, role: str) -> None:
        key = name if name not in facts else f"{name}@{pf.atom_key}"
        facts[key] = _component_fact(pf, c, role)
        if pf.trace_id and pf.trace_id not in trace_ids:
            trace_ids.append(pf.trace_id)
        evidence.append(
            f"trace {pf.trace_id}: {pf.atom_key} @ frame {pf.frame}: {c.name} = {c.value:.3f} +/- {c.sigma:.3f} "
            f"{c.unit} (threshold {c.threshold:.3f}, margin {c.margin:+.3f}, {c.tri.value})"
        )

    # 1. The cause component (from the blamed literal at t*).
    cause_name: str | None = transition.component
    cause_pf = index.get(lit_key, {}).get(f)
    if cause_pf is not None:
        comps = {c.name: c for c in cause_pf.components}
        c = comps.get(cause_name) if cause_name else None
        if c is None:
            rel = reliable_components(cause_pf)
            c = min(rel, key=lambda x: x.margin / max(x.sigma, 1e-3)) if rel else None
        if c is not None and c.reason not in {
            ReasonCode.NOT_VISIBLE,
            ReasonCode.OCCLUDED,
            ReasonCode.VIEW_BLOCKED,
            ReasonCode.APPEARANCE_UNRESOLVED,
            ReasonCode.DEPTH_AMBIGUOUS,
        }:
            cause_name = c.name
            add(fact_name(c.name), cause_pf, c, "cause")
        elif c is not None:
            evidence.append(f"cause {c.name} at frame {f} unavailable: {c.reason.value if c.reason else 'unknown'}")

    # 2. Context facts: every reliable component of atoms over the blamed objects, at t* — except for a
    #    moves_with True->False release, where they describe the release pose (last attached frame, t* - 1).
    f_ctx = f - 1 if (transition.cls == "broken_prerequisite" and pred == "moves_with" and f > 0) else f
    for key, slot in sorted(index.items()):
        if key == lit_key:
            continue
        _, args = parse_atom_key(key)
        if not args or not set(args) <= (blamed_objects | {"table", "surface"}) or not (set(args) & blamed_objects):
            continue
        if effector is not None and args and args[0] == effector:
            continue  # effector-target reference series: used for dt_before_reference_s, not a context fact
        pf = slot.get(f_ctx)
        if pf is None:
            continue
        for comp in pf.components:
            if comp.reason is not None and comp.reason in {
                ReasonCode.NOT_VISIBLE,
                ReasonCode.OCCLUDED,
                ReasonCode.VIEW_BLOCKED,
                ReasonCode.APPEARANCE_UNRESOLVED,
                ReasonCode.DEPTH_AMBIGUOUS,
            }:
                evidence.append(f"{comp.name} at frame {f_ctx} not used: {comp.reason.value}")
                continue
            name = fact_name(comp.name)
            if name in facts and facts[name].get("role") == "cause":
                continue
            add(name, pf, comp, "context")

    # 3. dt_before_reference_s: effector's closest xy approach to the target after t* (release transitions only).
    if transition.cls == "broken_prerequisite" and effector and target and n_total > 0:
        series = _xy_series(index, effector, target, f, n_total - 1)
        at_tstar = next((s for s in series if s[0] == f), None)
        after = [s for s in series if s[0] > f]
        if at_tstar is not None and after:
            d_min = min(s[1] for s in after)
            # Arrival at the closest approach: first frame within its own sigma of the minimum distance.
            ref = next(s for s in after if s[1] <= d_min + s[2])
            closer_by = at_tstar[1] - ref[1]
            if closer_by > max(at_tstar[2], ref[2]):
                sig_ref = _arrival_bootstrap(
                    [s[0] for s in after], [s[1] for s in after], [s[2] for s in after], seed=0
                )
                sig_dt = math.sqrt(float(tstar.sigma_frames) ** 2 + sig_ref**2) / fps
                facts["dt_before_reference_s"] = {
                    "value": (ref[0] - f) / fps,
                    "sigma": sig_dt,
                    "unit": "s",
                    "t_ref_frame": ref[0],
                    "t_ref_s": ref[0] / fps,
                    "objects": [effector, target],
                    "ref": f"{effector}->{target} xy",
                    "trace_ids": [at_tstar[3], ref[3]],
                    "role": "derived",
                    "formula": "(t_ref_frame - frame) / fps; sigma = sqrt(sigma_t*^2 + sigma_ref^2) / fps",
                }
                facts["reference_xy_cm"] = {
                    "value": ref[1],
                    "sigma": ref[2],
                    "unit": "cm",
                    "frame": ref[0],
                    "objects": [effector, target],
                    "trace_ids": [ref[3]],
                    "role": "derived",
                }
                for tid in (at_tstar[3], ref[3]):
                    if tid and tid not in trace_ids:
                        trace_ids.append(tid)
                evidence.append(
                    f"reference: {effector}->{target} xy {at_tstar[1]:.3f} cm at frame {f}, closest "
                    f"{ref[1]:.3f} cm at frame {ref[0]}"
                )
            else:
                evidence.append(
                    f"dt_before_reference_s omitted: {effector} did not get closer to {target} after frame {f}"
                )
        elif not series:
            evidence.append(f"dt_before_reference_s omitted: no {effector}->{target} xy measurement")

    # 4. Aperture / release event: only from sim-span evidence (the vision pipeline measures no aperture).
    if code_location is not None and "open" in code_location.code:
        facts["aperture_open_event"] = {
            "value": True,
            "unit": "event",
            "source": "sim_span",
            "span_id": code_location.span_id,
            "file": code_location.file,
            "line": code_location.line,
            "code": code_location.code,
        }

    # 5. Occlusion around t*.
    if blamed_objects and n_total > 0:
        half = max(1, int(round(0.25 * fps)))
        lo, hi = max(0, f - half), min(n_total - 1, f + half)
        checked = 0
        occluded = 0
        for key, slot in index.items():
            _, args = parse_atom_key(key)
            if not set(args) & blamed_objects:
                continue
            for fr in range(lo, hi + 1):
                pf = slot.get(fr)
                if pf is None:
                    continue
                checked += 1
                if any(c.reason in _OCCLUSION_REASONS for c in pf.components):
                    occluded += 1
        if checked:
            facts["occlusion"] = {
                "value": round(occluded / checked, 3),
                "sigma": None,
                "unit": "ratio",
                "frames_occluded": occluded,
                "frames_checked": checked,
                "window": [lo, hi],
                "role": "derived",
            }

    facts["blame_class"] = classify(transition, facts, cause_name)

    w0 = _window_start(result, transition.step_index)
    if transition.cls == "broken_prerequisite":
        kind = "T->F"
    elif transition.cls == "order_violation":
        kind = "order"
    else:
        kind = "unmet" if _was_ever_true(index, transition.literal, w0, max(w0, n_total - 1)) else "never_T"

    evidence.insert(0, f"run {result.run_id} verdict {result.verdict.value}; is_fixture={result.is_fixture}")
    if result.badges:
        evidence.insert(1, "badges: " + " ".join(result.badges))
    evidence.append(f"t* method {tstar.method}: frame {f} +/- {tstar.sigma_frames:.2f} frames")

    return FactTable(
        t_star_s=round(f / fps, 4),
        frame=f,
        fps=fps,
        sigma_frames=float(tstar.sigma_frames),
        step_index=transition.step_index,
        step_name=transition.step_name,
        literal=transition.literal,
        transition=kind,
        facts=facts,
        dataset_index=dataset_index,
        action_chunk=action_chunk,
        code_location=code_location,
        evidence=evidence,
        trace_ids=trace_ids,
    )


__all__ = [
    "build_fact_table",
    "reference_pred_frames",
    "fact_name",
    "component_op",
    "parse_atom_key",
    "classify",
    "FACT_NAMES",
    "BLAME_CLASSES",
]
