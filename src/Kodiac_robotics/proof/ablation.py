"""Ablation ladder R1..R5 (IMPLEMENTATION_PLAN P08.S07, IDEA §8 P-5).

Each rung adds one stage on the same benchmark. The reported metric is specificity
``TN / (TN + FP)`` (= 1 - false-PASS, PREREG §6 definition), CAN'T TELL counted as not accepted
(PREREG §4 arm 3). Allowed phrasing: "each stage adds +X points of specificity" — never "each Meta model
adds" (not every rung is a model, IDEA §8).

Rungs with no result are ``NOT_MEASURED``; synthetic, mock, or undeclared-provenance rungs are
``SYNTHETIC_TEST_ONLY``. A step ("adds") is computed only between two adjacent rungs that both have
data on the same benchmark; its CI is Newcombe's hybrid score interval (method 10) for a difference of
two independent proportions (conservative when the rungs are evaluated on the same episodes).
"""

from __future__ import annotations

import math
from typing import Any

from Kodiac_robotics.proof.stats import (
    STATUS_MEASURED,
    STATUS_NOT_MEASURED,
    STATUS_SYNTHETIC,
    wilson_ci,
)

RUNGS: tuple[tuple[str, str], ...] = (
    ("R1", "SAM + predicates (looks -> CAN'T TELL)"),
    ("R2", "+ Spark single question"),
    ("R3", "+ two-way"),
    ("R4", "+ Wonder"),
    ("R5", "+ calibrated sigma"),
)
STATUS_PARTIAL = "PARTIAL"


def newcombe_diff_ci(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float, float]:
    """``(p1 - p2, lo, hi)`` with Newcombe (1998) method-10 hybrid Wilson score 95% CI."""
    p1 = k1 / n1
    p2 = k2 / n2
    l1, u1 = wilson_ci(k1, n1)
    l2, u2 = wilson_ci(k2, n2)
    d = p1 - p2
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return d, lo, hi


def _rung_entry(rung: str, label: str, res: dict | None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "rung": rung,
        "label": label,
        "status": STATUS_NOT_MEASURED,
        "benchmark": None,
        "specificity": None,
        "sensitivity": None,
        "synthetic": False,
        "is_mock": False,
        "adds_points": None,
        "statement": None,
        "note": None,
    }
    if not res:
        entry["note"] = "no result for this rung"
        return entry
    tn = int(res.get("tn", 0))
    fp = int(res.get("fp", 0))
    if tn < 0 or fp < 0:
        raise ValueError(f"{rung}: counts must be >= 0")
    declared = res.get("is_mock") is not None
    entry["synthetic"] = bool(res.get("synthetic", False))
    entry["is_mock"] = bool(res["is_mock"]) if declared else True
    entry["benchmark"] = res.get("benchmark")
    if tn + fp == 0:
        entry["note"] = "no oracle-negative episodes: specificity undefined"
        return entry
    lo, hi = wilson_ci(tn, tn + fp)
    entry["specificity"] = {"value": tn / (tn + fp), "lo": lo, "hi": hi, "k": tn, "n": tn + fp}
    if "tp" in res and "fn" in res:
        tp, fn = int(res["tp"]), int(res["fn"])
        if tp + fn > 0:
            slo, shi = wilson_ci(tp, tp + fn)
            entry["sensitivity"] = {"value": tp / (tp + fn), "lo": slo, "hi": shi, "k": tp,
                                    "n": tp + fn}
    if not declared:
        entry["note"] = "provenance undeclared: treated as is_mock=True (fail closed)"
    flagged = entry["synthetic"] or entry["is_mock"]
    entry["status"] = STATUS_SYNTHETIC if flagged else STATUS_MEASURED
    return entry


def ablation_ladder(rung_results: dict[str, dict]) -> dict:
    """Build the R1..R5 ladder from ``{"R1": {"tn": .., "fp": .., ["tp", "fn"], "benchmark": str,
    "synthetic": bool, "is_mock": bool}, ...}``. Unknown rung keys raise ``ValueError``."""
    known = {r for r, _ in RUNGS}
    unknown = sorted(set(rung_results) - known)
    if unknown:
        raise ValueError(f"unknown ablation rungs {unknown}; expected {sorted(known)}")
    entries = [_rung_entry(r, label, rung_results.get(r)) for r, label in RUNGS]
    for prev, cur in zip(entries, entries[1:]):
        if prev["specificity"] is None or cur["specificity"] is None:
            continue
        if prev["benchmark"] != cur["benchmark"]:
            cur["note"] = f"benchmark differs from {prev['rung']}: step not computed"
            continue
        a, b = cur["specificity"], prev["specificity"]
        d, lo, hi = newcombe_diff_ci(a["k"], a["n"], b["k"], b["n"])
        cur["adds_points"] = {"value": 100 * d, "lo": 100 * lo, "hi": 100 * hi,
                              "ci_method": "newcombe_hybrid_score"}
        prefix = "" if cur["status"] == STATUS_MEASURED and prev["status"] == STATUS_MEASURED else (
            "[SYNTHETIC TEST DATA] "
        )
        cur["statement"] = (
            f"{prefix}{cur['rung']} ({cur['label']}) adds {100 * d:+.1f} points of specificity "
            f"over {prev['rung']} (95% CI [{100 * lo:+.1f}, {100 * hi:+.1f}], n={a['n']})"
        )
    statuses = [e["status"] for e in entries]
    synthetic = any(e["synthetic"] for e in entries)
    is_mock = any(e["is_mock"] for e in entries if e["status"] != STATUS_NOT_MEASURED)
    if STATUS_SYNTHETIC in statuses:
        overall = STATUS_SYNTHETIC
    elif all(s == STATUS_MEASURED for s in statuses):
        overall = STATUS_MEASURED
    elif any(s == STATUS_MEASURED for s in statuses):
        overall = STATUS_PARTIAL
    else:
        overall = STATUS_NOT_MEASURED
    return {
        "status": overall,
        "synthetic": synthetic,
        "is_mock": is_mock,
        "metric": "specificity = TN / (TN + FP) = 1 - false-PASS; CAN'T TELL counted as not accepted",
        "phrasing": "each stage adds",
        "source": "IMPLEMENTATION_PLAN P08.S07; IDEA §8 P-5; PREREG §6 (false-PASS definition)",
        "rungs": entries,
    }
