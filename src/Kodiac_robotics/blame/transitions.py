"""Transition finder: which step failed, which literal broke, and at which frame (ARCHITECTURE §5.4).

Three failure classes, in priority order:

1. ``broken_prerequisite``: a carried literal L (an ongoing ``moves_with`` relation achieved by an earlier step)
   enters a False run that never recovers before the failing step's condition holds. ``t*_L`` is the onset of
   L's final False run; the blamed literal is ``argmin_L t*_L``. False runs that later recover to True are
   *transient* breaks and are reported as warnings, never as blame.
2. ``order_violation``: the failing step's condition held (for ``n_on`` frames) only *before* its search window,
   i.e. after the first step was achieved but before the preceding step was, and never again; or the engine
   emitted an ``order_violation`` event.
3. ``unmet``: the failing step's condition never held. ``t* = argmax softscore(C_k)``; the cause is the most
   negative ``margin / sigma`` component at ``t*``.

Softscore of an atom is ``min_c margin_c / sigma_c`` over its *reliable* components (components gated as
not-visible, occluded, view-blocked, appearance-unresolved or depth-ambiguous are excluded because their value is
not a trustworthy measurement). ``and`` = min, ``or`` = max, ``not`` = negation.

If the failing step is CAN'T TELL, the run is not a FAIL, or every relevant frame is unresolved, ``find_transition``
returns ``None``: we never guess.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

import orjson
from pydantic import BaseModel, Field, PrivateAttr

from Kodiac_robotics.contracts.core import (
    Atom,
    Component,
    Expr,
    GreenTest,
    PredFrame,
    ReasonCode,
    RunResult,
    Step,
    Tri,
    Verdict,
)
from Kodiac_robotics.engine.logic import evaluate_expr_tree
from Kodiac_robotics.engine.steps import (
    _extract_atoms,
    _extract_negated_atom_keys,
    _extract_positive_relational_atoms,
)
from Kodiac_robotics.predicates.base import get_atom_key

UNRELIABLE_REASONS: frozenset[ReasonCode] = frozenset(
    {
        ReasonCode.NOT_VISIBLE,
        ReasonCode.OCCLUDED,
        ReasonCode.VIEW_BLOCKED,
        ReasonCode.APPEARANCE_UNRESOLVED,
        ReasonCode.DEPTH_AMBIGUOUS,
    }
)
_SIGMA_EPS = 1e-3

FrameIndex = dict[str, dict[int, PredFrame]]


class Transition(BaseModel):
    """The decisive transition behind a FAIL verdict."""

    cls: Literal["broken_prerequisite", "unmet", "order_violation"]
    step_index: int
    step_name: str
    literal: str
    t_frame: int
    component: str | None = None
    warnings: list[str] = Field(default_factory=list)

    # Not part of the frozen schema: per-frame softscore of the failing step's condition (class 2 only),
    # consumed by tstar.refine_tstar for the softscore-argmax bootstrap.
    _softscore: dict[int, float] = PrivateAttr(default_factory=dict)


# ==============================================================================
# Frame indexing helpers (shared with tstar / facts)
# ==============================================================================


def index_pred_frames(frames: dict[str, list[PredFrame]] | list[PredFrame]) -> FrameIndex:
    """Normalize per-atom PredFrames to ``{atom_key: {frame: PredFrame}}`` (last record wins)."""
    out: FrameIndex = {}
    if isinstance(frames, dict):
        for key, lst in frames.items():
            slot = out.setdefault(key, {})
            for pf in lst:
                slot[pf.frame] = pf
    else:
        for pf in frames:
            out.setdefault(pf.atom_key, {})[pf.frame] = pf
    return out


def load_trace_pred_frames(trace_path: str | Path) -> dict[str, list[PredFrame]]:
    """Read the ``pred_frame`` records of a run's ``trace.jsonl`` back into PredFrames.

    The trace writer appends, so if a directory was reused the most recent record per ``(atom, frame)`` wins.
    """
    latest: dict[tuple[str, int], PredFrame] = {}
    with open(trace_path, "rb") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = orjson.loads(line)
            if rec.get("record_type") != "pred_frame":
                continue
            pf = PredFrame(
                frame=int(rec["frame"]),
                atom_key=str(rec["atom"]),
                tri=Tri(rec["tri"]),
                components=[Component.model_validate(c) for c in rec.get("components", [])],
                trace_id=str(rec.get("trace_id", "")),
            )
            latest[(pf.atom_key, pf.frame)] = pf
    out: dict[str, list[PredFrame]] = {}
    for (key, _), pf in sorted(latest.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        out.setdefault(key, []).append(pf)
    return out


def n_on_frames(fps: float) -> int:
    """Engine confirmation window: ``n_on = max(2, round(0.10 * fps))``."""
    return max(2, int(round(0.10 * fps)))


def total_frames(index: FrameIndex) -> int:
    """Number of frames covered by the index (max frame + 1)."""
    last = -1
    for slot in index.values():
        if slot:
            last = max(last, max(slot))
    return last + 1


def lookup(index: FrameIndex, atom: Atom, frame: int) -> PredFrame | None:
    """Engine-compatible lookup: atom key first, then bare predicate name."""
    key = get_atom_key(atom)
    slot = index.get(key)
    if slot is None and atom.name:
        slot = index.get(atom.name)
    if slot is None:
        return None
    return slot.get(frame)


def reliable_components(pf: PredFrame) -> list[Component]:
    """Components whose value is a trustworthy measurement (see module docstring)."""
    return [c for c in pf.components if c.reason not in UNRELIABLE_REASONS]


def component_score(c: Component) -> float:
    """Signed margin in sigma units."""
    return float(c.margin) / max(float(c.sigma), _SIGMA_EPS)


def atom_softscore(pf: PredFrame | None) -> float | None:
    """Soft truth of one atom at one frame (``None`` if no reliable component)."""
    if pf is None:
        return None
    comps = reliable_components(pf)
    if not comps:
        return None
    return min(component_score(c) for c in comps)


def expr_softscore(expr: Expr, index: FrameIndex, frame: int) -> float | None:
    """Soft truth of an expression: and=min, or=max, not=negation; unknown children are skipped."""
    if expr.op == "atom":
        if expr.atom is None:
            return None
        return atom_softscore(lookup(index, expr.atom, frame))
    if expr.op == "not":
        if not expr.children:
            return None
        inner = expr_softscore(expr.children[0], index, frame)
        return None if inner is None else -inner
    vals = [expr_softscore(ch, index, frame) for ch in expr.children]
    known = [v for v in vals if v is not None]
    if not known:
        return None
    return min(known) if expr.op == "and" else max(known)


def expr_tri(expr: Expr, index: FrameIndex, frame: int) -> Tri:
    """Kleene value of an expression at a frame using the engine's evaluator."""
    values: dict[str, Tri] = {}
    for atom in _extract_atoms(expr):
        pf = lookup(index, atom, frame)
        values[get_atom_key(atom)] = pf.tri if pf is not None else Tri.U
    return evaluate_expr_tree(expr, values)


def _sustained_runs(tris: list[tuple[int, Tri]], target: Tri, n_on: int) -> list[tuple[int, int]]:
    """Maximal runs of ``target`` frames (U neither extends nor resets), keeping those with >= n_on hits."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    last_hit: int | None = None
    hits = 0
    for f, tri in tris:
        if tri == target:
            if start is None:
                start = f
                hits = 0
            hits += 1
            last_hit = f
        elif tri == Tri.U:
            continue
        else:
            if start is not None and last_hit is not None and hits >= n_on:
                runs.append((start, last_hit))
            start, last_hit, hits = None, None, 0
    if start is not None and last_hit is not None and hits >= n_on:
        runs.append((start, last_hit))
    return runs


def _fmt_s(frame: int, fps: float) -> str:
    return f"{frame / fps:.2f}s"


# ==============================================================================
# Transition finder
# ==============================================================================


def _failing_step(result: RunResult, test: GreenTest) -> tuple[int, Step] | None:
    by_index = {s.index: s for s in test.steps}
    for pos, sr in enumerate(result.steps):
        if sr.verdict == Verdict.PASS:
            continue
        if sr.verdict != Verdict.FAIL:
            return None  # first non-PASS step is CAN'T TELL / not evaluated: nothing to blame
        step = by_index.get(sr.index)
        if step is None and pos < len(test.steps):
            step = test.steps[pos]
        return (pos, step) if step is not None else None
    return None


def _achievement_frames(result: RunResult, upto_pos: int) -> list[int]:
    frames: list[int] = []
    for sr in result.steps[:upto_pos]:
        if sr.verdict == Verdict.PASS and sr.frame is not None:
            frames.append(int(sr.frame))
    return frames


def _carried_literals(test: GreenTest, achieved_steps: list[Step], failing: Step) -> list[Atom]:
    """Positive ongoing relations carried into the failing step, minus those it negates (engine semantics)."""
    carried: list[Atom] = []
    seen: set[str] = set()
    for st in achieved_steps:
        for a in _extract_positive_relational_atoms(st.expr):
            k = get_atom_key(a)
            if k not in seen:
                seen.add(k)
                carried.append(a)
    negated = _extract_negated_atom_keys(failing.expr)
    return [a for a in carried if get_atom_key(a) not in negated]


def _final_false_onset(
    index: FrameIndex, atom: Atom, w0: int, w1: int, n_on: int, fps: float
) -> tuple[int | None, list[str]]:
    """Onset of the literal's final False run inside [w0, w1] plus transient-break warnings.

    A recovery counts only if the literal is True for ``n_on`` frames (the engine's Schmitt confirmation, U
    neutral); isolated True blips inside a False run do not end it.
    """
    key = get_atom_key(atom)
    seq: list[tuple[int, Tri]] = []
    for f in range(w0, w1 + 1):
        pf = lookup(index, atom, f)
        seq.append((f, pf.tri if pf is not None else Tri.U))

    t_runs = _sustained_runs(seq, Tri.T, n_on)
    last_t = t_runs[-1][1] if t_runs else None
    onset: int | None = None
    for f, t in seq:
        if t == Tri.F and (last_t is None or f > last_t):
            onset = f
            break

    warnings: list[str] = []
    # Transient breaks: False runs followed by a sustained recovery.
    for r0, _r1 in t_runs:
        run = [f for f, t in seq if t == Tri.F and f < r0]
        prev_end = max((e for _s, e in t_runs if e < r0), default=w0 - 1)
        run = [f for f in run if f > prev_end]
        if run:
            a, b = run[0], run[-1]
            warnings.append(
                f"transient break: {key} was False on frames {a}-{b} "
                f"({_fmt_s(a, fps)}-{_fmt_s(b, fps)}) and recovered for >= {n_on} frames at frame {r0}; "
                "not blamed"
            )
    return onset, warnings


def _cause_component(
    step: Step, index: FrameIndex, frame: int
) -> tuple[Atom | None, Component | None, bool]:
    """Most negative margin/sigma reliable component among the step's positive atoms at ``frame``.

    Returns (atom, component, is_negated_atom). Negated atoms (``not L``) contribute ``-score``.
    """
    negated_keys = _extract_negated_atom_keys(step.expr)
    best: tuple[float, Atom, Component, bool] | None = None
    for atom in _extract_atoms(step.expr):
        pf = lookup(index, atom, frame)
        if pf is None:
            continue
        is_neg = get_atom_key(atom) in negated_keys
        for c in reliable_components(pf):
            s = component_score(c)
            s = -s if is_neg else s
            if best is None or s < best[0]:
                best = (s, atom, c, is_neg)
    if best is None:
        return None, None, False
    return best[1], best[2], best[3]


def find_transition(
    result: RunResult,
    frames: dict[str, list[PredFrame]] | list[PredFrame],
    test: GreenTest,
    fps: float,
) -> Transition | None:
    """Locate the decisive transition of a FAIL run. Returns None for PASS / CAN'T TELL / unresolvable runs."""
    if result.verdict != Verdict.FAIL:
        return None
    found = _failing_step(result, test)
    if found is None:
        return None
    pos, step = found
    index = index_pred_frames(frames)
    n_total = total_frames(index)
    if n_total == 0:
        return None
    n_on = n_on_frames(fps)

    ach = _achievement_frames(result, pos)
    w0 = (ach[-1] + 1) if ach else 0
    w1 = n_total - 1
    if w0 > w1:
        return None  # the clip ended before the failing step could start: nothing measurable to blame

    warnings: list[str] = []

    # ---- Class 1: broken prerequisite (carried literal, final False run) ----
    achieved_steps = [s for s in test.steps if any(
        sr.index == s.index and sr.verdict == Verdict.PASS for sr in result.steps[:pos]
    )]
    carried = _carried_literals(test, achieved_steps, step)
    broken: list[tuple[int, Atom]] = []
    for lit in carried:
        onset, lit_warnings = _final_false_onset(index, lit, w0, w1, n_on, fps)
        warnings.extend(lit_warnings)
        if onset is not None:
            broken.append((onset, lit))
    if broken:
        broken.sort(key=lambda x: x[0])
        onset, lit = broken[0]
        pf = lookup(index, lit, onset)
        comp = None
        if pf is not None:
            comps = reliable_components(pf) or list(pf.components)
            if comps:
                comp = min(comps, key=component_score).name
        tr = Transition(
            cls="broken_prerequisite",
            step_index=step.index,
            step_name=step.name,
            literal=get_atom_key(lit),
            t_frame=onset,
            component=comp,
            warnings=warnings,
        )
        return tr

    # ---- Class 3: order violation ----
    for ev in result.events:
        if ev.kind == "order_violation" and ev.source == "attempt":
            atoms = _extract_atoms(step.expr)
            lit_key = get_atom_key(atoms[0]) if atoms else step.name
            return Transition(
                cls="order_violation",
                step_index=step.index,
                step_name=step.name,
                literal=lit_key,
                t_frame=int(ev.frame),
                component=None,
                warnings=warnings + ["order violation reported by the step engine"],
            )
    if len(ach) >= 2:
        o0, o1 = ach[0] + 1, ach[-1]
        tris = [(f, expr_tri(step.expr, index, f)) for f in range(o0, o1 + 1)]
        runs = _sustained_runs(tris, Tri.T, n_on)
        if runs:
            onset = runs[0][0]
            atom, comp, _ = _cause_component(step, index, onset)
            prev_name = result.steps[pos - 1].name if pos >= 1 else "previous step"
            return Transition(
                cls="order_violation",
                step_index=step.index,
                step_name=step.name,
                literal=get_atom_key(atom) if atom is not None else step.name,
                t_frame=onset,
                component=comp.name if comp is not None else None,
                warnings=warnings
                + [
                    f"step '{step.name}' condition held at frames {runs[0][0]}-{runs[0][1]} before "
                    f"step '{prev_name}' was achieved (frame {ach[-1]}) and never afterwards"
                ],
            )

    # ---- Class 2: unmet condition (argmax softscore) ----
    scores: dict[int, float] = {}
    for f in range(w0, w1 + 1):
        s = expr_softscore(step.expr, index, f)
        if s is not None and math.isfinite(s):
            scores[f] = s
    if not scores:
        return None  # every frame unresolved: CAN'T TELL territory, never guess
    best_val = max(scores.values())
    t_star = min(f for f, v in scores.items() if v >= best_val - 1e-12)
    atom, comp, is_neg = _cause_component(step, index, t_star)
    if atom is None or comp is None:
        return None
    if comp.tri == Tri.U or abs(comp.margin) < comp.sigma:
        warnings.append(
            f"cause {comp.name} is below the noise floor at its best frame "
            f"(margin {comp.margin:+.2f} vs sigma {comp.sigma:.2f} {comp.unit}): the condition was never "
            "confirmed rather than measured as violated"
        )
    decided = [f for f in range(w0, w1 + 1) if expr_tri(step.expr, index, f) != Tri.U]
    undecided_run = _longest_u_run(step.expr, index, w0, w1)
    if undecided_run >= n_on:
        warnings.append(
            f"step '{step.name}' was unresolved (U) for {undecided_run} consecutive frames; a True run could be "
            "hidden there (ARCHITECTURE 7.5), so this FAIL is low-confidence"
        )
    if not decided:
        return None
    tr = Transition(
        cls="unmet",
        step_index=step.index,
        step_name=step.name,
        literal=("not " if is_neg else "") + get_atom_key(atom),
        t_frame=t_star,
        component=comp.name,
        warnings=warnings,
    )
    tr._softscore = scores
    return tr


def _longest_u_run(expr: Expr, index: FrameIndex, w0: int, w1: int) -> int:
    best = cur = 0
    for f in range(w0, w1 + 1):
        if expr_tri(expr, index, f) == Tri.U:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


__all__ = [
    "Transition",
    "find_transition",
    "index_pred_frames",
    "load_trace_pred_frames",
    "atom_softscore",
    "expr_softscore",
    "expr_tri",
    "component_score",
    "reliable_components",
    "n_on_frames",
    "lookup",
    "total_frames",
]
