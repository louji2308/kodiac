"""Dispatcher for AST Atoms to physical and visual predicates."""

from __future__ import annotations

from typing import Any

from Kodiac_robotics.contracts.core import (
    Atom,
    PredFrame,
    ScaleModel,
    Track,
    Tri,
)
from Kodiac_robotics.predicates.base import get_atom_key, make_trace_id
from Kodiac_robotics.predicates.dwell import evaluate_dwell
from Kodiac_robotics.predicates.inside import evaluate_inside
from Kodiac_robotics.predicates.lifted import evaluate_lifted
from Kodiac_robotics.predicates.moves_with import evaluate_moves_with
from Kodiac_robotics.predicates.near import evaluate_near
from Kodiac_robotics.predicates.on import evaluate_on


def evaluate_atom(
    atom: Atom,
    tracks: dict[str, Track],
    scale: ScaleModel,
    frame: int,
    fps: float,
    context: dict[str, Any] | None = None,
) -> PredFrame:
    """Evaluates an AST Atom on a single frame.

    - If atom.kind == 'pred', dispatches to predicate implementation in predicates/{name}.py.
    - If atom.kind == 'looks', returns PredFrame(tri=UNKNOWN, components=[]) pass-through.
    - If atom.kind == 'manual', skips evaluation (returns PredFrame(tri=T, components=[])).
    """
    atom_key = get_atom_key(atom)

    if atom.kind == "looks":
        return PredFrame(
            frame=frame,
            atom_key=atom_key,
            tri=Tri.U,
            components=[],
            trace_id=make_trace_id("tr_looks"),
        )

    if atom.kind == "manual":
        return PredFrame(
            frame=frame,
            atom_key=atom_key,
            tri=Tri.T,
            components=[],
            trace_id=make_trace_id("tr_manual"),
        )

    if atom.kind == "pred":
        name = atom.name
        if name == "on":
            return evaluate_on(atom, tracks, scale, frame, fps, context)
        elif name == "inside":
            return evaluate_inside(atom, tracks, scale, frame, fps, context)
        elif name == "near":
            return evaluate_near(atom, tracks, scale, frame, fps, context)
        elif name == "lifted":
            return evaluate_lifted(atom, tracks, scale, frame, fps, context)
        elif name == "moves_with":
            return evaluate_moves_with(atom, tracks, scale, frame, fps, context)
        elif name == "dwell":
            return evaluate_dwell(atom, tracks, scale, frame, fps, context)
        else:
            raise ValueError(f"Unknown predicate '{name}' for atom: {atom}")

    raise ValueError(f"Unknown atom kind '{atom.kind}' for atom: {atom}")


def evaluate_atom_over_clip(
    atom: Atom,
    tracks: dict[str, Track],
    scale: ScaleModel,
    n_frames: int,
    fps: float,
    context: dict[str, Any] | None = None,
) -> list[PredFrame]:
    """Evaluates an AST Atom sequentially over all frames in a clip."""
    return [
        evaluate_atom(atom, tracks, scale, f, fps, context)
        for f in range(n_frames)
    ]
