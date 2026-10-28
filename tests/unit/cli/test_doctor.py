"""Unit tests for Kodiac CLI and doctor command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from Kodiac_robotics.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_cli_version_flag(runner: CliRunner) -> None:
    """Kodiac --version must exit 0 and print version 0.1.0."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_cli_version_command(runner: CliRunner) -> None:
    """Kodiac version must exit 0 and print version 0.1.0."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_doctor_offline_healthy_exits_zero(runner: CliRunner) -> None:
    """Kodiac doctor must exit 0 when Table 1 (Core Engine Offline) checks pass."""
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Table 1: Core Engine (Offline)" in result.stdout
    assert "Table 2: Cloud Services & Sponsors (Online)" in result.stdout
    assert "Core Engine is healthy (exit 0)" in result.stdout

    # Verify terminal output capture artifact
    capture_path = Path("artifacts/p01/doctor_terminal.txt")
    assert capture_path.exists()
    captured_text = capture_path.read_text(encoding="utf-8")
    assert "Table 1: Core Engine (Offline)" in captured_text
    assert "Core Engine is healthy" in captured_text


def test_doctor_json_output(runner: CliRunner) -> None:
    """Kodiac doctor --json must produce valid JSON with offline and cloud status."""
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0

    data = json.loads(result.stdout)
    assert data["version"] == "0.1.0"
    assert data["offline_core"]["healthy"] is True
    assert data["offline_core"]["status"] == "PASS"

    offline_checks = {c["name"]: c["status"] for c in data["offline_core"]["checks"]}
    assert offline_checks.get("Python Version") == "PASS"
    assert offline_checks.get("ffmpeg Binary") == "PASS"
    assert offline_checks.get("Cache Directory") == "PASS"
    assert offline_checks.get("Core Contracts") == "PASS"

    cloud_check_names = [c["name"] for c in data["cloud_services"]["checks"]]
    assert "MODEL_API_KEY" in cloud_check_names
    assert "HF_TOKEN" in cloud_check_names
    assert "MODAL_TOKEN_ID" in cloud_check_names
    assert "BASETEN_API_KEY" in cloud_check_names
    assert "FIREWORKS_API_KEY" in cloud_check_names
    assert "nvidia-smi GPU" in cloud_check_names
    assert "opencode CLI" in cloud_check_names


def test_doctor_secret_redaction(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    """Kodiac doctor must NEVER leak secrets to stdout or terminal artifacts."""
    dummy_secrets = {
        "MODEL_API_KEY": "sk-meta-super-secret-key-12345",
        "HF_TOKEN": "hf_secret_token_abcdef67890",
        "MODAL_TOKEN_ID": "ak-modal-token-id-998877",
        "BASETEN_API_KEY": "baseten_key_secret_xyz123",
        "FIREWORKS_API_KEY": "fireworks_key_secret_qwe456",
    }

    for key, val in dummy_secrets.items():
        monkeypatch.setenv(key, val)

    # Invalidate cached settings so monkeypatch applies
    import Kodiac_robotics.config
    Kodiac_robotics.config._global_settings = None

    try:
        # Test regular output
        res_plain = runner.invoke(app, ["doctor"])
        assert res_plain.exit_code == 0
        for secret in dummy_secrets.values():
            assert secret not in res_plain.stdout

        # Test json output
        res_json = runner.invoke(app, ["doctor", "--json"])
        assert res_json.exit_code == 0
        for secret in dummy_secrets.values():
            assert secret not in res_json.stdout

        # Test captured artifact
        captured = Path("artifacts/p01/doctor_terminal.txt").read_text(encoding="utf-8")
        for secret in dummy_secrets.values():
            assert secret not in captured

    finally:
        Kodiac_robotics.config._global_settings = None


def test_doctor_offline_failure_exits_one(runner: CliRunner) -> None:
    """When Table 1 has a failing check, doctor must exit 1."""
    with patch("Kodiac_robotics.cli.shutil.which", return_value=None):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "FAIL" in result.stdout


def test_smoke_artifacts_law1_compliance() -> None:
    """All ST01-ST13 smoke artifacts must strictly obey Law 1 (anti-fabrication)."""
    smoke_dir = Path("artifacts/p01/smoke")
    assert smoke_dir.exists(), "Smoke test directory does not exist"

    for i in range(1, 14):
        test_file = smoke_dir / f"st{i:02d}.json"
        assert test_file.exists(), f"Missing artifact: {test_file}"

        data = json.loads(test_file.read_text(encoding="utf-8"))
        assert "test_id" in data
        assert "status" in data
        assert "is_fixture" in data
        assert "live_verified" in data

        if data["is_fixture"]:
            assert (
                data["latency_ms"] is None
            ), f"Law 1 violation in {test_file}: latency_ms must be null when is_fixture=True"
            assert (
                data["live_verified"] is False
            ), f"Law 1 violation in {test_file}: live_verified must be false when is_fixture=True"

        if data["live_verified"]:
            assert data["is_fixture"] is False
            assert (
                data["latency_ms"] is not None
            ), f"Missing latency_ms for live verified test in {test_file}"
            assert data["latency_ms"] >= 0
