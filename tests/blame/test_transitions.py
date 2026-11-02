"""Transition finder tests (class 1/2/3, transient break warnings, all-U, PASS, CAN'T TELL).

The ``scenario`` builder below is shared by the other blame tests. It produces *synthetic kinematic* episodes
(labelled as such, never presented as sim or real data): known gripper / cube trajectories in table-frame cm are fed
through the real predicates, gates and step engine via an exact (tier-A-like) fake scale model, so the ground-truth
onset of every failure is known by construction.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from Kodiac_robotics.blame.facts import reference_pred_frames
from Kodiac_robotics.blame.transitions import (
    Transition,
    expr_softscore,
    find_transition,
    index_pred_frames,
    load_trace_pred_frames,
)
from Kodiac_robotics.contracts.core import (
    Atom,
    ClipRef,
    Component,
    Event,
    Expr,
    GreenTest,
    ObjectDecl,
    ObjMask,
    PredFrame,
    Provenance,
    ReasonCode,
    RunResult,
    Step,
    StepResult,
    Track,
    Tri,
    Verdict,
)
from Kodiac_robotics.engine.steps import _extract_atoms, evaluate_step_chain
from Kodiac_robotics.engine.trace import TraceWriter
from Kodiac_robotics.pipeline.loader import load_green_test
from Kodiac_robotics.predicates.base import conjoin_components, get_atom_key
from Kodiac_robotics.predicates.dispatch import evaluate_atom
from Kodiac_robotics.uncertainty.gates import apply_gates

FPS = 30.0
N_FRAMES = 110
SIGMA_CM = 0.07
CUBE_B = (8.0, 22.0, 0.0)
CUBE_A0 = (-10.0, 22.0, 0.0)

# name -> (x_place, h_carry, h_place, release_frame). The cube detaches at release_frame + 1 (first bad frame).
SCENARIOS: dict[str, tuple[float, float, float, int]] = {
    "correct": (8.0, 10.0, 4.0, 72),
    "b01_early_release": (8.0, 10.0, 4.0, 45),
    "b02_xy_offset": (12.5, 10.0, 4.0, 72),
    "b10_place_high": (8.0, 10.0, 7.0, 72),
    "b09_low_lift": (1.0, 1.0, 1.0, 72),
}


class ExactScale:
    """Fake tier-A scale model returning known table-frame positions (cm) with a fixed sigma."""

    tier = "A"

    def __init__(self, pos: dict[str, np.ndarray], sigma: float) -> None:
        self.pos = pos
        self.sigma = sigma
        self.badges: list[str] = []

    def to_table_frame(self, obj: str, frame: int) -> tuple[float, float, float, float]:
        x, d, h = self.pos[obj][frame]
        return float(x), float(d), float(h), self.sigma


def _gripper(t: int, x_place: float, h_carry: float, h_place: float) -> tuple[float, float, float]:
    x0, d0, _ = CUBE_A0
    if t <= 10:
        return x0, d0, 12.0 * (1.0 - t / 10.0)
    if t <= 14:
        return x0, d0, 0.0
    if t <= 30:
        return x0, d0, h_carry * (t - 14) / 16.0
    if t <= 60:
        return x0 + (x_place - x0) * (t - 30) / 30.0, d0, h_carry
    if t <= 70:
        return x_place, d0, h_carry + (h_place - h_carry) * (t - 60) / 10.0
    if t <= 73:
        return x_place, d0, h_place
    return x_place, d0, h_place + 0.8 * (t - 73)


def kinematics(name: str, seed: int = 0) -> dict[str, np.ndarray]:
    """Gripper / cubeA / cubeB positions (X, D, h) in cm for a scenario; cube detaches at release + 1."""
    x_place, h_carry, h_place, release = SCENARIOS[name]
    rng = np.random.default_rng(seed)
    e = np.array([_gripper(t, x_place, h_carry, h_place) for t in range(N_FRAMES)], dtype=float)
    a = np.zeros_like(e)
    for t in range(N_FRAMES):
        if t <= 10:
            a[t] = CUBE_A0
        elif t <= release:
            a[t] = e[t]
        else:
            rx, rd, rh = a[release]
            rest = 4.0 if abs(rx - CUBE_B[0]) <= 2.0 and rh >= 3.5 else 0.0
            dt = (t - release) / FPS
            a[t] = (rx, rd, max(rest, rh - 0.5 * 981.0 * dt * dt))
    b = np.tile(np.array(CUBE_B, dtype=float), (N_FRAMES, 1))
    e += rng.normal(0.0, 0.005, size=e.shape)
    a += rng.normal(0.0, 0.005, size=a.shape)
    return {"gripper": e, "cubeA": a, "cubeB": b}


@dataclass
class Scenario:
    name: str
    test: GreenTest
    result: RunResult
    frames: dict[str, list[PredFrame]]
    reference: list[PredFrame]
    release_frame: int


def _tracks() -> dict[str, Track]:
    out: dict[str, Track] = {}
    for obj in ("gripper", "cubeA", "cubeB"):
        out[obj] = Track(
            obj=obj,
            frames={
                f: ObjMask(obj=obj, frame=f, score=0.95, bbox_xyxy=(0.0, 0.0, 10.0, 10.0), rle="", area_px=100)
                for f in range(N_FRAMES)
            },
            backend="fixture",
            direction="forward",
            trace_id=f"synthetic-{obj}",
        )
    return out


def run_result(
    test: GreenTest,
    verdict: Verdict,
    steps: list[StepResult],
    reasons: list[ReasonCode] | None = None,
    events: list[Event] | None = None,
) -> RunResult:
    return RunResult(
        run_id="synthetic",
        test_name=test.name,
        test_sha256="0" * 64,
        config_sha256="0" * 64,
        clip=ClipRef(uri="synthetic://kinematic", source_kind="sim"),
        verdict=verdict,
        exit_code=0 if verdict == Verdict.PASS else (1 if verdict == Verdict.FAIL else 2),
        steps=steps,
        reasons=reasons or [],
        events=events or [],
        nonce="0123456789abcdef",
        trace_path="",
        created_at="2026-11-02T00:00:00+00:00",
    )


def scenario(name: str, seed: int = 0) -> Scenario:
    """Run a synthetic kinematic episode through the real predicates, gates and step engine."""
    test, _ = load_green_test("examples/stackcube.green")
    pos = kinematics(name, seed)
    scale = ExactScale(pos, SIGMA_CM)
    tracks = _tracks()
    ctx = {"object_sizes": {"gripper": 4.0, "cubeA": 4.0, "cubeB": 4.0}, "object_heights": {"cubeA": 4.0, "cubeB": 4.0}}
    frames: dict[str, list[PredFrame]] = {}
    for step in test.steps:
        for atom in _extract_atoms(step.expr):
            key = get_atom_key(atom)
            if key in frames:
                continue
            lst: list[PredFrame] = []
            for f in range(N_FRAMES):
                pf = evaluate_atom(atom, tracks, scale, f, FPS, context=ctx)
                gated, _ = apply_gates(pf.components, tracks, scale, f)
                lst.append(
                    PredFrame(frame=f, atom_key=key, tri=conjoin_components(gated), components=gated, trace_id=pf.trace_id)
                )
            frames[key] = lst
    verdict, steps, reasons, events = evaluate_step_chain(test.steps, frames, FPS)
    result = run_result(test, verdict, steps, reasons, events)
    reference = reference_pred_frames("gripper", "cubeB", tracks, scale, N_FRAMES, FPS)
    return Scenario(name, test, result, frames, reference, SCENARIOS[name][3])


# ------------------------------------------------------------------------------------------------
# Hand-built PredFrame helpers for edge cases
# ------------------------------------------------------------------------------------------------


def atom_expr(name: str, *args: str) -> Expr:
    return Expr(op="atom", atom=Atom(kind="pred", name=name, args=list(args)))


def mk_test(steps: list[tuple[str, Expr]]) -> GreenTest:
    return GreenTest(
        name="t",
        objects=[ObjectDecl(name="gripper"), ObjectDecl(name="cubeA", size_cm=4), ObjectDecl(name="cubeB", size_cm=4)],
        steps=[
            Step(index=i, name=n, expr=e, provenance=Provenance(source="text")) for i, (n, e) in enumerate(steps)
        ],
    )


def series(key: str, comp: str, unit: str, values: list[float], threshold: float, upper: bool,
           sigma: float = 0.1, tris: list[Tri] | None = None, reason: ReasonCode | None = None) -> list[PredFrame]:
    out: list[PredFrame] = []
    for f, v in enumerate(values):
        margin = (threshold - v) if upper else (v - threshold)
        tri = tris[f] if tris is not None else (Tri.T if margin > 0 else Tri.F)
        if tris is None and abs(margin) < sigma:
            tri = Tri.U
        c = Component(name=comp, value=v, threshold=threshold, margin=margin, sigma=sigma, unit=unit, tri=tri,
                      reason=reason if tri == Tri.U else None)
        out.append(PredFrame(frame=f, atom_key=key, tri=tri, components=[c], trace_id=f"tr_{comp}_{f}"))
    return out


# ------------------------------------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------------------------------------


def test_correct_scenario_passes_and_yields_no_transition() -> None:
    sc = scenario("correct")
    assert sc.result.verdict == Verdict.PASS, [(s.name, s.verdict, s.frame) for s in sc.result.steps]
    assert find_transition(sc.result, sc.frames, sc.test, FPS) is None


def test_class1_early_release_is_broken_prerequisite_on_moves_with() -> None:
    sc = scenario("b01_early_release")
    assert sc.result.verdict == Verdict.FAIL
    tr = find_transition(sc.result, sc.frames, sc.test, FPS)
    assert tr is not None
    assert tr.cls == "broken_prerequisite"
    assert tr.step_name == "place"
    assert tr.literal == "moves_with(gripper, cubeA)"
    assert tr.component == "moves_with.slip"
    # final False run of the carried literal starts within 2 frames after the cube detaches (release + 1)
    assert sc.release_frame + 1 <= tr.t_frame <= sc.release_frame + 3


def test_class1_list_and_dict_inputs_agree() -> None:
    sc = scenario("b01_early_release")
    flat = [pf for lst in sc.frames.values() for pf in lst]
    a = find_transition(sc.result, sc.frames, sc.test, FPS)
    b = find_transition(sc.result, flat, sc.test, FPS)
    assert a is not None and b is not None
    assert a.model_dump() == b.model_dump()


def test_class2_low_lift_is_unmet_lifted_height() -> None:
    sc = scenario("b09_low_lift")
    assert sc.result.verdict == Verdict.FAIL
    tr = find_transition(sc.result, sc.frames, sc.test, FPS)
    assert tr is not None
    assert tr.cls == "unmet"
    assert tr.step_name == "grasp"
    assert tr.literal == "lifted(cubeA)"
    assert tr.component == "lifted.height"
    # t* is the softscore argmax: inside the carry, where the cube was highest
    assert 14 < tr.t_frame < 75


def test_class2_on_step_one_failing_and_softscore_argmax() -> None:
    values = [10.0 - 0.2 * f for f in range(20)] + [6.0 + 0.3 * (f - 20) for f in range(20, 30)]
    frames = {"on(cubeA, cubeB)": series("on(cubeA, cubeB)", "on.align_xy", "cm", values, 3.33, upper=True)}
    test = mk_test([("place", atom_expr("on", "cubeA", "cubeB"))])
    result = run_result(test, Verdict.FAIL, [StepResult(index=0, name="place", verdict=Verdict.FAIL, frame=29)])
    tr = find_transition(result, frames, test, FPS)
    assert tr is not None and tr.cls == "unmet"
    assert tr.t_frame == 20  # closest approach: 6.0 cm
    assert tr.component == "on.align_xy"
    idx = index_pred_frames(frames)
    assert expr_softscore(test.steps[0].expr, idx, 20) == pytest.approx((3.33 - 6.0) / 0.1)


def test_last_step_failing_unmet() -> None:
    lift = series("lifted(cubeA)", "lifted.height", "cm", [0.0] * 5 + [5.0] * 25, 2.0, upper=False)
    on = series("on(cubeA, cubeB)", "on.align_xy", "cm", [9.0] * 30, 3.33, upper=True)
    test = mk_test([("lift", atom_expr("lifted", "cubeA")), ("place", atom_expr("on", "cubeA", "cubeB"))])
    result = run_result(
        test,
        Verdict.FAIL,
        [
            StepResult(index=0, name="lift", verdict=Verdict.PASS, frame=7),
            StepResult(index=1, name="place", verdict=Verdict.FAIL, frame=29),
        ],
    )
    tr = find_transition(result, {"lifted(cubeA)": lift, "on(cubeA, cubeB)": on}, test, FPS)
    assert tr is not None and tr.cls == "unmet" and tr.step_index == 1
    assert tr.t_frame == 8  # first frame of the (flat) search window [a_0 + 1, end]


def test_transient_break_is_a_warning_not_blame() -> None:
    n = 40
    mw_tris = [Tri.T] * n
    for f in (15, 16):
        mw_tris[f] = Tri.F
    for f in range(30, n):
        mw_tris[f] = Tri.F
    mw_vals = [0.0 if t == Tri.T else 3.0 for t in mw_tris]
    mw = series("moves_with(gripper, cubeA)", "moves_with.slip", "cm", mw_vals, 1.0, upper=True, tris=mw_tris)
    lift = series("lifted(cubeA)", "lifted.height", "cm", [0.0] * 3 + [5.0] * (n - 3), 2.0, upper=False)
    on = series("on(cubeA, cubeB)", "on.align_xy", "cm", [9.0] * n, 3.33, upper=True)
    test = mk_test([
        ("grasp", Expr(op="and", children=[atom_expr("moves_with", "gripper", "cubeA"), atom_expr("lifted", "cubeA")])),
        ("place", atom_expr("on", "cubeA", "cubeB")),
    ])
    result = run_result(test, Verdict.FAIL, [
        StepResult(index=0, name="grasp", verdict=Verdict.PASS, frame=5),
        StepResult(index=1, name="place", verdict=Verdict.FAIL, frame=15),
    ])
    frames = {"moves_with(gripper, cubeA)": mw, "lifted(cubeA)": lift, "on(cubeA, cubeB)": on}
    tr = find_transition(result, frames, test, FPS)
    assert tr is not None
    assert tr.cls == "broken_prerequisite"
    assert tr.t_frame == 30  # the final False run, not the transient one at 15-16
    assert any("transient break" in w and "15-16" in w for w in tr.warnings)


def test_class3_order_violation_condition_held_before_predecessor() -> None:
    near = series("near(gripper, cubeA)", "near.distance", "cm", [10.0] * 5 + [1.0] * 5 + [10.0] * 30, 5.0, upper=True)
    lift = series("lifted(cubeA)", "lifted.height", "cm", [0.0] * 12 + [5.0] * 8 + [0.0] * 20, 2.0, upper=False)
    on = series("on(cubeA, cubeB)", "on.align_xy", "cm", [9.0] * 14 + [1.0] * 4 + [9.0] * 22, 3.33, upper=True)
    test = mk_test([
        ("reach", atom_expr("near", "gripper", "cubeA")),
        ("lift", atom_expr("lifted", "cubeA")),
        ("place", atom_expr("on", "cubeA", "cubeB")),
    ])
    result = run_result(test, Verdict.FAIL, [
        StepResult(index=0, name="reach", verdict=Verdict.PASS, frame=6),
        StepResult(index=1, name="lift", verdict=Verdict.PASS, frame=18),
        StepResult(index=2, name="place", verdict=Verdict.FAIL, frame=39),
    ])
    frames = {"near(gripper, cubeA)": near, "lifted(cubeA)": lift, "on(cubeA, cubeB)": on}
    tr = find_transition(result, frames, test, FPS)
    assert tr is not None
    assert tr.cls == "order_violation"
    assert tr.t_frame == 14
    assert tr.literal == "on(cubeA, cubeB)"


def test_engine_order_violation_event_is_honoured() -> None:
    on = series("on(cubeA, cubeB)", "on.align_xy", "cm", [9.0] * 20, 3.33, upper=True)
    test = mk_test([("place", atom_expr("on", "cubeA", "cubeB"))])
    ev = Event(step=0, step_name="place", kind="order_violation", t_s=0.3, frame=9, fps=FPS, source="attempt")
    result = run_result(test, Verdict.FAIL, [StepResult(index=0, name="place", verdict=Verdict.FAIL, frame=19)], events=[ev])
    tr = find_transition(result, {"on(cubeA, cubeB)": on}, test, FPS)
    assert tr is not None and tr.cls == "order_violation" and tr.t_frame == 9


def test_all_unknown_returns_none() -> None:
    n = 30
    on = series("on(cubeA, cubeB)", "on.align_xy", "cm", [9.0] * n, 3.33, upper=True,
                tris=[Tri.U] * n, reason=ReasonCode.OCCLUDED)
    test = mk_test([("place", atom_expr("on", "cubeA", "cubeB"))])
    result = run_result(test, Verdict.FAIL, [StepResult(index=0, name="place", verdict=Verdict.FAIL, frame=29)])
    assert find_transition(result, {"on(cubeA, cubeB)": on}, test, FPS) is None


def test_cant_tell_and_pass_return_none() -> None:
    on = series("on(cubeA, cubeB)", "on.align_xy", "cm", [9.0] * 10, 3.33, upper=True)
    test = mk_test([("place", atom_expr("on", "cubeA", "cubeB"))])
    ct = run_result(test, Verdict.CANT_TELL, [StepResult(index=0, name="place", verdict=Verdict.CANT_TELL)],
                    reasons=[ReasonCode.OCCLUDED])
    ok = run_result(test, Verdict.PASS, [StepResult(index=0, name="place", verdict=Verdict.PASS, frame=3)])
    assert find_transition(ct, {"on(cubeA, cubeB)": on}, test, FPS) is None
    assert find_transition(ok, {"on(cubeA, cubeB)": on}, test, FPS) is None


def test_below_noise_floor_cause_is_flagged() -> None:
    vals = [0.95] * 30  # margin 0.05 < sigma 0.1 -> U every frame, except two decided F frames
    tris = [Tri.U] * 30
    tris[0] = tris[1] = Tri.F
    mw = series("moves_with(gripper, cubeA)", "moves_with.slip", "cm", vals, 1.0, upper=True, tris=tris,
                reason=ReasonCode.BELOW_NOISE_FLOOR)
    test = mk_test([("grasp", atom_expr("moves_with", "gripper", "cubeA"))])
    result = run_result(test, Verdict.FAIL, [StepResult(index=0, name="grasp", verdict=Verdict.FAIL, frame=29)])
    tr = find_transition(result, {"moves_with(gripper, cubeA)": mw}, test, FPS)
    assert tr is not None and tr.cls == "unmet"
    assert any("below the noise floor" in w for w in tr.warnings)
    assert any("low-confidence" in w for w in tr.warnings)


def test_trace_roundtrip(tmp_path) -> None:
    sc = scenario("b01_early_release")
    path = tmp_path / "trace.jsonl"
    with TraceWriter(path) as w:
        for key, lst in sc.frames.items():
            for pf in lst:
                w.write_pred_frame(pf.frame, key, pf)
    loaded = load_trace_pred_frames(path)
    assert set(loaded) == set(sc.frames)
    a = find_transition(sc.result, sc.frames, sc.test, FPS)
    b = find_transition(sc.result, loaded, sc.test, FPS)
    assert isinstance(a, Transition) and isinstance(b, Transition)
    assert (a.cls, a.t_frame, a.literal) == (b.cls, b.t_frame, b.literal)
