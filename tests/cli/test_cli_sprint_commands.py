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
