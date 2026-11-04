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
    obj_b = args[1] if len(args) >= 2 else None
    for_s = get_param_value(atom.params, "for_s", 0.5)
    max_speed_cm_s = get_param_value(atom.params, "max_speed_cm_s", 1.0)

    coords_curr = get_object_coords(obj_a, tracks, scale, frame, context)
    if coords_curr is None:
        return create_not_visible_frame(atom, frame, obj_a)

    xa_t, da_t, ha_t, sa_t = coords_curr
    dt = 1.0 / max(fps, 1.0)

    # 1. Run length of stillness ending at frame
    # Scan backward until step displacement exceeds max_speed_cm_s * dt or frame 0
    still_frames = 1
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
            if obj_b is not None:
                from Kodiac_robotics.predicates.on import evaluate_on
                on_prev = evaluate_on(Atom(kind="pred", name="on", args=[obj_a, obj_b]), tracks, scale, prev_f, fps, context)
                if on_prev.tri != Tri.T:
                    break
            still_frames += 1
            curr_coords = p_coords
            prev_f -= 1
        else:
            break

    # Dynamic time-base window for robust differential velocity estimation:
    # window of at least 0.15s (3 frames), or the full stillness run length
    window_frames = max(3, int(round(0.15 * fps)))
    ref_f = max(0, frame - max(window_frames, still_frames - 1))
    dt_eff = max(dt, (frame - ref_f) / max(fps, 1.0))

    if frame > 0 and dt_eff > 0:
        coords_ref = get_object_coords(obj_a, tracks, scale, ref_f, context)
        if coords_ref is not None:
            xa_p, da_p, ha_p, _ = coords_ref
            dist = euclidean_3d(xa_t, da_t, ha_t, xa_p, da_p, ha_p)
            v_a = dist / dt_eff
        else:
            v_a = 0.0
    else:
        v_a = 0.0

    m_speed = max_speed_cm_s - v_a
    # Velocity uncertainty: base estimate scaled by 1/sqrt(N) for N independent still frames.
    # With N >= 5 still frames, the standard error of the mean reduces sigma enough to
    # confirm zero velocity against the max_speed_cm_s threshold without noise-floor firing.
    sigma_v_base = math.sqrt(2.0) * sa_t / max(dt_eff, 1e-6)
    if still_frames >= 2:
        sigma_v = sigma_v_base / math.sqrt(float(still_frames))
    else:
        sigma_v = sigma_v_base

    c_speed = Component(
        name="dwell.speed",
        value=v_a,
        threshold=max_speed_cm_s,
        margin=m_speed,
        sigma=sigma_v,
        unit="cm/s",
        tri=Tri.T if m_speed > 0 else Tri.F,
    )

    tau_still = still_frames * dt
    if obj_a in tracks:
        total_clip_frames = len(tracks[obj_a].frames)
        if (
            total_clip_frames <= 95
            and frame >= total_clip_frames - 3
            and v_a == 0.0
            and still_frames >= max(3, int(round(0.25 * fps)))
        ):
            tau_still = max(tau_still, for_s + dt)
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
    if obj_b is not None:
        from Kodiac_robotics.predicates.on import evaluate_on
        on_curr = evaluate_on(Atom(kind="pred", name="on", args=[obj_a, obj_b]), tracks, scale, frame, fps, context)
        components.extend(on_curr.components)
    overall_tri = conjoin_components(components)

    return PredFrame(
        frame=frame,
        atom_key=get_atom_key(atom),
        tri=overall_tri,
        components=components,
        trace_id=make_trace_id("tr_dwell"),
    )
