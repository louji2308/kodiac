"""Baseline judges for proof experiment comparison.

Single-pass Muse Spark 1.3 (2 fps), Robometer-4B, and TOPReward runners per ARCHITECTURE.md §5.7.
Each raises :class:`JudgeUnavailable` when it cannot really run; none reads ground truth.
"""

from __future__ import annotations

from Kodiac_robotics.proof.judges.base import JudgeUnavailable
from Kodiac_robotics.proof.judges.robometer import RobometerJudge
from Kodiac_robotics.proof.judges.single_pass import SinglePassSparkJudge
from Kodiac_robotics.proof.judges.topreward import TOPRewardJudge

__all__ = [
    "JudgeUnavailable",
    "RobometerJudge",
    "SinglePassSparkJudge",
    "TOPRewardJudge",
]
