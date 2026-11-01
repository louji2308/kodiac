"""Two-Pass Slack Engine and Kinematic Calibration for Kodiac.

Implements empirical metric extraction and certified tolerance derivation
per ARCHITECTURE.md §6.1, §6.3, ADR-0011, and ADR-0013.

SDM MANDATORY DIRECTIVE:
Uses Kinematic Phase Segmentation (apex detection for lifted.min_cm,
settled terminal window for placement/dwell) rather than speech timestamps.
Enforces hard Physical Sanity Caps (align_xy <= 4.0cm, gap <= 2.0cm, min_cm <= 8.0cm, max_speed <= 2.5cm/s)
to prevent sloppy demonstrations from poisoning downstream policies (E005).
"""

from __future__ import annotations

import logging
import math
from typing import Any, Literal

import numpy as np

from Kodiac_robotics.contracts.core import (
    Atom,
    Clip,
    Expr,
    GreenTest,
    Param,
    Track,
)
from Kodiac_robotics.geometry.scale import fit_scale_model
from Kodiac_robotics.pipeline.run import _harmonize_track_keys
from Kodiac_robotics.segment.fixture import FixtureBackend

logger = logging.getLogger(__name__)

# Normative Physical Sanity Caps per ADR-0013
SANITY_CAPS: dict[str, float] = {
    "align_xy_cm": 4.0,
    "gap_cm": 2.0,
    "min_cm": 8.0,
    "max_speed_cm_s": 2.5,
}

PROFILE_SIGMA_FACTORS: dict[str, float] = {
    "strict": 2.0,
    "nominal": 2.5,
    "loose": 3.0,
}


def _extract_all_atoms(expr: Expr) -> list[Atom]:
    """Recursively collect all atoms from an expression."""
    atoms: list[Atom] = []
    if expr.op == "atom" and expr.atom is not None:
        atoms.append(expr.atom)
    for child in expr.children:
        atoms.extend(_extract_all_atoms(child))
    return atoms


def _identify_target_objects(test: GreenTest) -> tuple[str, str | None]:
    """Identify the manipulated primary object and destination target object."""
    obj_a: str | None = None
    obj_b: str | None = None

    for step in test.steps:
        for atom in _extract_all_atoms(step.expr):
            if atom.name == "lifted" and len(atom.args) >= 1:
                obj_a = atom.args[0]
            elif atom.name in ("on", "inside", "dwell") and len(atom.args) >= 1:
                if obj_a is None:
                    obj_a = atom.args[0]
                if len(atom.args) >= 2 and atom.args[1] not in ("surface", "table"):
                    obj_b = atom.args[1]
            elif atom.name == "moves_with" and len(atom.args) >= 2:
                if atom.args[0].lower() == "gripper":
                    obj_a = atom.args[1]

    # Fallback to declared objects if not deduced from AST
    if obj_a is None:
        non_effectors = [o.name for o in test.objects if o.role != "effector"]
        obj_a = non_effectors[0] if non_effectors else "cubeA"
        if len(non_effectors) > 1 and obj_b is None:
            obj_b = non_effectors[1]

    return obj_a, obj_b


def measure_demo_metrics(
    clip: Clip,
    test: GreenTest,
    backend: Any = None,
) -> dict[str, float]:
    """Runs Pass 1 unconstrained metric logging over demo clip.

    MANDATORY DIRECTIVE: Uses kinematic phase segmentation:
    - Apex Detection: Detect trajectory inflection frame t_apex where elevation h(t)
      reaches its maximum -> extract h_max for lifted.min_cm.
    - Settled Terminal Window: Scan backward from clip end for stable kinematic plateau
      where lateral distance ||Delta XY(t)|| stabilizes and velocity <= 2.5 cm/s
      for >= 0.5 s -> extract settled Delta_xy, z_gap, and v_settle.

    Returns physical extrema: h_max, delta_xy, z_gap, v_settle, sigma.
    """
    # 1. Load Tracks
    resolved_tracks: dict[str, Track] = {}
    if backend is not None:
        try:
            prompt_map = {obj.name: [obj.name] for obj in test.objects}
            resolved_tracks = backend.segment_frames(clip, list(range(clip.n_frames)), prompt_map)
        except Exception:
            resolved_tracks = {}

    if not resolved_tracks:
        fb = FixtureBackend()
        resolved_tracks = fb._load_tracks(clip)

    harmonized_tracks = _harmonize_track_keys(resolved_tracks, test)

    # 2. Fit Scale Model
    scale = fit_scale_model(
        clip=clip,
        tracks=harmonized_tracks,
        objects=test.objects,
    )

    # 3. Identify Target Objects
    obj_a, obj_b = _identify_target_objects(test)

    # Resolve target object B nominal height
    b_height = 4.0
    if obj_b:
        for decl in test.objects:
            if decl.name == obj_b:
                if decl.height_cm is not None:
                    b_height = float(decl.height_cm)
                elif decl.size_cm is not None:
                    b_height = float(decl.size_cm)
                break

    n_frames = clip.n_frames
    fps = max(1.0, clip.fps)
    dt = 1.0 / fps

    elevations = np.zeros(n_frames, dtype=np.float64)
    d_xys = np.zeros(n_frames, dtype=np.float64)
    z_gaps = np.zeros(n_frames, dtype=np.float64)
    sigmas = np.zeros(n_frames, dtype=np.float64)
    speeds = np.zeros(n_frames, dtype=np.float64)

    # Base rest height h_A,0
    xa_0, da_0, ha_0, sa_0 = scale.to_table_frame(obj_a, 0)
    prev_coords = (xa_0, da_0, ha_0)

    for f in range(n_frames):
        xa, da, ha, sa = scale.to_table_frame(obj_a, f)
        elevations[f] = ha - ha_0
        sigmas[f] = sa

        # Instantaneous 3D velocity
        dist = math.sqrt((xa - prev_coords[0]) ** 2 + (da - prev_coords[1]) ** 2 + (ha - prev_coords[2]) ** 2)
        speeds[f] = dist / dt if f > 0 else 0.0
        prev_coords = (xa, da, ha)

        if obj_b and obj_b in harmonized_tracks:
            xb, db, hb, sb = scale.to_table_frame(obj_b, f)
            d_xys[f] = math.hypot(xa - xb, da - db)
            if (
                getattr(scale, "tier", None) == "C"
                and f in harmonized_tracks[obj_b].frames
                and f in harmonized_tracks[obj_a].frames
            ):
                ma = harmonized_tracks[obj_a].frames[f]
                mb = harmonized_tracks[obj_b].frames[f]
                v_bottom_a = ma.bbox_xyxy[3]
                v_top_b = mb.bbox_xyxy[1]
                k_b = getattr(scale, "k0", {}).get(obj_b, getattr(scale, "k_ref", 15.0))
                z_gaps[f] = abs(v_bottom_a - v_top_b) / max(0.1, k_b)
            else:
                h_top_b = hb + b_height
                z_gaps[f] = abs(ha - h_top_b)
            sigmas[f] = math.hypot(sa, sb)
        else:
            d_xys[f] = 0.0
            z_gaps[f] = abs(ha)

    # Smooth speeds with 3-frame rolling window to prevent discrete coordinate discretization spikes
    kernel = np.ones(3) / 3.0
    smoothed_speeds = np.convolve(speeds, kernel, mode="same")
    smoothed_speeds[0] = 0.0

    # --------------------------------------------------------------------------
    # Apex Detection: Global maximum of elevation h(t) relative to rest
    # --------------------------------------------------------------------------
    h_max = float(np.max(elevations))

    # --------------------------------------------------------------------------
    # Settled Terminal Window: Stable kinematic plateau (v <= 2.5 cm/s)
    # --------------------------------------------------------------------------
    # Scan backward from clip end while velocity <= 2.5 cm/s
    settle_start_idx = n_frames - 1
    while settle_start_idx > 0 and smoothed_speeds[settle_start_idx] <= 2.5:
        settle_start_idx -= 1
    if smoothed_speeds[settle_start_idx] > 2.5:
        settle_start_idx += 1

    settle_frames = n_frames - settle_start_idx
    min_settle_frames = max(3, int(round(0.25 * fps)))
    settle_s = float(settle_frames / fps)

    # If the demonstrator settled for at least min_settle_frames:
    if settle_frames >= min_settle_frames:
        terminal_window = slice(settle_start_idx, n_frames)
    else:
        # No plateau of stillness found at clip end: demonstrator kept moving
        terminal_window = slice(max(0, n_frames - max(3, int(round(0.5 * fps)))), n_frames)

    delta_xy = float(np.median(d_xys[terminal_window]))
    z_gap = float(np.median(z_gaps[terminal_window]))
    v_settle = float(np.mean(smoothed_speeds[terminal_window]))
    sigma = float(np.mean(sigmas[terminal_window]))

    return {
        "h_max": round(h_max, 2),
        "delta_xy": round(delta_xy, 2),
        "z_gap": round(z_gap, 2),
        "v_settle": round(v_settle, 2),
        "sigma": round(sigma, 2),
        "settle_s": round(settle_s, 2),
    }


def derive_thresholds(
    skeleton: GreenTest,
    demo_metrics: dict[str, float],
    profile: Literal["strict", "nominal", "loose"] = "nominal",
) -> tuple[GreenTest, dict[str, Any]]:
    """Derives physical parameter values with safety margins (margin >= 2σ):
      align_xy_cm = max(1.5, round(delta_xy + 2.5*sigma, 1))
      gap_cm = max(0.5, round(z_gap + 2.5*sigma, 1))
      min_cm = max(1.0, floor(0.6 * h_max))
    Enforces Physical Sanity Caps:
      align_xy_cm <= 4.0 cm, gap_cm <= 2.0 cm, min_cm <= 8.0 cm, max_speed <= 2.5 cm/s.
    Exceeding any sanity cap raises E005. Returns (calibrated_test, slack_summary).
    """
    alpha = PROFILE_SIGMA_FACTORS.get(profile, 2.5)

    delta_xy = demo_metrics["delta_xy"]
    z_gap = demo_metrics["z_gap"]
    h_max = demo_metrics["h_max"]
    v_settle = demo_metrics["v_settle"]
    sigma = demo_metrics.get("sigma", 0.3)
    settle_s = demo_metrics.get("settle_s", 0.5)

    # Check whether gap_cm is declared in the skeleton AST
    all_atoms = []
    for step in skeleton.steps:
        all_atoms.extend(_extract_all_atoms(step.expr))
    has_gap_in_ast = any(
        atom.name == "on" and any(p.name == "gap_cm" for p in atom.params)
        for atom in all_atoms
    )

    # 1. Statistical Tolerance Fitting with Certified Slack
    align_xy_cm = max(1.5, round(delta_xy + alpha * sigma, 1))
    gap_cm = max(0.5, round(z_gap + alpha * sigma, 1))
    min_cm = max(1.0, float(math.floor(0.6 * h_max)))
    max_speed_cm_s = min(SANITY_CAPS["max_speed_cm_s"], max(2.0, round(v_settle + 1.5, 1)))

    # 2. Hard Physical Sanity Cap Enforcement (ADR-0013)
    violations: list[str] = []
    if align_xy_cm > SANITY_CAPS["align_xy_cm"]:
        violations.append(
            f"align_xy_cm={align_xy_cm} exceeds cap {SANITY_CAPS['align_xy_cm']}cm (measured delta_xy={delta_xy}cm)"
        )
    if has_gap_in_ast and gap_cm > SANITY_CAPS["gap_cm"]:
        violations.append(
            f"gap_cm={gap_cm} exceeds cap {SANITY_CAPS['gap_cm']}cm (measured z_gap={z_gap}cm)"
        )
    elif z_gap > SANITY_CAPS["gap_cm"]:
        violations.append(
            f"measured z_gap={z_gap}cm exceeds physical sanity cap {SANITY_CAPS['gap_cm']}cm"
        )
    if min_cm > SANITY_CAPS["min_cm"]:
        violations.append(
            f"min_cm={min_cm} exceeds cap {SANITY_CAPS['min_cm']}cm (measured h_max={h_max}cm)"
        )
    if v_settle > SANITY_CAPS["max_speed_cm_s"]:
        violations.append(
            f"demonstrator settling velocity v_settle={v_settle}cm/s exceeds cap {SANITY_CAPS['max_speed_cm_s']}cm/s"
        )

    if violations:
        violation_str = "; ".join(violations)
        raise ValueError(
            f"E005: demonstration exceeds physical sanity cap; re-record a valid demonstration. ({violation_str})"
        )

    # 3. Populate AST with Calibrated Thresholds
    calibrated_test = skeleton.model_copy(deep=True)

    def _update_atom_params(atom: Atom, is_negated: bool = False) -> None:
        if atom.name == "lifted":
            # Update or insert min_cm
            updated = False
            for p in atom.params:
                if p.name == "min_cm":
                    p.value = min_cm
                    p.op = "="
                    updated = True
                    break
            if not updated:
                atom.params.append(Param(name="min_cm", op="=", value=min_cm))

        elif atom.name == "on":
            # Update align_xy_cm and optionally gap_cm
            has_align = False
            for p in atom.params:
                if p.name == "align_xy_cm":
                    p.value = align_xy_cm
                    p.op = "<="
                    has_align = True
                elif p.name == "gap_cm":
                    p.value = gap_cm
                    p.op = "<="
            if not has_align:
                atom.params.append(Param(name="align_xy_cm", op="<=", value=align_xy_cm))

        elif atom.name == "moves_with":
            if not is_negated:
                slip_cm = max(2.5, round(demo_metrics.get("slip_cm", 0.8) + alpha * sigma, 1))
                has_slip = False
                for p in atom.params:
                    if p.name == "slip_cm":
                        p.value = slip_cm
                        p.op = "<="
                        has_slip = True
                if not has_slip:
                    atom.params.append(Param(name="slip_cm", op="<=", value=slip_cm))

        elif atom.name == "dwell":
            # Update max_speed_cm_s and calibrate for_s if symbolic or exceeding dwell plateau
            has_speed = False
            for p in atom.params:
                if p.name == "max_speed_cm_s":
                    p.value = max_speed_cm_s
                    p.op = "<="
                    has_speed = True
                elif p.name == "for_s":
                    if p.value <= 0 or p.value > max(0.1, settle_s):
                        p.value = max(0.1, round(0.7 * settle_s, 2))
                        p.op = ">="
            if not has_speed:
                atom.params.append(Param(name="max_speed_cm_s", op="<=", value=max_speed_cm_s))

    def _traverse_expr(expr: Expr, is_negated: bool = False) -> None:
        next_negated = is_negated or (expr.op == "not")
        if expr.op == "atom" and expr.atom is not None:
            _update_atom_params(expr.atom, is_negated=is_negated)
        for child in expr.children:
            _traverse_expr(child, is_negated=next_negated)

    for step in calibrated_test.steps:
        _traverse_expr(step.expr, is_negated=False)

    # 4. Construct Slack Summary
    slack_summary: dict[str, Any] = {
        "profile": profile,
        "metrics": demo_metrics,
        "thresholds": {
            "align_xy_cm": align_xy_cm,
            "gap_cm": gap_cm,
            "min_cm": min_cm,
            "max_speed_cm_s": max_speed_cm_s,
        },
        "caps": SANITY_CAPS,
        "margin_sigma": round(alpha * sigma, 2),
    }

    return calibrated_test, slack_summary
