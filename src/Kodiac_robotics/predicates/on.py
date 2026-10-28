"""Implementation of physical predicate `on(a, b)`."""

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
    euclidean_2d,
    get_atom_key,
    get_object_coords,
    get_param_value,
    make_trace_id,
)


def evaluate_on(
    atom: Atom,
    tracks: dict[str, Track],
    scale: ScaleModel,
    frame: int,
    fps: float,
    context: dict[str, Any] | None = None,
) -> PredFrame:
    """Evaluates `on(a, b)` on a single frame.

    Components:
    - on.align_xy (cm): lateral alignment margin m_xy = align_xy_cm - d_xy
    - on.gap (cm): vertical gap margin m_z = gap_cm - |h_A - H_B|
    - on.scale_ratio (ratio): depth consistency margin m_rho = depth_tol - |D_A / D_B - 1|
    """
    args = atom.args
    if len(args) < 1:
        raise ValueError(f"on predicate requires at least 1 argument, got: {args}")

    obj_a = args[0]
    obj_b = args[1] if len(args) > 1 else "surface"

    align_xy_cm = get_param_value(atom.params, "align_xy_cm", 1.5)
    gap_cm = get_param_value(atom.params, "gap_cm", 1.0)
    depth_tol = get_param_value(atom.params, "depth_tol", 0.12)

    coords_a = get_object_coords(obj_a, tracks, scale, frame, context)
    if coords_a is None:
        return create_not_visible_frame(atom, frame, obj_a)

    xa, da, ha, sa = coords_a

    if obj_b in ("table", "surface"):
        xb, db, hb, sb = xa, da, 0.0, 0.0
        h_top_b = 0.0
    else:
        coords_b = get_object_coords(obj_b, tracks, scale, frame, context)
        if coords_b is None:
            return create_not_visible_frame(atom, frame, obj_b)
        xb, db, hb, sb = coords_b

        # Resolve top height of object B
        b_height = 0.0
        if context:
            if "object_heights" in context and obj_b in context["object_heights"]:
                b_height = float(context["object_heights"][obj_b])
            elif "object_sizes" in context and obj_b in context["object_sizes"]:
                b_height = float(context["object_sizes"][obj_b])
        h_top_b = hb + b_height

    # 1. Lateral alignment margin: m_xy = align_xy_cm - d_xy
    d_xy = euclidean_2d(xa, da, xb, db)
    m_xy = align_xy_cm - d_xy
    sigma_xy = math.hypot(sa, sb)
    c_align = Component(
        name="on.align_xy",
        value=d_xy,
        threshold=align_xy_cm,
        margin=m_xy,
        sigma=sigma_xy,
        unit="cm",
        tri=Tri.T if m_xy > 0 else Tri.F,
    )

    # 2. Vertical gap margin: m_z = gap_cm - |h_a - h_top_b|
    gap_val = abs(ha - h_top_b)
    m_z = gap_cm - gap_val
    sigma_z = math.hypot(sa, sb)
    c_gap = Component(
        name="on.gap",
        value=gap_val,
        threshold=gap_cm,
        margin=m_z,
        sigma=sigma_z,
        unit="cm",
        tri=Tri.T if m_z > 0 else Tri.F,
    )

    # 3. Depth consistency / scale ratio: m_rho = depth_tol - |D_A / D_B - 1|
    if db > 0 and da > 0 and obj_b not in ("table", "surface"):
        ratio_diff = abs(da / db - 1.0)
    else:
        ratio_diff = 0.0
    m_rho = depth_tol - ratio_diff
    sigma_rho = 0.02
    c_rho = Component(
        name="on.scale_ratio",
        value=ratio_diff,
        threshold=depth_tol,
        margin=m_rho,
        sigma=sigma_rho,
        unit="ratio",
        tri=Tri.T if m_rho > 0 else Tri.F,
    )

    components = [c_align, c_gap, c_rho]
    overall_tri = conjoin_components(components)

    return PredFrame(
        frame=frame,
        atom_key=get_atom_key(atom),
        tri=overall_tri,
        components=components,
        trace_id=make_trace_id("tr_on"),
    )
