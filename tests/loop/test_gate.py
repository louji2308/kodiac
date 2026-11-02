"""Anti-cheat tests for the done-gate (ARCHITECTURE KD-11, §5.5; T04).

Ground truths: the reference `examples/sim/pick_place.py` must PASS; its B01 (early release) copy must be refused with
blame. Every attack below must fail closed. Everything runs on KinematicMockEnv: [MOCK SIMULATION], not SAPIEN physics,
graded on tracks projected from the gate's own replayed sim state (not perception).

`KODIAC_WRITE_GATE_ARTIFACT=1` additionally writes `artifacts/p07/gate_refusals.json` (the recorded refusals) and runs
the B01-B10 gate matrix.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from Kodiac_robotics.contracts.core import ObjectDecl
from Kodiac_robotics.geometry.scale import TierAScaleModel
from Kodiac_robotics.loop import gate, pins
from Kodiac_robotics.loop.gate import (
    SYNTHETIC_TRACKS_BADGE,
    GateError,
    gate_check,
    gate_init,
    grade_sim_run,
    provenance_problems,
    tracks_from_state,
)
from Kodiac_robotics.sim.runner import MOCK_LABEL, resolve_backend, run_script_with_digests

REPO_ROOT = Path(__file__).resolve().parents[2]
PICK_PLACE = REPO_ROOT / "examples" / "sim" / "pick_place.py"
STACKCUBE = REPO_ROOT / "examples" / "stackcube.green"
ARTIFACT = REPO_ROOT / "artifacts" / "p07" / "gate_refusals.json"
WRITE_ENV = "KODIAC_WRITE_GATE_ARTIFACT"
GENERATING_COMMAND = (
    "$env:KODIAC_WRITE_GATE_ARTIFACT='1'; .venv\\Scripts\\python.exe -m pytest tests/loop/test_gate.py -q "
    "-p no:cacheprovider --basetemp=.cache\\pt_t04_artifact"
)
_SIG = "def execute_pick_place(robot: RobotController, bug_id: str | None = None)"
SCRIPT_REL = Path("examples/sim/pick_place.py")
TEST_REL = Path("tests/stackcube.green")

_RECORDS: list[dict[str, Any]] = []
_BUG_MATRIX: list[dict[str, Any]] = []


def pick_place_source(bug: str | None = None) -> str:
    src = PICK_PLACE.read_text(encoding="utf-8")
    assert src.count(_SIG) == 1, "pick_place.py signature changed; update the bug-copy helper"
    return src if bug is None else src.replace(_SIG, _SIG.replace("= None", f'= "{bug}"'))


def _scrub(text: str) -> str:
    """Keep machine-specific absolute paths (and the user name in them) out of the committed artifact."""
    for root, label in ((REPO_ROOT, "<repo>"), (Path(tempfile.gettempdir()), "<tmp>"), (Path.home(), "~")):
        for variant in {str(root), root.as_posix()}:
            text = text.replace(variant, label)
    return text


def record(attack: str, description: str, code: int, message: str) -> None:
    _RECORDS.append(
        {
            "attack": attack,
            "description": description,
            "exit_code": code,
            "stderr_first_line": _scrub(message.splitlines()[0]) if message else "",
            "backend": "kinematic_mock",
            "is_mock": True,
        }
    )


@pytest.fixture(scope="module", autouse=True)
def _artifact_writer() -> Any:
    yield
    if os.environ.get(WRITE_ENV) != "1" or not _RECORDS:
        return
    assert resolve_backend("auto") == "kinematic_mock", "artifact labels assume the kinematic mock backend"
    payload = {
        "schema": "kodiac.gate_refusals/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": GENERATING_COMMAND,
        "backend": "kinematic_mock",
        "is_mock": True,
        "label": MOCK_LABEL,
        "evidence_type": "kinematic_mock_replay + synthetic tracks projected from sim state (not perception)",
        "test": "examples/stackcube.green (copied into a temp workspace)",
        "script": "examples/sim/pick_place.py copies; bug copies flip the default bug_id of execute_pick_place",
        "note": (
            "Recorded by the test suite against temporary workspaces. Exit 2 = stop blocked, 0 = stop allowed. "
            "The privileged oracle is never part of the gate decision; bug_matrix lists it only as a cross-check."
        ),
        "attacks": _RECORDS,
        "bug_matrix": _BUG_MATRIX,
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@pytest.fixture
def gate_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "gate_home"
    monkeypatch.setenv(pins.GATE_HOME_ENV, str(home))
    for var in pins.ENV_FILE_VARS:
        monkeypatch.delenv(var, raising=False)
    return home


@pytest.fixture
def ws(tmp_path: Path, gate_home: Path) -> Path:
    w = tmp_path / "ws"
    (w / "examples" / "sim").mkdir(parents=True)
    (w / "tests").mkdir()
    (w / TEST_REL).write_bytes(STACKCUBE.read_bytes())
    (w / SCRIPT_REL).write_text(pick_place_source(), encoding="utf-8")
    return w


@pytest.fixture(scope="module")
def correct_episode(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """One real run of the correct script, graded the gate's way (shared by the cheap tests)."""
    base = tmp_path_factory.mktemp("correct_episode")
    script = base / "elsewhere" / "pick_place.py"
    script.parent.mkdir(parents=True)
    script.write_text(pick_place_source(), encoding="utf-8")
    sim, digests = run_script_with_digests(script, 0, base / "sim")
    test_copy = base / "stackcube.green"
    test_copy.write_bytes(STACKCUBE.read_bytes())
    result = grade_sim_run(test_copy, sim, base / "run", digests=digests)
    return {"script": script, "sim": sim, "digests": digests, "result": result}


def set_script(ws: Path, source: str) -> None:
    (ws / SCRIPT_REL).write_text(source, encoding="utf-8")


def init(ws: Path, max_blocks: int = 8) -> None:
    gate_init(ws, TEST_REL, SCRIPT_REL, seed=0, max_blocks=max_blocks)


def blocks(ws: Path) -> int:
    loaded = pins.load_pins(ws)
    assert loaded is not None
    return loaded[0].blocks


def edit_test(ws: Path) -> None:
    p = ws / TEST_REL
    p.write_text(p.read_text(encoding="utf-8").replace("align_xy_cm<=3.33", "align_xy_cm<=30"), encoding="utf-8")


# ==============================================================================
# Ground truths
# ==============================================================================


def test_no_init_state_allows_stop(ws: Path) -> None:
    code, msg = gate_check(ws, {"stop_hook_active": False})
    assert code == 0 and "not gating" in msg
    assert not (ws / ".Kodiac" / "gate_runs").exists()
    record("no_init", "workspace never initialised with `Kodiac gate --init`: unrelated sessions are not blocked", code, msg)


def test_b01_is_refused_with_blame_and_cached_pass_from_another_script_is_ignored(
    ws: Path, correct_episode: dict[str, Any]
) -> None:
    set_script(ws, pick_place_source("B01"))
    init(ws)
    # The agent "fixed" a different file and cached a genuine PASS for it, plus a hand-made PASS verdict file.
    (ws / "examples" / "sim" / "pick_place_fixed.py").write_text(pick_place_source(), encoding="utf-8")
    (ws / ".Kodiac").mkdir(exist_ok=True)
    genuine_pass = correct_episode["result"]
    assert genuine_pass.verdict.value == "PASS"
    (ws / ".Kodiac" / "last_verdict.json").write_text(genuine_pass.model_dump_json(indent=2), encoding="utf-8")
    (ws / "runs" / genuine_pass.run_id).mkdir(parents=True)
    (ws / "runs" / genuine_pass.run_id / "result.json").write_text(genuine_pass.model_dump_json(), encoding="utf-8")

    code, msg = gate_check(ws, None)

    assert code == 2
    first = msg.splitlines()[0]
    assert first.startswith("GATE BLOCKED [MOCK SIMULATION]: stackcube FAIL on a fresh re-run of examples/sim/pick_place.py")
    assert "goal NOT verified" in first
    assert "step 2 place: FAIL" in msg
    assert "blame:" in msg and "code: " in msg and "pick_place.py:" in msg
    assert MOCK_LABEL in msg and "synthetic from sim state" in msg
    assert "blocks 1/8" in msg and blocks(ws) == 1
    # The fabricated cache was never touched or trusted.
    assert json.loads((ws / ".Kodiac" / "last_verdict.json").read_text(encoding="utf-8"))["run_id"] == genuine_pass.run_id
    record(
        "b01_with_cached_pass_from_other_script",
        "pinned script is the B01 (early release) copy; .Kodiac/last_verdict.json and runs/<id>/result.json hold a "
        "genuine PASS earned by a different, correct script (pick_place_fixed.py): ignored, the gate re-runs the pinned "
        "script and refuses with blame",
        code,
        msg,
    )


def test_correct_script_passes_then_a_code_edit_is_refused_even_with_stop_hook_active(ws: Path) -> None:
    init(ws)
    code, msg = gate_check(ws, None)
    assert code == 0, msg
    assert msg.splitlines()[0].startswith("GATE PASS [MOCK SIMULATION]: stackcube PASS on a fresh re-run")
    loaded = pins.load_pins(ws)
    assert loaded is not None and loaded[0].blocks == 0 and loaded[0].last_nonce
    assert loaded[1]["last_result"]["oracle_success_crosscheck"] is True  # stored outside the workspace only
    assert "oracle" not in msg.lower()
    record("correct_script_ground_truth", "reference pick_place.py: the gate allows the stop (PASS on mock)", code, msg)

    set_script(ws, pick_place_source("B01"))
    code, msg = gate_check(ws, {"stop_hook_active": True})
    assert code == 2
    assert msg.splitlines()[0].startswith("GATE BLOCKED [MOCK SIMULATION]: stackcube FAIL")
    assert blocks(ws) == 1
    record(
        "stale_pass_after_code_edit_with_stop_hook_active",
        "after a PASS the script is edited back to B01 and the hook says stop_hook_active=true: no stale PASS, no "
        "auto-pass; fresh re-run refuses",
        code,
        msg,
    )


# ==============================================================================
# Pinned inputs
# ==============================================================================


def test_modified_test_is_refused_without_running_the_sim(ws: Path) -> None:
    init(ws)
    edit_test(ws)
    code, msg = gate_check(ws, None)
    assert code == 2
    assert msg.splitlines()[0].startswith("GATE BLOCKED [MOCK SIMULATION]: test modified since `Kodiac gate --init`")
    assert "tests/stackcube.green" in msg and blocks(ws) == 1
    assert not (ws / ".Kodiac" / "gate_runs").exists()
    record("test_modified", "agent loosened align_xy_cm<=3.33 to <=30 in the pinned .green", code, msg)


def test_modified_threshold_config_is_refused(ws: Path) -> None:
    init(ws)
    lock = ws / "tests" / "stackcube.green.lock"
    lock.write_text('{"slack": {"align_xy_cm": 30}}', encoding="utf-8")
    code, msg = gate_check(ws, None)
    assert code == 2 and "config modified" in msg.splitlines()[0] and "stackcube.green.lock" in msg
    record("config_modified_lock", "agent created/edited the .green.lock threshold sidecar after --init", code, msg)

    lock.unlink()
    (ws / "Kodiac.toml").write_text("[thresholds]\nalign_xy_cm = 30\n", encoding="utf-8")
    code, msg = gate_check(ws, None)
    assert code == 2 and "config modified" in msg.splitlines()[0] and "Kodiac.toml" in msg
    assert blocks(ws) == 2
    record("config_modified_toml", "agent added a Kodiac.toml threshold override after --init", code, msg)


def test_engine_source_edit_is_refused(ws: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    copy_root = tmp_path / "pkg_copy"
    for p in pins.ENGINE_ROOT.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        dst = copy_root / p.relative_to(pins.ENGINE_ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(p.read_bytes())
    monkeypatch.setattr(pins, "ENGINE_ROOT", copy_root)
    init(ws)
    on_py = copy_root / "predicates" / "on.py"
    on_py.write_text(on_py.read_text(encoding="utf-8") + "\n# agent edit: always satisfied\n", encoding="utf-8")
    code, msg = gate_check(ws, None)
    assert code == 2 and "Kodiac engine source modified" in msg.splitlines()[0]
    record("engine_source_modified", "agent edited the grader's own predicate source (predicates/on.py)", code, msg)


def test_pin_files_inside_the_workspace_have_no_effect(ws: Path) -> None:
    init(ws)
    real_pin = pins.pin_path(ws)
    edit_test(ws)
    new_sha = pins.file_sha256(ws / TEST_REL)
    # Fake mirror state and a fully re-digested fake pin file inside the workspace, plus a redirected marker.
    payload = json.loads(real_pin.read_text(encoding="utf-8"))
    payload["test"]["sha256"] = new_sha
    payload["state"]["pinned_test_sha256"] = new_sha
    payload["state"]["blocks"] = 0
    payload["digest"] = pins._digest(payload)
    fake_dir = ws / ".config" / "Kodiac" / "gates"
    fake_dir.mkdir(parents=True)
    (fake_dir / real_pin.name).write_text(json.dumps(payload), encoding="utf-8")
    (ws / ".Kodiac" / "gate_state.json").write_text(json.dumps({"state": payload["state"]}), encoding="utf-8")
    marker = json.loads(pins.marker_path(ws).read_text(encoding="utf-8"))
    marker["pin_path"] = str(fake_dir / real_pin.name)
    pins.marker_path(ws).write_text(json.dumps(marker), encoding="utf-8")

    code, msg = gate_check(ws, None)
    assert code == 2 and "test modified" in msg.splitlines()[0]
    code, msg = gate_check(ws, None)
    assert code == 2 and blocks(ws) == 2  # authoritative counter lives outside the workspace
    record(
        "pin_file_edited_inside_workspace",
        "agent edited the test and planted a re-digested pin file + gate_state.json inside the workspace: no effect",
        code,
        msg,
    )


def test_tampered_corrupt_or_missing_pins_fail_closed(ws: Path) -> None:
    init(ws)
    real_pin = pins.pin_path(ws)
    original = real_pin.read_text(encoding="utf-8")

    payload = json.loads(original)
    payload["test"]["sha256"] = "0" * 64
    payload["state"]["pinned_test_sha256"] = "0" * 64
    real_pin.write_text(json.dumps(payload), encoding="utf-8")
    code, msg = gate_check(ws, None)
    assert code == 2 and msg.startswith("GATE ERROR:") and "digest mismatch" in msg
    record("pin_file_edited_outside_workspace_naively", "pinned sha edited without the self-digest", code, msg)

    real_pin.write_text("{not json", encoding="utf-8")
    code, msg = gate_check(ws, None)
    assert code == 2 and msg.startswith("GATE ERROR:") and "not valid JSON" in msg
    record("pin_file_corrupt", "pin file overwritten with garbage", code, msg)

    real_pin.unlink()
    code, msg = gate_check(ws, None)
    assert code == 2 and msg.startswith("GATE ERROR:") and "pin file missing" in msg
    record("pin_file_deleted", "pin file deleted while the workspace marker remains", code, msg)

    # Documented limit: deleting both the pin and the workspace marker is indistinguishable from "never initialised".
    pins.marker_path(ws).unlink()
    code, msg = gate_check(ws, None)
    assert code == 0 and "not gating" in msg


def test_missing_or_corrupt_env_file_fails_closed(ws: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / "secrets" / "kodiac.env"
    env_file.parent.mkdir()
    secret = "-".join(("sk", "very", "secret", "value", "123"))  # synthetic, not a credential
    env_file.write_text(f"# keys\nMODEL_API_KEY={secret}\n", encoding="utf-8")
    monkeypatch.setenv("KODIAC_ENV_FILE", str(env_file))
    init(ws)
    monkeypatch.delenv("KODIAC_ENV_FILE")  # hooks run with a cleared env: the path pinned at --init is used

    env_file.write_text(f"MODEL_API_KEY={secret}\nthis line is {secret} not an assignment\n", encoding="utf-8")
    code, msg = gate_check(ws, None)
    assert code == 2 and msg.startswith("GATE ERROR:") and "line 2 is not KEY=VALUE" in msg
    assert secret not in msg
    record("env_file_corrupt", "pinned KODIAC_ENV_FILE has an unparsable line (value never echoed)", code, msg)

    env_file.unlink()
    code, msg = gate_check(ws, None)
    assert code == 2 and msg.startswith("GATE ERROR:") and "env file not found" in msg
    assert blocks(ws) == 2
    record("env_file_missing", "pinned KODIAC_ENV_FILE deleted", code, msg)


def test_max_blocks_exhausts_with_marker_and_exit_0(ws: Path) -> None:
    init(ws, max_blocks=2)
    edit_test(ws)
    assert gate_check(ws, None)[0] == 2
    assert gate_check(ws, None)[0] == 2
    code, msg = gate_check(ws, {"stop_hook_active": True})
    assert code == 0 and msg.startswith("GATE EXHAUSTED: goal NOT verified")
    marker = ws / ".Kodiac" / "gate_exhausted"
    assert marker.is_file() and json.loads(marker.read_text(encoding="utf-8"))["verified"] is False
    assert gate_check(ws, None)[0] == 0 and blocks(ws) == 2
    record("max_blocks_exhausted", "two refusals with max_blocks=2: the stop is allowed, labelled NOT verified", code, msg)


# ==============================================================================
# Script-side attacks
# ==============================================================================


def test_sim_crash_fails_closed(ws: Path) -> None:
    init(ws)
    set_script(ws, "def run(robot):\n    robot.wait(0.1)\n    raise RuntimeError('controller exploded')\n")
    code, msg = gate_check(ws, None)
    assert code == 2 and msg.startswith("GATE ERROR: sim run failed") and "controller exploded" in msg
    assert blocks(ws) == 1
    record("sim_crash", "pinned script raises inside run(robot)", code, msg)


def test_teleporting_the_arm_fails_closed(ws: Path) -> None:
    init(ws)
    set_script(ws, "def run(robot):\n    robot.arm.move_to([0.08, 0.22, 0.06], steps=1)\n    robot.gripper.open()\n")
    code, msg = gate_check(ws, None)
    assert code == 2 and msg.startswith("GATE ERROR: sim run failed") and "teleporting" in msg
    record("teleport_arm", "script jumps the end effector across the table in one control step", code, msg)


EVIL_SCRIPT = '''
import json, os
from pathlib import Path
import Kodiac_robotics.sim.env as sim_env
import Kodiac_robotics.pipeline.run as pipeline_run
import Kodiac_robotics.loop.gate as gate

def run(robot):
    sim_env.KinematicMockEnv.oracle_success = lambda self: True
    pipeline_run.run = lambda *a, **k: None
    gate.gate_check = lambda *a, **k: (0, "GATE PASS")
    os.environ["KODIAC_GATE_HOME"] = "/nonexistent"
    os.environ["KODIAC_FORCE_PASS"] = "1"
    ws = Path(__file__).resolve().parents[2]
    (ws / ".Kodiac").mkdir(exist_ok=True)
    (ws / ".Kodiac" / "last_verdict.json").write_text(json.dumps({"verdict": "PASS", "exit_code": 0}))
    (ws / "PASS").write_text("PASS")
    robot.wait(0.3)
    s = robot.env.privileged_state()
    robot.env.cubeA_pos[:] = [s.cubeB_pose[0], s.cubeB_pose[1], 0.06]
    robot.env.gripper_width = 0.08
    robot.env.release_step = 0
'''


def test_script_that_stubs_the_sim_oracle_and_verdict_path_is_refused(ws: Path) -> None:
    init(ws)
    set_script(ws, EVIL_SCRIPT)
    code, msg = gate_check(ws, None)
    assert code == 2
    first = msg.splitlines()[0]
    assert first.startswith("GATE BLOCKED [MOCK SIMULATION]: stackcube") and "goal NOT verified" in first
    assert (ws / "PASS").is_file()  # the script really ran and really tried
    record(
        "script_stubs_oracle_engine_gate_and_teleports_cube",
        "script monkeypatches oracle_success/pipeline.run/gate_check, sets KODIAC_* env vars, writes a PASS "
        ".Kodiac/last_verdict.json and a PASS file, then writes the cube onto the target in sim state: the gate "
        "re-simulates only the commanded actions in its own process and refuses",
        code,
        msg,
    )


# ==============================================================================
# Fail-closed guarantees: gate_check never returns 3
# ==============================================================================

_STAGES = [
    "load_pins",
    "_load_env_file",
    "current_config",
    "engine_sha256",
    "run_script_with_digests",
    "load_green_test",
    "synthetic_tracks_from_state",
    "pipeline_run",
    "grade_sim_run",
    "provenance_problems",
    "save_pins",
]


@pytest.mark.parametrize("exc", [RuntimeError("injected"), SystemExit(3), KeyboardInterrupt()], ids=["error", "exit3", "kbint"])
@pytest.mark.parametrize("stage", _STAGES)
def test_injected_failure_at_every_stage_exits_2(
    ws: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    correct_episode: dict[str, Any],
    stage: str,
    exc: BaseException,
) -> None:
    (ws / SCRIPT_REL).write_bytes(correct_episode["script"].read_bytes())
    env_file = tmp_path / "k.env"
    env_file.write_text("MODEL_API_KEY=abc12345\n", encoding="utf-8")
    monkeypatch.setenv("KODIAC_ENV_FILE", str(env_file))
    init(ws)
    monkeypatch.setattr(gate, "run_script_with_digests", lambda *a, **k: (correct_episode["sim"], correct_episode["digests"]))

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise exc

    monkeypatch.setattr(gate, stage, boom)
    code, msg = gate_check(ws, {"stop_hook_active": True})
    assert code == 2, msg
    assert msg.startswith("GATE ERROR:")
    assert "abc12345" not in msg


def test_sanity_without_injection_the_shared_episode_passes(
    ws: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, correct_episode: dict[str, Any]
) -> None:
    (ws / SCRIPT_REL).write_bytes(correct_episode["script"].read_bytes())
    init(ws)
    monkeypatch.setattr(gate, "run_script_with_digests", lambda *a, **k: (correct_episode["sim"], correct_episode["digests"]))
    monkeypatch.setattr(gate, "_append_log", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    code, msg = gate_check(ws, None)
    assert code == 0, msg  # an informational-log failure never changes the decision


@pytest.mark.parametrize("bad", [(3, "x"), (1, "x"), (None, "x")])
def test_out_of_range_exit_codes_are_mapped_to_2(monkeypatch: pytest.MonkeyPatch, ws: Path, bad: tuple[Any, str]) -> None:
    monkeypatch.setattr(gate, "_gate_check", lambda *a, **k: bad)
    code, msg = gate_check(ws, None)
    assert code == 2 and msg.startswith("GATE ERROR:")


def test_stub_episode_with_swapped_video_is_refused(
    ws: Path, monkeypatch: pytest.MonkeyPatch, correct_episode: dict[str, Any]
) -> None:
    (ws / SCRIPT_REL).write_bytes(correct_episode["script"].read_bytes())
    init(ws)
    forged = dict(correct_episode["digests"])
    forged["video"] = "f" * 64
    monkeypatch.setattr(gate, "run_script_with_digests", lambda *a, **k: (correct_episode["sim"], forged))
    code, msg = gate_check(ws, None)
    assert code == 2 and "video changed" in msg


# ==============================================================================
# Units: provenance, synthetic tracks, init validation, CLI adapter
# ==============================================================================


def test_provenance_problems_detects_every_mismatch(correct_episode: dict[str, Any]) -> None:
    result, sim, digests = correct_episode["result"], correct_episode["sim"], correct_episode["digests"]
    kw = {
        "pinned_test_sha256": result.test_sha256,
        "script_sha256_now": sim.script_sha256,
        "video_sha256_expected": digests["video"],
    }
    assert provenance_problems(result, sim, **kw) == []
    assert result.clip.source_kind == "sim"
    assert SYNTHETIC_TRACKS_BADGE in result.badges and "[MOCK SIMULATION]" in result.badges
    assert "[REPLAY: CACHED SAM 3.1 TRACKS]" not in result.badges
    assert result.backends["perception"] == "synthetic_from_sim_state" and result.is_fixture

    other_clip = result.model_copy(update={"clip": result.clip.model_copy(update={"uri": "C:/other/video.mp4"})})
    assert any("not the video" in p for p in provenance_problems(other_clip, sim, **kw))
    real_clip = result.model_copy(update={"clip": result.clip.model_copy(update={"source_kind": "real"})})
    assert any("source_kind" in p for p in provenance_problems(real_clip, sim, **kw))
    assert provenance_problems(result, sim, **{**kw, "pinned_test_sha256": "0" * 64})
    assert provenance_problems(result, sim, **{**kw, "script_sha256_now": "0" * 64})
    assert provenance_problems(result, sim, **{**kw, "video_sha256_expected": "0" * 64})


def test_synthetic_tracks_invert_exactly_through_tier_a(correct_episode: dict[str, Any]) -> None:
    sim = correct_episode["sim"]
    tracks, cam_K, cam_ext = tracks_from_state(sim.state_path, n_frames=sim.n_frames)
    state = np.load(sim.state_path)
    objects = [ObjectDecl(name="cubeA", size_cm=4), ObjectDecl(name="cubeB", size_cm=4), ObjectDecl(name="gripper")]
    scale = TierAScaleModel(cam_K, cam_ext, tracks, objects)
    worst = 0.0
    for name, key, dz in (("cubeA", "cubeA_pose", 0.02), ("cubeB", "cubeB_pose", 0.02), ("gripper", "ee_pos", 0.0)):
        assert len(tracks[name].frames) == sim.n_frames
        for f in range(0, sim.n_frames, 7):
            x, d, h, _ = scale.to_table_frame(name, f)
            truth = np.asarray(state[key][f, :3], dtype=np.float64) - np.array([0.0, 0.0, dz])
            worst = max(worst, float(np.max(np.abs(np.array([x, d, h]) / 100.0 - truth))))
    assert worst < 0.004  # < 4 mm worst case from pixel quantisation at ~0.7 m
    with pytest.raises(GateError, match="rows"):
        tracks_from_state(sim.state_path, n_frames=sim.n_frames + 1)


def test_gate_init_validates_inputs(ws: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(FileNotFoundError):
        gate_init(ws, Path("tests/missing.green"), SCRIPT_REL)
    with pytest.raises(FileNotFoundError):
        gate_init(ws, TEST_REL, Path("examples/sim/missing.py"))
    with pytest.raises(ValueError):
        gate_init(ws, TEST_REL, SCRIPT_REL, seed=-1)
    with pytest.raises(ValueError):
        gate_init(ws, TEST_REL, SCRIPT_REL, max_blocks=0)
    monkeypatch.setenv("KODIAC_ENV_FILE", str(tmp_path / "nope.env"))
    with pytest.raises(GateError, match="env file not found"):
        gate_init(ws, TEST_REL, SCRIPT_REL)
    assert pins.load_pins(ws) is None
    monkeypatch.delenv("KODIAC_ENV_FILE")
    state = gate_init(ws, TEST_REL, SCRIPT_REL, seed=3, max_blocks=5)
    assert state.blocks == 0 and state.max_blocks == 5
    pin_file = pins.pin_path(ws)
    assert ws.resolve() not in pin_file.resolve().parents  # pins live outside the workspace
    # Re-initialisation is recorded and surfaced.
    edit_test(ws)
    gate_init(ws, TEST_REL, SCRIPT_REL)
    loaded = pins.load_pins(ws)
    assert loaded is not None and len(loaded[1]["previous_pins"]) == 1


def test_cli_adapter_init_and_hook(ws: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    rc = gate.main(["--init", "--workspace", str(ws), "--test", str(TEST_REL), "--sim", str(SCRIPT_REL), "--max-blocks", "3"])
    assert rc == 0 and "gate pinned" in capsys.readouterr().out
    edit_test(ws)
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"stop_hook_active": true}'))
    rc = gate.main(["--workspace", str(ws), "--max-blocks", "0"])
    err = capsys.readouterr().err
    assert rc == 2 and err.startswith("GATE BLOCKED") and "blocks 1/3" in err  # pinned max_blocks wins
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    assert gate.main(["--workspace", str(ws)]) == 2
    assert gate.main(["--bogus-flag"]) == 2


# ==============================================================================
# B01-B10 gate matrix (artifact generation only; ~10 s per bug)
# ==============================================================================


@pytest.mark.slow
@pytest.mark.skipif(os.environ.get(WRITE_ENV) != "1", reason=f"set {WRITE_ENV}=1 to run the B01-B10 gate matrix")
@pytest.mark.parametrize("bug", [None] + [f"B{i:02d}" for i in range(1, 11)])
def test_bug_matrix_for_artifact(ws: Path, bug: str | None) -> None:
    set_script(ws, pick_place_source(bug))
    init(ws)
    code, msg = gate_check(ws, None)
    loaded = pins.load_pins(ws)
    assert loaded is not None
    last = loaded[1]["last_result"]
    _BUG_MATRIX.append(
        {
            "script": bug or "correct",
            "gate_exit_code": code,
            "verdict": last.get("verdict"),
            "oracle_success_crosscheck": last.get("oracle_success_crosscheck"),
            "honest_outcome": (
                "agree" if (code == 0) == bool(last.get("oracle_success_crosscheck")) else "DISAGREE (engine false PASS)"
                if code == 0 else "DISAGREE (gate refused an oracle success)"
            ),
            "stderr_first_line": _scrub(msg.splitlines()[0]),
            "code_location_line": next((_scrub(ln.strip()) for ln in msg.splitlines() if ln.strip().startswith("code:")), None),
        }
    )
    assert code in (0, 2)
