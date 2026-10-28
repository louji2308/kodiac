"""Unit tests for pre-registration document, pool config, and cryptographic integrity.

Verifies Invariant I8, ADR-0006, and P02 RULING pre-registration requirements.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from Kodiac_robotics.proof.pool import (
    assert_preregistration_ready,
    compute_prereg_hashes,
    find_repo_root,
    verify_preregistration_tag,
)


def test_prereg_and_config_files_exist() -> None:
    """Verify that PREREGISTRATION.md and pool_config.yaml exist in experiments/."""
    root = find_repo_root()
    prereg_path = root / "experiments" / "PREREGISTRATION.md"
    config_path = root / "experiments" / "pool_config.yaml"

    assert prereg_path.is_file(), f"Missing {prereg_path}"
    assert config_path.is_file(), f"Missing {config_path}"


def test_prereg_document_contents() -> None:
    """Verify that PREREGISTRATION.md covers all pre-registered criteria."""
    root = find_repo_root()
    prereg_text = (root / "experiments" / "PREREGISTRATION.md").read_text(encoding="utf-8")

    # Hypotheses
    assert "H1" in prereg_text
    assert "H2" in prereg_text
    assert "H3" in prereg_text
    assert "False-PASS" in prereg_text or "false-PASS" in prereg_text

    # Exact oracle thresholds
    assert "3.33" in prereg_text
    assert "0.5" in prereg_text
    assert "pd_ee_delta_pos" in prereg_text

    # Rejection rule & seeds
    assert "CAN'T TELL" in prereg_text
    assert "20,000" in prereg_text
    assert "200" in prereg_text
    assert "3 seeds" in prereg_text or "3 fixed seeds" in prereg_text

    # Benchmark arms
    assert "Single-Pass" in prereg_text or "Single-pass" in prereg_text
    assert "Robometer-4B" in prereg_text
    assert "TOPReward" in prereg_text
    assert "Prefix Salvage" in prereg_text or "salvage" in prereg_text


def test_pool_config_structure() -> None:
    """Verify that pool_config.yaml adheres to pre-registered distribution parameters."""
    root = find_repo_root()
    config_path = root / "experiments" / "pool_config.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    assert cfg["pool_size"] == 1000
    assert cfg["pi0_ratio"] == 0.70
    assert cfg["perturbed_expert_ratio"] == 0.30
    assert cfg["splits"]["calibration"] == 200
    assert cfg["splits"]["train"] == 800
    assert cfg["sharding"]["shard_size"] == 100

    # Action space contract (ADR-0007)
    assert cfg["action_space"]["control_mode"] == "pd_ee_delta_pos"
    assert cfg["action_space"]["action_dim"] == 7
    assert cfg["action_space"]["dtype"] == "float32"

    # Perturbations
    perts = cfg["perturbations"]
    assert "early_open" in perts
    assert "xy_offset" in perts
    assert "low_lift" in perts
    assert "short_dwell" in perts
    assert "regrasp" in perts


def test_prereg_hashes_computation() -> None:
    """Verify that SHA-256 hashes are valid 64-character hexadecimal strings."""
    prereg_sha, config_sha = compute_prereg_hashes()

    assert len(prereg_sha) == 64
    assert re.match(r"^[0-9a-f]{64}$", prereg_sha)
    assert len(config_sha) == 64
    assert re.match(r"^[0-9a-f]{64}$", config_sha)
    assert prereg_sha != config_sha


def test_assert_preregistration_ready_allow_untagged() -> None:
    """Verify that allow_untagged=True bypasses the git tag check during testing."""
    prereg_sha, config_sha, tag = assert_preregistration_ready(allow_untagged=True)
    assert len(prereg_sha) == 64
    assert len(config_sha) == 64
    assert tag == "prereg-v0"


def test_assert_preregistration_tripwire_fails_when_unready(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that assert_preregistration_ready raises RuntimeError when tag is absent."""
    # Force verify_preregistration_tag to return False
    monkeypatch.setattr(
        "Kodiac_robotics.proof.pool.verify_preregistration_tag",
        lambda repo_root=None, required_tag="prereg-v0": False,
    )

    with pytest.raises(RuntimeError, match="Pre-registration invariant I8 violated"):
        assert_preregistration_ready(allow_untagged=False)
