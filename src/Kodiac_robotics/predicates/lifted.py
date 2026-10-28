"""Implementation of physical predicate `lifted(a)`."""

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
    get_atom_key,
    get_object_coords,
    get_param_value,
    make_trace_id,
)


def evaluate_lifted(
    atom: Atom,
    tracks: dict[str, Track],
    scale: ScaleModel,
    frame: int,
    fps: float,
    context: dict[str, Any] | None = None,
) -> PredFrame:
    """Evaluates `lifted(a, min_cm=2.0)` on a single frame.

    Component:
    - lifted.height (cm): vertical displacement margin m = (h_A,t - h_A,0) - min_cm
    """
    args = atom.args
    if len(args) < 1:
        raise ValueError(f"lifted predicate requires at least 1 argument (obj_a), got: {args}")

    obj_a = args[0]
    min_cm = get_param_value(atom.params, "min_cm", 2.0)

    coords_curr = get_object_coords(obj_a, tracks, scale, frame, context)
    if coords_curr is None:
        return create_not_visible_frame(atom, frame, obj_a)

    xa, da, ha_t, sa_t = coords_curr

    # Determine baseline rest height h_A,0
    h_a_0 = 0.0
    sa_0 = sa_t
    found_baseline = False

    if context:
        if "baselines" in context and obj_a in context["baselines"]:
            b = context["baselines"][obj_a]
            if isinstance(b, dict) and "h0" in b:
                h_a_0 = float(b["h0"])
                sa_0 = float(b.get("sigma", sa_t))
                found_baseline = True
        elif "rest_heights" in context and obj_a in context["rest_heights"]:
            h_a_0 = float(context["rest_heights"][obj_a])
            found_baseline = True

    if not found_baseline:
        # Check frame 0 or earliest available frame
        track = tracks.get(obj_a)
        earliest_frame = 0
        if track and track.frames:
            sorted_frames = sorted(track.frames.keys())
            if sorted_frames:
                earliest_frame = sorted_frames[0]
        coords_0 = get_object_coords(obj_a, tracks, scale, earliest_frame, context)
        if coords_0 is not None:
            _, _, h_a_0, sa_0 = coords_0
        else:
            h_a_0 = 0.0

    delta_h = ha_t - h_a_0
    m = delta_h - min_cm
    sigma_h = math.hypot(sa_t, sa_0)

    c_lifted = Component(
        name="lifted.height",
        value=delta_h,
        threshold=min_cm,
        margin=m,
        sigma=sigma_h,
        unit="cm",
        tri=Tri.T if m > 0 else Tri.F,
    )

    components = [c_lifted]
    overall_tri = conjoin_components(components)

    return PredFrame(
        frame=frame,
        atom_key=get_atom_key(atom),
        tri=overall_tri,
        components=components,
        trace_id=make_trace_id("tr_lifted"),
    )
