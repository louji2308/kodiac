"""Known-answer tests for proof/stats.py (T09). All data here is SYNTHETIC or hand-built."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from Kodiac_robotics.proof import labels as L
from Kodiac_robotics.proof import stats as S

FX = Path(__file__).resolve().parents[1] / "fixtures" / "proof"
REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------- Wilson / Holm / McNemar / t


def test_wilson_hand_computed_values() -> None:
    # k=0: upper = z^2 / (n + z^2) = 3.841459 / 70.841459
    lo, hi = S.wilson_ci(0, 67)
    assert lo == 0.0
    assert hi == pytest.approx(0.0542263, abs=1e-6)
    # k=33, n=100: centre (0.33 + z^2/200) / (1 + z^2/100), half-width by the Wilson formula
    lo, hi = S.wilson_ci(33, 100)
    assert lo == pytest.approx(0.245628, abs=1e-5)
    assert hi == pytest.approx(0.426950, abs=1e-5)
    assert S.wilson_ci(10, 10)[1] == 1.0


def test_wilson_matches_scipy_reference() -> None:
    stats = pytest.importorskip("scipy.stats")
    for k, n in [(0, 67), (33, 100), (1, 5), (199, 200), (57, 800)]:
        ref = stats.binomtest(k, n).proportion_ci(method="wilson")
        lo, hi = S.wilson_ci(k, n)
        assert lo == pytest.approx(ref.low, abs=1e-6)
        assert hi == pytest.approx(ref.high, abs=1e-6)


@pytest.mark.parametrize("k,n", [(0, 0), (-1, 5), (6, 5)])
def test_wilson_rejects_invalid(k: int, n: int) -> None:
    with pytest.raises(ValueError):
        S.wilson_ci(k, n)


def test_holm_hand_example() -> None:
    adj = S.holm_adjust({"a": 0.01, "b": 0.04, "c": 0.03, "d": 0.005})
    # sorted: d .005*4=.02, a .01*3=.03, c .03*2=.06, b .04*1=.04 -> monotone max .06
    assert adj == pytest.approx({"d": 0.02, "a": 0.03, "c": 0.06, "b": 0.06})


def test_holm_keeps_degenerate_tests_in_family() -> None:
    adj = S.holm_adjust({"a": 0.01, "b": None})
    assert adj["a"] == pytest.approx(0.02)  # family size stays 2
    assert adj["b"] == 1.0


def test_mcnemar_exact_matches_scipy_binomtest() -> None:
    stats = pytest.importorskip("scipy.stats")
    for b, c in [(1, 3), (3, 11), (0, 9), (20, 13), (7, 7), (37, 11), (150, 120)]:
        ref = stats.binomtest(min(b, c), b + c, 0.5).pvalue
        assert S.mcnemar_exact_p(b, c) == pytest.approx(ref, rel=1e-9)
    assert S.mcnemar_exact_p(0, 0) == 1.0
    assert S.mcnemar_exact_p(1, 3) == pytest.approx(0.625)  # 2 * 5/16


def test_welch_matches_scipy_and_ci_agrees_with_p() -> None:
    stats = pytest.importorskip("scipy.stats")
    a = {1: [0.6, 0.7], 2: [0.5, 0.55], 3: [0.8, 0.6]}
    b = {1: [0.4], 2: [0.45], 3: [0.5]}
    w = S.welch_seed_means(a, b)
    ref = stats.ttest_ind([0.65, 0.525, 0.7], [0.4, 0.45, 0.5], equal_var=False)
    assert w["t"] == pytest.approx(ref.statistic, rel=1e-9)
    assert w["p"] == pytest.approx(ref.pvalue, rel=1e-7)
    assert S.t_quantile_975(w["df"]) == pytest.approx(stats.t.ppf(0.975, w["df"]), rel=1e-7)
    assert (w["ci"][0] > 0) == (w["p"] < 0.05)


def test_welch_degenerate_inputs() -> None:
    assert S.welch_seed_means({1: [1.0]}, {1: [0.0], 2: [0.0]})["p"] is None
    w = S.welch_seed_means({1: [1.0], 2: [1.0]}, {1: [0.0], 2: [0.0]})
    assert w["p"] is None and "zero between-seed variance" in w["note"]


# ---------------------------------------------------------------- bootstrap


def test_hier_bootstrap_contains_known_mean_and_covers() -> None:
    truth = 0.6
    rng = np.random.default_rng(123)
    data = {s: (rng.random(200) < truth).astype(float).tolist() for s in (42, 43, 44)}
    mean, lo, hi = S.hier_bootstrap_mean_ci(data, n_boot=10000, seed=0)
    assert lo < truth < hi
    assert mean == pytest.approx(np.mean([np.mean(v) for v in data.values()]))
    covered = 0
    for sim in range(100):
        r = np.random.default_rng(1000 + sim)
        d = {s: (r.random(200) < truth).astype(float).tolist() for s in (1, 2, 3)}
        _, lo, hi = S.hier_bootstrap_mean_ci(d, n_boot=2000, seed=sim)
        covered += lo <= truth <= hi
    assert covered >= 90  # nominal 95%; seed resampling with 3 seeds is conservative


def test_hier_bootstrap_is_seeded() -> None:
    data = {1: [0, 1, 1, 0, 1], 2: [1, 1, 0, 1, 1]}
    assert S.hier_bootstrap_mean_ci(data, 500, 7) == S.hier_bootstrap_mean_ci(data, 500, 7)


def test_delta_ci_identical_paired_arms_is_exactly_zero() -> None:
    rng = np.random.default_rng(5)
    a = {s: (rng.random(200) < 0.5).astype(float).tolist() for s in (1, 2, 3)}
    assert tuple(S.delta_ci(a, dict(a), n_boot=2000)) == (0.0, 0.0, 0.0)


def test_delta_ci_pairing_narrows_interval_on_correlated_arms() -> None:
    arms = L.load_arm_evals(FX / "evals_SYNTHETIC")
    a, b = arms["kodiac"], arms["single_pass"]
    d, lo, hi = S.delta_ci(a, b, n_boot=4000)
    b_unpaired = {s + 100: v for s, v in b.items()}  # different seed ids => independent resampling
    d2, lo2, hi2 = S.delta_ci(a, b_unpaired, n_boot=4000)
    assert d == pytest.approx(d2)
    assert lo < d < hi
    assert (hi - lo) < (hi2 - lo2)


def test_bootstrap_outputs_propagate_synthetic_flag() -> None:
    arms = L.load_arm_evals(FX / "evals_SYNTHETIC")
    ci = S.hier_bootstrap_mean_ci(arms["kodiac"], n_boot=200)
    assert ci.synthetic is True
    assert S.delta_ci(arms["kodiac"], arms["single_pass"], n_boot=200).synthetic is True
    plain = S.hier_bootstrap_mean_ci({1: [1.0, 0.0]}, n_boot=200)
    assert plain.synthetic is False and plain.is_mock is True  # undeclared => fail closed


# ---------------------------------------------------------------- judge metrics on a hand example


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def _lab(judge: str, ep: str, accept: bool, verdict: str | None, score: float | None = None) -> dict:
    return {"judge": judge, "episode_id": ep, "accept": accept, "verdict": verdict, "score": score,
            "latency_ms": 0, "cost_usd": 0.0, "synthetic": True, "is_mock": False}


@pytest.fixture()
def hand_frame(tmp_path: Path):
    oracle = L.OracleLabels(
        {"e1": True, "e2": True, "e3": True, "e4": False, "e5": False, "e6": False,
         "c1": True, "c2": False},
        synthetic=True, is_mock=False,
    )
    rows = [
        _lab("kodiac", "e1", True, "PASS"),
        _lab("kodiac", "e2", True, "CANT_TELL"),  # must be forced to "not accepted"
        _lab("kodiac", "e3", False, "FAIL"),
        _lab("kodiac", "e4", False, "FAIL"),
        _lab("kodiac", "e5", True, "PASS"),  # false PASS; e6 deliberately missing
        _lab("kodiac", "c1", True, "PASS"),
        _lab("kodiac", "c2", True, "PASS"),  # calibration row: must not count on train
    ]
    rows += [
        _lab("single_pass", e, acc, "PASS" if acc else "FAIL")
        for e, acc in [("e1", True), ("e2", True), ("e3", True), ("e4", True), ("e5", False),
                       ("e6", False), ("c1", True), ("c2", False)]
    ]
    df = L.load_labels([_write_jsonl(tmp_path / "SYNTHETIC_hand.jsonl", rows)])
    return L.apply_thresholds(df, {"c1", "c2"}, oracle), oracle


def test_judge_metrics_hand_example(hand_frame) -> None:
    df, oracle = hand_frame
    m = S.judge_metrics(df, oracle, split="train")
    assert m["n_episodes"] == 6 and m["status"] == S.STATUS_SYNTHETIC and m["synthetic"] is True
    k = m["judges"]["kodiac"]
    assert k["confusion"] == {"tp": 1, "fp": 1, "tn": 2, "fn": 2}
    assert k["false_pass"]["value"] == pytest.approx(1 / 3)
    assert (k["false_pass"]["lo"], k["false_pass"]["hi"]) == pytest.approx(S.wilson_ci(1, 3))
    assert k["false_reject"]["value"] == pytest.approx(2 / 3)
    assert k["coverage"]["value"] == pytest.approx(4 / 6)
    assert k["contamination"]["value"] == pytest.approx(0.5)
    assert k["balanced_accuracy"]["value"] == pytest.approx(0.5)
    assert (k["n_missing"], k["n_cant_tell"]) == (1, 1)
    assert k["auroc"]["basis"] == "binary_accept"
    s = m["judges"]["single_pass"]
    assert s["confusion"] == {"tp": 3, "fp": 1, "tn": 2, "fn": 0}
    assert s["coverage"]["value"] == 1.0


def test_mcnemar_holm_hand_example(hand_frame) -> None:
    df, oracle = hand_frame
    r = S.mcnemar_holm(df, oracle, ref_judge="Kodiac")
    assert r["ref_judge"] == "kodiac"
    c = r["comparisons"]["single_pass"]
    assert (c["primary"]["b"], c["primary"]["c"]) == (1, 3)
    assert c["primary"]["p"] == pytest.approx(0.625)
    assert (c["false_pass"]["b"], c["false_pass"]["c"]) == (1, 1)
    assert c["false_pass"]["p"] == 1.0
    assert c["primary"]["p_holm"] == pytest.approx(0.625)  # one comparison
    assert r["synthetic"] is True


def test_judge_metrics_on_synthetic_fixture_and_auroc_reference() -> None:
    df = L.load_labels(sorted(FX.glob("SYNTHETIC_labels_*.jsonl")))
    oracle = L.load_oracle(FX / "SYNTHETIC_oracle_manifest.json")
    calib = {e for e, s in oracle.splits.items() if s == "calibration"}
    m = S.judge_metrics(L.apply_thresholds(df, calib, oracle), oracle)
    assert m["status"] == S.STATUS_SYNTHETIC
    assert m["n_episodes"] == 200  # training split only, calibration excluded
    assert all(j["synthetic"] for j in m["judges"].values())
    robo = m["judges"]["robometer-4b"]
    assert robo["threshold_source"] == "calibration_max_ba" and robo["auroc"]["basis"] == "score"
    for j in m["judges"].values():
        for key in ("balanced_accuracy", "auroc", "contamination"):
            blk = j[key]
            assert blk["lo"] <= blk["value"] <= blk["hi"]
            assert blk["n_boot_valid"] > 900
    # known structure: synthetic Kodiac errs ~5%, synthetic single-pass ~25% on negatives
    assert m["judges"]["kodiac"]["false_pass"]["value"] < m["judges"]["single_pass_spark_1.3"][
        "false_pass"]["value"]
    sk = pytest.importorskip("sklearn.metrics")
    rows = [json.loads(x) for x in (FX / "SYNTHETIC_labels_robometer.jsonl").read_text().splitlines()]
    train = [r for r in rows if oracle.splits[r["episode_id"]] == "train"]
    ref = sk.roc_auc_score([oracle[r["episode_id"]] for r in train], [r["score"] for r in train])
    assert robo["auroc"]["value"] == pytest.approx(ref, abs=1e-12)


def test_judge_metrics_requires_thresholded_frame() -> None:
    df = L.load_labels(sorted(FX.glob("SYNTHETIC_labels_kodiac.jsonl")))
    with pytest.raises(ValueError, match="apply_thresholds"):
        S.judge_metrics(df, {})


def test_judge_metrics_plain_dict_oracle_is_fail_closed(hand_frame) -> None:
    df, oracle = hand_frame
    m = S.judge_metrics(df, dict(oracle))
    assert m["is_mock"] is True and m["status"] != S.STATUS_MEASURED


# ---------------------------------------------------------------- headline (fails closed)


def _arm(p: float, seeds=(42, 43, 44), n=200, rng_seed=0, **flags) -> S.ArmSuccess:
    rng = np.random.default_rng(rng_seed)
    data = {s: (rng.random(n) < p).astype(float).tolist() for s in seeds}
    flags.setdefault("synthetic", False)
    flags.setdefault("is_mock", False)
    return S.ArmSuccess(data, source="TEST-ONLY in-memory", **flags)


def test_headline_empty_is_not_measured() -> None:
    h = S.headline({})
    assert h["status"] == S.STATUS_NOT_MEASURED
    assert h["Y_points"] is None and h["sentence"] is None and h["delta"] is None
    assert any("no trained arms" in r for r in h["reasons"])


def test_headline_requires_kodiac_and_single_pass() -> None:
    h = S.headline({"oracle": _arm(0.6), "accept_all": _arm(0.4)})
    assert h["status"] == S.STATUS_NOT_MEASURED and h["delta"] is None


def test_headline_synthetic_fixture_is_test_only() -> None:
    h = S.headline(L.load_arm_evals(FX / "evals_SYNTHETIC"))
    assert h["status"] == S.STATUS_SYNTHETIC and h["synthetic"] is True
    assert h["sentence"] is None and h["Y_points"] is None
    assert h["delta"]["points"] == pytest.approx(100 * h["delta"]["delta"])
    assert set(h["comparisons"]) == {"single_pass", "accept_all"}
    for c in h["comparisons"].values():
        assert c["p_holm"] >= c["p_welch"]
    assert [d["k_percent"] for d in h["dose_response"]] == [0, 10]
    assert any("robometer_4b" in d for d in h["prereg_deviations"])
    assert all(a["synthetic"] for a in h["arms"].values())


def test_headline_mock_or_undeclared_inputs_never_measured() -> None:
    arms = {"kodiac": _arm(0.6), "single_pass": _arm(0.5, rng_seed=1),
            "oracle": _arm(0.65, rng_seed=2), "accept_all": _arm(0.4, rng_seed=3)}
    mocked = dict(arms, accept_all=_arm(0.4, rng_seed=3, is_mock=True))
    assert S.headline(mocked)["status"] == S.STATUS_SYNTHETIC
    plain = {k: dict(v) for k, v in arms.items()}
    h = S.headline(plain)
    assert h["status"] == S.STATUS_SYNTHETIC and h["is_mock"] is True and h["sentence"] is None
    assert any("undeclared" in r for r in h["reasons"])


@pytest.mark.parametrize(
    "arms,needle",
    [
        ({"kodiac": (0.6, 200, 3), "single_pass": (0.5, 200, 3), "oracle": (0.7, 200, 3)}, "arms <"),
        ({"kodiac": (0.6, 199, 3), "single_pass": (0.5, 200, 3), "oracle": (0.7, 200, 3),
          "accept_all": (0.4, 200, 3)}, "eval episodes"),
        ({"kodiac": (0.6, 200, 1), "single_pass": (0.5, 200, 3), "oracle": (0.7, 200, 3),
          "accept_all": (0.4, 200, 3)}, "seeds <"),
    ],
)
def test_headline_real_inputs_failing_gates_withhold_numbers(arms: dict, needle: str) -> None:
    built = {
        name: _arm(p, seeds=(42, 43, 44)[:ns], n=n, rng_seed=i)
        for i, (name, (p, n, ns)) in enumerate(arms.items())
    }
    h = S.headline(built)
    assert h["status"] == S.STATUS_NOT_MEASURED
    assert h["arms"] == {} and h["delta"] is None and h["Y_points"] is None
    assert any(needle in g for g in h["gate_failures"])


def test_headline_measured_branch_on_declared_inputs() -> None:
    # TEST-ONLY: arms declared real in memory to exercise the MEASURED branch; nothing is written.
    arms = {"kodiac": _arm(0.75), "single_pass": _arm(0.45, rng_seed=1),
            "oracle": _arm(0.8, rng_seed=2), "accept_all": _arm(0.35, rng_seed=3)}
    h = S.headline(arms)
    assert h["status"] == S.STATUS_MEASURED and not h["synthetic"] and not h["is_mock"]
    assert h["Y_points"] == pytest.approx(100 * h["delta"]["delta"])
    assert h["sentence"].startswith("Same robot, same practice data, only the judge changed:")
    assert "points of success (95% CI [" in h["sentence"] and "simulation" in h["sentence"]
    assert h["prereg_deviations"] == ["baselines not run: ['robometer_4b', 'topreward'] "
                                      "(PREREG §7.4 minimal fallback must be disclosed)"]


def test_headline_measured_not_significant_says_so() -> None:
    arms = {"kodiac": _arm(0.5, rng_seed=1), "single_pass": _arm(0.5, rng_seed=1),
            "oracle": _arm(0.8, rng_seed=2), "accept_all": _arm(0.35, rng_seed=3)}
    h = S.headline(arms)  # identical draws => delta 0, t = 0, p = 1
    assert h["delta"]["delta"] == 0.0 and h["delta"]["p_welch"] == pytest.approx(1.0)
    assert "+0.0 points of success" in h["sentence"]
    assert "Not statistically significant" in h["sentence"]
    assert h["delta"]["meets_prereg_target"] is False


def test_headline_malformed_synthetic_input_fails_closed() -> None:
    bad = S.ArmSuccess({1: []}, synthetic=True, is_mock=False)
    h = S.headline({"kodiac": bad, "single_pass": _arm(0.5, synthetic=True)})
    assert h["status"] == S.STATUS_NOT_MEASURED and h["delta"] is None
    assert any("malformed" in r for r in h["reasons"])


def test_headline_alias_conflict_raises() -> None:
    with pytest.raises(ValueError):
        S.headline({"kodiac": _arm(0.6), "kodiac_cloud": _arm(0.5, rng_seed=9)})


# ---------------------------------------------------------------- scripts/check_prereg.py


def _run_check(repo: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_prereg.py"), "--repo", str(repo), *extra],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )


def test_check_prereg_passes_on_this_repo() -> None:
    res = _run_check(REPO)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "RESULT: PASS" in res.stdout and "[PASS] tag prereg-v1" in res.stdout


def _git(repo: Path, *args: str, date: str | None = None) -> None:
    env = None
    if date:
        import os

        env = dict(os.environ, GIT_COMMITTER_DATE=date, GIT_AUTHOR_DATE=date)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=repo, check=True, capture_output=True, env=env,
    )


def test_check_prereg_fails_when_labels_predate_tag(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    (repo / "experiments" / "labels").mkdir(parents=True)
    _git(repo, "init", "-q")
    (repo / "experiments" / "PREREGISTRATION.md").write_text("prereg\n", encoding="utf-8")
    (repo / "experiments" / "pool_config.yaml").write_text("a: 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "prereg", date="2026-10-01T00:00:00+00:00")
    (repo / "experiments" / "labels" / "k.parquet").write_bytes(b"x")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "labels", date="2026-10-02T00:00:00+00:00")
    _git(repo, "tag", "prereg-v1")  # tag AFTER labels => violation
    res = _run_check(repo)
    assert res.returncode == 1 and "RESULT: FAIL" in res.stdout
    assert "does not descend" in res.stdout

    ok_repo = tmp_path / "ok"
    (ok_repo / "experiments" / "results").mkdir(parents=True)
    _git(ok_repo, "init", "-q")
    (ok_repo / "experiments" / "PREREGISTRATION.md").write_text("prereg\n", encoding="utf-8")
    (ok_repo / "experiments" / "pool_config.yaml").write_text("a: 1\n", encoding="utf-8")
    _git(ok_repo, "add", "-A")
    _git(ok_repo, "commit", "-qm", "prereg", date="2026-10-01T00:00:00+00:00")
    _git(ok_repo, "tag", "prereg-v1")
    (ok_repo / "experiments" / "results" / "h.json").write_text("{}", encoding="utf-8")
    _git(ok_repo, "add", "-A")
    _git(ok_repo, "commit", "-qm", "results", date="2026-10-02T00:00:00+00:00")
    assert _run_check(ok_repo).returncode == 0
    # editing the pre-registration after the tag is a FAIL (metrics re-defined post hoc)
    (ok_repo / "experiments" / "PREREGISTRATION.md").write_text("changed\n", encoding="utf-8")
    res = _run_check(ok_repo)
    assert res.returncode == 1 and "changed since prereg-v1" in res.stdout


def test_check_prereg_missing_tag_fails() -> None:
    res = _run_check(REPO, "--tag", "prereg-does-not-exist")
    assert res.returncode == 1 and "not found" in res.stdout
