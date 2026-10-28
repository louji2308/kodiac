"""Unit tests for evaluation Gates G1-G6 and ADR-0010 effector exclusion."""

from __future__ import annotations

import numpy as np

from Kodiac_robotics.contracts.core import (
    Atom,
    Component,
    Expr,
    ObjMask,
    Provenance,
    ReasonCode,
    Step,
    Track,
    Tri,
)
from Kodiac_robotics.segment.rle import mask_to_rle
from Kodiac_robotics.uncertainty.gates import apply_gates


def _make_mask_with_area(
    obj: str, frame: int, area: int, total_h=100, total_w=100, score=0.95
) -> ObjMask:
    canvas = np.zeros((total_h, total_w), dtype=np.uint8)
    # Fill a square with area pixels
    side = int(np.sqrt(area))
    canvas[:side, :side] = 1
    return ObjMask(
        obj=obj,
        frame=frame,
        score=score,
        bbox_xyxy=(0.0, 0.0, float(side), float(side)),
        rle=mask_to_rle(canvas),
        area_px=int(np.sum(canvas)),
        rle_size=(total_h, total_w),
    )


class DummyScale:
    tier = "A"


def test_gate_g1_not_visible():
    """Gate G1 triggers NOT_VISIBLE when track score < 0.5."""
    m0 = _make_mask_with_area("target", 0, 1000)
    m1 = _make_mask_with_area("target", 1, 1000, score=0.3)  # Degenerate score
    track = Track(
        obj="target", frames={0: m0, 1: m1}, backend="fixture", direction="forward", trace_id="t1"
    )

    comp = Component(
        name="on.target.surface",
        value=1.0,
        threshold=2.0,
        margin=1.0,
        sigma=0.2,
        unit="cm",
        tri=Tri.T,
    )

    gated, reasons = apply_gates([comp], {"target": track}, DummyScale(), frame=1)
    assert ReasonCode.NOT_VISIBLE in reasons
    assert gated[0].tri == Tri.U
    assert gated[0].reason == ReasonCode.NOT_VISIBLE


def test_gate_g2_standard_occlusion():
    """Gate G2 triggers OCCLUDED when object occlusion exceeds 40%."""
    # Base area at frame 0 = 1000 px. Frame 1 area = 400 px (60% occluded > 40%)
    m0 = _make_mask_with_area("block", 0, 1000)
    m1 = _make_mask_with_area("block", 1, 400)
    track = Track(
        obj="block", frames={0: m0, 1: m1}, backend="fixture", direction="forward", trace_id="t1"
    )

    comp = Component(
        name="on.block.table",
        value=1.0,
        threshold=2.0,
        margin=1.0,
        sigma=0.2,
        unit="cm",
        tri=Tri.T,
    )

    gated, reasons = apply_gates([comp], {"block": track}, DummyScale(), frame=1)
    assert ReasonCode.OCCLUDED in reasons
    assert gated[0].tri == Tri.U
    assert gated[0].reason == ReasonCode.OCCLUDED


def test_gate_g2_effector_exclusion_with_observability_floor():
    """ADR-0010: Target in active moves_with retains >=20% visible area -> NOT occluded."""
    m0_tgt = _make_mask_with_area("cubeA", 0, 1000)
    m1_tgt = _make_mask_with_area("cubeA", 1, 500)  # 50% occluded by gripper, but 50% >= 20% floor

    tr_tgt = Track(
        obj="cubeA",
        frames={0: m0_tgt, 1: m1_tgt},
        backend="fixture",
        direction="forward",
        trace_id="t1",
    )

    active_step = Step(
        index=0,
        name="grasp_cubeA",
        expr=Expr(
            op="atom",
            atom=Atom(kind="pred", name="moves_with", args=["gripper", "cubeA"]),
        ),
        provenance=Provenance(source="compiler-default"),
    )

    comp = Component(
        name="moves_with.gripper.cubeA",
        value=0.5,
        threshold=1.5,
        margin=1.0,
        sigma=0.2,
        unit="cm",
        tri=Tri.T,
    )

    gated, reasons = apply_gates(
        [comp], {"cubeA": tr_tgt}, DummyScale(), frame=1, active_step=active_step
    )
    # Effector exclusion applies! Gate G2 does NOT trigger
    assert ReasonCode.OCCLUDED not in reasons
    assert gated[0].tri == Tri.T


def test_gate_g2_effector_exclusion_drops_below_observability_floor():
    """ADR-0010: Target in active moves_with drops <20% visible area -> MUST fire OCCLUDED."""
    m0_tgt = _make_mask_with_area("cubeA", 0, 1000)
    m1_tgt = _make_mask_with_area("cubeA", 1, 100)  # 10% visible < 20% floor!

    tr_tgt = Track(
        obj="cubeA",
        frames={0: m0_tgt, 1: m1_tgt},
        backend="fixture",
        direction="forward",
        trace_id="t1",
    )

    active_step = Step(
        index=0,
        name="grasp_cubeA",
        expr=Expr(
            op="atom",
            atom=Atom(kind="pred", name="moves_with", args=["gripper", "cubeA"]),
        ),
        provenance=Provenance(source="compiler-default"),
    )

    comp = Component(
        name="moves_with.gripper.cubeA",
        value=0.5,
        threshold=1.5,
        margin=1.0,
        sigma=0.2,
        unit="cm",
        tri=Tri.T,
    )

    gated, reasons = apply_gates(
        [comp], {"cubeA": tr_tgt}, DummyScale(), frame=1, active_step=active_step
    )
    # 20% floor violated -> MUST fire Gate G2 OCCLUDED
    assert ReasonCode.OCCLUDED in reasons
    assert gated[0].tri == Tri.U
    assert gated[0].reason == ReasonCode.OCCLUDED


def test_gate_g2_non_target_not_exempt():
    """ADR-0010: Secondary non-target objects occluded > 40% are NOT exempt and MUST trigger OCCLUDED."""
    m0_ped = _make_mask_with_area("pedestal", 0, 1000)
    m1_ped = _make_mask_with_area("pedestal", 1, 400)  # 60% occluded

    tr_ped = Track(
        obj="pedestal",
        frames={0: m0_ped, 1: m1_ped},
        backend="fixture",
        direction="forward",
        trace_id="t1",
    )

    # Active step is grasping cubeA, NOT pedestal
    active_step = Step(
        index=0,
        name="grasp_cubeA",
        expr=Expr(
            op="atom",
            atom=Atom(kind="pred", name="moves_with", args=["gripper", "cubeA"]),
        ),
        provenance=Provenance(source="compiler-default"),
    )

    comp = Component(
        name="near.cubeA.pedestal",
        value=1.0,
        threshold=2.0,
        margin=1.0,
        sigma=0.2,
        unit="cm",
        tri=Tri.T,
    )

    gated, reasons = apply_gates(
        [comp], {"pedestal": tr_ped}, DummyScale(), frame=1, active_step=active_step
    )
    assert ReasonCode.OCCLUDED in reasons
    assert gated[0].tri == Tri.U


def test_gate_g3_below_noise_floor_unit_matched():
    """Gate G3 evaluates unit-matched noise floor |m| < sigma."""
    comp_cm = Component(
        name="on.align_xy",
        value=1.1,
        threshold=1.0,
        margin=0.1,  # |margin| = 0.1 < sigma = 0.35
        sigma=0.35,
        unit="cm",
        tri=Tri.T,
    )
    gated, reasons = apply_gates([comp_cm], {}, DummyScale(), frame=0)
    assert ReasonCode.BELOW_NOISE_FLOOR in reasons
    assert gated[0].tri == Tri.U
    assert gated[0].reason == ReasonCode.BELOW_NOISE_FLOOR


def test_gate_g4_view_blocked():
    """Gate G4 triggers VIEW_BLOCKED on dark or uniform frames."""
    dark_frame = np.zeros((480, 640), dtype=np.uint8)  # Complete blackout
    comp = Component(
        name="on.cube.table",
        value=1.0,
        threshold=2.0,
        margin=1.0,
        sigma=0.2,
        unit="cm",
        tri=Tri.T,
    )
    gated, reasons = apply_gates([comp], {}, DummyScale(), frame=0, raw_frame=dark_frame)
    assert ReasonCode.VIEW_BLOCKED in reasons
    assert gated[0].tri == Tri.U


def test_gate_g6_depth_ambiguous_on_tier_c():
    """Gate G6 triggers DEPTH_AMBIGUOUS when scale is Tier C on depth-critical components."""
    tier_c_scale = DummyScale()
    tier_c_scale.tier = "C"

    comp_depth = Component(
        name="on.gap",  # Depth-critical component
        value=0.2,
        threshold=0.5,
        margin=0.3,
        sigma=0.1,
        unit="cm",
        tri=Tri.T,
    )
    gated, reasons = apply_gates([comp_depth], {}, tier_c_scale, frame=0)
    assert ReasonCode.DEPTH_AMBIGUOUS in reasons
    assert gated[0].tri == Tri.U
    assert gated[0].reason == ReasonCode.DEPTH_AMBIGUOUS
