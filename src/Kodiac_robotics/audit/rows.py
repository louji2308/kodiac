"""Shared row schema helpers for the dataset-audit tooling (F49-F52).

Audit DataFrames are VerdictRow-conformant (contracts.core.VerdictRow) plus a few clearly
labelled extra columns. ``human_verified`` is ``None`` unless a reviewer decision file set it.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd

from Kodiac_robotics.contracts.core import VerdictRow

DEMO_BANNER = "DEMONSTRATION DATA: fixture clips, not a real dataset audit"
TEMPLATE_FALLBACK_BADGE = "[COMPILER: DETERMINISTIC TEMPLATE FALLBACK]"

VERDICT_ROW_COLUMNS: list[str] = list(VerdictRow.model_fields.keys())
EXTRA_COLUMNS: list[str] = [
    "task",
    "clip_path",
    "is_fixture",
    "is_demonstration_data",
    "notes",
    "error",
    "review_decision",
    "reviewer",
]
ALL_COLUMNS: list[str] = VERDICT_ROW_COLUMNS + EXTRA_COLUMNS

_SORT_KEYS = ["dataset", "camera", "episode_index"]


def clean(value: Any) -> Any:
    """Normalise pandas/pyarrow missing values (NaN, NA, NaT) to None."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return [str(v) for v in list(value)]
    except TypeError:
        return []


def to_verdict_row(record: dict[str, Any]) -> VerdictRow:
    """Validate one DataFrame record against the frozen VerdictRow contract."""
    payload: dict[str, Any] = {}
    for name in VERDICT_ROW_COLUMNS:
        raw = record.get(name)
        if name == "reasons":
            payload[name] = _as_list(raw)
            continue
        val = clean(raw)
        if name in ("episode_index", "frame") and val is not None:
            val = int(val)
        if name == "human_verified" and val is not None:
            val = bool(val)
        payload[name] = val
    return VerdictRow(**payload)


def normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Return a sorted copy with every audit column present and human_verified as object."""
    out = df.copy()
    for col in ALL_COLUMNS:
        if col not in out.columns:
            out[col] = None
    out["human_verified"] = pd.Series(
        [None if clean(v) is None else bool(v) for v in out["human_verified"]],
        index=out.index,
        dtype=object,
    )
    extra = [c for c in out.columns if c not in ALL_COLUMNS]
    out = out[ALL_COLUMNS + extra]
    out = out.sort_values(_SORT_KEYS, kind="mergesort").reset_index(drop=True)
    return out


def write_verdicts(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalize_frame(df).to_parquet(path, index=False)


def load_verdicts(path: Path) -> pd.DataFrame:
    return normalize_frame(pd.read_parquet(path))


def is_demo_frame(df: pd.DataFrame) -> bool:
    if "is_demonstration_data" not in df.columns or df.empty:
        return False
    return any(bool(clean(v)) for v in df["is_demonstration_data"])
