"""Tests for the two-stage bisect fast path (pipeline/bisect.py, KD-05, ARCHITECTURE.md §5.2).

All perception here is fixture replay (tests/fixtures/tracks); no number in this file is SAM latency or accuracy.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from Kodiac_robotics.contracts.core import (
    Atom,
    Clip,
    Expr,
    GreenTest,
    ObjectDecl,
    Param,
    Provenance,
    Step,
    Track,
    Verdict,
)
from Kodiac_robotics.io.clip import open_clip
from Kodiac_robotics.io.windows import cut_window
from Kodiac_robotics.pipeline import bisect
from Kodiac_robotics.pipeline.bisect import FastRun, pad_window, run_fast
from Kodiac_robotics.pipeline.loader import load_green_test
from Kodiac_robotics.pipeline.run import run
from Kodiac_robotics.segment.fixture import FixtureBackend

STACKCUBE = Path("examples/stackcube.green")
CLIPS_DIR = Path("tests/fixtures/clips")
GOLDEN = sorted(json.loads((CLIPS_DIR / "manifest.json").read_text(encoding="utf-8"))["clips"])


def _decisive(steps: list) -> int | None:
    return next((s.frame for s in steps if s.verdict in (Verdict.FAIL, Verdict.CANT_TELL)), None)


def _lift_test(min_cm: float = 2.0) -> GreenTest:
    return GreenTest(
        name="lift_only",
        objects=[ObjectDecl(name="gripper", role="effector"), ObjectDecl(name="cubeA", size_cm=4.0)],
        steps=[
            Step(
                index=1,
                name="lift",
                expr=Expr(
                    op="atom",
                    atom=Atom(kind="pred", name="lifted", args=["cubeA"], params=[Param(name="min_cm", op="=", value=min_cm)]),
                ),
                provenance=Provenance(source="compiler-default"),
            )
        ],
    )


class _Replay:
    """In-memory segmenter: keyframe calls and track calls can replay different recordings (crafted cases)."""

    def __init__(self, seg: dict[str, Track], trk: dict[str, Track] | None = None, drop: dict[str, set[int]] | None = None):
        self.seg, self.trk, self.drop = seg, trk if trk is not None else seg, drop or {}

    def _pick(self, src: dict[str, Track], keys, frames, direction: str) -> dict[str, Track]:
        wanted = set(frames)
        out = {}
        for k in keys:
            if k in src:
                fr = {f: m for f, m in src[k].frames.items() if f in wanted and f not in self.drop.get(k, set())}
                out[k] = Track(obj=k, frames=fr, backend="fixture", direction=direction, trace_id="replay")
        return out

    def segment_frames(self, clip: Clip, frames: list[int], prompts: dict[str, list[str]]) -> dict[str, Track]:
        return self._pick(self.seg, prompts.keys(), frames, "forward")

    def track(self, clip: Clip, f0: int, f1: int, seeds, direction) -> dict[str, Track]:
        return self._pick(self.trk, seeds.keys(), range(min(f0, f1), max(f0, f1) + 1), direction)


@pytest.fixture
def force_bisect(monkeypatch: pytest.MonkeyPatch) -> None:
    """Golden clips are 90 frames; the default short-clip rule would skip the bisect entirely."""
    monkeypatch.setattr(bisect, "MIN_BISECT_FRAMES", 0)


# ---------------------------------------------------------------------------------------------------------------------
# Window arithmetic
# ---------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("f0,f1", [(0, 0), (89, 89), (10, 80), (30, 40), (0, 20), (70, 89)])
def test_pad_window_matches_cut_window(f0: int, f1: int) -> None:
    clip = open_clip(CLIPS_DIR / "correct_run.mp4")
    cut = cut_window(clip, f0, f1)
    assert pad_window(f0, f1, clip.n_frames) == (cut.padded_f0, cut.padded_f1)


@pytest.mark.parametrize(
    "f0,f1,n,expected",
    [
        (-18, 3, 360, (0, 49)),  # failure at frame 0 (bracket pre-roll goes negative)
        (359, 359, 360, (310, 359)),  # failure at the last frame
        (0, 0, 90, (0, 49)),
        (89, 89, 90, (40, 89)),
        (0, 10, 30, (0, 29)),  # clip shorter than the 50-frame minimum: the whole clip
        (100, 300, 360, (100, 300)),  # already >= 50 frames: unchanged
    ],
)
def test_window_at_least_50_frames_and_inside_clip(f0: int, f1: int, n: int, expected: tuple[int, int]) -> None:
    w0, w1 = pad_window(f0, f1, n)
    assert (w0, w1) == expected
    assert 0 <= w0 <= w1 <= n - 1
    assert w1 - w0 + 1 >= min(50, n)


def test_keyframes_cover_both_ends_and_scale_with_duration() -> None:
    assert bisect.keyframe_indices(90, 30.0, 6) == [0, 18, 36, 53, 71, 89]
    kf = bisect.keyframe_indices(900, 30.0, 6)  # 30 s -> ceil(30 / 2.5) = 12 keyframes
    assert len(kf) == 12 and kf[0] == 0 and kf[-1] == 899


# ---------------------------------------------------------------------------------------------------------------------
# Dense evaluator pinned to the full path
# ---------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", GOLDEN)
def test_dense_evaluator_equals_run_full_when_every_frame_is_tracked(name: str, tmp_path: Path) -> None:
    clip = open_clip(CLIPS_DIR / name)
    tracks = FixtureBackend()._load_tracks(clip)
    full = run(test=STACKCUBE, clip=clip, tracks=tracks, output_dir=tmp_path / "full")
    test_obj, _ = load_green_test(STACKCUBE)
    ev = bisect._evaluate_dense(test_obj, test_obj.steps, clip, tracks, set(range(clip.n_frames)), {})
    assert ev.verdict == full.verdict
    assert ev.reasons == full.reasons
    assert [(s.verdict, s.frame) for s in ev.steps] == [(s.verdict, s.frame) for s in full.steps]


# ---------------------------------------------------------------------------------------------------------------------
# Fast vs full agreement on golden fixtures
# ---------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", GOLDEN)
@pytest.mark.parametrize("forced", [False, True])
def test_fast_agrees_with_full_on_golden(name: str, forced: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if forced:
        monkeypatch.setattr(bisect, "MIN_BISECT_FRAMES", 0)
    clip = open_clip(CLIPS_DIR / name)
    full = run(test=STACKCUBE, clip=clip, output_dir=tmp_path / "full")
    fast = run_fast(STACKCUBE, clip, FixtureBackend(), output_dir=tmp_path / "fast")
    assert isinstance(fast, FastRun)
    assert fast.result.verdict == full.verdict
    assert _decisive(fast.result.steps) == _decisive(full.steps)
    assert fast.result.is_fixture is True
    assert fast.result.backends["latency_kind"] == bisect.LATENCY_KIND_FIXTURE
    assert fast.plan.n_sam_calls >= 1 and fast.billed_frames >= 50
    if not forced:
        assert fast.plan.guards_fired[0].startswith("G-budget:short_clip_direct")
    else:
        assert fast.plan.stage1_frames == [0, 18, 36, 53, 71, 89]


def test_plan_is_deterministic(force_bisect: None, tmp_path: Path) -> None:
    clip = open_clip(CLIPS_DIR / "b01_early_release.mp4")
    a = run_fast(STACKCUBE, clip, FixtureBackend(), seed=7, output_dir=tmp_path / "a")
    b = run_fast(STACKCUBE, clip, FixtureBackend(), seed=7, output_dir=tmp_path / "b")
    assert a.plan.model_dump() == b.plan.model_dump()
    assert a.billed_frames == b.billed_frames
    assert a.result.verdict == b.result.verdict
    assert a.result.backends["seed"] == "7"


def test_unknown_run_kwargs_are_rejected() -> None:
    clip = open_clip(CLIPS_DIR / "b01_early_release.mp4")
    with pytest.raises(TypeError):
        run_fast(STACKCUBE, clip, FixtureBackend(), backend="api")


# ---------------------------------------------------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------------------------------------------------


def test_g_budget_falls_back_to_full_path(force_bisect: None, tmp_path: Path) -> None:
    clip = open_clip(CLIPS_DIR / "b09_lift_failure.mp4")
    full = run(test=STACKCUBE, clip=clip, output_dir=tmp_path / "full")
    fast = run_fast(STACKCUBE, clip, FixtureBackend(), budget_calls=1, output_dir=tmp_path / "fast")
    assert any(g.startswith("G-budget:calls_exceeded") for g in fast.plan.guards_fired)
    assert fast.plan.window == (0, clip.n_frames - 1)
    assert bisect.FALLBACK_BADGE in fast.result.badges
    assert fast.result.verdict == full.verdict


def test_g_miss_object_lost_at_keyframe_falls_back(force_bisect: None, tmp_path: Path) -> None:
    clip = open_clip(CLIPS_DIR / "b01_early_release.mp4")
    tracks = FixtureBackend()._load_tracks(clip)
    seg = _Replay(tracks, drop={"cube_b": {36}})
    fast = run_fast(STACKCUBE, clip, seg, output_dir=tmp_path / "fast")
    assert fast.plan.guards_fired[0] == "G-miss:object_lost_at_keyframes(cubeB)"
    assert fast.result.backends["mode"] == "fast->full_fallback"


def test_g_pass_verifies_densely_and_matches_full(force_bisect: None, tmp_path: Path) -> None:
    clip = open_clip(CLIPS_DIR / "correct_run.mp4")
    test = _lift_test()
    full = run(test=test, clip=clip, output_dir=tmp_path / "full")
    assert full.verdict == Verdict.PASS
    fast = run_fast(test, clip, FixtureBackend(), output_dir=tmp_path / "fast")
    assert fast.result.verdict == Verdict.PASS
    assert any(g.startswith("G-pass:dense_verification_windows") for g in fast.plan.guards_fired)
    assert fast.result.backends["mode"] == "fast"
    achieved = fast.result.steps[0].frame
    assert achieved == full.steps[0].frame
    w0, w1 = fast.plan.window
    assert w0 <= achieved <= w1 and achieved not in fast.plan.stage1_frames


def test_pass_is_never_declared_from_keyframes_alone(force_bisect: None, tmp_path: Path) -> None:
    """Keyframes show a lift; the dense window shows none. The shortcut must not output PASS."""
    lifted_clip = open_clip(CLIPS_DIR / "correct_run.mp4")
    flat_clip = open_clip(CLIPS_DIR / "b09_lift_failure.mp4")
    seg = _Replay(FixtureBackend()._load_tracks(lifted_clip), trk=FixtureBackend()._load_tracks(flat_clip))
    fast = run_fast(_lift_test(), lifted_clip, seg, output_dir=tmp_path / "fast")
    assert fast.result.verdict != Verdict.PASS
    assert any(g.startswith("G-pass:verification_not_pass") for g in fast.plan.guards_fired)


def test_dwell_proxy_follows_dwell_semantics_not_on(force_bisect: None, tmp_path: Path) -> None:
    """Regression: dwell(A, B) only asks that A stays still (dwell.py ignores B). A proxy built from on(A, B) missed the
    resting cube at frames 15-30 and turned this PASS into a FAIL."""
    base, _ = load_green_test(STACKCUBE)
    dwell = next(a for s in base.steps for a in bisect._extract_atoms(s.expr) if a.name == "dwell")
    step = base.steps[2].model_copy(update={"index": 1, "name": "dwell", "expr": Expr(op="atom", atom=dwell)})
    test = base.model_copy(update={"name": "dwell_only", "steps": [step]})
    clip = open_clip(CLIPS_DIR / "b02_xy_misalignment.mp4")
    full = run(test=test, clip=clip, output_dir=tmp_path / "full")
    fast = run_fast(test, clip, FixtureBackend(), output_dir=tmp_path / "fast")
    assert full.verdict == Verdict.PASS
    assert fast.result.verdict == Verdict.PASS
    assert fast.result.steps[0].frame == full.steps[0].frame


def test_carry_start_finds_the_step_that_introduces_a_checked_literal() -> None:
    steps = load_green_test(STACKCUBE)[0].steps  # grasp: moves_with ∧ lifted · place: on · release: ¬moves_with ∧ dwell
    assert bisect._carry_start(steps, anchor=0, failing=1) == 0
    assert bisect._carry_start(steps, anchor=1, failing=2) == 0  # checked while searching `place`
    assert bisect._carry_start(_lift_test().steps, anchor=0, failing=0) is None
    assert bisect._checks_carried(steps, 1) and not bisect._checks_carried(steps, 2)


def _pool_episode(name: str) -> tuple[Clip, dict[str, Track], dict]:
    import importlib.util

    import numpy as np

    spec = importlib.util.spec_from_file_location("_ve", Path("scripts/validate_engine.py"))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    npz = np.load(Path("experiments/pool/episodes") / f"{name}.state.npz")
    tracks = mod.build_synthetic_tracks_from_obs(npz["obs_state"], npz["cam_K"])
    clip = Clip(
        ref={"uri": f"sim://pool/{name}", "source_kind": "sim"},
        path_h264=f"experiments/pool/episodes/{name}.mp4",
        fps=30.0,
        n_frames=len(npz["obs_state"]),
        width=640,
        height=480,
        sha256=f"pool-{name}",
    )
    return clip, tracks, {"cam_K": npz["cam_K"], "cam_extrinsic": npz["cam_extrinsic"]}


def test_bisect_t_star_exact_on_mock_episode_with_carried_break(tmp_path: Path) -> None:
    """Regression: the engine breaks at the FIRST F of carried moves_with (any pause makes it F). Watching it only at
    keyframes put t* at 106 instead of 54; the carried interval is now tracked densely. Synthetic tracks from mock state."""
    clip, tracks, cam = _pool_episode("ep_00000_calibration")
    assert clip.n_frames > bisect.MIN_BISECT_FRAMES  # default policy runs the bisect
    full = run(test=STACKCUBE, clip=clip, tracks=tracks, output_dir=tmp_path / "full", **cam)
    names = {"cube_a": "cubeA", "cube_b": "cubeB", "gripper": "gripper"}
    seg = _Replay({k: tracks[v] for k, v in names.items()})
    fast = run_fast(STACKCUBE, clip, seg, output_dir=tmp_path / "fast", **cam)
    assert fast.result.backends["mode"] == "fast"
    assert fast.plan.stage1_frames and fast.plan.stage1_frames[-1] == clip.n_frames - 1
    assert any(g.startswith("carry-window:dense_from_step(grasp)") for g in fast.plan.guards_fired)
    assert fast.result.verdict == full.verdict == Verdict.FAIL
    assert _decisive(full.steps) == 54
    assert abs(_decisive(fast.result.steps) - _decisive(full.steps)) <= 2


def test_g_alias_records_effector_resolved_through_alias_prompts(force_bisect: None, tmp_path: Path) -> None:
    clip = open_clip(CLIPS_DIR / "correct_run.mp4")
    test = _lift_test()
    test.objects[0] = ObjectDecl(name="arm_tool", role="effector")
    prompts, alias_names = bisect.build_prompts(test)
    assert alias_names == ["arm_tool"] and "robot gripper" in prompts["arm_tool"]
    tracks = FixtureBackend()._load_tracks(clip)
    tracks["arm_tool"] = tracks.pop("gripper").model_copy(update={"obj": "arm_tool"})
    fast = run_fast(test, clip, _Replay(tracks), output_dir=tmp_path / "fast")
    assert any(g.startswith("G-alias:effector_resolved(arm_tool") for g in fast.plan.guards_fired)
