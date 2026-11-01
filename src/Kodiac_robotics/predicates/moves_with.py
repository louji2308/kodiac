"""Implementation of physical predicate `moves_with(a, b)`."""

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


def evaluate_moves_with(
    atom: Atom,
    tracks: dict[str, Track],
    scale: ScaleModel,
    frame: int,
    fps: float,
    context: dict[str, Any] | None = None,
) -> PredFrame:
    """Evaluates `moves_with(a, b, window_s=0.33, slip_cm=1.0)` on a single frame.

    Component:
    - moves_with.slip (cm): relative displacement margin m = slip_cm - ||Delta_A - Delta_B||
    """
    args = atom.args
    if len(args) < 2:
        raise ValueError(f"moves_with predicate requires 2 arguments (obj_a, obj_b), got: {args}")

    obj_a = args[0]
    obj_b = args[1]

    slip_cm = get_param_value(atom.params, "slip_cm", 1.0)
    window_s = get_param_value(atom.params, "window_s", 0.33)

    coords_curr_a = get_object_coords(obj_a, tracks, scale, frame, context)
    if coords_curr_a is None:
        return create_not_visible_frame(atom, frame, obj_a)

    coords_curr_b = get_object_coords(obj_b, tracks, scale, frame, context)
    if coords_curr_b is None:
        return create_not_visible_frame(atom, frame, obj_b)

    xa_t, da_t, ha_t, sa_t = coords_curr_a
    xb_t, db_t, hb_t, sb_t = coords_curr_b

    # Dynamic time-base: window_frames = max(2, int(round(window_s * fps)))
    window_frames = max(2, int(round(window_s * fps)))
    ref_frame = max(0, frame - window_frames)

    coords_ref_a = get_object_coords(obj_a, tracks, scale, ref_frame, context)
    coords_ref_b = get_object_coords(obj_b, tracks, scale, ref_frame, context)

    if coords_ref_a is None or coords_ref_b is None or frame == 0:
        delta_xa, delta_da, delta_ha = 0.0, 0.0, 0.0
        delta_xb, delta_db, delta_hb = 0.0, 0.0, 0.0
    else:
        xa_0, da_0, ha_0, _ = coords_ref_a
        xb_0, db_0, hb_0, _ = coords_ref_b
        delta_xa, delta_da, delta_ha = xa_t - xa_0, da_t - da_0, ha_t - ha_0
        delta_xb, delta_db, delta_hb = xb_t - xb_0, db_t - db_0, hb_t - hb_0

    # Relative displacement: ||Delta_A - Delta_B||
    rho_rel = euclidean_3d(
        delta_xa,
        delta_da,
        delta_ha,
        delta_xb,
        delta_db,
        delta_hb,
    )

    # Check if both objects are currently stationary (at rest) over recent 3-frame window.
    # Two motionless objects cannot be in an active coupled motion: moves_with evaluates to False.
    short_ref = max(0, frame - 3)
    coords_short_a = get_object_coords(obj_a, tracks, scale, short_ref, context)
    coords_short_b = get_object_coords(obj_b, tracks, scale, short_ref, context)
    if coords_short_a is not None and coords_short_b is not None and frame > 0:
        short_da = euclidean_3d(xa_t, da_t, ha_t, coords_short_a[0], coords_short_a[1], coords_short_a[2])
        short_db = euclidean_3d(xb_t, db_t, hb_t, coords_short_b[0], coords_short_b[1], coords_short_b[2])
        is_motionless = (short_da < 0.3 and short_db < 0.3)
    else:
        mag_a = euclidean_3d(delta_xa, delta_da, delta_ha, 0.0, 0.0, 0.0)
        mag_b = euclidean_3d(delta_xb, delta_db, delta_hb, 0.0, 0.0, 0.0)
        is_motionless = (mag_a < 0.5 and mag_b < 0.5)

    m = slip_cm - rho_rel
    sigma_slip = math.sqrt(2.0) * math.hypot(sa_t, sb_t)

    tri_val = Tri.F if is_motionless else (Tri.T if m > 0 else Tri.F)
    effective_margin = -max(1.5, 2.5 * sigma_slip) if is_motionless else m

    c_slip = Component(
        name="moves_with.slip",
        value=rho_rel,
        threshold=slip_cm,
        margin=effective_margin,
        sigma=sigma_slip,
        unit="cm",
        tri=tri_val,
    )

    components = [c_slip]
    overall_tri = conjoin_components(components)

    return PredFrame(
        frame=frame,
        atom_key=get_atom_key(atom),
        tri=overall_tri,
        components=components,
        trace_id=make_trace_id("tr_moves_with"),
    )
