"""Unit tests for baseline judges: Single-pass Spark 1.3, Robometer-4B, and TOPReward.

Verifies JudgeLabel contract compliance and calibration tuning per ARCHITECTURE.md §5.7.
"""

from __future__ import annotations

import pytest

from Kodiac_robotics.contracts.core import JudgeLabel, Verdict
from Kodiac_robotics.proof.judges.robometer import RobometerJudge
from Kodiac_robotics.proof.judges.single_pass import SinglePassSparkJudge
from Kodiac_robotics.proof.judges.topreward import TOPRewardJudge


def test_single_pass_spark_judge_contract() -> None:
    """Verify SinglePassSparkJudge outputs valid JudgeLabel instances."""
    judge = SinglePassSparkJudge()
    label = judge.evaluate_episode(
        episode_id="ep_001_train",
        video_path=None,  # Offline fallback
        oracle_success_hint=True,
    )

    assert isinstance(label, JudgeLabel)
    assert label.judge == "single_pass_spark_1.3"
    assert label.episode_id == "ep_001_train"
    assert label.accept is True
    assert label.verdict == Verdict.PASS
    assert label.score is not None
    assert label.cost_usd > 0.0


def test_robometer_judge_and_calibration_tuning() -> None:
    """Verify RobometerJudge scoring and threshold tuning on calibration split."""
    judge = RobometerJudge(calibration_threshold=0.60)
    label = judge.evaluate_episode(
        episode_id="ep_002_train",
        oracle_success_hint=False,
    )

    assert isinstance(label, JudgeLabel)
    assert label.judge == "robometer-4b"
    assert label.accept is False
    assert label.verdict == Verdict.FAIL

    # Test calibration threshold tuning
    cal_data = [
        (0.85, True),
        (0.75, True),
        (0.65, True),
        (0.55, False),
        (0.40, False),
        (0.20, False),
    ]
    tuned_tau = judge.tune_threshold_on_calibration(cal_data)
    assert 0.50 <= tuned_tau <= 0.70


def test_topreward_judge_contract() -> None:
    """Verify TOPRewardJudge scoring and threshold tuning."""
    judge = TOPRewardJudge(calibration_threshold=0.55)
    label = judge.evaluate_episode(
        episode_id="ep_003_train",
        oracle_success_hint=True,
    )

    assert isinstance(label, JudgeLabel)
    assert label.judge == "topreward-lerobot-v0.6"
    assert label.accept is True
    assert label.verdict == Verdict.PASS
