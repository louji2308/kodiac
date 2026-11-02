"""assemble_proof_arms is fail-closed: judge arms exist only when a real label file exists (Law 1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from Kodiac_robotics.proof.arms import NO_LABELS_REASON, assemble_proof_arms

JUDGE_ARM_KEYS = [
    "kodiac_cloud",
    "kodiac_open_weights",
    "kodiac_salvage",
    "single_pass_spark_2fps",
    "single_pass",
    "robometer_4b",
    "topreward",
    "kodiac_sam31",
    "kodiac_kinematic",
]


def _manifest(tmp_path: Path, *, n_train: int = 60, n_cal: int = 20, is_mock: bool = True) -> Path:
    rows = []
    for i in range(n_cal):
        rows.append({"episode_id": f"c{i}", "split": "calibration", "oracle_success": i % 2 == 0, "is_mock": is_mock})
    for i in range(n_train):
        rows.append({"episode_id": f"t{i}", "split": "train", "oracle_success": i % 2 == 0, "is_mock": is_mock})
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    return p


def _label_rows(judge: str, ids: list[str], accept_fn, *, is_mock: bool | None, t_star=None) -> list[dict]:
    rows = []
    for e in ids:
        acc = bool(accept_fn(e))
        row = {
            "judge": judge,
            "episode_id": e,
            "accept": acc,
            "verdict": "PASS" if acc else "FAIL",
            "latency_ms": 5,
            "cost_usd": 0.0,
        }
        if is_mock is not None:
            row["is_mock"] = is_mock
            row["evidence_type"] = "fixture" if is_mock else "live"
        if t_star is not None and not acc:
            row["t_star_frame"] = t_star(e)
        rows.append(row)
    return rows


def _write(labels_dir: Path, stem: str, rows: list[dict]) -> None:
    labels_dir.mkdir(parents=True, exist_ok=True)
    (labels_dir / f"{stem}.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def _all_ids(n_train: int = 60, n_cal: int = 20) -> list[str]:
    return [f"c{i}" for i in range(n_cal)] + [f"t{i}" for i in range(n_train)]


def test_empty_labels_dir_builds_no_judge_arm(tmp_path: Path) -> None:
    arms = assemble_proof_arms(_manifest(tmp_path), tmp_path / "labels")
    for key in JUDGE_ARM_KEYS:
        assert key not in arms, f"{key} was fabricated without labels"
        assert key in arms.absent
    assert arms.absent["kodiac_cloud"] == NO_LABELS_REASON
    assert arms.absent["robometer_4b"] == NO_LABELS_REASON
    assert "size_matched_control" not in arms and "kodiac_cloud" in arms.absent["size_matched_control"]


def test_oracle_only_arms_are_kept_and_labelled(tmp_path: Path) -> None:
    arms = assemble_proof_arms(_manifest(tmp_path), tmp_path / "labels")
    assert {"oracle", "ground_truth", "accept_all"} <= set(arms)
    assert len(arms["oracle"]) == 30 and len(arms["accept_all"]) == 60
    assert all(e.startswith("t") for e in arms["accept_all"])  # train split only
    for k in (5, 10, 20, 30):
        dose = arms[f"oracle_k_{k}"]
        prov = arms.provenance[f"oracle_k_{k}"]
        assert prov["kind"] == "injected_noise" and prov["evidence_type"] == "synthetic"
        assert prov["is_mock"] is True
        assert len(dose) == 30 + int(round(30 * k / 100))
    assert arms.provenance["oracle"]["is_mock"] is True
    assert arms.provenance["oracle"]["evidence_type"] == "synthetic"


def test_real_manifest_marks_oracle_arms_not_mock(tmp_path: Path) -> None:
    arms = assemble_proof_arms(_manifest(tmp_path, is_mock=False), tmp_path / "labels")
    assert arms.provenance["oracle"]["is_mock"] is False
    assert arms.provenance["oracle_k_10"]["evidence_type"] == "synthetic"  # injected noise stays synthetic


def test_labels_build_arm_and_carry_provenance(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    rows = _label_rows("kodiac", _all_ids(), lambda e: e in {"t0", "t2", "t4", "t1"}, is_mock=False)
    _write(labels, "kodiac_cloud", rows)
    arms = assemble_proof_arms(_manifest(tmp_path), labels)
    assert sorted(arms["kodiac_cloud"]) == ["t0", "t1", "t2", "t4"]
    assert arms["kodiac_sam31"] == arms["kodiac_cloud"]
    prov = arms.provenance["kodiac_cloud"]
    assert prov["is_mock"] is False and prov["evidence_types"] == ["live"] and prov["coverage"] == 1.0
    assert len(arms["size_matched_control"]) == 4
    assert all(e in arms["oracle"] for e in arms["size_matched_control"])
    assert "robometer_4b" in arms.absent  # other judges stay absent


def test_undeclared_provenance_is_mock(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    _write(labels, "kodiac_cloud", _label_rows("kodiac", _all_ids(), lambda e: e == "t0", is_mock=None))
    arms = assemble_proof_arms(_manifest(tmp_path), labels)
    assert arms.provenance["kodiac_cloud"]["is_mock"] is True
    assert arms.provenance["kodiac_cloud"]["provenance_declared"] is False


def test_cant_tell_is_never_accepted(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    rows = _label_rows("kodiac", _all_ids(), lambda e: True, is_mock=False)
    for r in rows:
        if r["episode_id"] == "t3":
            r["verdict"] = "CANT_TELL"
    _write(labels, "kodiac_cloud", rows)
    arms = assemble_proof_arms(_manifest(tmp_path), labels)
    assert "t3" not in arms["kodiac_cloud"] and "t4" in arms["kodiac_cloud"]


def test_unlabelled_episode_is_not_accepted(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    ids = [e for e in _all_ids() if e != "t5"]
    _write(labels, "kodiac_cloud", _label_rows("kodiac", ids, lambda e: True, is_mock=False))
    arms = assemble_proof_arms(_manifest(tmp_path), labels)
    assert "t5" not in arms["kodiac_cloud"]
    assert arms.provenance["kodiac_cloud"]["coverage"] < 1.0


def test_salvage_needs_measured_t_star_not_manifest_onset(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    manifest = tmp_path / "manifest.json"
    rows = json.loads(_manifest(tmp_path).read_text())
    for r in rows:
        r["onset_frame"] = 90  # ground-truth injected onset must never be used for salvage
    manifest.write_text(json.dumps(rows))
    _write(labels, "kodiac_cloud", _label_rows("kodiac", _all_ids(), lambda e: e == "t0", is_mock=False))
    arms = assemble_proof_arms(manifest, labels)
    assert "kodiac_salvage" not in arms
    assert "t_star_frame" in arms.absent["kodiac_salvage"]

    _write(
        labels,
        "kodiac_cloud",
        _label_rows("kodiac", _all_ids(), lambda e: e == "t0", is_mock=False, t_star=lambda e: 45 if e == "t1" else 10),
    )
    arms = assemble_proof_arms(manifest, labels)
    assert "t1_prefix" in arms["kodiac_salvage"] and "t2_prefix" not in arms["kodiac_salvage"]
    assert arms["kodiac_salvage"][0] == "t0"


def test_score_judge_threshold_is_fitted_on_calibration_only(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    rows = []
    for e in _all_ids():
        truth = int(e[1:]) % 2 == 0
        score = 0.8 if truth else 0.3
        rows.append(
            {"judge": "robometer-4b", "episode_id": e, "accept": score >= 0.65, "score": score,
             "latency_ms": 1, "cost_usd": 0.0, "is_mock": False, "evidence_type": "live"}
        )
    _write(labels, "robometer-4b", rows)
    arms = assemble_proof_arms(_manifest(tmp_path), labels)
    assert sorted(arms["robometer_4b"]) == sorted(e for e in arms["oracle"])


def test_missing_oracle_column_or_train_split_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"episode_id": "a"}]))
    with pytest.raises(ValueError):
        assemble_proof_arms(bad, tmp_path / "labels")
    only_cal = tmp_path / "cal.json"
    only_cal.write_text(json.dumps([{"episode_id": "a", "split": "calibration", "oracle_success": True}]))
    with pytest.raises(ValueError, match="train"):
        assemble_proof_arms(only_cal, tmp_path / "labels")


def test_dose_arm_absent_when_not_enough_failures(tmp_path: Path) -> None:
    rows = [{"episode_id": f"t{i}", "split": "train", "oracle_success": True} for i in range(20)]
    m = tmp_path / "m.json"
    m.write_text(json.dumps(rows))
    arms = assemble_proof_arms(m, tmp_path / "labels")
    assert "oracle_k_10" not in arms and "oracle-failed" in arms.absent["oracle_k_10"]
