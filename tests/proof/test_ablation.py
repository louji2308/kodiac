"""Tests for proof/ablation.py (T09). Counts below are SYNTHETIC / hand-built."""

from __future__ import annotations

import pytest

from Kodiac_robotics.proof import ablation as A
from Kodiac_robotics.proof import stats as S


def _r(tn: int, fp: int, **kw) -> dict:
    base = {"tn": tn, "fp": fp, "benchmark": "bench-v1", "synthetic": False, "is_mock": False}
    base.update(kw)
    return base


def test_newcombe_known_answer() -> None:
    # Newcombe (1998), Stat Med 17:873, example 56/70 vs 48/80, method 10: +0.0524 to +0.3339
    d, lo, hi = A.newcombe_diff_ci(56, 70, 48, 80)
    assert d == pytest.approx(0.2)
    assert lo == pytest.approx(0.0524, abs=1e-3)
    assert hi == pytest.approx(0.3339, abs=1e-3)


def test_empty_ladder_is_not_measured() -> None:
    lad = A.ablation_ladder({})
    assert lad["status"] == S.STATUS_NOT_MEASURED
    assert [r["rung"] for r in lad["rungs"]] == ["R1", "R2", "R3", "R4", "R5"]
    assert all(r["status"] == S.STATUS_NOT_MEASURED and r["statement"] is None for r in lad["rungs"])


def test_full_measured_ladder_phrasing() -> None:
    res = {f"R{i}": _r(60 + 5 * i, 40 - 5 * i) for i in range(1, 6)}
    lad = A.ablation_ladder(res)
    assert lad["status"] == S.STATUS_MEASURED
    r2 = lad["rungs"][1]
    assert r2["specificity"]["value"] == pytest.approx(70 / 100)
    assert r2["adds_points"]["value"] == pytest.approx(5.0)
    assert r2["statement"].startswith("R2 (+ Spark single question) adds +5.0 points of specificity")
    assert lad["rungs"][0]["adds_points"] is None
    assert all("Meta model" not in (r["statement"] or "") for r in lad["rungs"])


def test_missing_rung_breaks_the_step_and_marks_partial() -> None:
    res = {"R1": _r(60, 40), "R2": _r(70, 30), "R4": _r(80, 20), "R5": _r(85, 15)}
    lad = A.ablation_ladder(res)
    assert lad["status"] == A.STATUS_PARTIAL
    r3, r4 = lad["rungs"][2], lad["rungs"][3]
    assert r3["status"] == S.STATUS_NOT_MEASURED
    assert r4["adds_points"] is None and r4["statement"] is None
    assert lad["rungs"][4]["adds_points"]["value"] == pytest.approx(5.0)


def test_synthetic_and_undeclared_rungs_are_flagged() -> None:
    lad = A.ablation_ladder({"R1": _r(60, 40, synthetic=True), "R2": _r(70, 30)})
    assert lad["status"] == S.STATUS_SYNTHETIC and lad["synthetic"] is True
    assert lad["rungs"][1]["statement"].startswith("[SYNTHETIC TEST DATA] ")
    undeclared = {"tn": 5, "fp": 5, "benchmark": "bench-v1"}
    lad2 = A.ablation_ladder({"R1": undeclared})
    assert lad2["rungs"][0]["status"] == S.STATUS_SYNTHETIC and lad2["is_mock"] is True


def test_benchmark_mismatch_and_bad_keys() -> None:
    lad = A.ablation_ladder({"R1": _r(60, 40), "R2": _r(70, 30, benchmark="other")})
    assert lad["rungs"][1]["adds_points"] is None and "benchmark differs" in lad["rungs"][1]["note"]
    with pytest.raises(ValueError, match="unknown ablation rungs"):
        A.ablation_ladder({"R6": _r(1, 1)})
    zero = A.ablation_ladder({"R1": _r(0, 0)})
    assert zero["rungs"][0]["status"] == S.STATUS_NOT_MEASURED
