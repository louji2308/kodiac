"""Implementation of physical predicate `inside(a, b)`."""

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


def evaluate_inside(
    atom: Atom,
    tracks: dict[str, Track],
    scale: ScaleModel,
    frame: int,
    fps: float,
    context: dict[str, Any] | None = None,
) -> PredFrame:
    """Evaluates `inside(a, b)` on a single frame.

    Components:
    - inside.rim_margin (cm): clearance to container rim: m_rim = (R_B - d_xy) - rim_margin_cm
    - inside.depth_consistency (ratio): m_depth = depth_tol - |D_A / D_B - 1|
    - inside.front_occluder (cm): containment depth: m_occ = (h_B + H_B) - h_A
    """
    args = atom.args
    if len(args) < 2:
        raise ValueError(f"inside predicate requires 2 arguments (obj, container), got: {args}")

    obj_a = args[0]
    obj_b = args[1]

    rim_margin_cm = get_param_value(atom.params, "rim_margin_cm", 0.5)
    depth_tol = get_param_value(atom.params, "depth_tol", 0.15)

    coords_a = get_object_coords(obj_a, tracks, scale, frame, context)
    if coords_a is None:
        return create_not_visible_frame(atom, frame, obj_a)

    coords_b = get_object_coords(obj_b, tracks, scale, frame, context)
    if coords_b is None:
        return create_not_visible_frame(atom, frame, obj_b)

    xa, da, ha, sa = coords_a
    xb, db, hb, sb = coords_b

    # Resolve container radius and height
    container_radius = 5.0  # default 5 cm radius
    container_height = 8.0  # default 8 cm height
    if context:
        if "container_radii" in context and obj_b in context["container_radii"]:
            container_radius = float(context["container_radii"][obj_b])
        elif "object_sizes" in context and obj_b in context["object_sizes"]:
            container_radius = float(context["object_sizes"][obj_b]) / 2.0

        if "object_heights" in context and obj_b in context["object_heights"]:
            container_height = float(context["object_heights"][obj_b])

    # 1. In-rim clearance margin: m_rim = (R_B - d_xy) - rim_margin_cm
    d_xy = euclidean_2d(xa, da, xb, db)
    clearance_to_rim = container_radius - d_xy
    m_rim = clearance_to_rim - rim_margin_cm
    sigma_rim = math.hypot(sa, sb)
    c_rim = Component(
        name="inside.rim_margin",
        value=clearance_to_rim,
        threshold=rim_margin_cm,
        margin=m_rim,
        sigma=sigma_rim,
        unit="cm",
        tri=Tri.T if m_rim > 0 else Tri.F,
    )

    # 2. Depth consistency margin: m_depth = depth_tol - |D_A / D_B - 1|
    if db > 0 and da > 0:
        depth_diff = abs(da / db - 1.0)
    else:
        depth_diff = 0.0
    m_depth = depth_tol - depth_diff
    sigma_depth = 0.02
    c_depth = Component(
        name="inside.depth_consistency",
        value=depth_diff,
        threshold=depth_tol,
        margin=m_depth,
        sigma=sigma_depth,
        unit="ratio",
        tri=Tri.T if m_depth > 0 else Tri.F,
    )

    # 3. Front-occluder / containment height check: m_occ = (h_B + H_B) - h_A
    h_top_b = hb + container_height
    m_occ = h_top_b - ha
    sigma_occ = math.hypot(sa, sb)
    c_occ = Component(
        name="inside.front_occluder",
        value=ha - hb,
        threshold=container_height,
        margin=m_occ,
        sigma=sigma_occ,
        unit="cm",
        tri=Tri.T if m_occ >= 0 else Tri.F,
    )

    components = [c_rim, c_depth, c_occ]
    overall_tri = conjoin_components(components)

    return PredFrame(
        frame=frame,
        atom_key=get_atom_key(atom),
        tri=overall_tri,
        components=components,
        trace_id=make_trace_id("tr_inside"),
    )
