"""Robometer-4B baseline judge (PREREGISTRATION §4 arm 7).

Status: **no Robometer inference is implemented or has been run.** Loading the 4B model needs weights and a
GPU (Modal L4); neither is available and the model's loading/scoring API has not been verified
([UNVERIFIED]). Therefore :meth:`RobometerJudge.evaluate_episode` raises :class:`JudgeUnavailable` unless
the caller supplies a ``scorer`` (a function that really runs the model on an episode and returns a
reward score). The score is then thresholded; the label carries the provenance the caller declares
(``"live"`` for a real model run, ``"fixture"`` for a recorded replay).
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


class RobometerJudge:
    """Robometer-4B harness: needs a real scorer, otherwise fails closed."""

    def __init__(
        self,
        calibration_threshold: float = 0.65,
        model_name: str = "robometer-4b",
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
        video_path: str | Path | None = None,
        task_instruction: str = "Stack Cube A onto Cube B.",
    ) -> JudgeLabel:
        """Score an episode and classify it against the (calibration-fitted) threshold."""
        if self.scorer is None or self.provenance is None:
            raise JudgeUnavailable(
                "Robometer-4B has not been run: no scorer is configured (needs model weights + GPU; "
                "no inference backend is implemented). Judge not run."
            )
        if video_path is None:
            raise JudgeUnavailable(f"Robometer-4B needs a video for episode {episode_id!r}")
        start = time.perf_counter()
        score = float(self.scorer(str(video_path)))
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
