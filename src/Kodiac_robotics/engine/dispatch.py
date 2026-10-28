"""Engine-level predicate and step dispatch utilities."""

from __future__ import annotations

from typing import Any

from Kodiac_robotics.contracts.core import (
    GreenTest,
    PredFrame,
    ScaleModel,
    Step,
    Track,
)
from Kodiac_robotics.engine.steps import _extract_atoms
from Kodiac_robotics.predicates.base import get_atom_key
from Kodiac_robotics.predicates.dispatch import evaluate_atom, evaluate_atom_over_clip


def evaluate_step_atoms(
    step: Step,
    tracks: dict[str, Track],
    scale: ScaleModel,
    n_frames: int,
    fps: float,
    context: dict[str, Any] | None = None,
) -> dict[str, list[PredFrame]]:
    """Evaluates all atoms in a single Step over all frames of a clip."""
    atoms = _extract_atoms(step.expr)
    result: dict[str, list[PredFrame]] = {}
    for atom in atoms:
        key = get_atom_key(atom)
        if key not in result:
            result[key] = evaluate_atom_over_clip(
                atom, tracks, scale, n_frames, fps, context
            )
    return result


def evaluate_green_test_atoms(
    test: GreenTest,
    tracks: dict[str, Track],
    scale: ScaleModel,
    n_frames: int,
    fps: float,
    context: dict[str, Any] | None = None,
) -> dict[str, list[PredFrame]]:
    """Evaluates all atoms across all steps of a GreenTest over all frames of a clip."""
    result: dict[str, list[PredFrame]] = {}
    for step in test.steps:
        for atom in _extract_atoms(step.expr):
            key = get_atom_key(atom)
            if key not in result:
                result[key] = evaluate_atom_over_clip(
                    atom, tracks, scale, n_frames, fps, context
                )
    return result


__all__ = [
    "evaluate_atom",
    "evaluate_atom_over_clip",
    "evaluate_green_test_atoms",
    "evaluate_step_atoms",
]
