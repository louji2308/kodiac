"""CLI wiring tests for the P06-P10 sprint commands: blame, diff, gate, loop, fast mode.

These assert wiring and honesty (labels, exit codes), not engine accuracy: the golden fixture clips
are Tier C, so a verdict may legitimately be FAIL or CAN'T TELL. The tests therefore check that the
command's output is *consistent with the run it performed* rather than pinning a verdict.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from Kodiac_robotics.cli import app

TEST = "examples/stackcube.green"
B01 = "tests/fixtures/clips/b01_early_release.mp4"
B02 = "tests/fixtures/clips/b02_xy_misalignment.mp4"
CORRECT = "tests/fixtures/clips/correct_run.mp4"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_run_fast_mode_is_real_and_labelled(runner: CliRunner, tmp_path: Path) -> None:
    """`run --mode fast` takes the bisect path and says what it spent."""
    res = runner.invoke(
        app, ["run", TEST, B01, "--mode", "fast", "--json", "--output", str(tmp_path)]
    )
    assert res.exit_code in (0, 1, 2), res.stdout
    payload = json.loads(res.stdout)
    assert payload["exit_code"] == res.exit_code
    badges = " ".join(payload["badges"])
    assert "BISECT SPEND" in badges
    assert "billed frames" in badges
    # The spend numbers are measured, not claimed: they are in timings too.
    assert payload["timings_ms"]["bisect_billed_frames"] > 0


def test_blame_json_consistent_with_verdict(runner: CliRunner, tmp_path: Path) -> None:
    """`blame` reports t* + measured facts on FAIL, and refuses to invent a cause otherwise."""
    res = runner.invoke(app, ["blame", TEST, B01, "--json", "--output", str(tmp_path)])
    assert res.exit_code in (1, 2), res.stdout
    payload = json.loads(res.stdout)
    assert payload["exit_code"] == res.exit_code
    if payload["verdict"] == "FAIL":
        assert payload["blame"] is not None
        facts = payload["blame"]["facts"]
        assert facts["frame"] >= 0
        assert facts["t_star_s"] >= 0
        assert facts["sigma_frames"] >= 0
        assert payload["blame"]["summary_source"] in {"template", "muse-spark"}
        assert isinstance(facts["facts"], dict)
    else:
        assert payload["verdict"] == "CANT_TELL"
        assert payload["blame"] is None
        assert payload["note"]


def test_diff_json_has_aligned_events(runner: CliRunner, tmp_path: Path) -> None:
    """`diff` compares demo vs attempt events and does not crash on degenerate event lists."""
    res = runner.invoke(
        app,
        ["diff", TEST, B02, "--demo", CORRECT, "--json"],
    )
    assert res.exit_code in (0, 1, 2), res.stdout
    payload = json.loads(res.stdout)
    assert payload["demo_source"] == CORRECT
    assert "--- demo" in payload["diff"]
    assert "+++ attempt" in payload["diff"]


def test_diff_without_reference_refuses_honestly(runner: CliRunner) -> None:
    """No `--demo` and no `.green.lock` sidecar -> exit 3 with a message, never a fabricated diff."""
    res = runner.invoke(app, ["diff", "examples/stack_blocks.green", B02, "--json"])
    assert res.exit_code == 3
    payload = json.loads(res.stdout)
    assert "no demo reference" in payload["error"]


def test_gate_without_pins_allows_stop(runner: CliRunner, tmp_path: Path, monkeypatch) -> None:
    """A workspace with no `--init` pins must never block an unrelated session."""
    monkeypatch.setenv("KODIAC_GATE_HOME", str(tmp_path / "gates"))
    workspace = tmp_path / "ws"
    workspace.mkdir()
    res = runner.invoke(app, ["gate", "--workspace", str(workspace)], input="")
    assert res.exit_code == 0


def test_gate_init_without_test_fails_closed(runner: CliRunner, tmp_path: Path, monkeypatch) -> None:
    """A broken gate invocation never returns 3 and never claims the goal was verified."""
    monkeypatch.setenv("KODIAC_GATE_HOME", str(tmp_path / "gates"))
    workspace = tmp_path / "ws"
    workspace.mkdir()
    res = runner.invoke(app, ["gate", "--init", "--workspace", str(workspace)])
    assert res.exit_code == 2


def test_loop_init_dry_run_lists_actions(runner: CliRunner, tmp_path: Path) -> None:
    """`loop init --dry-run` lists what it would write and writes nothing."""
    project = tmp_path / "proj"
    project.mkdir()
    res = runner.invoke(app, ["loop", "init", "--dir", str(project), "--dry-run"])
    assert res.exit_code == 0, res.stdout
    assert not (project / ".mcp.json").exists()
    assert ".mcp.json" in res.stdout


def test_audit_and_loop_subcommands_registered(runner: CliRunner) -> None:
    """The audit / loop groups exist with their expected subcommands."""
    audit = runner.invoke(app, ["audit", "--help"])
    assert audit.exit_code == 0
    for command in ("run", "candidates", "review", "digest", "export", "publish"):
        assert command in audit.stdout
    loop = runner.invoke(app, ["loop", "--help"])
    assert loop.exit_code == 0
    assert "init" in loop.stdout and "eval" in loop.stdout


# ---------------------------------------------------------------------------
# Simulated-episode path: the only non-degenerate verdict source in this repo.
# These tests protect two things at once: the wiring, and the promise that a
# sim grade is never dressed up as perception.
# ---------------------------------------------------------------------------

SIM = "examples/sim/pick_place.py"


def test_run_sim_episode_is_labelled_as_synthetic(runner: CliRunner, tmp_path: Path) -> None:
    """An unpatched sim episode PASSes and every badge says the tracks came from sim state."""
    res = runner.invoke(
        app, ["run", TEST, "--sim", SIM, "--seed", "0", "--json", "--output", str(tmp_path)]
    )
    assert res.exit_code == 0, res.stdout
    payload = json.loads(res.stdout)
    assert payload["verdict"] == "PASS"
    badges = " ".join(payload["badges"])
    assert "[SIM]" in badges
    assert "SYNTHETIC TRACKS FROM SIM STATE" in badges
    assert "MOCK SIMULATION" in badges
    # The false claim that killed credibility on the video path must never reappear here.
    assert "CACHED SAM 3.1" not in badges


def test_run_sim_episode_with_seeded_bug_fails(runner: CliRunner, tmp_path: Path) -> None:
    """Injecting B01 turns the same episode into a FAIL and says how the bug got in."""
    res = runner.invoke(
        app,
        ["run", TEST, "--sim", SIM, "--bug", "B01", "--seed", "0", "--json", "--output", str(tmp_path)],
    )
    assert res.exit_code == 1, res.stdout
    payload = json.loads(res.stdout)
    assert payload["verdict"] == "FAIL"
    badges = " ".join(payload["badges"])
    assert "[SIM BUG B01: injected via patch]" in badges
    assert "SYNTHETIC TRACKS FROM SIM STATE" in badges


def test_blame_sim_episode_returns_tstar_and_source_line(runner: CliRunner, tmp_path: Path) -> None:
    """`blame --sim --bug` attributes the failure to a frame and the actuation line that caused it."""
    res = runner.invoke(
        app,
        ["blame", TEST, "--sim", SIM, "--bug", "B01", "--seed", "0", "--json", "--output", str(tmp_path)],
    )
    assert res.exit_code == 1, res.stdout
    payload = json.loads(res.stdout)
    assert payload["verdict"] == "FAIL"
    blame = payload["blame"]
    assert blame is not None
    facts = blame["facts"]
    assert facts["transition"] == "T->F"
    assert facts["frame"] > 0
    assert facts["t_star_s"] > 0
    assert facts["sigma_frames"] >= 0
    assert facts["facts"], "a blame without measured facts is not a blame"
    loc = facts["code_location"]
    assert loc is not None, "the sim path must point at the actuation line"
    assert loc["line"] > 0
    assert loc["code"].strip()
    assert loc["file"]


def test_run_requires_exactly_one_input(runner: CliRunner) -> None:
    """Neither a clip nor --sim (or both) is a usage error, never a silent guess."""
    neither = runner.invoke(app, ["run", TEST, "--json"])
    assert neither.exit_code == 3
    assert "exactly one" in json.loads(neither.stdout)["error"]
    both = runner.invoke(app, ["run", TEST, B01, "--sim", SIM, "--json"])
    assert both.exit_code == 3
    assert "exactly one" in json.loads(both.stdout)["error"]


def test_diff_sim_episode_shows_demo_only_and_attempt_only(runner: CliRunner) -> None:
    """A buggy sim attempt diffs against the correct run: achieved events vs the failed one."""
    res = runner.invoke(
        app,
        [
            "diff",
            TEST,
            "--sim",
            SIM,
            "--bug",
            "B01",
            "--demo-sim",
            SIM,
            "--geometry",
            "tier_a",
            "--json",
        ],
    )
    assert res.exit_code == 1, res.stdout
    payload = json.loads(res.stdout)
    assert payload["demo_source"].startswith("sim:")
    body = payload["diff"]
    assert "--- demo" in body and "+++ attempt" in body
    assert "- [1] place:" in body, "the demonstration placed the cube and the attempt did not"
    assert "+ [1] place:" in body
    assert "failed" in body

