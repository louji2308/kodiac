"""Unit tests for calibration split isolation and lambda fitting."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from Kodiac_robotics.uncertainty.calibrate import fit_inflation_lambda


def test_split_isolation_rejects_training_episodes(tmp_path: Path):
    """Calibrate MUST raise ValueError if training episode (ep_id >= 200 or split='train') is accessed."""
    leaked_manifest = tmp_path / "manifest_leak.json"
    data = [
        {"episode_id": "ep_00001_calibration", "split": "calibration"},
        {
            "episode_id": "ep_00250_train",
            "split": "calibration",
        },  # Leaked ID in training range >= 200
    ]
    with open(leaked_manifest, "w", encoding="utf-8") as f:
        json.dump(data, f)

    with pytest.raises(ValueError, match="Cryptographic split violation"):
        fit_inflation_lambda(leaked_manifest, tmp_path / "lambda.json")


def test_split_isolation_rejects_train_split_in_fit_range(tmp_path: Path):
    """Calibrate MUST raise ValueError if split='train' appears with num_id < 100."""
    leaked_manifest = tmp_path / "manifest_leak_split.json"
    data = [
        {"episode_id": "ep_00005_train", "split": "train"},
    ]
    with open(leaked_manifest, "w", encoding="utf-8") as f:
        json.dump(data, f)

    with pytest.raises(ValueError, match="Cryptographic split violation"):
        fit_inflation_lambda(leaked_manifest, tmp_path / "lambda.json")


def test_valid_calibration_fit(tmp_path: Path):
    """Valid calibration manifest strictly fits lambda on ep_id < 100."""
    valid_manifest = tmp_path / "manifest_valid.json"
    data = [{"episode_id": f"ep_{i:05d}_calibration", "split": "calibration"} for i in range(50)]
    out_json = tmp_path / "lambda.json"
    with open(valid_manifest, "w", encoding="utf-8") as f:
        json.dump(data, f)

    lam = fit_inflation_lambda(valid_manifest, out_json)
    assert 1.0 <= lam <= 3.0
    assert out_json.exists()

    with open(out_json, "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["split"] == "calibration_fit"
    assert saved["n_episodes"] == 50
    assert saved["lambda"] == lam
