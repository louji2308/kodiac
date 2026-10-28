"""Unit tests for Kodiac infrastructure, Modal definitions, and SDM harness."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modal import hello_cpu, hello_l4, volumes  # noqa: E402
from scripts.sdm import invoke_sdm  # noqa: E402


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


def test_features_yaml_schema_validity(repo_root: Path):
    """Verify docs/features.yaml parses cleanly, adheres to schema, and covers F01-F60."""
    features_path = repo_root / "docs" / "features.yaml"
    assert features_path.exists(), f"Missing features.yaml at {features_path}"

    with open(features_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert isinstance(data, list), "features.yaml root must be a list"
    assert len(data) >= 60, f"Expected at least 60 features, found {len(data)}"

    feature_ids = set()
    expected_keys = {"id", "name", "tier", "status", "evidence"}
    allowed_tiers = {"MVP", "Strong", "Stretch"}
    allowed_statuses = {"planned", "in_progress", "done", "blocked"}
    id_pattern = re.compile(r"^F\d{2}[a-z]?$")

    for idx, item in enumerate(data):
        assert isinstance(item, dict), f"Feature item {idx} must be a dictionary"
        assert set(item.keys()) == expected_keys, (
            f"Feature item {idx} keys mismatch: {set(item.keys())} != {expected_keys}"
        )
        fid = item["id"]
        assert id_pattern.match(fid), f"Invalid feature id format: {fid}"
        assert fid not in feature_ids, f"Duplicate feature id detected: {fid}"
        feature_ids.add(fid)

        assert isinstance(item["name"], str) and item["name"].strip(), (
            f"Empty or non-string name for feature {fid}"
        )
        assert item["tier"] in allowed_tiers, (
            f"Invalid tier '{item['tier']}' for feature {fid}"
        )
        assert item["status"] in allowed_statuses, (
            f"Invalid status '{item['status']}' for feature {fid}"
        )

    # Verify coverage of F01 through F60 (with F35 split into F35a and F35b)
    for i in range(1, 61):
        if i == 35:
            assert "F35a" in feature_ids, "Missing F35a (real footage blame target)"
            assert "F35b" in feature_ids, "Missing F35b (sim code blame target)"
        else:
            fid = f"F{i:02d}"
            assert fid in feature_ids, f"Missing required feature {fid}"


def test_modal_volumes_definition():
    """Verify Modal volumes and secrets definitions."""
    assert volumes.check() is True
    assert len(volumes.VOLUME_NAMES) == 5
    assert "hf-cache" in volumes.VOLUME_NAMES
    assert "gl-cache" in volumes.VOLUME_NAMES
    assert "gl-replays" in volumes.VOLUME_NAMES
    assert "gl-pool" in volumes.VOLUME_NAMES
    assert "gl-uploads" in volumes.VOLUME_NAMES

    assert len(volumes.SECRET_NAMES) == 2
    assert "meta-model-api" in volumes.SECRET_NAMES
    assert "huggingface" in volumes.SECRET_NAMES

    assert len(volumes.VOLUMES) == 5
    assert len(volumes.SECRETS) == 2


def test_modal_hello_cpu_scaledown_window():
    """Verify modal/hello_cpu.py enforces scaledown_window=0 cost guard."""
    assert hello_cpu.check() is True
    assert hello_cpu.SCALEDOWN_WINDOW == 0
    assert hello_cpu.app.name == "kodiac-hello-cpu"
    if hasattr(hello_cpu.hello_cpu, "__modal_kwargs__"):
        kwargs = hello_cpu.hello_cpu.__modal_kwargs__
        assert kwargs.get("scaledown_window") == 0


def test_modal_hello_l4_scaledown_window():
    """Verify modal/hello_l4.py enforces scaledown_window=0 cost guard and L4 GPU."""
    assert hello_l4.check() is True
    assert hello_l4.SCALEDOWN_WINDOW == 0
    assert hello_l4.GPU_TYPE == "L4"
    assert hello_l4.app.name == "kodiac-hello-l4"
    if hasattr(hello_l4.hello_l4, "__modal_kwargs__"):
        kwargs = hello_l4.hello_l4.__modal_kwargs__
        assert kwargs.get("scaledown_window") == 0, (
            "Modal L4 container must enforce scaledown_window=0 to avoid warm GPU charges"
        )
        assert kwargs.get("gpu") == "L4"


def test_invoke_sdm_dry_run_programmatic(tmp_path: Path):
    """Verify invoke_sdm.py dry-run returns 0 and constructs valid command."""
    packet_file = tmp_path / "SDM_PACKET.md"
    packet_file.write_text("# Test Packet", encoding="utf-8")
    output_file = tmp_path / "RULING.md"

    # Test basic dry run
    ret = invoke_sdm.main(["--dry-run"])
    assert ret == 0

    # Test dry run with packet and output specified
    ret = invoke_sdm.main(
        [
            "--packet",
            str(packet_file),
            "--output",
            str(output_file),
            "--dry-run",
        ]
    )
    assert ret == 0

    cmd = invoke_sdm.build_command(packet_file, model="deepseek/deepseek-chat")
    assert "opencode" in cmd
    assert "run" in cmd
    assert "-m" in cmd
    assert "deepseek/deepseek-chat" in cmd


def test_invoke_sdm_dry_run_cli(repo_root: Path):
    """Verify running scripts/sdm/invoke_sdm.py --dry-run via CLI exits with code 0."""
    script_path = repo_root / "scripts" / "sdm" / "invoke_sdm.py"
    res = subprocess.run(
        [sys.executable, str(script_path), "--dry-run"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"invoke_sdm.py failed with: {res.stderr}"
    assert "[DRY RUN]" in res.stdout


def test_demo_filming_guide_content(repo_root: Path):
    """Verify docs/DEMO_FILMING_GUIDE.md exists and contains mandatory filming constraints."""
    guide_path = repo_root / "docs" / "DEMO_FILMING_GUIDE.md"
    assert guide_path.exists(), "DEMO_FILMING_GUIDE.md must exist"

    text = guide_path.read_text(encoding="utf-8")
    assert "30°" in text or "30" in text, "Missing camera elevation angle range"
    assert "50°" in text or "50" in text, "Missing camera elevation angle range"
    assert "4.0 cm" in text or "4.0" in text, "Missing hero object prior dimension"
    assert "0.7" in text, "Missing 0.7s pause requirement for Muse Voice ENDPOINTING"
    assert "Tier B" in text, "Missing Tier B ground-plane calibration reference"
    assert "CAN'T TELL" in text, "Missing CAN'T TELL honesty recording instructions"
