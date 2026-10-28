"""Unit tests for closed 6-predicate vocabulary and dispatch."""

from __future__ import annotations

from Kodiac_robotics.contracts.core import (
    Atom,
    ObjMask,
    Param,
    ReasonCode,
    Track,
    Tri,
)
from Kodiac_robotics.predicates.dispatch import evaluate_atom


class MockScaleModel:
    """Mock implementation of ScaleModel protocol."""

    tier = "A"

    def __init__(self, coords: dict[tuple[str, int], tuple[float, float, float, float]]) -> None:
        self.coords = coords

    def to_table_frame(self, obj: str, frame: int) -> tuple[float, float, float, float]:
        if (obj, frame) in self.coords:
            return self.coords[(obj, frame)]
        return (0.0, 0.0, 0.0, 0.5)


def make_mock_track(obj: str, frames: list[int]) -> Track:
    """Create a mock Track for an object across given frames."""
    mask_dict: dict[int, ObjMask] = {}
    for f in frames:
        mask_dict[f] = ObjMask(
            obj=obj,
            frame=f,
            score=0.95,
            bbox_xyxy=(10.0, 10.0, 50.0, 50.0),
            rle="dummy_rle",
            area_px=1600,
        )
    return Track(
        obj=obj,
        frames=mask_dict,
        backend="fixture",
        direction="forward",
        trace_id=f"track_{obj}",
    )


def test_on_predicate_pass_and_fail():
    """Verify on(a, b) lateral margin, vertical gap, and scale consistency."""
    atom_pass = Atom(
        kind="pred",
        name="on",
        args=["red_block", "green_block"],
        params=[
            Param(name="align_xy_cm", op="<=", value=1.5),
            Param(name="gap_cm", op="<=", value=1.0),
            Param(name="depth_tol", op="<=", value=0.12),
        ],
    )

    # Coordinates: (X, D, h, sigma)
    # red_block at (10.0, 20.0, 4.2), green_block at (10.3, 20.2, 0.0) with height 4.0
    coords: dict[tuple[str, int], tuple[float, float, float, float]] = {
        ("red_block", 0): (10.0, 20.0, 4.2, 0.3),
        ("green_block", 0): (10.3, 20.2, 0.0, 0.3),
    }
    scale = MockScaleModel(coords)
    tracks = {
        "red_block": make_mock_track("red_block", [0]),
        "green_block": make_mock_track("green_block", [0]),
    }
    context = {"object_heights": {"green_block": 4.0}}

    pf = evaluate_atom(atom_pass, tracks, scale, frame=0, fps=30.0, context=context)
    assert pf.tri == Tri.T
    assert len(pf.components) == 3

    # Check component signs: m > 0 for all
    comp_map = {c.name: c for c in pf.components}
    assert comp_map["on.align_xy"].margin > 0
    assert comp_map["on.gap"].margin > 0
    assert comp_map["on.scale_ratio"].margin > 0
    assert comp_map["on.align_xy"].unit == "cm"
    assert comp_map["on.scale_ratio"].unit == "ratio"

    # Test lateral alignment failure: red_block placed 3 cm away
    coords_fail = {
        ("red_block", 0): (13.0, 20.0, 4.2, 0.3),
        ("green_block", 0): (10.0, 20.0, 0.0, 0.3),
    }
    scale_fail = MockScaleModel(coords_fail)
    pf_fail = evaluate_atom(atom_pass, tracks, scale_fail, frame=0, fps=30.0, context=context)
    assert pf_fail.tri == Tri.F
    comp_map_fail = {c.name: c for c in pf_fail.components}
    assert comp_map_fail["on.align_xy"].margin < 0
    assert comp_map_fail["on.align_xy"].tri == Tri.F


def test_on_surface_table():
    """Verify on(red_block, table) evaluates correctly against surface plane."""
    atom = Atom(kind="pred", name="on", args=["red_block", "table"])
    coords = {("red_block", 0): (5.0, 15.0, 0.2, 0.2)}
    scale = MockScaleModel(coords)
    tracks = {"red_block": make_mock_track("red_block", [0])}

    pf = evaluate_atom(atom, tracks, scale, frame=0, fps=30.0)
    assert pf.tri == Tri.T
    comp_map = {c.name: c for c in pf.components}
    assert comp_map["on.gap"].margin > 0


def test_inside_predicate():
    """Verify inside(a, b) in-rim clearance and front-occluder height."""
    atom = Atom(
        kind="pred",
        name="inside",
        args=["red_block", "bin"],
        params=[Param(name="rim_margin_cm", op=">=", value=0.5)],
    )

    # Bin at (0, 30, 0), radius 6.0 cm, height 10.0 cm
    # red_block at (1.0, 31.0, 2.0) -> d_xy = sqrt(2) ≈ 1.41 cm, clearance = 6 - 1.41 = 4.59 cm > 0.5 cm
    coords = {
        ("red_block", 0): (1.0, 31.0, 2.0, 0.3),
        ("bin", 0): (0.0, 30.0, 0.0, 0.3),
    }
    scale = MockScaleModel(coords)
    tracks = {
        "red_block": make_mock_track("red_block", [0]),
        "bin": make_mock_track("bin", [0]),
    }
    context = {"container_radii": {"bin": 6.0}, "object_heights": {"bin": 10.0}}

    pf = evaluate_atom(atom, tracks, scale, frame=0, fps=30.0, context=context)
    assert pf.tri == Tri.T
    comp_map = {c.name: c for c in pf.components}
    assert comp_map["inside.rim_margin"].margin > 0
    assert comp_map["inside.front_occluder"].margin > 0

    # Outside rim failure: red_block at (6.0, 30.0, 2.0) -> clearance = 0.0 < 0.5 cm
    coords_outside = {
        ("red_block", 0): (6.0, 30.0, 2.0, 0.3),
        ("bin", 0): (0.0, 30.0, 0.0, 0.3),
    }
    pf_out = evaluate_atom(atom, tracks, MockScaleModel(coords_outside), frame=0, fps=30.0, context=context)
    assert pf_out.tri == Tri.F
    assert {c.name: c for c in pf_out.components}["inside.rim_margin"].margin < 0


def test_near_predicate():
    """Verify near(a, b) 3D Euclidean boundary distance."""
    atom = Atom(
        kind="pred",
        name="near",
        args=["gripper", "red_block"],
        params=[Param(name="max_cm", op="<=", value=5.0)],
    )

    coords_near = {
        ("gripper", 0): (10.0, 20.0, 5.0, 0.2),
        ("red_block", 0): (12.0, 21.0, 4.0, 0.2),
    }
    scale = MockScaleModel(coords_near)
    tracks = {
        "gripper": make_mock_track("gripper", [0]),
        "red_block": make_mock_track("red_block", [0]),
    }

    pf = evaluate_atom(atom, tracks, scale, frame=0, fps=30.0)
    assert pf.tri == Tri.T
    assert pf.components[0].name == "near.distance"
    assert pf.components[0].margin > 0

    # Far failure
    coords_far = {
        ("gripper", 0): (10.0, 20.0, 15.0, 0.2),
        ("red_block", 0): (10.0, 20.0, 0.0, 0.2),
    }
    pf_far = evaluate_atom(atom, tracks, MockScaleModel(coords_far), frame=0, fps=30.0)
    assert pf_far.tri == Tri.F
    assert pf_far.components[0].margin < 0


def test_lifted_predicate():
    """Verify lifted(a, min_cm=2.0) relative vertical displacement."""
    atom = Atom(
        kind="pred",
        name="lifted",
        args=["red_block"],
        params=[Param(name="min_cm", op=">=", value=2.0)],
    )

    # Frame 0: rest height h=0.0; Frame 10: lifted to h=3.5
    coords = {
        ("red_block", 0): (10.0, 20.0, 0.0, 0.2),
        ("red_block", 10): (10.0, 20.0, 3.5, 0.2),
    }
    scale = MockScaleModel(coords)
    tracks = {"red_block": make_mock_track("red_block", [0, 10])}

    pf_f0 = evaluate_atom(atom, tracks, scale, frame=0, fps=30.0)
    assert pf_f0.tri == Tri.F  # delta_h = 0.0 < 2.0

    pf_f10 = evaluate_atom(atom, tracks, scale, frame=10, fps=30.0)
    assert pf_f10.tri == Tri.T
    assert pf_f10.components[0].value == 3.5
    assert pf_f10.components[0].margin == 1.5  # 3.5 - 2.0 = 1.5 > 0


def test_moves_with_predicate():
    """Verify moves_with(a, b) relative displacement over window."""
    atom = Atom(
        kind="pred",
        name="moves_with",
        args=["gripper", "red_block"],
        params=[
            Param(name="slip_cm", op="<=", value=1.0),
            Param(name="window_s", op="=", value=0.33),
        ],
    )

    # At 30 fps, window_s=0.33 -> 10 frames
    # Between frame 0 and frame 10, both move by (2.0, 1.0, 3.0)
    coords = {
        ("gripper", 0): (0.0, 0.0, 0.0, 0.2),
        ("red_block", 0): (0.0, 0.0, 0.0, 0.2),
        ("gripper", 10): (2.0, 1.0, 3.0, 0.2),
        ("red_block", 10): (2.1, 1.0, 3.0, 0.2),  # slip = 0.1 cm < 1.0 cm
    }
    scale = MockScaleModel(coords)
    tracks = {
        "gripper": make_mock_track("gripper", [0, 10]),
        "red_block": make_mock_track("red_block", [0, 10]),
    }

    pf = evaluate_atom(atom, tracks, scale, frame=10, fps=30.0)
    assert pf.tri == Tri.T
    assert pf.components[0].name == "moves_with.slip"
    assert pf.components[0].margin > 0

    # Slip failure: block dropped / didn't move with gripper
    coords_slip = {
        ("gripper", 0): (0.0, 0.0, 0.0, 0.2),
        ("red_block", 0): (0.0, 0.0, 0.0, 0.2),
        ("gripper", 10): (5.0, 0.0, 5.0, 0.2),
        ("red_block", 10): (0.0, 0.0, 0.0, 0.2),  # stayed at origin -> rho_rel ≈ 7.07 cm
    }
    pf_slip = evaluate_atom(atom, tracks, MockScaleModel(coords_slip), frame=10, fps=30.0)
    assert pf_slip.tri == Tri.F
    assert pf_slip.components[0].margin < 0


def test_dwell_predicate():
    """Verify dwell(a, for_s=0.5, max_speed_cm_s=1.0) stillness run length."""
    atom = Atom(
        kind="pred",
        name="dwell",
        args=["red_block"],
        params=[
            Param(name="for_s", op=">=", value=0.5),
            Param(name="max_speed_cm_s", op="<=", value=1.0),
        ],
    )

    # 16 frames of stationary red_block at 30 fps (16 / 30 ≈ 0.53 s >= 0.5 s)
    frames = list(range(16))
    coords = {("red_block", f): (10.0, 20.0, 0.0, 0.2) for f in frames}
    scale = MockScaleModel(coords)
    tracks = {"red_block": make_mock_track("red_block", frames)}

    pf = evaluate_atom(atom, tracks, scale, frame=15, fps=30.0)
    assert pf.tri == Tri.T
    comp_map = {c.name: c for c in pf.components}
    assert comp_map["dwell.speed"].margin > 0
    assert comp_map["dwell.duration"].margin >= 0
    assert comp_map["dwell.speed"].unit == "cm/s"
    assert comp_map["dwell.duration"].unit == "s"

    # Moving failure: red_block moving 10 cm every frame (300 cm/s)
    coords_moving = {("red_block", f): (float(f * 10), 20.0, 0.0, 0.2) for f in frames}
    pf_moving = evaluate_atom(atom, tracks, MockScaleModel(coords_moving), frame=15, fps=30.0)
    assert pf_moving.tri == Tri.F
    assert {c.name: c for c in pf_moving.components}["dwell.speed"].margin < 0


def test_dispatch_looks_and_manual():
    """Verify dispatch passes through looks (Tri.U) and manual (Tri.T) atoms."""
    atom_looks = Atom(kind="looks", args=["drawer"], looks_pos="closed", looks_neg="open")
    atom_manual = Atom(kind="manual", manual_text="gently release contact force")
    tracks: dict[str, Track] = {}
    scale = MockScaleModel({})

    pf_looks = evaluate_atom(atom_looks, tracks, scale, frame=0, fps=30.0)
    assert pf_looks.tri == Tri.U
    assert pf_looks.components == []
    assert "looks(" in pf_looks.atom_key

    pf_manual = evaluate_atom(atom_manual, tracks, scale, frame=0, fps=30.0)
    assert pf_manual.tri == Tri.T
    assert pf_manual.components == []
    assert "MANUAL(" in pf_manual.atom_key


def test_not_visible_handling():
    """Verify missing object track or frame returns Tri.U with ReasonCode.NOT_VISIBLE."""
    atom = Atom(kind="pred", name="near", args=["missing_obj", "red_block"])
    tracks = {"red_block": make_mock_track("red_block", [0])}
    scale = MockScaleModel({})

    pf = evaluate_atom(atom, tracks, scale, frame=0, fps=30.0)
    assert pf.tri == Tri.U
    assert len(pf.components) == 1
    assert pf.components[0].reason == ReasonCode.NOT_VISIBLE
