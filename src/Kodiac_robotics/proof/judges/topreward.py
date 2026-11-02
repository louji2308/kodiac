"""TOPReward baseline judge (PREREGISTRATION §4 arm 8, LeRobot v0.6 ``lerobot.rewards``).

Status: **no TOPReward inference is implemented or has been run.** The ``lerobot.rewards`` interface has not
been verified here ([UNVERIFIED]) and no model/GPU is available. :meth:`TOPRewardJudge.evaluate_episode`
therefore raises :class:`JudgeUnavailable` unless the caller supplies a ``scorer`` that really runs the
model on an episode and returns a reward score, plus the provenance of that scorer (``"live"`` or
``"fixture"``).
"""

from __future__ import annotations

import time
from pathlib import Path

from Kodiac_robotics.contracts.core import JudgeLabel
from Kodiac_robotics.proof.judges.base import (
    JudgeUnavailable,
    Provenance,
    ScoreFn,
    score_label,
    tune_threshold,
)


class TOPRewardJudge:
    """Trajectory-level reward judge: needs a real scorer, otherwise fails closed."""

    def __init__(
        self,
        calibration_threshold: float = 0.60,
        model_name: str = "topreward-lerobot-v0.6",
        scorer: ScoreFn | None = None,
        provenance: Provenance | None = None,
    ) -> None:
        if scorer is not None and provenance is None:
            raise ValueError("a scorer requires an explicit provenance: 'live' or 'fixture'")
        self.calibration_threshold = calibration_threshold
        self.model_name = model_name
        self.scorer = scorer
        self.provenance = provenance

    def evaluate_episode(
        self,
        episode_id: str,
        state_npz_path: str | Path | None = None,
    ) -> JudgeLabel:
        """Score an episode's state/action sequence and classify it against the threshold."""
        if self.scorer is None or self.provenance is None:
            raise JudgeUnavailable(
                "TOPReward has not been run: no scorer is configured (no lerobot.rewards backend "
                "is implemented). Judge not run."
            )
        if state_npz_path is None:
            raise JudgeUnavailable(f"TOPReward needs a state file for episode {episode_id!r}")
        start = time.perf_counter()
        score = float(self.scorer(str(state_npz_path)))
        return score_label(
            judge=self.model_name,
            episode_id=episode_id,
            score=score,
            threshold=self.calibration_threshold,
            latency_ms=int((time.perf_counter() - start) * 1000),
            provenance=self.provenance,
        )

    def tune_threshold_on_calibration(
        self,
        calibration_labels: list[tuple[float, bool]],
    ) -> float:
        """Fit the score threshold maximising balanced accuracy on ``(score, truth)`` calibration pairs."""
        self.calibration_threshold = tune_threshold(calibration_labels, self.calibration_threshold)
        return self.calibration_threshold
