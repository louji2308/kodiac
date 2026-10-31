"""Tests for CANT_TELL reason codes, synthetic frame decorators, and Gates G1-G6."""

from __future__ import annotations

import cv2
import numpy as np

from Kodiac_robotics.contracts.core import (
    Component,
    ObjMask,
    ReasonCode,
    Track,
    Tri,
    Verdict,
)
from Kodiac_robotics.pipeline.run import run
from Kodiac_robotics.segment.rle import mask_to_rle
from Kodiac_robotics.uncertainty.gates import apply_gates

# ==============================================================================
# In-Memory Synthetic Frame Decorators (S13)
# ==============================================================================


def apply_synthetic_box(
    frame: np.ndarray,
    x: int,
    y: int,
    w: int,
    h: int,
    color: tuple[int, int, int] | tuple[int, ...] = (0, 0, 0),
) -> np.ndarray:
    """Draws a solid synthetic occlusion box on the frame."""
    out = frame.copy()
    out[y : y + h, x : x + w] = color
    return out


def apply_black_out(
    frame: np.ndarray,
    color: tuple[int, int, int] | tuple[int, ...] = (0, 0, 0),
) -> np.ndarray:
    """Simulates complete camera obstruction or blackout (Gate G4)."""
    out = np.zeros_like(frame)
    if any(color):
        out[:] = color
    return out


def apply_gaussian_blur(
    frame: np.ndarray,
    ksize: int = 51,
    sigma: float = 20.0,
) -> np.ndarray:
    """Simulates extreme defocus or lens frosting (Gate G4)."""
    if ksize % 2 == 0:
        ksize += 1
    return cv2.GaussianBlur(frame, (ksize, ksize), sigmaX=sigma, sigmaY=sigma)


# Helper scale model
class _DummyScale:
    def __init__(self, tier: str = "A") -> None:
        self.tier = tier


def _make_test_mask(
    obj: str, frame: int, h: int = 100, w: int = 100, area: int = 1000, score: float = 0.95
) -> ObjMask:
    canvas = np.zeros((h, w), dtype=np.uint8)
    side = int(np.sqrt(area))
    canvas[:side, :side] = 1
    return ObjMask(
        obj=obj,
        frame=frame,
        score=score,
        bbox_xyxy=(0.0, 0.0, float(side), float(side)),
        rle=mask_to_rle(canvas),
        area_px=int(np.sum(canvas)),
        rle_size=(h, w),
    )


# ==============================================================================
# Gate G1-G6 Unit Tests with Decorators
# ==============================================================================


def test_apply_black_out_gate_g4_view_blocked() -> None:
    """apply_black_out sets luminance < 15 and triggers Gate G4 VIEW_BLOCKED."""
    clean_frame = np.full((120, 160, 3), 180, dtype=np.uint8)
    blacked = apply_black_out(clean_frame)

    assert float(np.mean(blacked)) < 15.0

    comp = Component(
        name="on.block.surface",
        value=1.0,
        threshold=2.0,
        margin=1.0,
        sigma=0.2,
        unit="cm",
        tri=Tri.T,
    )
    gated, reasons = apply_gates(
        components=[comp],
        tracks={},
        scale=_DummyScale(),  # type: ignore[arg-type]
        frame=0,
        raw_frame=blacked,
    )

    assert ReasonCode.VIEW_BLOCKED in reasons
    assert gated[0].tri == Tri.U
    assert gated[0].reason == ReasonCode.VIEW_BLOCKED


def test_apply_gaussian_blur_uniform_view_blocked() -> None:
    """apply_gaussian_blur on low-contrast frame creates uniform frame triggering VIEW_BLOCKED."""
    low_contrast = np.full((120, 160, 3), 100, dtype=np.uint8)
    low_contrast[50:60, 50:60] = 102
    blurred = apply_gaussian_blur(low_contrast, ksize=51, sigma=30.0)

    assert float(np.std(blurred)) < 3.0

    comp = Component(
        name="on.block.surface",
        value=1.0,
        threshold=2.0,
        margin=1.0,
        sigma=0.2,
        unit="cm",
        tri=Tri.T,
    )
    gated, reasons = apply_gates(
        components=[comp],
        tracks={},
        scale=_DummyScale(),  # type: ignore[arg-type]
        frame=0,
        raw_frame=blurred,
    )

    assert ReasonCode.VIEW_BLOCKED in reasons
    assert gated[0].tri == Tri.U
    assert gated[0].reason == ReasonCode.VIEW_BLOCKED


def test_apply_synthetic_box_gate_g2_occluded() -> None:
    """apply_synthetic_box reducing target area > 40% triggers Gate G2 OCCLUDED."""
    # Frame 0: unoccluded mask (area = 2500 px)
    m0 = _make_test_mask("cube", 0, area=2500)

    # Frame 1: simulate synthetic box cutting 70% of the mask
    canvas = np.zeros((100, 100), dtype=np.uint8)
    canvas[:50, :50] = 1  # 50x50 = 2500
    # Apply synthetic box over top 35 rows (35x50 = 1750 px removed -> leaves 750 px visible)
    occluded_canvas = apply_synthetic_box(canvas, x=0, y=0, w=50, h=35, color=(0,))
    vis_area = int(np.sum(occluded_canvas))

    m1 = ObjMask(
        obj="cube",
        frame=1,
        score=0.95,
        bbox_xyxy=(0.0, 35.0, 50.0, 50.0),
        rle=mask_to_rle(occluded_canvas),
        area_px=vis_area,
        rle_size=(100, 100),
    )

    tr = Track(obj="cube", frames={0: m0, 1: m1}, backend="fixture", direction="forward", trace_id="t1")
    comp = Component(
        name="on.cube.table",
        value=1.0,
        threshold=2.0,
        margin=1.0,
        sigma=0.2,
        unit="cm",
        tri=Tri.T,
    )

    gated, reasons = apply_gates(
        components=[comp],
        tracks={"cube": tr},
        scale=_DummyScale(),  # type: ignore[arg-type]
        frame=1,
    )

    assert ReasonCode.OCCLUDED in reasons
    assert gated[0].tri == Tri.U
    assert gated[0].reason == ReasonCode.OCCLUDED


def test_gate_g1_not_visible() -> None:
    """Gate G1 triggers NOT_VISIBLE when track score < 0.5."""
    m0 = _make_test_mask("target", 0, area=1000)
    m1 = _make_test_mask("target", 1, area=1000, score=0.2)
    tr = Track(obj="target", frames={0: m0, 1: m1}, backend="fixture", direction="forward", trace_id="t1")

    comp = Component(
        name="on.target.surface",
        value=1.0,
        threshold=2.0,
        margin=1.0,
        sigma=0.2,
        unit="cm",
        tri=Tri.T,
    )

    gated, reasons = apply_gates([comp], {"target": tr}, _DummyScale(), frame=1)  # type: ignore[arg-type]
    assert ReasonCode.NOT_VISIBLE in reasons
    assert gated[0].tri == Tri.U
    assert gated[0].reason == ReasonCode.NOT_VISIBLE


def test_gate_g3_below_noise_floor() -> None:
    """Gate G3 triggers BELOW_NOISE_FLOOR when |margin| < sigma."""
    comp = Component(
        name="moves_with.slip",
        value=0.5,
        threshold=1.0,
        margin=0.5,
        sigma=0.8,
        unit="cm",
        tri=Tri.T,
    )

    gated, reasons = apply_gates([comp], {}, _DummyScale(), frame=0)  # type: ignore[arg-type]
    assert ReasonCode.BELOW_NOISE_FLOOR in reasons
    assert gated[0].tri == Tri.U
    assert gated[0].reason == ReasonCode.BELOW_NOISE_FLOOR


def test_gate_g6_depth_ambiguous() -> None:
    """Gate G6 triggers DEPTH_AMBIGUOUS for Tier C scale model on depth-critical relations."""
    comp = Component(
        name="inside.depth",
        value=1.0,
        threshold=2.0,
        margin=1.0,
        sigma=0.2,
        unit="cm",
        tri=Tri.T,
    )

    gated, reasons = apply_gates([comp], {}, _DummyScale(tier="C"), frame=0)  # type: ignore[arg-type]
    assert ReasonCode.DEPTH_AMBIGUOUS in reasons
    assert gated[0].tri == Tri.U
    assert gated[0].reason == ReasonCode.DEPTH_AMBIGUOUS


def test_occluded_clip_returns_cant_tell_and_exit_code_2() -> None:
    """occluded_clip.mp4 returns Verdict.CANT_TELL, exit code 2, and ReasonCode.OCCLUDED."""
    res = run(
        test="examples/stackcube.green",
        clip="tests/fixtures/clips/occluded_clip.mp4",
    )
    assert res.verdict == Verdict.CANT_TELL
    assert res.exit_code == 2
    assert ReasonCode.OCCLUDED in res.reasons
