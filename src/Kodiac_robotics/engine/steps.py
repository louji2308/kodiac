"""Step-chain execution engine with carried literals and Kleene logic."""

from __future__ import annotations

from Kodiac_robotics.contracts.core import (
    Atom,
    Component,
    Event,
    Expr,
    PredFrame,
    ReasonCode,
    Step,
    StepResult,
    Tri,
    Verdict,
)
from Kodiac_robotics.engine.logic import evaluate_expr_tree
from Kodiac_robotics.predicates.base import get_atom_key


def _extract_atoms(expr: Expr) -> list[Atom]:
    """Recursively extract all atoms from an Expr tree."""
    if expr.op == "atom":
        return [expr.atom] if expr.atom is not None else []
    atoms: list[Atom] = []
    for child in expr.children:
        atoms.extend(_extract_atoms(child))
    return atoms


def _extract_positive_relational_atoms(expr: Expr) -> list[Atom]:
    """Extract positive atoms from an expression that represent ongoing relations.

    Specifically, `moves_with` representing an ongoing grasp/hold invariant.
    """
    if expr.op == "atom":
        if expr.atom and expr.atom.name == "moves_with":
            return [expr.atom]
        return []
    if expr.op == "not":
        return []
    if expr.op == "and":
        res: list[Atom] = []
        for child in expr.children:
            res.extend(_extract_positive_relational_atoms(child))
        return res
    return []


def _extract_negated_atom_keys(expr: Expr) -> set[str]:
    """Extract keys of atoms that appear negated (inside a 'not' node)."""
    if expr.op == "not":
        return {get_atom_key(a) for a in _extract_atoms(expr)}
    negated: set[str] = set()
    for child in expr.children:
        negated.update(_extract_negated_atom_keys(child))
    return negated


def _lookup_pred_frame(
    atom: Atom,
    frame: int,
    pred_frames_by_atom: dict[str, list[PredFrame]],
) -> PredFrame | None:
    """Find the PredFrame for a given atom and frame index."""
    key = get_atom_key(atom)
    if key in pred_frames_by_atom:
        frames = pred_frames_by_atom[key]
        if 0 <= frame < len(frames):
            return frames[frame]

    # Fallback to atom.name lookup
    if atom.name and atom.name in pred_frames_by_atom:
        frames = pred_frames_by_atom[atom.name]
        if 0 <= frame < len(frames):
            return frames[frame]

    return None


def evaluate_step_chain(
    steps: list[Step],
    pred_frames_by_atom: dict[str, list[PredFrame]],
    fps: float,
) -> tuple[Verdict, list[StepResult], list[ReasonCode], list[Event]]:
    """Evaluates sequential step chain over clip.

    - Step achievement: a_k = min { t > a_{k-1} : C_k == TRUE for n_on frames }.
    - Carried literals persistence: positive literals in C_k persist into subsequent steps
      unless explicitly negated or the next step achieves.
    - Resolves overall Verdict: PASS if all steps achieve; FAIL if a terminal violation occurs;
      CANT_TELL if decisive step is UNKNOWN.
    - Returns: (overall_verdict, step_results, top_level_reasons, events).
    - INVARIANT: If overall_verdict == CANT_TELL, len(top_level_reasons) >= 1.
    """
    if not steps:
        return Verdict.PASS, [], [], []

    # Dynamic confirmation window: n_on = max(2, int(round(0.10 * fps)))
    n_on = max(2, int(round(0.10 * fps)))

    # Determine total frame count T
    total_frames = 0
    for frames_list in pred_frames_by_atom.values():
        if len(frames_list) > total_frames:
            total_frames = len(frames_list)

    if total_frames == 0:
        # No frames available -> CANT_TELL with NOT_VISIBLE
        reasons = [ReasonCode.NOT_VISIBLE]
        res = [
            StepResult(
                index=s.index,
                name=s.name,
                verdict=Verdict.CANT_TELL if i == 0 else None,
                reasons=reasons if i == 0 else [],
                evidence=["no frames available in clip"] if i == 0 else [],
            )
            for i, s in enumerate(steps)
        ]
        return Verdict.CANT_TELL, res, reasons, []

    step_results: list[StepResult] = []
    events: list[Event] = []
    top_level_reasons: list[ReasonCode] = []
    overall_verdict = Verdict.PASS

    carried_atoms: list[Atom] = []
    prev_achievement_frame = -1

    for step_idx, step in enumerate(steps):
        t_start = prev_achievement_frame + 1
        if t_start >= total_frames:
            # Clip ended before step started
            step_verdict = Verdict.FAIL
            step_res = StepResult(
                index=step.index,
                name=step.name,
                verdict=step_verdict,
                t_s=round((total_frames - 1) / fps, 4),
                frame=total_frames - 1,
                decisive=[],
                reasons=[],
                evidence=[f"clip ended at frame {total_frames - 1} before step start"],
            )
            step_results.append(step_res)
            events.append(
                Event(
                    step=step.index,
                    step_name=step.name,
                    kind="failed",
                    t_s=round((total_frames - 1) / fps, 4),
                    frame=total_frames - 1,
                    fps=fps,
                    source="attempt",
                    verdict=Verdict.FAIL,
                )
            )
            overall_verdict = Verdict.FAIL
            # Mark subsequent steps as unreached
            for rem_step in steps[step_idx + 1 :]:
                step_results.append(
                    StepResult(
                        index=rem_step.index,
                        name=rem_step.name,
                        verdict=None,
                        t_s=None,
                        frame=None,
                        decisive=[],
                        reasons=[],
                    )
                )
            break

        # Filter carried literals: exclude those explicitly negated in this step
        negated_keys = _extract_negated_atom_keys(step.expr)
        active_carried = [
            a for a in carried_atoms if get_atom_key(a) not in negated_keys
        ]

        consecutive_t = 0
        achievement_frame: int | None = None
        broken_carried: tuple[Atom, int, PredFrame] | None = None
        decisive_components: list[Component] = []
        step_atoms = _extract_atoms(step.expr)

        for t in range(t_start, total_frames):
            # 1. Check carried literals at frame t
            carried_failed = False
            for carried_atom in active_carried:
                pf = _lookup_pred_frame(carried_atom, t, pred_frames_by_atom)
                if pf is not None and pf.tri == Tri.F:
                    broken_carried = (carried_atom, t, pf)
                    carried_failed = True
                    break

            if carried_failed:
                break

            # 2. Evaluate step condition C_k at frame t
            atom_values: dict[str, Tri] = {}
            frame_components: list[Component] = []
            for atom in step_atoms:
                pf = _lookup_pred_frame(atom, t, pred_frames_by_atom)
                if pf is not None:
                    atom_values[get_atom_key(atom)] = pf.tri
                    frame_components.extend(pf.components)
                else:
                    atom_values[get_atom_key(atom)] = Tri.U

            c_val = evaluate_expr_tree(step.expr, atom_values)
            decisive_components = frame_components

            if c_val == Tri.T:
                consecutive_t += 1
                if consecutive_t >= n_on:
                    achievement_frame = t
                    break
            elif c_val == Tri.F:
                consecutive_t = 0
            elif c_val == Tri.U:
                # UNKNOWN is neutral in Schmitt trigger
                pass

        # Handle Step Outcome
        if achievement_frame is not None:
            # Case A: Step achieved!
            t_s = round(achievement_frame / fps, 4)
            prev_achievement_frame = achievement_frame
            step_res = StepResult(
                index=step.index,
                name=step.name,
                verdict=Verdict.PASS,
                t_s=t_s,
                frame=achievement_frame,
                decisive=decisive_components,
                reasons=[],
                evidence=[f"achieved at frame {achievement_frame} (t={t_s}s)"],
            )
            step_results.append(step_res)

            # Record event
            event_kind = "achieved"
            predicate_name = None
            if len(step_atoms) == 1 and step_atoms[0].name:
                predicate_name = step_atoms[0].name
                if predicate_name == "lifted":
                    event_kind = "lifted"
                elif predicate_name == "moves_with":
                    event_kind = "grasped"
                elif predicate_name == "inside":
                    event_kind = "entered"
                elif predicate_name == "on":
                    event_kind = "settled"

            events.append(
                Event(
                    step=step.index,
                    step_name=step.name,
                    kind=event_kind,  # type: ignore[arg-type]
                    predicate=predicate_name,
                    args=step_atoms[0].args if step_atoms else [],
                    t_s=t_s,
                    frame=achievement_frame,
                    fps=fps,
                    measurements={
                        c.name: (c.value, c.sigma) for c in decisive_components
                    },
                    source="attempt",
                    verdict=Verdict.PASS,
                )
            )

            # Accumulate newly achieved ongoing positive relations into carried_atoms
            new_carried = _extract_positive_relational_atoms(step.expr)
            for a in new_carried:
                if get_atom_key(a) not in [get_atom_key(ca) for ca in carried_atoms]:
                    carried_atoms.append(a)

        elif broken_carried is not None:
            # Case B: Carried literal broke (Class 1 broken prerequisite)
            broken_atom, t_break, pf = broken_carried
            t_s = round(t_break / fps, 4)
            overall_verdict = Verdict.FAIL
            step_reasons = [c.reason for c in pf.components if c.reason is not None]

            step_res = StepResult(
                index=step.index,
                name=step.name,
                verdict=Verdict.FAIL,
                t_s=t_s,
                frame=t_break,
                decisive=pf.components,
                reasons=step_reasons,
                evidence=[
                    f"carried invariant {get_atom_key(broken_atom)} broke at frame {t_break} (t={t_s}s)"
                ],
            )
            step_results.append(step_res)

            # Event for break
            events.append(
                Event(
                    step=step.index,
                    step_name=step.name,
                    kind="failed",
                    t_s=t_s,
                    frame=t_break,
                    fps=fps,
                    source="attempt",
                    verdict=Verdict.FAIL,
                )
            )
            if broken_atom.name == "moves_with":
                events.append(
                    Event(
                        step=step.index,
                        step_name=step.name,
                        kind="released",
                        predicate="moves_with",
                        args=broken_atom.args,
                        t_s=t_s,
                        frame=t_break,
                        fps=fps,
                        source="attempt",
                        verdict=Verdict.FAIL,
                    )
                )

            # Mark remaining steps as not evaluated
            for rem_step in steps[step_idx + 1 :]:
                step_results.append(
                    StepResult(
                        index=rem_step.index,
                        name=rem_step.name,
                        verdict=None,
                        t_s=None,
                        frame=None,
                        decisive=[],
                        reasons=[],
                    )
                )
            break

        else:
            # Case C: Step did not achieve and no carried invariant broke
            decisive_frame = total_frames - 1
            t_s = round(decisive_frame / fps, 4)

            # Determine if CANT_TELL or FAIL
            has_unknown = False
            reasons_found: list[ReasonCode] = []
            for comp in decisive_components:
                if comp.tri == Tri.U:
                    has_unknown = True
                if comp.reason is not None:
                    reasons_found.append(comp.reason)

            # Also check if any atom had Tri.U at the decisive frame
            for atom in step_atoms:
                pf = _lookup_pred_frame(atom, decisive_frame, pred_frames_by_atom)
                if pf is not None:
                    if pf.tri == Tri.U:
                        has_unknown = True
                    for c in pf.components:
                        if c.reason is not None and c.reason not in reasons_found:
                            reasons_found.append(c.reason)

            if has_unknown or reasons_found:
                step_verdict = Verdict.CANT_TELL
                overall_verdict = Verdict.CANT_TELL
                if not reasons_found:
                    reasons_found.append(ReasonCode.NOT_VISIBLE)
                top_level_reasons.extend(reasons_found)
            else:
                step_verdict = Verdict.FAIL
                overall_verdict = Verdict.FAIL

            step_res = StepResult(
                index=step.index,
                name=step.name,
                verdict=step_verdict,
                t_s=t_s,
                frame=decisive_frame,
                decisive=decisive_components,
                reasons=reasons_found,
                evidence=[
                    f"step condition unmet by clip end (frame {decisive_frame}, t={t_s}s)"
                ],
            )
            step_results.append(step_res)

            events.append(
                Event(
                    step=step.index,
                    step_name=step.name,
                    kind="failed",
                    t_s=t_s,
                    frame=decisive_frame,
                    fps=fps,
                    source="attempt",
                    verdict=step_verdict,
                )
            )

            # Mark remaining steps as not reached
            for rem_step in steps[step_idx + 1 :]:
                step_results.append(
                    StepResult(
                        index=rem_step.index,
                        name=rem_step.name,
                        verdict=None,
                        t_s=None,
                        frame=None,
                        decisive=[],
                        reasons=[],
                    )
                )
            break

    # Crucial Invariant: If overall_verdict == CANT_TELL, len(top_level_reasons) >= 1
    if overall_verdict == Verdict.CANT_TELL and not top_level_reasons:
        top_level_reasons.append(ReasonCode.NOT_VISIBLE)

    return overall_verdict, step_results, top_level_reasons, events
