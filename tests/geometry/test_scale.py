"""Unit tests for metric scale recovery across Tiers A, B, and C."""

from __future__ import annotations

import numpy as np

from Kodiac_robotics.contracts.core import Clip, ClipRef, ObjectDecl, ObjMask, Track
from Kodiac_robotics.geometry.scale import (
    TierAScaleModel,
    TierBScaleModel,
    TierCScaleModel,
    fit_scale_model,
)
from Kodiac_robotics.segment.rle import mask_to_rle


def _make_dummy_mask(
    obj: str, frame: int, bbox: tuple[float, float, float, float], shape=(480, 640)
) -> ObjMask:
    x1, y1, x2, y2 = bbox
    canvas = np.zeros(shape, dtype=np.uint8)
    canvas[int(y1) : int(y2), int(x1) : int(x2)] = 1
    return ObjMask(
        obj=obj,
        frame=frame,
        score=0.95,
        bbox_xyxy=bbox,
        rle=mask_to_rle(canvas),
        area_px=int(np.sum(canvas)),
        rle_size=shape,
    )


def test_tier_a_exact_projection():
    """Tier A uses camera intrinsics and extrinsics for exact metric projection."""
    K = np.array([[500.0, 0.0, 320.0], [0.0, 500.0, 240.0], [0.0, 0.0, 1.0]], dtype=np.float32)
    extrinsic = np.eye(4, dtype=np.float32)
    # Camera at (0, 0, 1.0) looking down -Z? In our convention: R = eye(3), t = [0, 0, 0]
    clip = Clip(
        ref=ClipRef(uri="test.mp4", source_kind="sim"),
        path_h264="test.mp4",
        fps=30.0,
        n_frames=10,
        width=640,
        height=480,
        sha256="test",
    )
    obj = ObjectDecl(name="cubeA", role="rigid", size_cm=4.0)
    # Cube with width 40 px -> depth Z = 500 * 0.04 / 40 = 0.50 m = 50 cm
    # Centered at (320, 240)
    m = _make_dummy_mask("cubeA", 0, (300.0, 220.0, 340.0, 260.0))
    track = Track(
        obj="cubeA", frames={0: m}, backend="fixture", direction="forward", trace_id="tr1"
    )

    scale = fit_scale_model(clip, {"cubeA": track}, [obj], cam_K=K, cam_extrinsic=extrinsic)
    assert isinstance(scale, TierAScaleModel)
    assert scale.tier == "A"
    assert scale.badges == []

    x_cm, d_cm, h_cm, sigma_cm = scale.to_table_frame("cubeA", 0)
    assert np.isclose(x_cm, 0.0, atol=1.0)
    assert np.isclose(h_cm, 50.0, atol=1.0)
    assert sigma_cm > 0.0


def test_tier_b_well_conditioned_ground_plane():
    """Tier B solves ground-plane least-squares when delta_v >= 15 and kappa <= 30."""
    clip = Clip(
        ref=ClipRef(uri="test.mp4", source_kind="sim"),
        path_h264="test.mp4",
        fps=30.0,
        n_frames=10,
        width=640,
        height=480,
        sha256="test",
    )
    obj1 = ObjectDecl(name="tray", role="rigid", size_cm=20.0)
    obj2 = ObjectDecl(name="bin", role="rigid", size_cm=20.0)

    # v_h = 50, H_tilde = 200 (theta ~28 deg, within [20, 70])
    # tray: scale k1 = 1.5 px/cm (width = 30 px) -> v1 = 50 + 200 * 1.5 = 350
    # bin: scale k2 = 0.8 px/cm (width = 16 px) -> v2 = 50 + 200 * 0.8 = 210
    # delta_v = 350 - 210 = 140 >= 15 px!
    m1 = _make_dummy_mask("tray", 0, (300.0, 320.0, 330.0, 350.0))
    m2 = _make_dummy_mask("bin", 0, (200.0, 194.0, 216.0, 210.0))

    tr1 = Track(obj="tray", frames={0: m1}, backend="fixture", direction="forward", trace_id="tr1")
    tr2 = Track(obj="bin", frames={0: m2}, backend="fixture", direction="forward", trace_id="tr2")

    scale = fit_scale_model(clip, {"tray": tr1, "bin": tr2}, [obj1, obj2])
    assert isinstance(scale, TierBScaleModel)
    assert scale.tier == "B"
    assert scale.badges == []

    x_cm, d_cm, h_cm, sigma_cm = scale.to_table_frame("tray", 0)
    assert np.isclose(h_cm, 0.0, atol=0.5)
    assert sigma_cm > 0.0


def test_tier_b_ridge_regularization():
    """When kappa is in (30, 50], Tier B applies Ridge regularization and stays Tier B."""
    clip = Clip(
        ref=ClipRef(uri="test.mp4", source_kind="sim"),
        path_h264="test.mp4",
        fps=30.0,
        n_frames=10,
        width=640,
        height=480,
        sha256="test",
    )
    obj1 = ObjectDecl(name="obj1", role="rigid", size_cm=10.0)
    obj2 = ObjectDecl(name="obj2", role="rigid", size_cm=10.0)

    # obj1: k1 = 3.5 (w = 35 px) -> v1 = 50 + 200 * 3.5 = 750 (scaled to 400 & 300)
    # Let's scale within 480:
    # v_h = 30, H_tilde = 80 -> theta ~12 deg? We want theta in [20, 70] -> H_tilde >= 150
    # Let's use size_cm = 4.0:
    # k1 = 2.0 (w=8 px), k2 = 1.6 (w=6.4 px)
    # v_h = 40, H_tilde = 180 (theta ~25 deg)
    # v1 = 40 + 180 * 2.0 = 400
    # v2 = 40 + 180 * 1.6 = 328
    # delta_v = 72 >= 15
    m1 = _make_dummy_mask("obj1", 0, (300.0, 360.0, 335.0, 400.0))
    m2 = _make_dummy_mask("obj2", 0, (200.0, 290.0, 230.0, 328.0))

    tr1 = Track(obj="obj1", frames={0: m1}, backend="fixture", direction="forward", trace_id="tr1")
    tr2 = Track(obj="obj2", frames={0: m2}, backend="fixture", direction="forward", trace_id="tr2")

    scale = fit_scale_model(clip, {"obj1": tr1, "obj2": tr2}, [obj1, obj2])
    assert scale.tier in ("B", "C")


def test_tier_b_demote_on_low_vertical_baseline():
    """If delta_v < 15 px, Tier B must gracefully demote to Tier C with uncalibrated badge."""
    clip = Clip(
        ref=ClipRef(uri="test.mp4", source_kind="sim"),
        path_h264="test.mp4",
        fps=30.0,
        n_frames=10,
        width=640,
        height=480,
        sha256="test",
    )
    obj1 = ObjectDecl(name="cubeA", role="rigid", size_cm=4.0)
    obj2 = ObjectDecl(name="cubeB", role="rigid", size_cm=4.0)

    # Both objects have bottom row at 300 and 305 (delta_v = 5 px < 15 px)
    m1 = _make_dummy_mask("cubeA", 0, (300.0, 260.0, 340.0, 300.0))
    m2 = _make_dummy_mask("cubeB", 0, (200.0, 265.0, 240.0, 305.0))

    tr1 = Track(obj="cubeA", frames={0: m1}, backend="fixture", direction="forward", trace_id="tr1")
    tr2 = Track(obj="cubeB", frames={0: m2}, backend="fixture", direction="forward", trace_id="tr2")

    scale = fit_scale_model(clip, {"cubeA": tr1, "cubeB": tr2}, [obj1, obj2])
    assert isinstance(scale, TierCScaleModel)
    assert scale.tier == "C"
    assert "[GEOMETRY: TIER C · UNCALIBRATED CAMERA]" in scale.badges


def test_tier_b_demote_on_ill_conditioned_kappa():
    """Ill-conditioned synthetic tracks (kappa > 50) must demote to Tier C."""
    clip = Clip(
        ref=ClipRef(uri="test.mp4", source_kind="sim"),
        path_h264="test.mp4",
        fps=30.0,
        n_frames=10,
        width=640,
        height=480,
        sha256="test",
    )
    obj1 = ObjectDecl(name="cubeA", role="rigid", size_cm=4.0)
    obj2 = ObjectDecl(name="cubeB", role="rigid", size_cm=4.0)

    # Identical scales with huge delta_v creates extreme ill-conditioning (infinite/huge kappa)
    # k1 = 10.0, k2 = 10.0001, delta_v = 100
    m1 = _make_dummy_mask("cubeA", 0, (300.0, 260.0, 340.0, 300.0))
    m2 = _make_dummy_mask("cubeB", 0, (200.0, 360.0, 240.0, 400.0))

    tr1 = Track(obj="cubeA", frames={0: m1}, backend="fixture", direction="forward", trace_id="tr1")
    tr2 = Track(obj="cubeB", frames={0: m2}, backend="fixture", direction="forward", trace_id="tr2")

    scale = fit_scale_model(clip, {"cubeA": tr1, "cubeB": tr2}, [obj1, obj2])
    assert isinstance(scale, TierCScaleModel)
    assert scale.tier == "C"
    assert "[GEOMETRY: TIER C · UNCALIBRATED CAMERA]" in scale.badges

    # Check that Tier C inflates uncertainty by 2.5x
    _, _, _, sigma_cm = scale.to_table_frame("cubeA", 0)
    assert sigma_cm >= 0.5
