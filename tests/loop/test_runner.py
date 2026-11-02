"""Tests for sim.runner.run_script: isolated execution, parent-side replay, honest labels, action sanity bounds.

All episodes run on KinematicMockEnv (mani_skill is not installed): outputs are [MOCK SIMULATION], not SAPIEN physics.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from Kodiac_robotics.sim import runner
from Kodiac_robotics.sim.runner import (
    MOCK_LABEL,
    SimRunError,
    SimRunResult,
    load_spans,
    maniskill_available,
    run_script,
    run_script_with_digests,
    validate_actions,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PICK_PLACE = REPO_ROOT / "examples" / "sim" / "pick_place.py"
_SIG = "def execute_pick_place(robot: RobotController, bug_id: str | None = None)"


def write_pick_place(path: Path, bug: str | None = None) -> Path:
    """Copy the reference script; a bug copy flips the default `bug_id` so `execute_pick_place(robot)` runs the bug."""
    src = PICK_PLACE.read_text(encoding="utf-8")
    assert src.count(_SIG) == 1, "pick_place.py signature changed; update the bug-copy helper"
    if bug is not None:
        src = src.replace(_SIG, _SIG.replace("= None", f'= "{bug}"'))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(src, encoding="utf-8")
    return path


def write_script(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_correct_script_records_gradeable_mock_episode(tmp_path: Path) -> None:
    script = write_pick_place(tmp_path / "ws" / "pick_place.py")
    out = tmp_path / "out"
    result, digests = run_script_with_digests(script, 0, out)

    assert isinstance(result, SimRunResult)
    if not maniskill_available():
        assert result.backend == "kinematic_mock"
        assert result.is_mock is True
    assert result.oracle_success is True
    assert result.seed == 0 and result.fps == 30.0
    assert result.script_sha256 == runner.sha256_bytes(script.read_bytes()) == digests["script"]

    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["is_mock"] is True and meta["label"] == MOCK_LABEL
    assert meta["evidence_type"] == "kinematic_mock_replay"
    assert meta["entry_point"] == "execute_pick_place"
    assert meta["child_replay_divergence_m"] == pytest.approx(0.0, abs=1e-9)
    assert "never the gate verdict" in meta["oracle_note"]

    state = np.load(result.state_path)
    n = result.n_frames
    assert state["actions"].shape == (n - 1, 7)
    for key in ("ee_pos", "cubeA_pose", "cubeB_pose", "gripper_width", "t_s"):
        assert state[key].shape[0] == n, key
    assert bool(state["frame_aligned"]) and bool(state["camera_known"]) and bool(state["is_mock"])
    # Correct run ends with cube A resting on cube B (4 cm cubes).
    assert state["cubeA_pose"][-1, 2] == pytest.approx(state["cubeB_pose"][-1, 2] + 0.04, abs=1e-4)

    cap = cv2.VideoCapture(result.video_path)
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == n
    ok, first = cap.read()
    cap.release()
    assert ok and first.shape == (512, 512, 3)
    assert digests["video"] == runner.sha256_bytes(Path(result.video_path).read_bytes())

    spans = load_spans(result.spans_path)
    assert spans and all(s.file.endswith("pick_place.py") for s in spans)
    assert {"gripper.close", "gripper.open", "arm.move_to"} <= {s.actuation_class for s in spans}


@pytest.mark.slow
@pytest.mark.parametrize("bug", [f"B{i:02d}" for i in range(1, 11)])
def test_bug_copies_run_and_fail_the_oracle(tmp_path: Path, bug: str) -> None:
    script = write_pick_place(tmp_path / "ws" / f"pick_place_{bug}.py", bug)
    result = run_script(script, 0, tmp_path / "out", backend="kinematic_mock")
    assert result.oracle_success is False
    assert result.is_mock is True
    assert Path(result.video_path).is_file() and Path(result.state_path).is_file()


def test_script_cannot_reach_the_grader_or_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatching, state writes, fake files and env tricks inside the script do not reach the replay."""
    monkeypatch.setenv("MODEL_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("KODIAC_GATE_HOME", str(tmp_path / "pins"))
    script = write_script(
        tmp_path / "ws" / "evil.py",
        """
import json, os
from pathlib import Path
import Kodiac_robotics.sim.env as sim_env
import Kodiac_robotics.pipeline.run as pipeline_run

def run(robot):
    sim_env.KinematicMockEnv.oracle_success = lambda self: True
    pipeline_run.run = lambda *a, **k: "PASS"
    os.environ["KODIAC_FORCE_PASS"] = "1"
    Path("leaked_env.json").write_text(json.dumps(sorted(os.environ)))
    Path("verdict.json").write_text('{"verdict": "PASS"}')
    robot.wait(0.2)
    state = robot.env.privileged_state()
    robot.env.cubeA_pos[:] = [state.cubeB_pose[0], state.cubeB_pose[1], 0.06]
    robot.env.release_step = 0
""",
    )
    out = tmp_path / "out"
    result = run_script(script, 0, out)

    assert result.oracle_success is False
    state = np.load(result.state_path)
    assert state["cubeA_pose"][-1, 2] == pytest.approx(0.02, abs=1e-6)  # never left the table in the replay
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["entry_point"] == "run"
    assert meta["child_replay_divergence_m"] > 0.05  # the teleport is visible as child/replay divergence

    leaked = json.loads((out / "_child_kinematic_mock" / "leaked_env.json").read_text(encoding="utf-8"))
    assert "MODEL_API_KEY" not in leaked
    assert not [k for k in leaked if k.upper().startswith("KODIAC_") and k != "KODIAC_FORCE_PASS"]


def test_crashing_script_raises(tmp_path: Path) -> None:
    script = write_script(tmp_path / "crash.py", "def run(robot):\n    raise RuntimeError('boom at line 2')\n")
    with pytest.raises(SimRunError, match=r"crashed.*boom at line 2"):
        run_script(script, 0, tmp_path / "out")
    assert not (tmp_path / "out" / "video.mp4").exists()


def test_script_without_entry_point_raises(tmp_path: Path) -> None:
    script = write_script(tmp_path / "noentry.py", "def main(robot):\n    robot.wait(0.1)\n")
    with pytest.raises(SimRunError, match="no entry point"):
        run_script(script, 0, tmp_path / "out")


def test_script_exiting_early_raises(tmp_path: Path) -> None:
    script = write_script(tmp_path / "exit.py", "import os\ndef run(robot):\n    robot.wait(0.1)\n    os._exit(0)\n")
    with pytest.raises(SimRunError, match="no action log"):
        run_script(script, 0, tmp_path / "out")


def test_teleporting_arm_is_rejected(tmp_path: Path) -> None:
    script = write_script(
        tmp_path / "teleport.py",
        "def run(robot):\n    robot.arm.move_to([0.3, 0.4, 0.3], steps=1)\n",
    )
    with pytest.raises(SimRunError, match="teleporting"):
        run_script(script, 0, tmp_path / "out")


def test_self_modifying_script_is_rejected(tmp_path: Path) -> None:
    script = write_script(
        tmp_path / "selfmod.py",
        "from pathlib import Path\n"
        "def run(robot):\n"
        "    robot.wait(0.1)\n"
        "    p = Path(__file__)\n"
        "    p.write_text(p.read_text() + '\\n# edited during the run\\n')\n",
    )
    with pytest.raises(SimRunError, match="changed on disk"):
        run_script(script, 0, tmp_path / "out")


def test_hanging_script_is_killed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "CHILD_TIMEOUT_S", 4.0)
    script = write_script(tmp_path / "hang.py", "import time\ndef run(robot):\n    time.sleep(60)\n")
    with pytest.raises(SimRunError, match="exceeded"):
        run_script(script, 0, tmp_path / "out")


def test_bad_inputs_raise(tmp_path: Path) -> None:
    with pytest.raises(SimRunError, match="not found"):
        run_script(tmp_path / "missing.py", 0, tmp_path / "out")
    script = write_script(tmp_path / "ok.py", "def run(robot):\n    robot.wait(0.1)\n")
    with pytest.raises(SimRunError, match="seed"):
        run_script(script, -1, tmp_path / "out")
    with pytest.raises(SimRunError, match="unknown sim backend"):
        run_script(script, 0, tmp_path / "out", backend="mujoco")  # type: ignore[arg-type]


@pytest.mark.skipif(maniskill_available(), reason="ManiSkill is installed here")
def test_explicit_maniskill_without_install_fails_loudly(tmp_path: Path) -> None:
    script = write_script(tmp_path / "ok.py", "def run(robot):\n    robot.wait(0.1)\n")
    with pytest.raises(SimRunError, match="backend unavailable"):
        run_script(script, 0, tmp_path / "out", backend="maniskill")


def test_validate_actions_bounds() -> None:
    ok = np.zeros((5, 7), dtype=np.float32)
    ok[:, 0] = 0.004
    ok[:, 6] = -1.0
    assert validate_actions(ok).dtype == np.float32
    with pytest.raises(SimRunError, match="shape"):
        validate_actions(np.zeros((5, 4)))
    with pytest.raises(SimRunError, match="no robot actions"):
        validate_actions(np.zeros((0, 7)))
    with pytest.raises(SimRunError, match="NaN"):
        bad = ok.copy()
        bad[2, 1] = np.nan
        validate_actions(bad)
    with pytest.raises(SimRunError, match="gripper"):
        bad = ok.copy()
        bad[1, 6] = 5.0
        validate_actions(bad)
    with pytest.raises(SimRunError, match="limit"):
        validate_actions(np.zeros((runner.MAX_ACTIONS + 1, 7)))
    with pytest.raises(SimRunError, match="floating"):
        validate_actions(np.zeros((3, 7), dtype=np.int64))
