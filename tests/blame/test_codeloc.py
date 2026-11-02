"""Code-location tests: unit cases plus the B01-B10 accuracy validation on the kinematic MOCK sim.

Validation honesty (Law 1): every number comes from `KinematicMockEnv` (`is_mock=True`).
The onset frame/component for each bug are derived from *privileged mock state* by a small
documented step-machine that mirrors ARCHITECTURE section 5.4 (class 1 broken carried literal,
class 2 unmet condition) on the `examples/stackcube.green` spec. It is NOT the Kodiac blame
engine and NOT real SAM tracks; it checks that, given a correct (frame, component), the
span log resolves to the buggy source line. Expected lines are anchored by source text in
`examples/sim/pick_place.py`, independent of the span machinery.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from examples.sim.pick_place import execute_pick_place  # noqa: E402
from Kodiac_robotics.blame.codeloc import (  # noqa: E402
    classes_for_component,
    component_for_facts,
    locate_code,
    locate_from_fact_table,
)
from Kodiac_robotics.contracts.core import FactTable  # noqa: E402
from Kodiac_robotics.sim.bugs import get_bug  # noqa: E402
from Kodiac_robotics.sim.env import KinematicMockEnv  # noqa: E402
from Kodiac_robotics.sim.robot import RobotController  # noqa: E402
from Kodiac_robotics.sim.spans import SimSpan  # noqa: E402

PICK_PLACE = _REPO_ROOT / "examples" / "sim" / "pick_place.py"
ARTIFACT = _REPO_ROOT / "artifacts" / "p06" / "codeloc_B01_B10.json"
FPS = 30.0
SEED = 0


def _span(i: int, cls: str, line: int, start: int, end: int, code: str = "x") -> SimSpan:
    return SimSpan(
        span_id=i,
        func=cls.split(".")[-1],
        file="examples/sim/pick_place.py",
        line=line,
        code=code,
        actuation_class=cls,  # type: ignore[arg-type]
        step_start=start,
        step_end=end,
        t_start_s=start / FPS,
        t_end_s=end / FPS,
    )


SYNTH = [
    _span(0, "arm.move_to", 10, 0, 20),
    _span(1, "gripper.close", 11, 20, 35),
    _span(2, "arm.lift", 12, 35, 60),
    _span(3, "arm.move_to", 13, 60, 100),
    _span(4, "gripper.open", 14, 100, 115),
    _span(5, "wait", 15, 115, 135),
    _span(6, "arm.retract", 16, 135, 170),
]


# ---------------------------------------------------------------- unit tests
def test_empty_spans_returns_none() -> None:
    assert locate_code([], 50, "moves_with.slip") is None


def test_latest_matching_span_wins() -> None:
    loc = locate_code(SYNTH, 118, "moves_with.slip")
    assert loc is not None and (loc.line, loc.span_id) == (14, 4)
    assert loc.file == "examples/sim/pick_place.py"


def test_slack_frames_boundary() -> None:
    # open starts at step 100: frame 97 + slack 3 reaches it, frame 96 does not
    assert locate_code(SYNTH, 97, "moves_with.slip", slack_frames=3).span_id == 4  # type: ignore[union-attr]
    assert locate_code(SYNTH, 96, "moves_with.slip", slack_frames=3).span_id == 3  # type: ignore[union-attr]
    assert locate_code(SYNTH, 96, "moves_with.slip", slack_frames=4).span_id == 4  # type: ignore[union-attr]


def test_component_class_filter() -> None:
    assert classes_for_component("dwell.duration") == ("wait",)
    assert locate_code(SYNTH, 160, "dwell.duration").span_id == 5  # type: ignore[union-attr]
    assert locate_code(SYNTH, 160, "lifted.height").span_id == 2  # type: ignore[union-attr]
    assert locate_code(SYNTH, 160, "on.align_xy").span_id == 3  # type: ignore[union-attr]


def test_unknown_component_falls_back_to_find_blame_span() -> None:
    loc = locate_code(SYNTH, 118, "mystery.component")
    assert loc is not None  # wrapped find_blame_span returns a covering span, never invents one
    assert loc.span_id in {s.span_id for s in SYNTH}


def test_no_admissible_class_falls_back() -> None:
    only_move = [_span(0, "arm.move_to", 5, 0, 30)]
    loc = locate_code(only_move, 10, "dwell.duration")
    assert loc is not None and loc.span_id == 0


def _ft(facts: dict[str, dict[str, Any]], literal: str = "moves_with(gripper, cubeA)") -> FactTable:
    return FactTable(
        t_star_s=1.0,
        frame=30,
        fps=FPS,
        sigma_frames=1.0,
        step_index=1,
        step_name="place",
        literal=literal,
        transition="T->F",
        facts=facts,
    )


def test_component_for_facts_disambiguation() -> None:
    release_first = _ft({"dt_before_reference_s": {"value": 0.9, "sigma": 0.1, "unit": "s"}})
    assert component_for_facts(release_first) == "moves_with.slip"
    xy = _ft({"xy_offset_cm": {"value": 5.0, "sigma": 0.3, "unit": "cm", "threshold": 3.33}})
    assert component_for_facts(xy) == "on.align_xy"
    gap = _ft(
        {
            "xy_offset_cm": {"value": 0.2, "sigma": 0.3, "unit": "cm", "threshold": 3.33},
            "gap_cm": {"value": 11.0, "sigma": 0.5, "unit": "cm", "threshold": 0.5},
        }
    )
    assert component_for_facts(gap) == "on.gap"
    explicit = _ft({"blame_class": {"value": "z_gap"}})
    assert component_for_facts(explicit) == "on.gap"
    assert component_for_facts(_ft({}, literal="dwell(cubeA, cubeB, for_s=0.5)")) == "dwell.duration"


def test_locate_from_fact_table_uses_frame_and_component() -> None:
    ft = _ft({"dt_before_reference_s": {"value": 0.9, "sigma": 0.1, "unit": "s"}}).model_copy(
        update={"frame": 118}
    )
    loc = locate_from_fact_table(SYNTH, ft)
    assert loc is not None and loc.span_id == 4


# ------------------------------------------------- B01-B10 mock-sim validation
def _anchor_line(marker: str, snippet: str) -> int:
    """1-based line of the first `snippet` at/after the first line containing `marker`."""
    lines = PICK_PLACE.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if marker in ln)
    for j in range(start, len(lines)):
        if snippet in lines[j]:
            return j + 1
    raise AssertionError(f"{snippet!r} not found after {marker!r}")


# bug -> (marker, statement the bug makes wrong); see module docstring
_EXPECTED_ANCHORS: dict[str, tuple[str, str]] = {
    "B01": ('bug_id == "B01"', "robot.gripper.open(steps=15)"),
    "B02": ('bug_id == "B02"', "robot.arm.move_to(place_pose)"),
    "B03": ('bug_id == "B03"', "robot.arm.lift(distance=0.005)"),
    "B04": ('bug_id == "B04"', "robot.wait(duration_s=0.03)"),
    "B05": ('bug_id == "B05"', "robot.arm.lift(distance=0.12)"),
    "B06": ('bug_id == "B06"', "robot.arm.move_to(grasp_pose)"),
    "B07": ('bug_id == "B07"', "robot.arm.lift(distance=0.12)"),
    "B08": ('bug_id == "B08"', "robot.arm.move_to(pre_grasp)"),
    "B09": ('bug_id != "B09"', "robot.arm.retract(distance=0.15)"),
    "B10": ('bug_id == "B10"', "robot.arm.move_to(place_pose)"),
}


class _Episode:
    def __init__(self, bug: str) -> None:
        env = KinematicMockEnv()
        robot = RobotController(env)
        robot.reset(seed=SEED)
        self.oracle_success = execute_pick_place(robot, bug_id=bug)
        self.spans: list[SimSpan] = list(robot.spans)
        st = robot.states
        self.n = len(st)
        ee0 = np.array([st[0].cubeA_pose[0], st[0].cubeA_pose[1], 0.20])
        self.ee = np.vstack([ee0, ee0 + np.cumsum(np.array(robot.actions)[:, :3], axis=0)])
        self.A = np.array([s.cubeA_pose[:3] for s in st])
        self.B = np.array([s.cubeB_pose[:3] for s in st])
        self.speed_cm_s = np.array([np.linalg.norm(s.cubeA_vel) for s in st]) * 100.0
        self.width = np.array([s.gripper_width for s in st])
        self.dist_cm = np.linalg.norm(self.A - self.ee, axis=1) * 100.0
        self.lift_cm = (self.A[:, 2] - self.A[0, 2]) * 100.0
        self.xy_cm = np.linalg.norm(self.A[:, :2] - self.B[:, :2], axis=1) * 100.0
        self.gap_cm = np.abs((self.A[:, 2] - self.B[:, 2]) * 100.0 - 4.0)
        self.closed = self.width < 0.02
        self.mw = self.closed & (self.dist_cm <= 1.5)
        self.on = (self.xy_cm <= 3.33) & (self.gap_cm <= 0.5)


def _clip_mean(*margins: np.ndarray) -> np.ndarray:
    return np.mean([np.clip(m, -100.0, 100.0) for m in margins], axis=0)


def _still_run_s(still: np.ndarray) -> np.ndarray:
    run = np.zeros(len(still))
    for i in range(1, len(still)):
        run[i] = run[i - 1] + 1.0 / FPS if still[i] else 0.0
    return run


def mock_onset(ep: _Episode) -> dict[str, Any]:
    """Step machine over stackcube.green on privileged mock state -> (frame, component, facts)."""
    n = ep.n
    f1 = next((f for f in range(n) if ep.mw[f] and ep.lift_cm[f] >= 2.0), None)
    if f1 is None:  # class 2 on step 1: moves_with and lifted(min_cm=2.0)
        m = {"moves_with.slip": 1.5 - ep.dist_cm, "lifted.height": ep.lift_cm - 2.0}
        f = int(np.argmax(_clip_mean(*m.values())))
        comp = min(m, key=lambda k: float(m[k][f]))
        return {"frame": f, "component": comp, "klass": "unmet@step1"}

    f2 = next((f for f in range(f1, n) if ep.on[f]), n)
    detached = [f for f in range(f1, f2) if not ep.mw[f]]
    if detached:  # class 1: carried moves_with broke before `on` ever held
        t = detached[0]
        xy_after = np.linalg.norm(ep.ee[t:, :2] - ep.B[t:, :2], axis=1)
        t_ref = t + int(np.argmin(xy_after))
        dt = (t_ref - t) / FPS
        facts: dict[str, dict[str, Any]] = {
            "xy_offset_cm": {
                "value": float(ep.xy_cm[t]), "sigma": 0.3, "unit": "cm", "threshold": 3.33
            },
            "gap_cm": {
                "value": float(ep.gap_cm[t]), "sigma": 0.3, "unit": "cm", "threshold": 0.5
            },
        }
        if dt > 1.0 / FPS:
            facts["dt_before_reference_s"] = {"value": dt, "sigma": 1.0 / FPS, "unit": "s"}
        return {"frame": t, "klass": "broken_prerequisite", "facts": facts, "component": None}

    # class 2 on step 3: not moves_with and dwell(0.5 s) on the target
    still = (ep.speed_cm_s < 1.0) & ep.on & ~ep.closed  # dwell clock runs only after release
    dwell_s = _still_run_s(still)
    not_mw = np.where(ep.closed, ep.dist_cm - 1.5, 1.5)
    m3 = {"moves_with.slip": not_mw, "dwell.duration": dwell_s - 0.5}
    ok3 = (not_mw >= 0) & (dwell_s >= 0.5)
    assert not ok3[f2:].any(), "step 3 unexpectedly achieved on a buggy episode"
    f = f2 + int(np.argmax(_clip_mean(*[v[f2:] for v in m3.values()])))
    comp = min(m3, key=lambda k: float(m3[k][f]))
    return {"frame": f, "component": comp, "klass": "unmet@step3"}


def _resolve(ep: _Episode, onset: dict[str, Any]) -> tuple[int, str]:
    if onset["component"] is not None:
        return onset["frame"], onset["component"]
    ft = _ft(onset["facts"]).model_copy(update={"frame": onset["frame"]})
    return onset["frame"], component_for_facts(ft)


@pytest.fixture(scope="module")
def report() -> dict[str, Any]:
    rows = []
    for i in range(1, 11):
        bug = f"B{i:02d}"
        ep = _Episode(bug)
        assert ep.oracle_success is False
        onset = mock_onset(ep)
        frame, comp = _resolve(ep, onset)
        loc = locate_code(ep.spans, frame, comp)
        marker, snippet = _EXPECTED_ANCHORS[bug]
        exp_line = _anchor_line(marker, snippet)
        lo = hi = frame
        while lo > 0 and getattr(locate_code(ep.spans, lo - 1, comp), "line", None) == exp_line:
            lo -= 1
        while (
            hi < ep.n - 1
            and getattr(locate_code(ep.spans, hi + 1, comp), "line", None) == exp_line
        ):
            hi += 1
        reg = get_bug(bug)
        by_id = {s.span_id: s for s in ep.spans}
        rows.append(
            {
                "bug": bug,
                "name": reg.name,
                "seed": SEED,
                "onset_frame": frame,
                "onset_rule": onset["klass"],
                "component": comp,
                "expected_line": exp_line,
                "expected_code": snippet,
                "located_line": loc.line if loc else None,
                "stable_frame_window": [lo, hi] if loc and loc.line == exp_line else None,
                "located_code": loc.code if loc else None,
                "located_span_class": by_id[loc.span_id].actuation_class if loc else None,
                "registry_expected_span_class": reg.expected_blame_span,
                "match": bool(loc and loc.line == exp_line),
                "match_registry_span_class": bool(
                    loc and by_id[loc.span_id].actuation_class == reg.expected_blame_span
                ),
            }
        )
    n_ok = sum(r["match"] for r in rows)
    out = {
        "backend": "kinematic_mock",
        "is_mock": True,
        "evidence_type": "mock_sim_privileged_state",
        "note": (
            "Onset frame/component derived from privileged KinematicMockEnv state by a "
            "step-machine in tests/blame/test_codeloc.py (not the Kodiac blame engine, not "
            "real SAM tracks). Expected lines anchored by source text in "
            "examples/sim/pick_place.py. B09 is an omission bug: the expected line is the "
            "manifestation (retract drags the cube), per the bug registry."
        ),
        "n_correct": n_ok,
        "n_total": len(rows),
        "bugs": rows,
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out


@pytest.mark.parametrize("bug", [f"B{i:02d}" for i in range(1, 11)])
def test_bug_location_matches_buggy_line(report: dict[str, Any], bug: str) -> None:
    row = next(r for r in report["bugs"] if r["bug"] == bug)
    assert row["match"], json.dumps(row, indent=2)


def test_report_written_and_labelled_mock(report: dict[str, Any]) -> None:
    saved = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert saved["backend"] == "kinematic_mock" and saved["is_mock"] is True
    assert saved["n_total"] == 10
