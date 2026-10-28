"""Baseline judges for proof experiment comparison.

Implements Single-pass Muse Spark 1.3 (2 fps), Robometer-4B, and TOPReward runners
per ARCHITECTURE.md §5.7 and P02 RULING.
"""

from __future__ import annotations

from Kodiac_robotics.proof.judges.robometer import RobometerJudge
from Kodiac_robotics.proof.judges.single_pass import SinglePassSparkJudge
from Kodiac_robotics.proof.judges.topreward import TOPRewardJudge

__all__ = [
    "RobometerJudge",
    "SinglePassSparkJudge",
    "TOPRewardJudge",
]
