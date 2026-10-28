"""Unit tests for the teleoperation labeling tool and A/B timing study runner.

Verifies:
- TimingRecord schema validation (frozen contract per T03 §3).
- Strict data isolation between blind evaluation slice and timing study.
- Manifest generation for DROID evaluation slice (200 episodes).
- Telemetry generation and schema conformance.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project root so scripts package is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from scripts.label_tool import (  # noqa: E402
    TimingRecord,
    generate_droid_slice_episodes,
    generate_timing_audit_episodes,
    run_test_telemetry,
)


def test_timing_record_validation():
    valid = TimingRecord(
        session_id="test_sess_01",
        annotator="annotator_alice",
        episode_id="droid_ep_0042",
        dataset="alexander-soare/droid_100",
        mode="blame",
        time_to_verdict_ms=3150.5,
        verdict="FAIL",
        notes="Grip slip detected",
    )
    assert valid.mode == "blame"
    assert valid.time_to_verdict_ms == 3150.5
    assert valid.verdict == "FAIL"


def test_timing_record_invalid_mode():
    with pytest.raises(ValidationError):
        TimingRecord(
            session_id="s1",
            annotator="bob",
            episode_id="ep1",
            dataset="droid",
            mode="manual_scrubbing",  # Must be 'scrub' or 'blame'
            time_to_verdict_ms=5000.0,
            verdict="PASS",
        )


def test_timing_record_invalid_verdict():
    with pytest.raises(ValidationError):
        TimingRecord(
            session_id="s1",
            annotator="bob",
            episode_id="ep1",
            dataset="droid",
            mode="scrub",
            time_to_verdict_ms=5000.0,
            verdict="MAYBE",  # Must be PASS, FAIL, or CANT_TELL
        )


def test_timing_record_invalid_time():
    with pytest.raises(ValidationError):
        TimingRecord(
            session_id="s1",
            annotator="bob",
            episode_id="ep1",
            dataset="droid",
            mode="scrub",
            time_to_verdict_ms=-100.0,  # Must be > 0
            verdict="PASS",
        )


def test_blind_slice_strict_data_isolation():
    slice_eps = generate_droid_slice_episodes(count=200)
    assert len(slice_eps) == 200

    for ep in slice_eps:
        # Strict isolation invariants:
        assert "blame_hint" not in ep, "Leaked blame_hint in blind slice"
        assert "verdict" not in ep, "Leaked verdict in blind slice"
        assert "failure_predicate" not in ep, "Leaked failure_predicate in blind slice"
        assert "t_star" not in ep, "Leaked t_star in blind slice"
        assert ep["source_kind"] == "real", "DROID slice must be real robot footage"
        assert "video_url" in ep
        assert "task" in ep


def test_timing_audit_episodes_structure():
    audit_eps = generate_timing_audit_episodes(count=40)
    assert len(audit_eps) == 40
    for ep in audit_eps:
        assert "blame_hint" in ep
        hint = ep["blame_hint"]
        assert "t_star" in hint
        assert "predicate" in hint
        assert "explanation" in hint


def test_run_test_telemetry(tmp_path: Path):
    res = run_test_telemetry(
        annotator="ci_runner",
        episodes_count=40,
        output_dir=tmp_path,
    )
    assert res == 0

    timing_file = tmp_path / "timing_ci_runner.jsonl"
    blind_file = tmp_path / "droid_slice_ci_runner.jsonl"

    assert timing_file.exists()
    assert blind_file.exists()

    with open(timing_file, "r", encoding="utf-8") as f:
        timing_lines = [json.loads(line) for line in f if line.strip()]

    assert len(timing_lines) == 40
    modes = {r["mode"] for r in timing_lines}
    assert "scrub" in modes
    assert "blame" in modes

    for rec in timing_lines:
        parsed = TimingRecord(**rec)
        assert parsed.time_to_verdict_ms > 0
        assert parsed.verdict in ("PASS", "FAIL", "CANT_TELL")
