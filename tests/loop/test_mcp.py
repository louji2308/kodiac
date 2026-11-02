"""Tests for the `Kodiac.verify` MCP tool (loop/mcp_server.py).

Unit tests monkeypatch the sim runner / pipeline so they run before and after T04's runner exists.
The integration tests at the bottom use the real runner + engine and skip if the runner is missing.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from Kodiac_robotics.contracts.core import (
    Clip,
    ReasonCode,
    RunResult,
    StepResult,
    Verdict,
    VerifyRequest,
)
from Kodiac_robotics.loop import mcp_server

REPO = Path(__file__).resolve().parents[2]
NONCE = "0123456789abcdef"


# ---------------------------------------------------------------- fakes
def _fake_runner(tmp: Path, *, crash: bool = False, is_mock: bool = True) -> types.ModuleType:
    mod = types.ModuleType("Kodiac_robotics.sim.runner")
    calls: list[tuple[Path, int]] = []

    def run_script(script: Path, seed: int, out_dir: Path, backend: str = "auto") -> Any:
        calls.append((Path(script), seed))
        if crash:
            raise RuntimeError("boom inside the user's script")
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        video, state, spans = out_dir / "run.mp4", out_dir / "run.state.npz", out_dir / "spans.jsonl"
        video.write_bytes(b"not-a-real-video")
        obs = np.zeros((5, 24), dtype=np.float32)
        obs[:, 2] = 0.3
        obs[:, 8:11] = [0.1, 0.0, 0.02]
        obs[:, 15:18] = [0.2, 0.0, 0.02]
        np.savez(state, obs_state=obs, cam_K=np.array([[400, 0, 256], [0, 400, 256], [0, 0, 1]], dtype=np.float32), cam_extrinsic=np.eye(4, dtype=np.float32))
        spans.write_text(
            json.dumps(
                {
                    "span_id": 0, "func": "open", "file": "examples/sim/pick_place.py", "line": 7,
                    "code": "robot.gripper.open()", "actuation_class": "gripper.open",
                    "step_start": 1, "step_end": 2, "t_start_s": 0.03, "t_end_s": 0.06,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        from pydantic import BaseModel

        class SimRunResult(BaseModel):
            video_path: str
            state_path: str
            spans_path: str
            oracle_success: bool
            backend: str
            is_mock: bool
            script_sha256: str
            seed: int
            n_frames: int
            fps: float

        return SimRunResult(
            video_path=str(video), state_path=str(state), spans_path=str(spans), oracle_success=True,
            backend="kinematic_mock" if is_mock else "maniskill", is_mock=is_mock,
            script_sha256="ab" * 32, seed=seed, n_frames=5, fps=30.0,
        )

    mod.run_script = run_script  # type: ignore[attr-defined]
    mod.calls = calls  # type: ignore[attr-defined]
    return mod


def _install_fakes(monkeypatch: pytest.MonkeyPatch, tmp: Path, *, verdict: Verdict = Verdict.PASS, crash: bool = False, is_mock: bool = True) -> types.ModuleType:
    runner = _fake_runner(tmp, crash=crash, is_mock=is_mock)
    monkeypatch.setitem(sys.modules, "Kodiac_robotics.sim.runner", runner)

    def fake_open_clip(ref: Any) -> Clip:
        return Clip(ref=ref, path_h264=str(ref.uri), fps=30.0, n_frames=5, width=512, height=512, sha256="cd" * 32)

    monkeypatch.setattr("Kodiac_robotics.io.clip.open_clip", fake_open_clip)

    def fake_run(test: Any, clip: Any, mode: str = "full", tracks: Any = None, output_dir: Path | None = None, **kw: Any) -> RunResult:
        assert tracks is not None and set(tracks) >= {"cubeA", "cubeB", "gripper"}
        assert all(len(t.frames) == clip.n_frames for t in tracks.values())
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        trace = out / "trace.jsonl"
        trace.write_text("", encoding="utf-8")
        reasons = [ReasonCode.NOT_VISIBLE] if verdict == Verdict.CANT_TELL else []
        steps = [
            StepResult(index=1, name="grasp", verdict=Verdict.PASS),
            StepResult(index=2, name="place", verdict=None if verdict == Verdict.PASS else verdict, frame=3, t_s=0.1),
        ]
        return RunResult(
            run_id=NONCE, test_name="stackcube", test_sha256="1" * 64, config_sha256="0" * 64, clip=clip.ref,
            verdict=verdict, exit_code={Verdict.PASS: 0, Verdict.FAIL: 1}.get(verdict, 2), steps=steps, reasons=reasons,
            badges=["[REPLAY: CACHED SAM 3.1 TRACKS]"], backends={"perception": "cached_replay"}, nonce=NONCE,
            is_fixture=True, trace_path=str(trace), card_path=None, created_at="2026-11-02T00:00:00+00:00",
        )

    monkeypatch.setattr(importlib.import_module("Kodiac_robotics.pipeline.run"), "run", fake_run)
    return runner


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "examples" / "sim").mkdir(parents=True)
    (tmp_path / "examples" / "sim" / "pick_place.py").write_text("def run(robot):\n    pass\n", encoding="utf-8")
    (tmp_path / "stackcube.green").write_text((REPO / "examples" / "stackcube.green").read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def _req(**kw: Any) -> VerifyRequest:
    base: dict[str, Any] = {"test": "stackcube.green", "sim_script": "examples/sim/pick_place.py", "seed": 3}
    base.update(kw)
    return VerifyRequest(**base)


# ---------------------------------------------------------------- registration
def test_tool_registered_with_schema_equal_to_verify_request() -> None:
    server = mcp_server.build_server()
    assert server.name == "Kodiac"
    tools = asyncio.run(server.list_tools())
    assert [t.name for t in tools] == ["verify"]
    ref = VerifyRequest.model_json_schema()
    schema = tools[0].inputSchema
    assert schema["properties"] == ref["properties"]
    assert schema.get("required") == ref.get("required")


def test_tool_call_through_mcp_server_returns_structured_payload(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch, project)
    server = mcp_server.build_server()
    out = asyncio.run(server.call_tool("verify", {"test": "stackcube.green", "sim_script": "examples/sim/pick_place.py", "seed": 1}))
    structured = out[1] if isinstance(out, tuple) else out
    assert structured["verdict"] == "PASS"
    assert structured["nonce"] == NONCE


# ---------------------------------------------------------------- success path + honesty labels
def test_verify_pass_writes_last_verdict_with_nonce_and_honest_labels(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _install_fakes(monkeypatch, project)
    out = mcp_server.verify(_req())
    assert out["verdict"] == "PASS" and out["exit_code"] == 0
    assert runner.calls == [(project / "examples/sim/pick_place.py", 3)]
    last = json.loads((project / ".Kodiac" / "last_verdict.json").read_text(encoding="utf-8"))
    assert last["nonce"] == NONCE == out["nonce"]
    assert RunResult.model_validate(last).verdict == Verdict.PASS  # still a valid RunResult
    assert "[REPLAY: CACHED SAM 3.1 TRACKS]" not in out["badges"]
    assert mcp_server.BADGE_SIM_STATE in out["badges"] and mcp_server.BADGE_MOCK in out["badges"]
    assert out["evidence_type"] == "sim_state_tracks" and out["is_mock"] is True
    assert out["backends"]["perception"] == "sim_state_projection"
    assert "oracle" not in json.dumps(out).lower()
    assert out["blame"] is None and out["blame_status"].startswith("not_applicable")
    assert Path(out["evidence"]["trace"]).is_file() and Path(out["evidence"]["video"]).is_file()
    assert "PASS" in out["message"] and "[MOCK SIMULATION]" in out["message"]


def test_non_mock_backend_has_no_mock_badge(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch, project, is_mock=False)
    out = mcp_server.verify(_req())
    assert mcp_server.BADGE_MOCK not in out["badges"] and out["is_mock"] is False


def test_fail_without_blame_module_reports_measured_failure_and_null_blame(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch, project, verdict=Verdict.FAIL)
    monkeypatch.setattr("Kodiac_robotics.blame.blame_from_run", None, raising=False)
    import Kodiac_robotics.blame as blame_pkg

    monkeypatch.delattr(blame_pkg, "blame_from_run", raising=False)
    out = mcp_server.verify(_req())
    assert out["verdict"] == "FAIL" and out["exit_code"] == 1
    assert out["blame"] is None and out["hint"] is None
    assert out["blame_status"].startswith(("unavailable", "failed", "no_blame"))
    assert out["failure"]["step"] == "place" and out["failure"]["step_index"] == 2
    assert out["message"].startswith("FAIL at step 2 (place)")


def test_cant_tell_is_passed_through_not_guessed(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch, project, verdict=Verdict.CANT_TELL)
    out = mcp_server.verify(_req())
    assert out["verdict"] == "CANT_TELL" and out["reasons"] == ["not_visible"]
    assert "didn't guess" in out["message"] or "did not guess" in out["message"]


def test_blame_and_hint_included_when_blame_module_provides_them(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from Kodiac_robotics.contracts.core import Blame, FactTable, Hint

    _install_fakes(monkeypatch, project, verdict=Verdict.FAIL)
    seen: dict[str, Any] = {}

    def fake_blame(result: RunResult, test: Any, pred_frames: Any, fps: float, **kw: Any) -> Blame:
        seen["spans"] = kw.get("spans")
        seen["kw"] = sorted(kw)
        seen["fps"] = fps
        ft = FactTable(
            t_star_s=0.1, frame=3, fps=30.0, sigma_frames=0.5, step_index=2, step_name="place", literal="on(cubeA, cubeB)",
            transition="T->F", facts={"xy_offset_cm": {"value": 5.0, "sigma": 0.4, "unit": "cm"}},
        )
        return Blame(facts=ft, summary="Cube A left the gripper at t*=0.10 s.", summary_source="template",
                     hint=Hint(variable="gripper.open timing", move="after arm.move_to", basis="margin"))

    import Kodiac_robotics.blame as blame_pkg

    monkeypatch.setattr(blame_pkg, "blame_from_run", fake_blame, raising=False)
    out = mcp_server.verify(_req())
    assert out["blame"]["summary"].startswith("Cube A left")
    assert out["blame_status"] == "ok" and out["hint"]["variable"] == "gripper.open timing"
    assert len(seen["spans"]) == 1 and seen["spans"][0].code == "robot.gripper.open()"
    assert {"spans", "code_locator", "hint_fn"} <= set(seen["kw"])
    assert "Hint: change gripper.open timing" in out["message"]


def test_blame_exception_is_swallowed_into_status(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch, project, verdict=Verdict.FAIL)
    import Kodiac_robotics.blame as blame_pkg

    def bad(*a: Any, **k: Any) -> None:
        raise ValueError("kaput")

    monkeypatch.setattr(blame_pkg, "blame_from_run", bad, raising=False)
    out = mcp_server.verify(_req())
    assert out["verdict"] == "FAIL" and out["blame"] is None and out["blame_status"].startswith("failed: ValueError")


# ---------------------------------------------------------------- structured errors
@pytest.mark.parametrize(
    ("kw", "code"),
    [
        ({"test": "nope.green"}, "test_not_found"),
        ({"sim_script": None}, "missing_input"),
        ({"clip": "x.mp4"}, "ambiguous_input"),
        ({"sim_script": "missing.py"}, "script_not_found"),
        ({"sim_script": None, "clip": "missing.mp4"}, "clip_not_found"),
    ],
)
def test_input_validation_errors_are_structured(project: Path, kw: dict[str, Any], code: str) -> None:
    out = mcp_server.verify(_req(**kw))
    assert out["verdict"] is None and out["error"]["code"] == code
    assert "Traceback" not in json.dumps(out)


def test_unparsable_test_is_structured_error(project: Path) -> None:
    (project / "bad.green").write_text("this is not a green test\n", encoding="utf-8")
    out = mcp_server.verify(_req(test="bad.green"))
    assert out["error"]["code"] == "test_invalid"


def test_empty_test_is_rejected_because_it_would_pass_vacuously(project: Path) -> None:
    (project / "empty.green").write_text("# nothing here\n", encoding="utf-8")
    out = mcp_server.verify(_req(test="empty.green"))
    assert out["error"]["code"] == "test_invalid" and "no steps" in out["error"]["message"]


def test_sim_crash_returns_structured_error_without_traceback(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch, project, crash=True)
    out = mcp_server.verify(_req())
    assert out["error"]["code"] == "sim_failed" and "boom inside" in out["error"]["message"]
    assert "Traceback" not in json.dumps(out)
    assert not (project / ".Kodiac" / "last_verdict.json").exists()


def test_tool_wrapper_turns_pydantic_error_into_structured_error() -> None:
    server = mcp_server.build_server()
    tool = server._tool_manager.get_tool("verify")
    assert tool is not None
    out = tool.fn(test="x.green", seed="not-an-int")  # type: ignore[arg-type]
    assert out["error"]["code"] == "invalid_request"


def test_verify_never_raises_on_internal_error(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fakes(monkeypatch, project)

    def explode(*a: Any, **k: Any) -> None:
        raise OSError("disk on fire")

    monkeypatch.setattr(mcp_server, "tracks_from_state", explode)
    out = mcp_server.verify(_req())
    assert out["error"]["code"] == "internal_error" and "disk on fire" in out["error"]["message"]


def test_stdout_is_not_polluted(project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _install_fakes(monkeypatch, project)
    runner = sys.modules["Kodiac_robotics.sim.runner"]
    orig = runner.run_script

    def noisy(*a: Any, **k: Any) -> Any:
        print("library chatter that would corrupt MCP stdio")
        return orig(*a, **k)

    monkeypatch.setattr(runner, "run_script", noisy)
    mcp_server.verify(_req())
    cap = capsys.readouterr()
    assert cap.out == "" and "library chatter" in cap.err


# ---------------------------------------------------------------- fresh / cache
def test_fresh_false_reuses_labelled_cache_and_fresh_true_reruns(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _install_fakes(monkeypatch, project)
    first = mcp_server.verify(_req())
    cached = mcp_server.verify(_req(fresh=False))
    assert cached["cached"] is True and cached["nonce"] == first["nonce"]
    assert "[CACHED VERDICT: fresh=false]" in cached["badges"]
    assert len(runner.calls) == 1
    mcp_server.verify(_req(fresh=True))
    assert len(runner.calls) == 2
    # editing the script invalidates the cache key
    (project / "examples/sim/pick_place.py").write_text("def run(robot):\n    robot.wait(1)\n", encoding="utf-8")
    mcp_server.verify(_req(fresh=False))
    assert len(runner.calls) == 3


# ---------------------------------------------------------------- helpers
def test_tracks_from_state_covers_every_clip_frame_and_pads_short_state(tmp_path: Path) -> None:
    obs = np.zeros((4, 24), dtype=np.float32)
    obs[:, 2] = 0.3
    obs[:, 8:11] = [0.05, 0.0, 0.02]
    obs[:, 15:18] = [0.10, 0.0, 0.02]
    p = tmp_path / "s.state.npz"
    np.savez(p, obs_state=obs, cam_K=np.array([[400, 0, 256], [0, 400, 256], [0, 0, 1]], dtype=np.float32), cam_extrinsic=np.eye(4, dtype=np.float32))
    tracks, K, ext = mcp_server._local_tracks_from_state(p, n_frames=9, height=512, width=512)
    assert set(tracks) == {"gripper", "cubeA", "cubeB"}
    for t in tracks.values():
        assert sorted(t.frames) == list(range(9))
        assert t.frames[8].rle_size == (512, 512)
    assert K.shape == (3, 3) and ext.shape == (4, 4)


def test_load_pred_frames_roundtrip(tmp_path: Path) -> None:
    from Kodiac_robotics.contracts.core import Component, PredFrame, Tri
    from Kodiac_robotics.engine.trace import TraceWriter

    comp = Component(name="on.align_xy", value=1.0, threshold=3.3, margin=2.3, sigma=0.2, unit="cm", tri=Tri.T)
    p = tmp_path / "trace.jsonl"
    with TraceWriter(p) as w:
        for f in range(3):
            w.write_pred_frame(f, "on(cubeA,cubeB)", PredFrame(frame=f, atom_key="on(cubeA,cubeB)", tri=Tri.T, components=[comp], trace_id=f"t{f}"))
    frames = mcp_server.load_pred_frames(p)
    assert list(frames) == ["on(cubeA,cubeB)"] and [pf.frame for pf in frames["on(cubeA,cubeB)"]] == [0, 1, 2]
    assert frames["on(cubeA,cubeB)"][0].components[0].sigma == 0.2


def test_load_spans_tolerates_missing_and_garbage(tmp_path: Path) -> None:
    assert mcp_server.load_spans(None) == []
    assert mcp_server.load_spans(tmp_path / "none.jsonl") == []
    bad = tmp_path / "bad.jsonl"
    bad.write_text("{not json\n", encoding="utf-8")
    assert mcp_server.load_spans(bad) == []


# ---------------------------------------------------------------- real integration (needs T04's runner)
def _runner_available() -> bool:
    try:
        import Kodiac_robotics.sim.runner  # noqa: F401
    except ImportError:
        return False
    return not hasattr(sys.modules["Kodiac_robotics.sim.runner"], "calls")


needs_runner = pytest.mark.skipif(not _runner_available(), reason="T04 sim.runner not landed yet")


@pytest.fixture()
def real_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import shutil

    (tmp_path / "examples" / "sim").mkdir(parents=True)
    shutil.copy(REPO / "examples" / "sim" / "pick_place.py", tmp_path / "examples" / "sim" / "pick_place.py")
    shutil.copy(REPO / "examples" / "stackcube.green", tmp_path / "stackcube.green")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@needs_runner
@pytest.mark.slow
def test_integration_correct_script_passes(real_project: Path) -> None:
    out = mcp_server.verify(VerifyRequest(test="stackcube.green", sim_script="examples/sim/pick_place.py", seed=0))
    assert out.get("error") is None, out
    assert out["verdict"] == "PASS", out["message"]
    assert out["is_mock"] is True and mcp_server.BADGE_MOCK in out["badges"]
    assert json.loads((real_project / ".Kodiac" / "last_verdict.json").read_text(encoding="utf-8"))["nonce"] == out["nonce"]


@needs_runner
@pytest.mark.slow
def test_integration_b01_script_fails_with_measured_failure(real_project: Path) -> None:
    from Kodiac_robotics.proof.loop_eval import inject_bug

    script = real_project / "examples" / "sim" / "pick_place.py"
    inject_bug(script, "B01", REPO / "examples" / "sim" / "bugs" / "B01.patch")
    out = mcp_server.verify(VerifyRequest(test="stackcube.green", sim_script="examples/sim/pick_place.py", seed=0))
    assert out.get("error") is None, out
    assert out["verdict"] == "FAIL", out["message"]
    assert out["failure"] is not None and out["failure"]["decisive"]
    assert out["blame_status"]
    if out["blame"] is not None:  # blame/hint only when T01/T03 provide them
        assert out["blame"]["facts"]["t_star_s"] >= 0
