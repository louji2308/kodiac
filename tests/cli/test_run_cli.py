"""Tests for the Kodiac run CLI command."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from Kodiac_robotics.cli import app
from Kodiac_robotics.contracts.core import RunResult, Verdict


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_cli_run_b01_fail(runner: CliRunner) -> None:
    """Kodiac run on b01_early_release returns exit code 1 (FAIL)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        res = runner.invoke(
            app,
            [
                "run",
                "examples/stackcube.green",
                "tests/fixtures/clips/b01_early_release.mp4",
                "--output",
                tmpdir,
            ],
        )
        assert res.exit_code == 1
        assert "FAIL" in res.stdout
        assert "stackcube" in res.stdout
        assert "b01_early_release.mp4" in res.stdout


def test_cli_run_occluded_cant_tell(runner: CliRunner) -> None:
    """Kodiac run on occluded_clip returns exit code 2 (CAN'T TELL) and occluded reason."""
    with tempfile.TemporaryDirectory() as tmpdir:
        res = runner.invoke(
            app,
            [
                "run",
                "examples/stackcube.green",
                "tests/fixtures/clips/occluded_clip.mp4",
                "--output",
                tmpdir,
            ],
        )
        assert res.exit_code == 2
        assert "CAN'T TELL" in res.stdout
        assert "occluded" in res.stdout


def test_cli_run_json_output(runner: CliRunner) -> None:
    """--json emits purely valid JSON that validates against RunResult."""
    with tempfile.TemporaryDirectory() as tmpdir:
        res = runner.invoke(
            app,
            [
                "run",
                "examples/stackcube.green",
                "tests/fixtures/clips/b01_early_release.mp4",
                "--json",
                "--output",
                tmpdir,
            ],
        )
        assert res.exit_code == 1
        parsed = json.loads(res.stdout)
        assert parsed["verdict"] == "FAIL"
        assert parsed["exit_code"] == 1
        assert parsed["test_name"] == "stackcube"
        model = RunResult.model_validate(parsed)
        assert model.verdict == Verdict.FAIL


def test_cli_run_card_flag(runner: CliRunner) -> None:
    """--card flag triggers verdict card rendering."""
    with tempfile.TemporaryDirectory() as tmpdir:
        res = runner.invoke(
            app,
            [
                "run",
                "examples/stackcube.green",
                "tests/fixtures/clips/b01_early_release.mp4",
                "--card",
                "--output",
                tmpdir,
            ],
        )
        assert res.exit_code == 1
        card_file = Path(tmpdir) / "card.png"
        assert card_file.is_file()
        assert card_file.stat().st_size > 0


def test_cli_run_invalid_test_error(runner: CliRunner) -> None:
    """Invalid test file returns exit code 3."""
    res = runner.invoke(
        app,
        [
            "run",
            "nonexistent/test.green",
            "tests/fixtures/clips/b01_early_release.mp4",
        ],
    )
    assert res.exit_code == 3


def test_cli_run_invalid_test_error_json(runner: CliRunner) -> None:
    """Invalid test file with --json outputs valid JSON with exit_code 3."""
    res = runner.invoke(
        app,
        [
            "run",
            "nonexistent/test.green",
            "tests/fixtures/clips/b01_early_release.mp4",
            "--json",
        ],
    )
    assert res.exit_code == 3
    parsed = json.loads(res.stdout)
    assert parsed["exit_code"] == 3
    assert "error" in parsed
