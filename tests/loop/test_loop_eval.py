"""Tests for proof/loop_eval.py (F42 harness). Gate and sim runner are faked: this tests the plumbing."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from Kodiac_robotics.proof import loop_eval
from Kodiac_robotics.proof.loop_eval import (
    DriverResult,
    InjectionError,
    MuseDriverUnavailable,
    SpendGuardError,
    build_report,
    inject_bug,
    muse_exec_driver,
    reference_patcher,
    run_loop_eval,
)

REPO = Path(__file__).resolve().parents[2]
SCRIPT = "examples/sim/pick_place.py"
TEST = "examples/stackcube.green"

TINY_SCRIPT = '''\
def execute_pick_place(robot, bug_id: str | None = None) -> bool:
    x = 1
    return True
'''
TINY_PATCH = """\
--- a/examples/sim/pick_place.py
+++ b/examples/sim/pick_place.py
@@ -1,3 +1,3 @@
 def execute_pick_place(robot, bug_id: str | None = None) -> bool:
-    x = 1
+    x = 2  # BUG
     return True
"""


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _buggy(script: Path) -> bool:
    text = script.read_text(encoding="utf-8")
    return "# BUG" in text or re.search(r'bug_id: str \| None = "B\d\d"', text) is not None


class _Sim(BaseModel):
    oracle_success: bool
    backend: str = "kinematic_mock"
    is_mock: bool = True


def _install_fake_gate_and_runner(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"pins": {}, "inits": [], "home_seen": []}
    gate = types.ModuleType("Kodiac_robotics.loop.gate")
    runner = types.ModuleType("Kodiac_robotics.sim.runner")

    def gate_init(workspace: Path, test: Path, sim_script: Path, seed: int = 0, max_blocks: int = 8) -> None:
        state["home_seen"].append(os.environ.get("KODIAC_GATE_HOME"))
        state["pins"][str(workspace)] = {"test": _sha(test), "script": sim_script}
        state["inits"].append((workspace, seed, max_blocks))

    def gate_check(workspace: Path, hook_payload: dict | None = None) -> tuple[int, str]:
        pin = state["pins"].get(str(workspace))
        if pin is None:
            return 0, ""
        if _sha(workspace / TEST) != pin["test"]:
            return 2, "GATE: test modified"
        if _buggy(pin["script"]):
            return 2, "GATE: verdict FAIL"
        return 0, ""

    def run_script(script: Path, seed: int, out_dir: Path, backend: str = "auto") -> _Sim:
        return _Sim(oracle_success=not _buggy(Path(script)))

    gate.gate_init, gate.gate_check = gate_init, gate_check  # type: ignore[attr-defined]
    runner.run_script = run_script  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "Kodiac_robotics.loop.gate", gate)
    monkeypatch.setitem(sys.modules, "Kodiac_robotics.sim.runner", runner)
    return state


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "examples" / "sim" / "bugs").mkdir(parents=True)
    (root / SCRIPT).write_text(TINY_SCRIPT, encoding="utf-8")
    (root / TEST).write_text("objects: [gripper]\n", encoding="utf-8")
    (root / "examples" / "sim" / "bugs" / "B01.patch").write_text(TINY_PATCH, encoding="utf-8")
    return root


def _fix_driver(ws: Path, bug: str) -> DriverResult:
    (ws / SCRIPT).write_text(TINY_SCRIPT, encoding="utf-8")
    return DriverResult(iterations=2, transcript="fixed it", driver="fake_agent")


# ------------------------------------------------------------------ bug injection
def test_inject_bug_applies_a_matching_patch(fake_repo: Path, tmp_path: Path) -> None:
    ws = tmp_path / "ws.py"
    ws.write_text(TINY_SCRIPT, encoding="utf-8")
    assert inject_bug(ws, "B01", fake_repo / "examples/sim/bugs/B01.patch") == "patch"
    assert "x = 2  # BUG" in ws.read_text(encoding="utf-8")


def test_inject_bug_falls_back_to_bug_id_pin_when_patch_does_not_fit(tmp_path: Path) -> None:
    ws = tmp_path / "ws.py"
    ws.write_text("def execute_pick_place(robot, bug_id: str | None = None) -> bool:\n    return True\n", encoding="utf-8")
    patch = tmp_path / "stale.patch"
    patch.write_text(TINY_PATCH, encoding="utf-8")
    assert inject_bug(ws, "B07", patch) == "bug_id_pin"
    assert 'bug_id: str | None = "B07"' in ws.read_text(encoding="utf-8")


def test_inject_bug_raises_when_nothing_can_be_injected(tmp_path: Path) -> None:
    ws = tmp_path / "ws.py"
    ws.write_text("def run(robot):\n    pass\n", encoding="utf-8")
    with pytest.raises(InjectionError):
        inject_bug(ws, "B01", None)


@pytest.mark.parametrize("bug", loop_eval.BUG_IDS)
def test_every_real_bug_injects_into_the_real_script_and_stays_valid_python(bug: str, tmp_path: Path) -> None:
    ws = tmp_path / "pick_place.py"
    ws.write_text((REPO / SCRIPT).read_text(encoding="utf-8"), encoding="utf-8")
    method = inject_bug(ws, bug, REPO / "examples" / "sim" / "bugs" / f"{bug}.patch")
    assert method in {"patch", "bug_id_pin"}
    text = ws.read_text(encoding="utf-8")
    compile(text, str(ws), "exec")
    assert text != (REPO / SCRIPT).read_text(encoding="utf-8")


# ------------------------------------------------------------------ harness
def test_reference_patcher_dry_run_plumbing_on_real_script(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    state = _install_fake_gate_and_runner(monkeypatch)
    out = tmp_path / "out"
    outcomes = run_loop_eval(["B01", "B05"], reference_patcher, max_iters=5, out_dir=out)
    assert [o.bug for o in outcomes] == ["B01", "B05"]
    for o in outcomes:
        assert o.fixed and o.gate_pass and o.oracle_success and o.hash_unchanged
        assert o.driver == "reference_patcher" and o.iterations == 1
        assert o.bug_manifests is True  # the injected bug really made the (fake) oracle fail first
        assert o.injection in {"patch", "bug_id_pin"} and o.is_mock is True
        text = Path(o.transcript_path).read_text(encoding="utf-8")
        assert "NOT an AI agent" in text and o.bug in text
    # workspace copies never contain the patches (no answer key for a real agent)
    assert not list((out / "workspaces" / "B01").rglob("*.patch"))
    # gate pins go to the harness-owned home and the env is restored afterwards
    assert all(h and h.endswith("gate_home") for h in state["home_seen"])
    assert "KODIAC_GATE_HOME" not in os.environ or not os.environ["KODIAC_GATE_HOME"].endswith("gate_home")
    assert all(max_blocks == 5 for _, _, max_blocks in state["inits"])


def test_unfixed_bug_is_reported_not_fixed(monkeypatch: pytest.MonkeyPatch, fake_repo: Path, tmp_path: Path) -> None:
    _install_fake_gate_and_runner(monkeypatch)

    def lazy(ws: Path, bug: str) -> DriverResult:
        return DriverResult(iterations=3, transcript="gave up", driver="lazy")

    (o,) = run_loop_eval(["B01"], lazy, out_dir=tmp_path / "o", repo_root=fake_repo)
    assert not o.fixed and not o.gate_pass and not o.oracle_success and o.hash_unchanged


def test_test_file_changed_means_not_fixed_even_if_script_is_fixed(monkeypatch: pytest.MonkeyPatch, fake_repo: Path, tmp_path: Path) -> None:
    _install_fake_gate_and_runner(monkeypatch)

    def cheater(ws: Path, bug: str) -> DriverResult:
        (ws / TEST).write_text("objects: [gripper]\n# weakened\n", encoding="utf-8")
        return _fix_driver(ws, bug)

    (o,) = run_loop_eval(["B01"], cheater, out_dir=tmp_path / "o", repo_root=fake_repo)
    assert o.oracle_success and not o.hash_unchanged and not o.gate_pass and not o.fixed
    assert "hash_unchanged: False" in Path(o.transcript_path).read_text(encoding="utf-8")


def test_new_green_file_also_counts_as_a_test_change(monkeypatch: pytest.MonkeyPatch, fake_repo: Path, tmp_path: Path) -> None:
    _install_fake_gate_and_runner(monkeypatch)

    def sneaky(ws: Path, bug: str) -> DriverResult:
        (ws / "examples" / "easy.green").write_text("objects: []\n", encoding="utf-8")
        return _fix_driver(ws, bug)

    (o,) = run_loop_eval(["B01"], sneaky, out_dir=tmp_path / "o", repo_root=fake_repo)
    assert not o.hash_unchanged and not o.fixed


def test_exceeding_max_iters_is_not_fixed(monkeypatch: pytest.MonkeyPatch, fake_repo: Path, tmp_path: Path) -> None:
    _install_fake_gate_and_runner(monkeypatch)

    def slow(ws: Path, bug: str) -> DriverResult:
        r = _fix_driver(ws, bug)
        return r.model_copy(update={"iterations": 6})

    (o,) = run_loop_eval(["B01"], slow, max_iters=5, out_dir=tmp_path / "o", repo_root=fake_repo)
    assert o.gate_pass and o.oracle_success and o.hash_unchanged and not o.fixed


def test_fixing_driver_within_budget_is_fixed(monkeypatch: pytest.MonkeyPatch, fake_repo: Path, tmp_path: Path) -> None:
    _install_fake_gate_and_runner(monkeypatch)
    (o,) = run_loop_eval(["B01"], _fix_driver, max_iters=5, out_dir=tmp_path / "o", repo_root=fake_repo)
    assert o.fixed and o.iterations == 2 and o.driver == "fake_agent" and o.injection == "patch"


def test_crashing_driver_fails_that_bug_and_eval_continues(monkeypatch: pytest.MonkeyPatch, fake_repo: Path, tmp_path: Path) -> None:
    _install_fake_gate_and_runner(monkeypatch)
    (fake_repo / "examples/sim/bugs/B02.patch").write_text(TINY_PATCH, encoding="utf-8")
    calls: list[str] = []

    def flaky(ws: Path, bug: str) -> DriverResult:
        calls.append(bug)
        if bug == "B01":
            raise RuntimeError("driver exploded")
        return _fix_driver(ws, bug)

    o1, o2 = run_loop_eval(["B01", "B02"], flaky, out_dir=tmp_path / "o", repo_root=fake_repo)
    assert calls == ["B01", "B02"] and not o1.fixed and o2.fixed
    assert "driver exploded" in Path(o1.transcript_path).read_text(encoding="utf-8")


def test_gate_exhausted_marker_is_not_a_pass(monkeypatch: pytest.MonkeyPatch, fake_repo: Path, tmp_path: Path) -> None:
    state = _install_fake_gate_and_runner(monkeypatch)
    gate = sys.modules["Kodiac_robotics.loop.gate"]

    def exhausted(workspace: Path, hook_payload: dict | None = None) -> tuple[int, str]:
        (workspace / ".Kodiac").mkdir(exist_ok=True)
        (workspace / ".Kodiac" / "gate_exhausted").write_text("x", encoding="utf-8")
        return 0, "GATE EXHAUSTED: goal NOT verified"

    monkeypatch.setattr(gate, "gate_check", exhausted)
    (o,) = run_loop_eval(["B01"], _fix_driver, out_dir=tmp_path / "o", repo_root=fake_repo)
    assert state["inits"] and not o.gate_pass and not o.fixed


# ------------------------------------------------------------------ spend guard
def test_muse_driver_refuses_without_spend_env_and_before_touching_anything(
    monkeypatch: pytest.MonkeyPatch, fake_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state = _install_fake_gate_and_runner(monkeypatch)
    monkeypatch.delenv("KODIAC_ALLOW_MUSE_SPEND", raising=False)
    out = tmp_path / "o"
    with pytest.raises(SpendGuardError, match="KODIAC_ALLOW_MUSE_SPEND=1"):
        run_loop_eval(["B01", "B02"], muse_exec_driver(5), max_iters=5, out_dir=out, repo_root=fake_repo)
    assert "up to 10 agent iterations" in capsys.readouterr().err
    assert not (out / "workspaces").exists() and state["inits"] == []


def test_spend_env_must_be_exactly_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KODIAC_ALLOW_MUSE_SPEND", "true")
    with pytest.raises(SpendGuardError):
        loop_eval.require_spend_guard(["B01"], 5)
    monkeypatch.setenv("KODIAC_ALLOW_MUSE_SPEND", "1")
    assert loop_eval.require_spend_guard(["B01"], 5) == 5


def test_muse_driver_without_command_template_is_unavailable_not_faked(
    monkeypatch: pytest.MonkeyPatch, fake_repo: Path, tmp_path: Path
) -> None:
    _install_fake_gate_and_runner(monkeypatch)
    monkeypatch.setenv("KODIAC_ALLOW_MUSE_SPEND", "1")
    monkeypatch.delenv("KODIAC_MUSE_EXEC_TEMPLATE", raising=False)
    with pytest.raises(MuseDriverUnavailable, match="UNVERIFIED"):
        run_loop_eval(["B01"], muse_exec_driver(5), out_dir=tmp_path / "o", repo_root=fake_repo)


def test_muse_driver_with_operator_template_runs_and_counts_verify_calls(
    monkeypatch: pytest.MonkeyPatch, fake_repo: Path, tmp_path: Path
) -> None:
    _install_fake_gate_and_runner(monkeypatch)
    monkeypatch.setenv("KODIAC_ALLOW_MUSE_SPEND", "1")
    helper = tmp_path / "fake_muse.py"
    helper.write_text(
        "import sys, pathlib\n"
        "ws = pathlib.Path(sys.argv[1])\n"
        "for i in range(2):\n"
        "    (ws / '.Kodiac' / 'verify' / f'run{i}').mkdir(parents=True)\n"
        "(ws / 'examples' / 'sim' / 'pick_place.py').write_text(%r)\n"
        "print('agent done')\n" % TINY_SCRIPT,
        encoding="utf-8",
    )
    template = f'"{sys.executable}" "{helper}" "{{workspace}}"'
    driver = muse_exec_driver(5, command_template=template)
    (o,) = run_loop_eval(["B01"], driver, max_iters=5, out_dir=tmp_path / "o", repo_root=fake_repo)
    assert o.driver == "muse_exec" and o.iterations == 2 and o.fixed
    assert "agent done" in Path(o.transcript_path).read_text(encoding="utf-8")


# ------------------------------------------------------------------ report + CLI
def test_dry_run_report_is_labelled_and_has_no_fix_rate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fake_gate_and_runner(monkeypatch)
    outcomes = run_loop_eval(["B01", "B05"], reference_patcher, out_dir=tmp_path / "o")
    rep = build_report(outcomes, max_iters=5)
    assert rep["driver"] == "reference_patcher" and rep["evidence_type"] == "plumbing_dry_run"
    assert rep["agent_fix_rate"] is None and rep["note"] == "NOT a Muse Code fix rate"
    assert rep["is_mock"] == [True] and rep["sim_backend"] == ["kinematic_mock"]
    assert not re.search(r"\b\d+\s*/\s*10\b", json.dumps(rep))


def test_agent_report_carries_a_computed_count_only_for_non_reference_drivers(monkeypatch: pytest.MonkeyPatch, fake_repo: Path, tmp_path: Path) -> None:
    _install_fake_gate_and_runner(monkeypatch)
    outcomes = run_loop_eval(["B01"], _fix_driver, out_dir=tmp_path / "o", repo_root=fake_repo)
    rep = build_report(outcomes, max_iters=5)
    assert rep["evidence_type"] == "agent_run" and rep["agent_fix_rate"] == {"fixed": 1, "n_bugs": 1}


def test_main_reference_run_writes_labelled_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fake_gate_and_runner(monkeypatch)
    report = tmp_path / "rep" / "dry.json"
    rc = loop_eval.main(["--bugs", "B01,B04", "--out-dir", str(tmp_path / "o"), "--report", str(report)])
    assert rc == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["evidence_type"] == "plumbing_dry_run" and data["agent_fix_rate"] is None
    assert [o["bug"] for o in data["outcomes"]] == ["B01", "B04"]
    for o in data["outcomes"]:
        assert Path(o["transcript_path"]).name == f"{o['bug']}.md"
        assert (report.parent / "transcripts" / f"{o['bug']}.md").is_file()


def test_main_muse_driver_is_refused_without_opt_in(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _install_fake_gate_and_runner(monkeypatch)
    monkeypatch.delenv("KODIAC_ALLOW_MUSE_SPEND", raising=False)
    rc = loop_eval.main(["--driver", "muse_exec", "--bugs", "B01", "--out-dir", str(tmp_path / "o")])
    assert rc == 2 and "REFUSED" in capsys.readouterr().err
    assert loop_eval.main(["--bugs", "B99", "--out-dir", str(tmp_path / "o2")]) == 2
