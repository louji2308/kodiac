"""Implementation of physical predicate `near(a, b)`."""

from __future__ import annotations

import math
from typing import Any

from Kodiac_robotics.contracts.core import (
    Atom,
    Component,
    PredFrame,
    ScaleModel,
    Track,
    Tri,
)
from Kodiac_robotics.predicates.base import (
    conjoin_components,
    create_not_visible_frame,
    euclidean_3d,
    get_atom_key,
    get_object_coords,
    get_param_value,
    make_trace_id,
)


def evaluate_near(
    atom: Atom,
    tracks: dict[str, Track],
    scale: ScaleModel,
    frame: int,
    fps: float,
    context: dict[str, Any] | None = None,
) -> PredFrame:
    """Evaluates `near(a, b)` on a single frame.

    Component:
    - near.distance (cm): 3D Euclidean distance margin m = max_cm - d_3D
    """
    args = atom.args
    if len(args) < 2:
        raise ValueError(f"near predicate requires 2 arguments (obj_a, obj_b), got: {args}")

    obj_a = args[0]
    obj_b = args[1]

    max_cm = get_param_value(atom.params, "max_cm", 5.0)

    coords_a = get_object_coords(obj_a, tracks, scale, frame, context)
    if coords_a is None:
        return create_not_visible_frame(atom, frame, obj_a)

    coords_b = get_object_coords(obj_b, tracks, scale, frame, context)
    if coords_b is None:
        return create_not_visible_frame(atom, frame, obj_b)

    xa, da, ha, sa = coords_a
    xb, db, hb, sb = coords_b

    d_3d = euclidean_3d(xa, da, ha, xb, db, hb)
    m = max_cm - d_3d
    sigma_dist = math.hypot(sa, sb)

    c_near = Component(
        name="near.distance",
        value=d_3d,
        threshold=max_cm,
        margin=m,
        sigma=sigma_dist,
        unit="cm",
        tri=Tri.T if m > 0 else Tri.F,
    )

    components = [c_near]
    overall_tri = conjoin_components(components)

    return PredFrame(
        frame=frame,
        atom_key=get_atom_key(atom),
        tri=overall_tri,
        components=components,
        trace_id=make_trace_id("tr_near"),
    )
