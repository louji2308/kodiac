"""Base helpers and coordinate extraction for physical predicates."""

from __future__ import annotations

import math
import uuid
from typing import Any

from Kodiac_robotics.contracts.core import (
    Atom,
    Component,
    Param,
    PredFrame,
    ReasonCode,
    ScaleModel,
    Track,
    Tri,
)


def make_trace_id(prefix: str = "tr") -> str:
    """Generate a unique traceable identifier."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def get_atom_key(atom: Atom) -> str:
    """Return canonical representation key for an atom."""
    if atom.kind == "pred" and atom.name:
        args_str = ", ".join(atom.args)
        return f"{atom.name}({args_str})"
    elif atom.kind == "looks":
        opposite = f" | {atom.looks_neg}" if atom.looks_neg else ""
        return f"looks({', '.join(atom.args)}, '{atom.looks_pos}'{opposite})"
    elif atom.kind == "manual":
        return f"MANUAL('{atom.manual_text}')"
    return f"unknown_atom_{uuid.uuid4().hex[:6]}"


def get_param_value(params: list[Param], name: str, default: float) -> float:
    """Retrieve a parameter value by name from an Atom's param list."""
    for p in params:
        if p.name == name:
            return float(p.value)
    return default


def get_object_coords(
    obj: str,
    tracks: dict[str, Track],
    scale: ScaleModel,
    frame: int,
    context: dict[str, Any] | None = None,
) -> tuple[float, float, float, float] | None:
    """Extract (X, D, h, sigma) for an object in table frame.

    Returns None if the object is not visible or missing.
    """
    if obj in ("table", "surface"):
        return (0.0, 0.0, 0.0, 0.0)

    # Check track existence
    track = tracks.get(obj)
    if track is None:
        return None

    # Check frame existence in track
    if frame not in track.frames:
        return None

    mask = track.frames[frame]
    if mask.area_px <= 0 or mask.score < 0.2:
        return None

    try:
        x, d, h, sigma = scale.to_table_frame(obj, frame)
        return float(x), float(d), float(h), float(sigma)
    except Exception:
        return None


def conjoin_components(components: list[Component]) -> Tri:
    """Compute overall Tri-state for a list of components using Kleene AND.

    If any component is F -> F.
    Else if any component is U -> U.
    Else -> T. (Empty list -> T).
    """
    if not components:
        return Tri.T

    has_u = False
    for comp in components:
        if comp.tri == Tri.F:
            return Tri.F
        if comp.tri == Tri.U:
            has_u = True

    return Tri.U if has_u else Tri.T


def euclidean_2d(x1: float, y1: float, x2: float, y2: float) -> float:
    """2D Euclidean distance."""
    return math.hypot(x1 - x2, y1 - y2)


def euclidean_3d(x1: float, y1: float, z1: float, x2: float, y2: float, z2: float) -> float:
    """3D Euclidean distance."""
    return math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2 + (z1 - z2) ** 2)


def create_not_visible_frame(atom: Atom, frame: int, obj_name: str) -> PredFrame:
    """Generate a PredFrame when an object is not visible."""
    atom_key = get_atom_key(atom)
    trace_id = make_trace_id(f"tr_{atom.name or 'atom'}")
    comp = Component(
        name=f"{atom.name or 'pred'}.visible",
        value=0.0,
        threshold=1.0,
        margin=-1.0,
        sigma=0.0,
        unit="ratio",
        tri=Tri.U,
        reason=ReasonCode.NOT_VISIBLE,
    )
    return PredFrame(
        frame=frame,
        atom_key=atom_key,
        tri=Tri.U,
        components=[comp],
        trace_id=trace_id,
    )
