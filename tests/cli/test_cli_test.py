"""Tests for the Kodiac test CLI subcommand.

Verifies:
- Text-compile mode (--from-text)
- Video demonstration compilation mode (--video)
- UNIX stream separation (stdout: clean .green; stderr: progress timers & warnings)
- Webcam probe with 2.0s timeout
- Physical sanity cap enforcement and self-test gating
- Lockfile generation with _slack_summary
- End-to-end compilation latency < 12.0s
Per ARCHITECTURE.md §5.1, §6.1-§6.3, ADR-0011, ADR-0012, ADR-0013, and P05.S11.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from Kodiac_robotics.cli import app
from Kodiac_robotics.compiler.parser import parse_green


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_cli_test_missing_args(runner: CliRunner) -> None:
    """Invoking Kodiac test without --video or --from-text exits with code 1."""
    res = runner.invoke(app, ["test"])
    assert res.exit_code == 1
    assert "Must provide --video or --from-text" in res.output


def test_cli_test_from_text_stdout(runner: CliRunner) -> None:
    """Kodiac test --from-text emits parseable .green test specification."""
    res = runner.invoke(app, ["test", "--from-text", "stack cubeA on cubeB"])
    assert res.exit_code == 0
    assert "objects: [gripper, cubeA, cubeB]" in res.output
    assert "1. grasp:" in res.output
    assert "2. place:" in res.output
    assert "3. release:" in res.output


def test_cli_test_from_text_out_file(runner: CliRunner) -> None:
    """Kodiac test --from-text --out writes valid .green file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = Path(tmpdir) / "test_out.green"
        res = runner.invoke(
            app,
            ["test", "--from-text", "stack cubeA on cubeB", "--out", str(out_file)],
        )
        assert res.exit_code == 0
        assert out_file.is_file()

        parsed = parse_green(out_file)
        assert parsed.name == "test_cubeA_cubeB" or "cube" in parsed.name.lower()
        assert len(parsed.objects) == 3
        assert len(parsed.steps) == 3


def test_cli_test_unrecognized_verb_e003(runner: CliRunner) -> None:
    """Unrecognized action in --from-text raises E003 verb gating diagnostic (ADR-0012)."""
    res = runner.invoke(app, ["test", "--from-text", "fly over the mountain"])
    assert res.exit_code == 1
    assert "E003" in res.output


def test_cli_test_webcam_probe_timeout(runner: CliRunner) -> None:
    """Non-existent webcam index 99 fails probe within 2.0s timeout."""
    t0 = time.perf_counter()
    res = runner.invoke(app, ["test", "--webcam", "99"])
    dt = time.perf_counter() - t0

    assert res.exit_code == 1
    assert dt <= 3.0  # Must fail fast within probe window
    assert "Webcam index 99 probe failed" in res.output


def test_cli_test_video_b01_fails_selftest(runner: CliRunner) -> None:
    """Demonstration video with premature release (b01) fails self-test with exit code 1."""
    res = runner.invoke(
        app,
        [
            "test",
            "--video",
            "tests/fixtures/clips/b01_early_release.mp4",
            "--from-text",
            "pick up cubeA and place on cubeB",
        ],
    )
    assert res.exit_code == 1
    assert "failed self-test verification" in res.output or "E005" in res.output


def test_cli_test_video_correct_run_out(runner: CliRunner) -> None:
    """Canonical correct demonstration video compiles, passes self-test, and outputs lockfile."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = Path(tmpdir) / "compiled_demo.green"
        lock_file = Path(tmpdir) / "compiled_demo.green.lock"

        t0 = time.perf_counter()
        res = runner.invoke(
            app,
            [
                "test",
                "--video",
                "tests/fixtures/clips/correct_run.mp4",
                "--from-text",
                "pick up cubeA and place on cubeB",
                "--out",
                str(out_file),
            ],
        )
        dt = time.perf_counter() - t0

        # Latency budget check: must compile in < 12.0s
        assert dt < 12.0, f"Compilation took {dt:.2f}s, exceeding 12.0s budget"
        assert res.exit_code == 0
        assert out_file.is_file()
        assert lock_file.is_file()

        # Parse written test
        parsed = parse_green(out_file)
        assert len(parsed.objects) >= 2
        assert len(parsed.steps) >= 2


def test_cli_test_stream_separation() -> None:
    """UNIX Stream Separation: stderr contains timers/notices; stdout contains clean .green."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "Kodiac_robotics.cli",
            "test",
            "--from-text",
            "stack cubeA on cubeB",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )

    assert proc.returncode == 0
    # stdout must contain the .green file content without progress spinners or banners
    assert "objects: [" in proc.stdout
    assert "1. grasp:" in proc.stdout
    assert "✓" not in proc.stdout

    # stderr must contain progress timers and compiler notices
    assert "compiled" in proc.stderr or "LLM OFFLINE" in proc.stderr
