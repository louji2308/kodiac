"""Judge-label consolidation and calibration-split thresholding (IMPLEMENTATION_PLAN P08.S02).

Rules (``experiments/PREREGISTRATION.md``, cited as ``PREREG §n``):
* Truth is the physics oracle's ``oracle_success`` at the final step (PREREG §2).
* Score-judge thresholds are fitted on the **calibration split only**, maximising balanced accuracy
  (PREREG §3: the calibration split is "reserved strictly for tuning threshold hyper-parameters";
  ARCHITECTURE §5.7: "max balanced accuracy", i.e. the baselines' best case).
* CAN'T TELL is never accepted (PREREG §4 arm 3).

Provenance (Law 1): the frozen ``JudgeLabel`` contract has no provenance field, so label files carry
optional ``synthetic`` / ``is_mock`` columns. A file named ``*SYNTHETIC*`` is synthetic. A row without an
explicit ``is_mock`` is treated as ``is_mock=True`` (unknown provenance never counts as measured).
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pydantic import ValidationError

from Kodiac_robotics.contracts.core import JudgeLabel
from Kodiac_robotics.proof.stats import ArmSuccess

#: Judges whose decision is a continuous score thresholded on the calibration split (PREREG §4 arms 7–8).
SCORE_JUDGES = frozenset({"robometer-4b", "robometer_4b", "topreward", "topreward-lerobot-v0.6"})

LABEL_COLUMNS = [
    "judge",
    "episode_id",
    "accept",
    "score",
    "verdict",
    "latency_ms",
    "cost_usd",
    "calibration_threshold",
    "synthetic",
    "is_mock",
    "provenance_declared",
    "judge_kind",
    "source",
]


class OracleLabels(dict):
    """``{episode_id: oracle_success}`` with provenance flags (see :func:`load_oracle`)."""

    def __init__(
        self,
        data: Mapping[str, bool],
        *,
        synthetic: bool,
        is_mock: bool,
        source: str = "",
        splits: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__({str(k): bool(v) for k, v in data.items()})
        self.synthetic = bool(synthetic)
        self.is_mock = bool(is_mock)
        self.source = str(source)
        self.splits = dict(splits or {})


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "t"}
    return bool(value)


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"label file not found: {path}")
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq

        return pq.read_table(path).to_pylist()
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    if path.suffix == ".json":
        data = json.loads(text)
        if isinstance(data, dict) and "labels" in data:
            data = data["labels"]
        if not isinstance(data, list):
            raise ValueError(f"{path}: expected a JSON list of JudgeLabel rows")
        return data
    raise ValueError(f"{path}: unsupported label format {path.suffix!r} (parquet/json/jsonl)")


def load_labels(paths: list[Path]) -> pd.DataFrame:
    """Load and validate ``JudgeLabel`` rows from parquet/json/jsonl files into one frame.

    Every row is validated against the frozen ``contracts.core.JudgeLabel`` model. Duplicate
    ``(judge, episode_id)`` pairs are rejected (``ValueError``), across files too. Provenance columns
    ``synthetic`` / ``is_mock`` / ``provenance_declared`` are added; ``df.attrs`` carries the frame-level
    flags used by :mod:`Kodiac_robotics.proof.stats`.
    """
    rows: list[dict[str, Any]] = []
    for raw in paths:
        path = Path(raw)
        file_synthetic = "SYNTHETIC" in path.name.upper()
        for i, rec in enumerate(_read_records(path)):
            if not isinstance(rec, dict):
                raise ValueError(f"{path}:{i}: row is not an object")
            try:
                label = JudgeLabel.model_validate(rec)
            except ValidationError as exc:
                raise ValueError(f"{path}:{i}: invalid JudgeLabel: {exc}") from exc
            row = label.model_dump(mode="json")
            declared = "is_mock" in rec and rec["is_mock"] is not None
            row["synthetic"] = file_synthetic or _as_bool(rec.get("synthetic", False))
            row["is_mock"] = _as_bool(rec["is_mock"]) if declared else True
            row["provenance_declared"] = declared
            kind = rec.get("judge_kind")
            if kind is not None and kind not in ("score", "verdict"):
                raise ValueError(f"{path}:{i}: judge_kind must be 'score' or 'verdict'")
            row["judge_kind"] = kind
            row["source"] = str(path)
            rows.append(row)
    df = pd.DataFrame(rows, columns=LABEL_COLUMNS)
    dup = df.duplicated(["judge", "episode_id"], keep=False)
    if dup.any():
        pairs = df.loc[dup, ["judge", "episode_id"]].drop_duplicates().head(5).values.tolist()
        raise ValueError(f"duplicate (judge, episode_id) labels, e.g. {pairs}")
    df.attrs["synthetic"] = bool(df["synthetic"].any())
    df.attrs["is_mock"] = bool(df["is_mock"].any())
    df.attrs["provenance_declared"] = bool(len(df) == 0 or df["provenance_declared"].all())
    return df


def load_oracle(manifest_path: Path) -> OracleLabels:
    """Read ``{episode_id: oracle_success}`` + splits from the practice-pool manifest (parquet/json).

    ``is_mock`` comes from the manifest rows (``proof/pool.py`` schema); a missing column means
    unknown provenance and is treated as mock.
    """
    path = Path(manifest_path)
    recs = _read_records(path)
    data = {str(r["episode_id"]): bool(r["oracle_success"]) for r in recs}
    splits = {str(r["episode_id"]): str(r.get("split", "")) for r in recs}
    is_mock = any(_as_bool(r.get("is_mock", True)) for r in recs) or not recs
    synthetic = "SYNTHETIC" in path.name.upper() or any(
        _as_bool(r.get("synthetic", False)) for r in recs
    )
    return OracleLabels(data, synthetic=synthetic, is_mock=is_mock, source=str(path), splits=splits)


def fit_max_ba_threshold(scores: Iterable[float], truth: Iterable[bool]) -> tuple[float, float]:
    """Return ``(tau, balanced_accuracy)`` maximising BA of ``accept = score >= tau``.

    Candidates are every observed score plus ``+inf`` (accept nothing). Ties go to the HIGHEST tau
    (fewest accepts, i.e. the lowest false-PASS for the baseline; conservative for our H1 claim).
    """
    s = np.asarray(list(scores), dtype=float)
    y = np.asarray(list(truth), dtype=bool)
    if s.size == 0 or y.size != s.size:
        raise ValueError("need equal-length, non-empty scores and truth")
    if not np.all(np.isfinite(s)):
        raise ValueError("non-finite score in calibration data")
    if y.all() or (~y).all():
        raise ValueError("calibration data must contain both oracle successes and failures")
    candidates = np.append(np.unique(s), np.inf)
    pred = s[None, :] >= candidates[:, None]
    tpr = (pred & y).sum(axis=1) / y.sum()
    tnr = (~pred & ~y).sum(axis=1) / (~y).sum()
    ba = 0.5 * (tpr + tnr)
    best = np.flatnonzero(ba == ba.max())[-1]
    return float(candidates[best]), float(ba[best])


def _judge_kinds(df: pd.DataFrame) -> dict[str, str]:
    kinds: dict[str, str] = {}
    for judge, sub in df.groupby("judge", sort=True):
        explicit = sub["judge_kind"].dropna().unique() if "judge_kind" in sub else []
        if len(explicit) > 1:
            raise ValueError(f"judge {judge!r}: inconsistent judge_kind {list(explicit)}")
        if len(explicit) == 1:
            kinds[judge] = str(explicit[0])
        elif str(judge).casefold() in SCORE_JUDGES:
            kinds[judge] = "score"
        elif sub["verdict"].notna().all():
            kinds[judge] = "verdict"
        elif sub["score"].notna().all():
            kinds[judge] = "score"
        else:
            raise ValueError(f"judge {judge!r}: rows have neither a verdict nor a score throughout")
    return kinds


def apply_thresholds(
    df: pd.DataFrame, calib_split_ids: set[str], oracle: dict[str, bool]
) -> pd.DataFrame:
    """Return a copy of ``df`` with final ``accept`` decisions and a ``split`` column.

    * ``split`` = ``"calibration"`` for ``calib_split_ids``, else ``"train"`` (PREREG §3).
    * Score judges: ``tau`` fitted by :func:`fit_max_ba_threshold` on rows whose episode is in the
      calibration split AND in ``oracle`` — never on training rows (leakage guard) — then applied to
      every row of that judge. Columns ``threshold``, ``threshold_source``, ``calibration_ba``.
    * Verdict judges keep their own ``accept`` (``threshold_source = "native_verdict"``).
    * ``verdict == CANT_TELL`` forces ``accept = False`` for every judge (PREREG §4 arm 3).
    """
    calib = {str(e) for e in calib_split_ids}
    if not calib:
        raise ValueError("calibration split is empty: thresholds cannot be fitted (PREREG §3)")
    out = df.copy()
    out.attrs = dict(df.attrs)
    out["split"] = np.where(out["episode_id"].isin(calib), "calibration", "train")
    out["accept_raw"] = out["accept"].astype(bool)
    out["accept"] = out["accept"].astype(bool)
    out["threshold"] = np.nan
    out["threshold_source"] = "native_verdict"
    out["calibration_ba"] = np.nan
    kinds = _judge_kinds(out) if len(out) else {}
    for judge, kind in kinds.items():
        if kind != "score":
            continue
        mask = out["judge"] == judge
        if out.loc[mask, "score"].isna().any():
            raise ValueError(f"score judge {judge!r} has rows without a score")
        cal = out[mask & (out["split"] == "calibration") & out["episode_id"].isin(set(oracle))]
        if cal.empty:
            raise ValueError(f"score judge {judge!r}: no labelled calibration episodes")
        tau, ba = fit_max_ba_threshold(
            cal["score"].astype(float), [oracle[e] for e in cal["episode_id"]]
        )
        out.loc[mask, "accept"] = out.loc[mask, "score"].astype(float) >= tau
        out.loc[mask, "threshold"] = tau
        out.loc[mask, "threshold_source"] = "calibration_max_ba"
        out.loc[mask, "calibration_ba"] = ba
    cant = out["verdict"] == "CANT_TELL"
    out.loc[cant, "accept"] = False
    out.attrs["calib_split_ids"] = sorted(calib)
    out.attrs["n_cant_tell_forced_reject"] = int((cant & out["accept_raw"]).sum())
    or_synth = bool(getattr(oracle, "synthetic", False))
    or_mock = getattr(oracle, "is_mock", None)
    out.attrs["synthetic"] = bool(out.attrs.get("synthetic", False)) or or_synth
    out.attrs["is_mock"] = bool(out.attrs.get("is_mock", True)) or (or_mock is None or bool(or_mock))
    out.attrs["provenance_declared"] = bool(out.attrs.get("provenance_declared", False)) and (
        or_mock is not None
    )
    return out


def size_matched_control(
    kodiac_accepted_ids: Iterable[str],
    oracle: Mapping[str, bool],
    train_ids: Iterable[str],
    seed: int = 0,
) -> list[str]:
    """PREREG §4 arm 9: a seeded random subset of training-split oracle successes with
    ``|set| = |Kodiac accepted|`` (raises if there are not enough oracle successes)."""
    target = len(set(kodiac_accepted_ids))
    pool = sorted(e for e in set(train_ids) if oracle.get(e, False))
    if target > len(pool):
        raise ValueError(f"need {target} oracle successes, only {len(pool)} in the training split")
    return sorted(random.Random(seed).sample(pool, target))


def load_arm_evals(evals_dir: Path) -> dict[str, ArmSuccess]:
    """Load downstream eval results ``<evals_dir>/*.json`` into ``{arm: ArmSuccess}``.

    One file per (arm, training seed): ``{"arm": str, "seed": int, "success": [0/1 per eval episode],
    "is_mock": bool, "synthetic": bool, "source": str}``. A missing ``is_mock`` means unknown provenance
    and is treated as mock. Duplicate (arm, seed) pairs raise ``ValueError``.
    """
    root = Path(evals_dir)
    merged: dict[str, dict[int, list[float]]] = {}
    flags: dict[str, list[tuple[bool, bool, str]]] = {}
    if not root.is_dir():
        return {}
    for path in sorted(root.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        arm = str(rec["arm"])
        seed = int(rec["seed"])
        if seed in merged.setdefault(arm, {}):
            raise ValueError(f"duplicate eval for arm {arm!r} seed {seed}: {path}")
        merged[arm][seed] = [float(x) for x in rec["success"]]
        declared = rec.get("is_mock") is not None
        flags.setdefault(arm, []).append(
            (
                "SYNTHETIC" in path.name.upper() or _as_bool(rec.get("synthetic", False)),
                _as_bool(rec["is_mock"]) if declared else True,
                str(rec.get("source", path)),
            )
        )
    return {
        arm: ArmSuccess(
            data,
            synthetic=any(f[0] for f in flags[arm]),
            is_mock=any(f[1] for f in flags[arm]),
            source=";".join(f[2] for f in flags[arm]),
        )
        for arm, data in merged.items()
    }
