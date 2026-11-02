"""Proof statistics for the headline experiment, computed exactly as pre-registered.

Authority order (highest first):
1. ``experiments/PREREGISTRATION.md`` (cited below as ``PREREG §n``; tags ``prereg-v0`` / ``prereg-v1``).
2. ``ARCHITECTURE.md`` §5.7 (stats line) and §1.4 (proof chart).
3. ``IMPLEMENTATION_PLAN.md`` P08.S03 / P08.S05 and the T09 task card.

Where the pre-registration is silent, the lower authority is cited in the docstring that uses it.

Law 1 (never fake anything): every output carries ``synthetic`` / ``is_mock`` flags propagated from its
inputs. Unknown provenance is treated as ``is_mock=True`` (fail closed): only inputs explicitly declared
real (``synthetic=False, is_mock=False``) can ever yield ``status == "MEASURED"``.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

# ------------------------------------------------------------------------------------------------
# Constants (each tied to its source)
# ------------------------------------------------------------------------------------------------

Z95 = 1.959964

STATUS_MEASURED = "MEASURED"
STATUS_SYNTHETIC = "SYNTHETIC_TEST_ONLY"
STATUS_NOT_MEASURED = "NOT_MEASURED"

PREREG_DOC = "experiments/PREREGISTRATION.md"
#: PREREG §6: "Balanced Accuracy and AUROC: Computed via 1,000-sample non-parametric episode bootstrap."
METRIC_BOOTSTRAP_SAMPLES = 1000
METRIC_BOOTSTRAP_SEED = 0
#: PREREG §5: ">= 200 held-out environment seeds per training seed".
PREREG_MIN_EVAL_EPISODES = 200
#: PREREG §5 registers 3 seeds; IMPLEMENTATION_PLAN P08.S04 minimal fallback allows >= 2 (disclosed).
PREREG_REGISTERED_SEEDS = 3
MIN_SEEDS = 2
#: T09 card: the headline needs >= 4 arms (minimal fallback, PREREG §7.4 / P08.S04).
MIN_ARMS = 4
#: PREREG §6 "Target Success Criteria": Delta(Kodiac - Spark) >= +5.0% absolute, p < 0.05.
PREREG_TARGET_DELTA = 0.05
PREREG_ALPHA = 0.05

#: Canonical arm name -> accepted aliases (PREREG §4; aliases used by ``proof/arms.py``).
ARM_ALIASES: dict[str, tuple[str, ...]] = {
    "kodiac": ("kodiac", "kodiac_cloud", "kodiac_sam31"),
    "single_pass": ("single_pass", "single_pass_spark_2fps", "single_pass_spark_1.3"),
    "robometer_4b": ("robometer_4b", "robometer-4b"),
    "topreward": ("topreward", "topreward-lerobot-v0.6"),
    "accept_all": ("accept_all",),
    "oracle": ("oracle", "ground_truth"),
    "kodiac_open_weights": ("kodiac_open_weights", "kodiac_kinematic"),
    "kodiac_salvage": ("kodiac_salvage",),
    "size_matched_control": ("size_matched_control",),
    "oracle_k_5": ("oracle_k_5",),
    "oracle_k_10": ("oracle_k_10", "oracle_k_percent"),
    "oracle_k_20": ("oracle_k_20",),
    "oracle_k_30": ("oracle_k_30",),
}
#: PREREG §1 H1/H2 baseline set B, in pre-registered order. The primary headline baseline is single-pass.
PREREG_BASELINES: tuple[str, ...] = ("single_pass", "robometer_4b", "topreward", "accept_all")
#: PREREG §4 arm 10: oracle + k% injected false-PASS doses (k = 0 is the oracle arm itself).
DOSE_ARMS: tuple[tuple[int, str], ...] = (
    (0, "oracle"),
    (5, "oracle_k_5"),
    (10, "oracle_k_10"),
    (20, "oracle_k_20"),
    (30, "oracle_k_30"),
)
#: Judge-name aliases used to resolve ``ref_judge="Kodiac"`` in :func:`mcnemar_holm`.
KODIAC_JUDGE_ALIASES = ("kodiac", "kodiac_cloud", "kodiac_sam31")


# ------------------------------------------------------------------------------------------------
# Provenance carriers
# ------------------------------------------------------------------------------------------------


class FlaggedCI(tuple):
    """A plain ``(…)`` float tuple that also carries ``synthetic`` / ``is_mock`` provenance flags.

    Compares equal to the bare tuple, so callers that unpack it are unaffected.
    """

    synthetic: bool
    is_mock: bool

    def __new__(cls, values: Iterable[float], *, synthetic: bool = False, is_mock: bool = False):
        obj = super().__new__(cls, tuple(float(v) for v in values))
        obj.synthetic = bool(synthetic)
        obj.is_mock = bool(is_mock)
        return obj


class ArmSuccess(dict):
    """Per-seed, per-eval-episode oracle success values of ONE trained arm, with provenance.

    ``{training_seed: [success of eval episode 0, 1, ...]}``. Eval episode ``i`` of every arm must use
    the same held-out environment seed (PREREG §5: ``1001..1200``) so arms can be paired by index.
    ``source`` should point at the eval artifact(s) the numbers came from.
    """

    def __init__(
        self,
        data: Mapping[int, Sequence[float]],
        *,
        synthetic: bool,
        is_mock: bool,
        source: str = "",
    ) -> None:
        super().__init__({int(k): [float(x) for x in v] for k, v in data.items()})
        self.synthetic = bool(synthetic)
        self.is_mock = bool(is_mock)
        self.source = str(source)


def provenance_of(obj: Any) -> tuple[bool, bool, bool]:
    """Return ``(synthetic, is_mock, declared)`` for any input.

    Objects without explicit flags (plain dicts) are *undeclared*: they are treated as ``is_mock=True``
    so that they can never be reported as measured (fail closed, Law 1).
    """
    declared_override: bool | None = None
    if isinstance(obj, pd.DataFrame):
        synthetic = obj.attrs.get("synthetic")
        is_mock = obj.attrs.get("is_mock")
        if synthetic is None and "synthetic" in obj.columns:
            synthetic = bool(obj["synthetic"].any())
        if is_mock is None and "is_mock" in obj.columns:
            is_mock = bool(obj["is_mock"].any())
        declared_override = obj.attrs.get("provenance_declared")
    else:
        synthetic = getattr(obj, "synthetic", None)
        is_mock = getattr(obj, "is_mock", None)
    declared = synthetic is not None and is_mock is not None
    if declared_override is not None:
        declared = declared and bool(declared_override)
    synthetic_b = bool(synthetic) if synthetic is not None else False
    is_mock_b = bool(is_mock) if is_mock is not None else True
    if not declared:
        is_mock_b = True
    return synthetic_b, is_mock_b, declared


def _status(synthetic: bool, is_mock: bool) -> str:
    return STATUS_SYNTHETIC if (synthetic or is_mock) else STATUS_MEASURED


# ------------------------------------------------------------------------------------------------
# Binomial proportions, multiple comparisons
# ------------------------------------------------------------------------------------------------


def wilson_ci(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion ``k / n`` (PREREG §6: "95% Confidence Intervals:
    Computed via Wilson score intervals for binomial proportions").

    Raises ``ValueError`` for ``n <= 0`` or ``k`` outside ``[0, n]`` (no silent vacuous interval).
    """
    k = int(k)
    n = int(n)
    if n <= 0:
        raise ValueError(f"wilson_ci needs n > 0 (got n={n})")
    if k < 0 or k > n:
        raise ValueError(f"wilson_ci needs 0 <= k <= n (got k={k}, n={n})")
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n)) / denom
    lo = 0.0 if k == 0 else max(0.0, center - half)
    hi = 1.0 if k == n else min(1.0, center + half)
    return (lo, hi)


def holm_adjust(pvalues: Mapping[str, float | None]) -> dict[str, float]:
    """Holm–Bonferroni step-down adjusted p-values (PREREG §6: "Holm-Bonferroni correction").

    ``None`` / NaN p-values (degenerate tests) stay in the family as ``p = 1.0`` so the family size
    is never shrunk after seeing the data. Ties are broken by key for determinism.
    """
    cleaned = {
        k: (1.0 if v is None or not math.isfinite(float(v)) else float(v)) for k, v in pvalues.items()
    }
    order = sorted(cleaned.items(), key=lambda kv: (kv[1], kv[0]))
    m = len(order)
    adjusted: dict[str, float] = {}
    running = 0.0
    for i, (key, p) in enumerate(order):
        running = max(running, min(1.0, (m - i) * p))
        adjusted[key] = running
    return adjusted


def mcnemar_exact_p(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value: binomial test of ``min(b, c)`` in ``b + c`` trials at 0.5.

    Exact integer arithmetic (``Binomial(n, 1/2)`` is symmetric, so the two-sided p is twice the
    lower tail, capped at 1). Cross-checked against ``scipy.stats.binomtest`` in the tests.
    """
    b = int(b)
    c = int(c)
    if b < 0 or c < 0:
        raise ValueError("discordant counts must be >= 0")
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1))
    return min(1.0, 2 * tail / 2**n)


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the regularized incomplete beta (modified Lentz)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 500):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta ``I_x(a, b)``."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_front = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x)
    )
    front = math.exp(ln_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_two_sided_p(t: float, dof: float) -> float:
    """Two-sided p-value of Student's t with (possibly fractional) ``dof``: ``I_{v/(v+t^2)}(v/2, 1/2)``."""
    return _betainc(dof / 2.0, 0.5, dof / (dof + t * t))


def t_quantile_975(dof: float) -> float:
    """Upper 97.5% quantile of Student's t (bisection on :func:`t_two_sided_p`)."""
    lo, hi = 0.0, 1e4
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if t_two_sided_p(mid, dof) > 0.05:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ------------------------------------------------------------------------------------------------
# Judge metrics (training split)
# ------------------------------------------------------------------------------------------------

_LABEL_COLUMNS = ("judge", "episode_id", "accept", "verdict", "score", "split")


def _require_columns(df: pd.DataFrame) -> None:
    missing = [c for c in _LABEL_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"label frame lacks columns {missing}; run proof.labels.apply_thresholds() first"
        )


def _episode_universe(df: pd.DataFrame, oracle: Mapping[str, bool], split: str) -> list[str]:
    calib = df.attrs.get("calib_split_ids")
    if calib is not None:
        calib = set(calib)
        if split == "train":
            return sorted(e for e in oracle if e not in calib)
        if split == "calibration":
            return sorted(e for e in oracle if e in calib)
    ids = set(df.loc[df["split"] == split, "episode_id"])
    return sorted(e for e in ids if e in oracle)


def _judge_vectors(
    df: pd.DataFrame, judge: str, universe: Sequence[str], split: str
) -> dict[str, np.ndarray]:
    sub = df[(df["judge"] == judge) & (df["split"] == split)]
    by_ep = {r.episode_id: r for r in sub.itertuples(index=False)}
    n = len(universe)
    accept = np.zeros(n, dtype=bool)
    adjud = np.zeros(n, dtype=bool)
    present = np.zeros(n, dtype=bool)
    cant = np.zeros(n, dtype=bool)
    score = np.full(n, np.nan)
    for i, ep in enumerate(universe):
        row = by_ep.get(ep)
        if row is None:
            continue
        present[i] = True
        verdict = row.verdict if isinstance(row.verdict, str) else None
        is_cant = verdict == "CANT_TELL"
        cant[i] = is_cant
        # PREREG §4 arm 3 / IDEA §8: CAN'T TELL is "not accepted"; coverage counts it as not adjudicated.
        accept[i] = bool(row.accept) and not is_cant
        adjud[i] = not is_cant
        if row.score is not None and not pd.isna(row.score):
            score[i] = float(row.score)
    return {"accept": accept, "adjud": adjud, "present": present, "cant": cant, "score": score}


def _wilson_block(k: int, n: int) -> dict[str, Any]:
    if n == 0:
        return {"value": None, "lo": None, "hi": None, "k": k, "n": n, "ci_method": "wilson"}
    lo, hi = wilson_ci(k, n)
    return {"value": k / n, "lo": lo, "hi": hi, "k": k, "n": n, "ci_method": "wilson"}


def _auroc(scores: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Rank-based AUROC (Mann–Whitney U with average ranks for ties). Works row-wise on 2-D input."""
    scores = np.atleast_2d(scores)
    y = np.atleast_2d(y).astype(float)
    ranks = np.empty_like(scores, dtype=float)
    for r in range(scores.shape[0]):
        _, inv, counts = np.unique(scores[r], return_inverse=True, return_counts=True)
        avg = np.cumsum(counts) - (counts - 1) / 2.0
        ranks[r] = avg[inv]
    n_pos = y.sum(axis=1)
    n_neg = y.shape[1] - n_pos
    u = (ranks * y).sum(axis=1) - n_pos * (n_pos + 1) / 2.0
    with np.errstate(invalid="ignore", divide="ignore"):
        auc = u / (n_pos * n_neg)
    auc[(n_pos == 0) | (n_neg == 0)] = np.nan
    return auc


def _ba(accept: np.ndarray, y: np.ndarray) -> np.ndarray:
    accept = np.atleast_2d(accept)
    y = np.atleast_2d(y)
    tp = (accept & y).sum(axis=1)
    fn = (~accept & y).sum(axis=1)
    tn = (~accept & ~y).sum(axis=1)
    fp = (accept & ~y).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        ba = 0.5 * (tp / (tp + fn) + tn / (tn + fp))
    return ba


def _contamination(accept: np.ndarray, y: np.ndarray) -> np.ndarray:
    accept = np.atleast_2d(accept)
    y = np.atleast_2d(y)
    fp = (accept & ~y).sum(axis=1)
    acc = accept.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = fp / acc
    return out.astype(float)


def _boot_block(point: float | None, draws: np.ndarray, method: str) -> dict[str, Any]:
    finite = draws[np.isfinite(draws)]
    if point is None or (isinstance(point, float) and math.isnan(point)) or finite.size == 0:
        return {"value": None, "lo": None, "hi": None, "ci_method": method, "n_boot_valid": 0}
    lo, hi = np.percentile(finite, [2.5, 97.5])
    return {
        "value": float(point),
        "lo": float(lo),
        "hi": float(hi),
        "ci_method": method,
        "n_boot_valid": int(finite.size),
    }


def judge_metrics(df: pd.DataFrame, oracle: Mapping[str, bool], split: str = "train") -> dict:
    """Per-judge label-quality metrics on one split (default: the training split, PREREG §6).

    Definitions (truth = oracle success at the final step, PREREG §2; accept = PASS / score >= tau with
    CAN'T TELL counted as not accepted, PREREG §4 arm 3):

    * false-PASS = FP / (FP + TN)            PREREG §1 H1, §6 — Wilson CI.
    * false-REJECT = FN / (FN + TP)          PREREG §6 — Wilson CI.
    * coverage = adjudicated / total         PREREG §6 — Wilson CI. Missing labels are not adjudicated.
    * contamination = FP / (TP + FP)         not defined in PREREG; ARCHITECTURE §5.7 / P08.S03 —
                                             1,000-sample episode-bootstrap CI (ARCHITECTURE §5.7).
    * balanced accuracy, AUROC               PREREG §6 — 1,000-sample episode-bootstrap percentile CI.
      AUROC uses the judge's continuous ``score`` when every episode has one, else the binary accept
      decision (``auroc.basis`` says which).

    The denominator is every oracle-labelled episode of the split; a judge with no label for an episode
    is counted as "not accepted, not adjudicated" and reported in ``n_missing`` (never silently dropped).
    """
    _require_columns(df)
    universe = _episode_universe(df, oracle, split)
    y = np.array([bool(oracle[e]) for e in universe], dtype=bool)
    df_synth, df_mock, df_declared = provenance_of(df)
    or_synth, or_mock, or_declared = provenance_of(oracle)
    synthetic = df_synth or or_synth
    is_mock = df_mock or or_mock
    notes: list[str] = []
    if not or_declared:
        notes.append("oracle provenance undeclared: treated as is_mock=True (fail closed)")
    if not df_declared:
        notes.append("label provenance undeclared: treated as is_mock=True (fail closed)")

    judges = sorted(df["judge"].unique()) if len(df) else []
    out: dict[str, Any] = {
        "split": split,
        "n_episodes": len(universe),
        "n_pos": int(y.sum()),
        "n_neg": int((~y).sum()),
        "synthetic": synthetic,
        "is_mock": is_mock,
        "status": STATUS_NOT_MEASURED if not judges or not universe else _status(synthetic, is_mock),
        "prereg": f"{PREREG_DOC} §6",
        "bootstrap": {"samples": METRIC_BOOTSTRAP_SAMPLES, "seed": METRIC_BOOTSTRAP_SEED},
        "notes": notes,
        "judges": {},
    }
    if not judges or not universe:
        out["notes"].append("no judge labels or no oracle episodes on this split")
        return out

    rng = np.random.default_rng(METRIC_BOOTSTRAP_SEED)
    n = len(universe)
    idx = rng.integers(0, n, size=(METRIC_BOOTSTRAP_SAMPLES, n))
    y_b = y[idx]
    for judge in judges:
        v = _judge_vectors(df, judge, universe, split)
        acc = v["accept"]
        tp = int((acc & y).sum())
        fp = int((acc & ~y).sum())
        tn = int((~acc & ~y).sum())
        fn = int((~acc & y).sum())
        n_missing = int((~v["present"]).sum())
        acc_b = acc[idx]

        ba_point = _ba(acc, y)[0]
        cont_point = _contamination(acc, y)[0]
        use_score = bool(v["present"].all() and np.isfinite(v["score"]).all())
        s = v["score"] if use_score else acc.astype(float)
        auc_point = _auroc(s, y)[0]
        auc_draws = _auroc(s[idx], y_b)

        sub = df[df["judge"] == judge]
        thr = sub["threshold"].dropna().unique() if "threshold" in sub else []
        jsynth = bool(sub["synthetic"].any()) if "synthetic" in sub else synthetic
        jmock = bool(sub["is_mock"].any()) if "is_mock" in sub else is_mock
        out["judges"][judge] = {
            "n": n,
            "n_pos": int(y.sum()),
            "n_neg": int((~y).sum()),
            "n_accepted": int(acc.sum()),
            "n_cant_tell": int(v["cant"].sum()),
            "n_missing": n_missing,
            "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
            "false_pass": _wilson_block(fp, fp + tn),
            "false_reject": _wilson_block(fn, fn + tp),
            "coverage": _wilson_block(int(v["adjud"].sum()), n),
            "contamination": _boot_block(
                None if math.isnan(cont_point) else float(cont_point),
                _contamination(acc_b, y_b),
                "episode_bootstrap_percentile",
            ),
            "balanced_accuracy": _boot_block(
                None if math.isnan(ba_point) else float(ba_point),
                _ba(acc_b, y_b),
                "episode_bootstrap_percentile",
            ),
            "auroc": {
                **_boot_block(
                    None if math.isnan(auc_point) else float(auc_point),
                    auc_draws,
                    "episode_bootstrap_percentile",
                ),
                "basis": "score" if use_score else "binary_accept",
            },
            "threshold": float(thr[0]) if len(thr) == 1 else None,
            "threshold_source": (
                str(sub["threshold_source"].iloc[0]) if "threshold_source" in sub else None
            ),
            "synthetic": jsynth or synthetic,
            "is_mock": jmock or is_mock,
        }
    # PREREG §1 H1 (directional): false-PASS(Kodiac) < min over baselines. Reported, not asserted.
    out["status"] = _status(synthetic, is_mock)
    return out


def _resolve_judge(judges: Iterable[str], ref_judge: str) -> str:
    judges = list(judges)
    if ref_judge in judges:
        return ref_judge
    folded = [j for j in judges if j.casefold() == ref_judge.casefold()]
    if len(folded) == 1:
        return folded[0]
    if ref_judge.casefold() == "kodiac":
        cands = [j for j in judges if j.casefold() in KODIAC_JUDGE_ALIASES]
        if len(cands) == 1:
            return cands[0]
    raise ValueError(f"reference judge {ref_judge!r} not found unambiguously among {sorted(judges)}")


def mcnemar_holm(
    df: pd.DataFrame, oracle: Mapping[str, bool], ref_judge: str = "Kodiac"
) -> dict:
    """Exact McNemar test of every judge against ``ref_judge`` on the training split, Holm-corrected.

    Source: IMPLEMENTATION_PLAN P08.S03 / ARCHITECTURE §5.7 ("Holm-corrected McNemar vs Kodiac"; the
    PREREG §6 Holm rule is applied to this family too). Paired on the same training episodes.

    * ``primary`` — per-episode correctness (accept == oracle success), the standard paired comparison
      of two classifiers. ``b`` = ref correct & other wrong, ``c`` = ref wrong & other correct.
    * ``false_pass`` — the same test restricted to oracle failures (paired false-PASS comparison, H1).

    Each family is Holm-corrected separately over all compared judges. CAN'T TELL / missing = rejected.
    """
    _require_columns(df)
    universe = _episode_universe(df, oracle, "train")
    y = np.array([bool(oracle[e]) for e in universe], dtype=bool)
    synthetic, is_mock, _ = provenance_of(df)
    or_synth, or_mock, _ = provenance_of(oracle)
    synthetic = synthetic or or_synth
    is_mock = is_mock or or_mock
    judges = sorted(df["judge"].unique()) if len(df) else []
    out: dict[str, Any] = {
        "split": "train",
        "n_episodes": len(universe),
        "synthetic": synthetic,
        "is_mock": is_mock,
        "status": STATUS_NOT_MEASURED,
        "ref_judge": None,
        "test": "exact McNemar (two-sided binomial on discordant pairs), Holm-corrected",
        "comparisons": {},
    }
    if len(judges) < 2 or not universe:
        return out
    ref = _resolve_judge(judges, ref_judge)
    out["ref_judge"] = ref
    ref_acc = _judge_vectors(df, ref, universe, "train")["accept"]
    ref_ok = ref_acc == y
    raw_primary: dict[str, float] = {}
    raw_fp: dict[str, float] = {}
    for judge in judges:
        if judge == ref:
            continue
        acc = _judge_vectors(df, judge, universe, "train")["accept"]
        ok = acc == y
        b = int((ref_ok & ~ok).sum())
        c = int((~ref_ok & ok).sum())
        neg = ~y
        b_fp = int((~ref_acc & acc & neg).sum())  # ref correctly rejects, other false-PASSes
        c_fp = int((ref_acc & ~acc & neg).sum())  # ref false-PASSes, other correctly rejects
        raw_primary[judge] = mcnemar_exact_p(b, c)
        raw_fp[judge] = mcnemar_exact_p(b_fp, c_fp)
        out["comparisons"][judge] = {
            "primary": {"b": b, "c": c, "p": raw_primary[judge]},
            "false_pass": {"b": b_fp, "c": c_fp, "p": raw_fp[judge]},
        }
    holm_p = holm_adjust(raw_primary)
    holm_fp = holm_adjust(raw_fp)
    for judge, comp in out["comparisons"].items():
        comp["primary"]["p_holm"] = holm_p[judge]
        comp["false_pass"]["p_holm"] = holm_fp[judge]
    out["status"] = _status(synthetic, is_mock)
    return out


# ------------------------------------------------------------------------------------------------
# Downstream success: hierarchical bootstrap, Welch, headline
# ------------------------------------------------------------------------------------------------


def _as_arrays(d: Mapping[int, Sequence[float]]) -> dict[int, np.ndarray]:
    if not d:
        raise ValueError("success map is empty (need >= 1 seed with >= 1 episode)")
    out: dict[int, np.ndarray] = {}
    for seed, vals in d.items():
        arr = np.asarray(list(vals), dtype=float)
        if arr.ndim != 1 or arr.size == 0:
            raise ValueError(f"seed {seed}: need a non-empty 1-D list of episode outcomes")
        if not np.all(np.isfinite(arr)):
            raise ValueError(f"seed {seed}: non-finite episode outcome")
        out[int(seed)] = arr
    return out


def _grand_mean(arrs: Mapping[int, np.ndarray]) -> float:
    """Mean of per-seed means: each training seed is one replicate (PREREG §1 H2, §6)."""
    return float(np.mean([a.mean() for a in arrs.values()]))


def _hier_draws(
    arms: Sequence[Mapping[int, np.ndarray]],
    seeds: Sequence[int],
    n_boot: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Two-stage bootstrap: resample seeds with replacement, then episodes within each drawn seed.

    All ``arms`` share ``seeds``; when every arm has the same number of episodes in a seed, the SAME
    episode indices are drawn for every arm (paired by eval-environment seed). Each drawn seed slot gets
    an independent episode resample. Returns an ``(n_arms, n_boot)`` array of grand means.
    """
    n_seeds = len(seeds)
    choice = rng.integers(0, n_seeds, size=(n_boot, n_seeds))
    totals = np.zeros((len(arms), n_boot))
    for slot in range(n_seeds):
        for si, seed in enumerate(seeds):
            rows = np.nonzero(choice[:, slot] == si)[0]
            if rows.size == 0:
                continue
            lengths = {arm[seed].size for arm in arms}
            if len(lengths) == 1:
                n_ep = lengths.pop()
                idx = rng.integers(0, n_ep, size=(rows.size, n_ep))
                for a, arm in enumerate(arms):
                    totals[a, rows] += arm[seed][idx].mean(axis=1)
            else:
                for a, arm in enumerate(arms):
                    n_ep = arm[seed].size
                    idx = rng.integers(0, n_ep, size=(rows.size, n_ep))
                    totals[a, rows] += arm[seed][idx].mean(axis=1)
    return totals / n_seeds


def hier_bootstrap_mean_ci(
    success_by_seed_episode: dict[int, list[float]], n_boot: int = 10000, seed: int = 0
) -> tuple[float, float, float]:
    """``(mean, lo, hi)``: mean of per-seed success means with a 95% two-stage (seeds, then episodes)
    percentile bootstrap CI. Source: IMPLEMENTATION_PLAN P08.S05 ("hierarchical-bootstrap CI");
    ARCHITECTURE §5.7 lists it as the secondary interval next to the Welch test (PREREG §6).
    """
    arrs = _as_arrays(success_by_seed_episode)
    seeds = sorted(arrs)
    draws = _hier_draws([arrs], seeds, int(n_boot), np.random.default_rng(seed))[0]
    lo, hi = np.percentile(draws, [2.5, 97.5])
    synthetic, is_mock, _ = provenance_of(success_by_seed_episode)
    return FlaggedCI((_grand_mean(arrs), lo, hi), synthetic=synthetic, is_mock=is_mock)


def delta_ci(a: dict, b: dict, n_boot: int = 10000, seed: int = 0) -> tuple[float, float, float]:
    """``(delta, lo, hi)`` for ``mean(a) - mean(b)`` (means of per-seed means) with a 95% hierarchical
    percentile bootstrap CI. Paired where possible: when both arms have the same training seeds, the
    same seeds are drawn for both; within a seed, the same eval-episode indices are drawn when the
    episode counts match (same held-out env seeds, PREREG §5). Otherwise arms are resampled
    independently.
    """
    aa = _as_arrays(a)
    bb = _as_arrays(b)
    rng = np.random.default_rng(seed)
    if sorted(aa) == sorted(bb):
        draws = _hier_draws([aa, bb], sorted(aa), int(n_boot), rng)
        diff = draws[0] - draws[1]
    else:
        da = _hier_draws([aa], sorted(aa), int(n_boot), rng)[0]
        db = _hier_draws([bb], sorted(bb), int(n_boot), rng)[0]
        diff = da - db
    lo, hi = np.percentile(diff, [2.5, 97.5])
    sa, ma, _ = provenance_of(a)
    sb, mb, _ = provenance_of(b)
    return FlaggedCI(
        (_grand_mean(aa) - _grand_mean(bb), lo, hi), synthetic=sa or sb, is_mock=ma or mb
    )


def welch_seed_means(a: Mapping[int, Sequence[float]], b: Mapping[int, Sequence[float]]) -> dict:
    """Two-sided Welch t-test on per-seed success means (PREREG §1 H2, §6), with the matching
    Welch–Satterthwaite 95% CI for the difference. Degenerate inputs give ``p = None`` and a note.
    Pure Python (cross-checked against ``scipy.stats.ttest_ind(equal_var=False)`` in the tests).
    """
    ma = np.array([v.mean() for v in _as_arrays(a).values()])
    mb = np.array([v.mean() for v in _as_arrays(b).values()])
    diff = float(ma.mean() - mb.mean())
    res: dict[str, Any] = {
        "diff": diff,
        "n_seeds_a": int(ma.size),
        "n_seeds_b": int(mb.size),
        "t": None,
        "df": None,
        "p": None,
        "ci": [None, None],
        "note": None,
    }
    if ma.size < 2 or mb.size < 2:
        res["note"] = "Welch t needs >= 2 seeds per arm"
        return res
    va = ma.var(ddof=1) / ma.size
    vb = mb.var(ddof=1) / mb.size
    se = math.sqrt(va + vb)
    if se == 0.0:
        res["note"] = "zero between-seed variance in both arms: Welch t undefined"
        return res
    dof = (va + vb) ** 2 / (va**2 / (ma.size - 1) + vb**2 / (mb.size - 1))
    t_stat = float(diff / se)
    dof = float(dof)
    q = t_quantile_975(dof)
    res.update(
        t=t_stat,
        df=dof,
        p=float(t_two_sided_p(t_stat, dof)),
        ci=[diff - q * se, diff + q * se],
    )
    return res


def _canonical_arms(arm_success: Mapping[str, Any]) -> dict[str, Any]:
    alias_to_canon = {alias: canon for canon, aliases in ARM_ALIASES.items() for alias in aliases}
    out: dict[str, Any] = {}
    for name, data in arm_success.items():
        canon = alias_to_canon.get(name, name)
        if canon in out:
            if dict(out[canon]) != dict(data):
                raise ValueError(f"arm {canon!r} given twice with different data (alias {name!r})")
            continue
        out[canon] = data
    return out


def _arm_summary(name: str, data: Any, n_boot: int, seed: int) -> dict[str, Any]:
    arrs = _as_arrays(data)
    synthetic, is_mock, declared = provenance_of(data)
    mean, lo, hi = hier_bootstrap_mean_ci(arrs, n_boot=n_boot, seed=seed)
    return {
        "arm": name,
        "mean": mean,
        "ci": [lo, hi],
        "ci_method": "hierarchical_bootstrap_percentile (seeds, then episodes)",
        "n_seeds": len(arrs),
        "seeds": {str(s): {"mean": float(a.mean()), "n": int(a.size)} for s, a in sorted(arrs.items())},
        "min_episodes_per_seed": int(min(a.size for a in arrs.values())),
        "synthetic": synthetic,
        "is_mock": is_mock,
        "provenance_declared": declared,
        "source": getattr(data, "source", ""),
    }


def headline(arm_success: dict[str, dict[int, list[float]]]) -> dict:
    """The headline proof object: Delta(Kodiac - single-pass) in success, with CIs (Invariant I8).

    Statistics (PREREG §1 H2, §6; ARCHITECTURE §1.4, §5.7):
    * per arm: mean of per-seed success means + hierarchical bootstrap CI (P08.S05);
    * Delta vs each PREREG baseline present: two-sided Welch t on seed means + Welch CI (primary,
      PREREG §6), Holm-corrected across the baseline comparisons (PREREG §6), paired hierarchical
      bootstrap CI (secondary, ARCHITECTURE §5.7);
    * dose-response: oracle + k% injected false-PASS arms (PREREG §4 arm 10).

    Status (fails closed, T09 card):
    * ``NOT_MEASURED`` — no arms, Kodiac or single-pass arm missing, or (for declared-real inputs) any
      gate fails: >= 4 arms, >= 2 seeds per arm, >= 200 eval episodes per seed (PREREG §5). No numbers.
    * ``SYNTHETIC_TEST_ONLY`` — any input synthetic, mock, or of undeclared provenance. Numbers are
      computed for testing only and flagged; ``sentence`` is always ``None``.
    * ``MEASURED`` — all gates pass and every arm is an :class:`ArmSuccess` declared real.
    """
    n_boot = 10000
    base: dict[str, Any] = {
        "status": STATUS_NOT_MEASURED,
        "synthetic": False,
        "is_mock": False,
        "Y_points": None,
        "sentence": None,
        "kodiac_arm": None,
        "baseline_arm": None,
        "delta": None,
        "comparisons": {},
        "arms": {},
        "dose_response": [],
        "gate_failures": [],
        "prereg_deviations": [],
        "reasons": [],
        "prereg": f"{PREREG_DOC} §1 H2, §4, §5, §6",
        "bootstrap": {"samples": n_boot, "seed": 0},
    }
    if not arm_success:
        base["reasons"].append("no trained arms: no downstream evaluation results exist")
        return base
    arms = _canonical_arms(arm_success)
    for key in ("kodiac", "single_pass"):
        if key not in arms:
            base["reasons"].append(f"required arm missing: {key} (aliases {ARM_ALIASES[key]})")
    if base["reasons"]:
        return base

    prov = {name: provenance_of(d) for name, d in arms.items()}
    synthetic = any(p[0] for p in prov.values())
    is_mock = any(p[1] for p in prov.values())
    undeclared = sorted(name for name, p in prov.items() if not p[2])
    gate_failures: list[str] = []
    if len(arms) < MIN_ARMS:
        gate_failures.append(f"{len(arms)} arms < {MIN_ARMS} required")
    for name, data in sorted(arms.items()):
        if len(data) < MIN_SEEDS:
            gate_failures.append(f"arm {name}: {len(data)} seeds < {MIN_SEEDS} required")
        for s, vals in sorted(data.items()):
            if len(vals) < PREREG_MIN_EVAL_EPISODES:
                gate_failures.append(
                    f"arm {name} seed {s}: {len(vals)} eval episodes < {PREREG_MIN_EVAL_EPISODES} "
                    "(PREREG §5)"
                )
    base["gate_failures"] = gate_failures
    base["synthetic"] = synthetic
    base["is_mock"] = is_mock
    if undeclared:
        base["reasons"].append(
            f"provenance undeclared for arms {undeclared}: treated as is_mock=True (fail closed)"
        )
    if synthetic or is_mock:
        base["status"] = STATUS_SYNTHETIC
        base["reasons"].append("inputs flagged synthetic/mock: numbers are for testing only")
    elif gate_failures:
        base["reasons"].append("pre-registered gates failed: headline withheld")
        return base
    else:
        base["status"] = STATUS_MEASURED

    try:
        return _fill_headline(base, arms, n_boot)
    except ValueError as exc:
        base.update(
            status=STATUS_NOT_MEASURED,
            arms={},
            comparisons={},
            dose_response=[],
            delta=None,
            Y_points=None,
            sentence=None,
            kodiac_arm=None,
            baseline_arm=None,
        )
        base["reasons"].append(f"malformed arm data: {exc}")
        return base


def _fill_headline(base: dict[str, Any], arms: Mapping[str, Any], n_boot: int) -> dict[str, Any]:
    for name, data in sorted(arms.items()):
        base["arms"][name] = _arm_summary(name, data, n_boot, 0)
    n_seeds_min = min(len(d) for d in arms.values())
    if n_seeds_min < PREREG_REGISTERED_SEEDS:
        base["prereg_deviations"].append(
            f"{n_seeds_min} seeds < {PREREG_REGISTERED_SEEDS} registered (PREREG §5); "
            "minimal fallback per IMPLEMENTATION_PLAN P08.S04"
        )
    absent = [b for b in PREREG_BASELINES if b not in arms]
    if absent:
        base["prereg_deviations"].append(
            f"baselines not run: {absent} (PREREG §7.4 minimal fallback must be disclosed)"
        )

    welch: dict[str, dict] = {}
    for b in PREREG_BASELINES:
        if b in arms:
            welch[b] = welch_seed_means(arms["kodiac"], arms[b])
    p_holm = holm_adjust({b: w["p"] for b, w in welch.items()})
    for b, w in welch.items():
        d, lo, hi = delta_ci(arms["kodiac"], arms[b], n_boot=n_boot, seed=0)
        base["comparisons"][b] = {
            "delta": d,
            "ci_welch": w["ci"],
            "ci_hier_bootstrap": [lo, hi],
            "welch_t": w["t"],
            "welch_df": w["df"],
            "p_welch": w["p"],
            "p_holm": p_holm[b],
            "note": w["note"],
        }
    primary = base["comparisons"]["single_pass"]
    significant = primary["p_welch"] is not None and primary["p_holm"] < PREREG_ALPHA
    base["kodiac_arm"] = "kodiac"
    base["baseline_arm"] = "single_pass"
    base["delta"] = {
        **primary,
        "points": 100.0 * primary["delta"],
        "significant_holm": significant,
        "meets_prereg_target": bool(significant and primary["delta"] >= PREREG_TARGET_DELTA),
        "target": f"Delta >= +{PREREG_TARGET_DELTA * 100:.1f} points, Holm p < {PREREG_ALPHA}",
    }
    for k, name in DOSE_ARMS:
        if name in arms:
            summ = base["arms"][name]
            base["dose_response"].append(
                {"k_percent": k, "arm": name, "mean": summ["mean"], "ci": summ["ci"]}
            )

    if base["status"] == STATUS_MEASURED:
        y_pts = 100.0 * primary["delta"]
        base["Y_points"] = y_pts
        ci = primary["ci_welch"]
        ci_txt = (
            f"95% CI [{100 * ci[0]:+.1f}, {100 * ci[1]:+.1f}], simulation"
            if ci[0] is not None
            else "CI undefined, simulation"
        )
        sentence = (
            "Same robot, same practice data, only the judge changed: "
            f"{y_pts:+.1f} points of success ({ci_txt})."
        )
        if not significant:
            p_txt = "undefined" if primary["p_welch"] is None else f"{primary['p_holm']:.3g}"
            sentence += f" Not statistically significant (Holm-adjusted Welch p = {p_txt})."
        base["sentence"] = sentence
    return base
