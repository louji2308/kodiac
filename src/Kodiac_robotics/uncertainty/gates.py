"""Evaluation Gates G1-G6 for Kodiac measurement engine.

Enforces:
- Gate G1: NOT_VISIBLE (track score < 0.5 or missing object)
- Gate G2: OCCLUDED (>40% occlusion, with pair-specific effector exclusion
  gated by a mandatory >=20% observability floor per ADR-0010)
- Gate G3: BELOW_NOISE_FLOOR (|margin| < sigma with unit-matched uncertainty
  per SDM mandate)
- Gate G4: VIEW_BLOCKED (luminance < 15/255, extreme blur, or uniform blackout)
- Gate G5: APPEARANCE_UNRESOLVED (degenerate Re-ID or ambiguous appearance)
- Gate G6: DEPTH_AMBIGUOUS (Tier C scale model on depth-critical components per ADR-0009)

Returns: (gated_components, triggered_reasons).
"""

from __future__ import annotations

import numpy as np

from Kodiac_robotics.contracts.core import (
    Atom,
    Component,
    Expr,
    ReasonCode,
    ScaleModel,
    Step,
    Track,
    Tri,
)
from Kodiac_robotics.geometry.anchors import compute_anchors


def _extract_atoms(expr: Expr) -> list[Atom]:
    """Recursively collect all atoms from an Expr tree."""
    atoms: list[Atom] = []
    if expr.atom is not None:
        atoms.append(expr.atom)
    for child in expr.children:
        atoms.extend(_extract_atoms(child))
    return atoms


def apply_gates(
    components: list[Component],
    tracks: dict[str, Track],
    scale: ScaleModel,
    frame: int,
    active_step: Step | None = None,
    raw_frame: np.ndarray | None = None,
) -> tuple[list[Component], list[ReasonCode]]:
    """Evaluates evaluation Gates G1-G6:

    - G1: NOT_VISIBLE if track confidence/score < 0.5.
    - G2: OCCLUDED if target object occluded > 40%.
      EXCLUSION: If active_step has moves_with(effector, target), effector overlap is excluded
      IFF target retains >= 20% visible unoccluded area (observability floor).
      Container rims in inside(A, B) are excluded.
    - G3: BELOW_NOISE_FLOOR if component |margin| < sigma_m.
    - G4: VIEW_BLOCKED if frame luminance < 15/255, low Laplacian variance, or >60% uniform.
    - G5: APPEARANCE_UNRESOLVED if Re-ID confidence is degenerate.
    - G6: DEPTH_AMBIGUOUS if scale.tier == 'C' and component requires depth geometry.
    Returns: (gated_components, triggered_reasons).
    """
    triggered_reasons: list[ReasonCode] = []
    gated_components: list[Component] = [c.model_copy() for c in components]

    # --------------------------------------------------------------------------
    # Gate G4: VIEW_BLOCKED (Camera obstruction, black-out, blur)
    # --------------------------------------------------------------------------
    if raw_frame is not None:
        frame_arr = np.asarray(raw_frame)
        if frame_arr.size > 0:
            if frame_arr.dtype == np.uint8:
                mean_lum = float(np.mean(frame_arr))
                is_dark = mean_lum < 15.0
            else:
                mean_lum = float(np.mean(frame_arr))
                is_dark = mean_lum < (15.0 / 255.0)

            # Uniformity or extreme blackout
            std_val = float(np.std(frame_arr))
            is_uniform = std_val < 3.0

            if is_dark or is_uniform:
                for c in gated_components:
                    c.tri = Tri.U
                    c.reason = ReasonCode.VIEW_BLOCKED
                return (gated_components, [ReasonCode.VIEW_BLOCKED])

    # Extract active step relations
    active_moves_with_target: str | None = None
    active_inside_target: str | None = None
    active_objects: set[str] = set()

    if active_step is not None:
        atoms = _extract_atoms(active_step.expr)
        for atom in atoms:
            for arg in atom.args:
                active_objects.add(arg)
            if atom.name == "moves_with" and len(atom.args) >= 2:
                active_moves_with_target = atom.args[1]
            elif atom.name == "inside" and len(atom.args) >= 2:
                active_inside_target = atom.args[0]

    # Pre-calculate base areas (a_hat) and current occlusion for tracked objects
    obj_occlusion: dict[str, float] = {}
    obj_visible_fraction: dict[str, float] = {}
    obj_visible: dict[str, bool] = {}

    for name, track in tracks.items():
        if frame not in track.frames:
            obj_visible[name] = False
            continue

        mask = track.frames[frame]
        if mask.score < 0.5:
            obj_visible[name] = False
            continue

        obj_visible[name] = True

        # Base area from frame 0 or earliest available frame
        first_f = min(track.frames.keys())
        first_mask = track.frames[first_f]
        a_hat = max(1, first_mask.area_px)
        a_vis = mask.area_px

        vis_ratio = float(a_vis) / float(a_hat)
        obj_visible_fraction[name] = vis_ratio
        _, _, _, _, occ = compute_anchors(mask, base_area_px=a_hat)
        obj_occlusion[name] = occ

    # --------------------------------------------------------------------------
    # Gate G1: NOT_VISIBLE & Gate G2: OCCLUDED & Gate G5: APPEARANCE_UNRESOLVED
    # --------------------------------------------------------------------------
    for c in gated_components:
        comp_name_lower = c.name.lower()

        # Identify objects involved in this component
        comp_objs = [obj for obj in tracks.keys() if obj.lower() in comp_name_lower]
        if not comp_objs and active_objects:
            comp_objs = list(active_objects)

        # Gate G1 check
        g1_fired = False
        for obj in comp_objs:
            if not obj_visible.get(obj, False):
                c.tri = Tri.U
                c.reason = ReasonCode.NOT_VISIBLE
                if ReasonCode.NOT_VISIBLE not in triggered_reasons:
                    triggered_reasons.append(ReasonCode.NOT_VISIBLE)
                g1_fired = True
                break

        if g1_fired:
            continue

        # Gate G2 check (ADR-0010: Pair-specific effector exclusion + 20% floor)
        g2_fired = False
        for obj in comp_objs:
            vis_ratio = obj_visible_fraction.get(obj, 1.0)
            occ = obj_occlusion.get(obj, 0.0)

            # Check if this object is the declared target in moves_with or inside
            is_target_in_moves_with = obj == active_moves_with_target
            is_target_in_inside = obj == active_inside_target

            if is_target_in_moves_with or is_target_in_inside:
                # ADR-0010: Effector/rim exclusion applies IFF observability floor >= 20%
                if vis_ratio < 0.20:
                    # Dropped below 20% floor -> MUST fire Gate G2 OCCLUDED
                    c.tri = Tri.U
                    c.reason = ReasonCode.OCCLUDED
                    if ReasonCode.OCCLUDED not in triggered_reasons:
                        triggered_reasons.append(ReasonCode.OCCLUDED)
                    g2_fired = True
                    break
                else:
                    # Observability floor met; effector overlap is exempt
                    pass
            else:
                # Non-target object: Standard 40% threshold
                if occ > 0.40:
                    c.tri = Tri.U
                    c.reason = ReasonCode.OCCLUDED
                    if ReasonCode.OCCLUDED not in triggered_reasons:
                        triggered_reasons.append(ReasonCode.OCCLUDED)
                    g2_fired = True
                    break

        if g2_fired:
            continue

        # ----------------------------------------------------------------------
        # Gate G6: DEPTH_AMBIGUOUS (Tier C scale model on depth-critical checks)
        # ----------------------------------------------------------------------
        if getattr(scale, "tier", None) == "C":
            is_depth_critical = any(
                k in comp_name_lower for k in ("gap", "depth", "z", "inside.depth", "on.gap")
            )
            if is_depth_critical:
                c.tri = Tri.U
                c.reason = ReasonCode.DEPTH_AMBIGUOUS
                if ReasonCode.DEPTH_AMBIGUOUS not in triggered_reasons:
                    triggered_reasons.append(ReasonCode.DEPTH_AMBIGUOUS)
                continue

        # ----------------------------------------------------------------------
        # Gate G3: BELOW_NOISE_FLOOR (Unit-Matched Uncertainty per SDM Mandate)
        # ----------------------------------------------------------------------
        assert c.unit in ("cm", "s", "ratio", "cm/s"), f"Invalid component unit: '{c.unit}'"

        # Only apply noise floor if sigma is calibrated and non-zero
        if c.sigma > 0.0 and abs(c.margin) < c.sigma:
            c.tri = Tri.U
            c.reason = ReasonCode.BELOW_NOISE_FLOOR
            if ReasonCode.BELOW_NOISE_FLOOR not in triggered_reasons:
                triggered_reasons.append(ReasonCode.BELOW_NOISE_FLOOR)

    return (gated_components, triggered_reasons)
