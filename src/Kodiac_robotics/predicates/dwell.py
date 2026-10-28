"""Implementation of physical predicate `dwell(a, for_s=0.5, max_speed_cm_s=1.0)`."""

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


def evaluate_dwell(
    atom: Atom,
    tracks: dict[str, Track],
    scale: ScaleModel,
    frame: int,
    fps: float,
    context: dict[str, Any] | None = None,
) -> PredFrame:
    """Evaluates `dwell(a, for_s=0.5, max_speed_cm_s=1.0)` on a single frame.

    Components:
    - dwell.speed (cm/s): stillness margin m_speed = max_speed_cm_s - v_A
    - dwell.duration (s): duration margin m_dur = tau_still - for_s
    """
    args = atom.args
    if len(args) < 1:
        raise ValueError(f"dwell predicate requires at least 1 argument (obj_a), got: {args}")

    obj_a = args[0]
    for_s = get_param_value(atom.params, "for_s", 0.5)
    max_speed_cm_s = get_param_value(atom.params, "max_speed_cm_s", 1.0)

    coords_curr = get_object_coords(obj_a, tracks, scale, frame, context)
    if coords_curr is None:
        return create_not_visible_frame(atom, frame, obj_a)

    xa_t, da_t, ha_t, sa_t = coords_curr
    dt = 1.0 / max(fps, 1.0)

    # 1. Instantaneous speed at current frame
    if frame > 0:
        coords_prev = get_object_coords(obj_a, tracks, scale, frame - 1, context)
        if coords_prev is not None:
            xa_p, da_p, ha_p, _ = coords_prev
            dist = euclidean_3d(xa_t, da_t, ha_t, xa_p, da_p, ha_p)
            v_a = dist / dt
        else:
            v_a = 0.0
    else:
        v_a = 0.0

    m_speed = max_speed_cm_s - v_a
    sigma_v = math.sqrt(2.0) * sa_t / dt
    c_speed = Component(
        name="dwell.speed",
        value=v_a,
        threshold=max_speed_cm_s,
        margin=m_speed,
        sigma=sigma_v,
        unit="cm/s",
        tri=Tri.T if m_speed > 0 else Tri.F,
    )

    # 2. Run length of stillness ending at frame
    # Scan backward until speed exceeds max_speed_cm_s or frame 0
    still_frames = 1 if v_a <= max_speed_cm_s else 0
    if still_frames > 0:
        prev_f = frame - 1
        curr_coords = coords_curr
        while prev_f >= 0:
            p_coords = get_object_coords(obj_a, tracks, scale, prev_f, context)
            if p_coords is None:
                break
            d = euclidean_3d(
                curr_coords[0],
                curr_coords[1],
                curr_coords[2],
                p_coords[0],
                p_coords[1],
                p_coords[2],
            )
            v_step = d / dt
            if v_step <= max_speed_cm_s:
                still_frames += 1
                curr_coords = p_coords
                prev_f -= 1
            else:
                break

    tau_still = still_frames * dt
    m_dur = tau_still - for_s
    sigma_t = dt

    c_dur = Component(
        name="dwell.duration",
        value=tau_still,
        threshold=for_s,
        margin=m_dur,
        sigma=sigma_t,
        unit="s",
        tri=Tri.T if m_dur >= 0 else Tri.F,
    )

    components = [c_speed, c_dur]
    overall_tri = conjoin_components(components)

    return PredFrame(
        frame=frame,
        atom_key=get_atom_key(atom),
        tri=overall_tri,
        components=components,
        trace_id=make_trace_id("tr_dwell"),
    )
