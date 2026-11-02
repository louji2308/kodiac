"""Shared pieces for the baseline judges (fail-closed provenance rules, Law 1).

A baseline judge either calls a real model (``is_mock=False, evidence_type="live"``), replays a recorded
response (``is_mock=True, evidence_type="fixture"``), or raises :class:`JudgeUnavailable`. It never
returns a decision it did not obtain from a model, and no judge in this package reads ground truth.
"""

from __future__ import annotations

from typing import Callable, Literal

from Kodiac_robotics.contracts.core import JudgeLabel, Verdict

Provenance = Literal["live", "fixture"]

#: Maps one episode's video/state path to a continuous reward score, supplied by a real model runner.
ScoreFn = Callable[[str], float]


class JudgeUnavailable(RuntimeError):
    """The model, API key, weights, GPU, or input needed to run this judge is not available.

    Raised instead of returning a stand-in decision. Callers must treat the judge as *not run*.
    """


def provenance_flags(provenance: Provenance) -> tuple[bool, Provenance]:
    """Return ``(is_mock, evidence_type)`` for a label produced under ``provenance``."""
    if provenance == "live":
        return False, "live"
    if provenance == "fixture":
        return True, "fixture"
    raise ValueError(f"provenance must be 'live' or 'fixture', got {provenance!r}")


def score_label(
    *,
    judge: str,
    episode_id: str,
    score: float,
    threshold: float,
    latency_ms: int,
    provenance: Provenance,
    cost_usd: float = 0.0,
) -> JudgeLabel:
    """Build a score-judge label (``accept = score >= threshold``) carrying explicit provenance."""
    if score != score:  # NaN
        raise ValueError(f"{judge}: model returned a NaN score for {episode_id}")
    is_mock, evidence = provenance_flags(provenance)
    accept = float(score) >= float(threshold)
    return JudgeLabel(
        judge=judge,
        episode_id=episode_id,
        accept=accept,
        score=float(score),
        verdict=Verdict.PASS if accept else Verdict.FAIL,
        latency_ms=max(0, int(latency_ms)),
        cost_usd=float(cost_usd),
        calibration_threshold=float(threshold),
        is_mock=is_mock,
        evidence_type=evidence,
    )


def tune_threshold(
    calibration_pairs: list[tuple[float, bool]], default: float
) -> float:
    """Threshold maximising balanced accuracy over ``(score, is_success)`` calibration pairs.

    Pure function of the pairs it is given; the caller is responsible for passing calibration-split
    rows only (PREREGISTRATION §3).
    """
    if not calibration_pairs:
        return default
    best_ba, best_tau = -1.0, default
    for tau in (i / 100.0 for i in range(10, 90, 5)):
        tp = sum(1 for s, y in calibration_pairs if s >= tau and y)
        fn = sum(1 for s, y in calibration_pairs if s < tau and y)
        tn = sum(1 for s, y in calibration_pairs if s < tau and not y)
        fp = sum(1 for s, y in calibration_pairs if s >= tau and not y)
        ba = 0.5 * (tp / max(1, tp + fn) + tn / max(1, tn + fp))
        if ba > best_ba:
            best_ba, best_tau = ba, tau
    return best_tau
