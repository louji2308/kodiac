"""TEST-ONLY utilities. Never import this module from production code or a CLI default.

``OracleCopyDouble`` copies a ground-truth answer into a ``JudgeLabel`` so unit tests can exercise label
plumbing. It is **not a judge**: it knows the answer. Every label it emits is marked
``is_mock=True, evidence_type="synthetic"`` and its judge name ends in ``(oracle-copy test double)``.
``tests/proof/test_no_oracle_leak.py`` enforces that nothing under ``src/`` imports this module.
"""

from __future__ import annotations

from Kodiac_robotics.contracts.core import JudgeLabel, Verdict

DOUBLE_SUFFIX = " (oracle-copy test double)"


class OracleCopyDouble:
    """Echoes a supplied ground-truth boolean as a mock-marked label."""

    def __init__(self, judge: str = "double") -> None:
        self.judge = judge + DOUBLE_SUFFIX

    def label(self, episode_id: str, truth: bool) -> JudgeLabel:
        return JudgeLabel(
            judge=self.judge,
            episode_id=episode_id,
            accept=bool(truth),
            score=1.0 if truth else 0.0,
            verdict=Verdict.PASS if truth else Verdict.FAIL,
            latency_ms=0,
            cost_usd=0.0,
            is_mock=True,
            evidence_type="synthetic",
        )
