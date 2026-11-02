"""LeRobot-compatible verdict export (F51): ``Kodiac_verdicts.parquet`` + evidence manifest.

The parquet carries every VerdictRow column (validated against the frozen contract) keyed by
``episode_index``. Two honesty columns are added: ``is_demonstration_data`` and ``notes`` (which
carries compiler / replay badges). ``human_verified`` is exported exactly as reviewers left it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from Kodiac_robotics.audit.rows import (
    DEMO_BANNER,
    VERDICT_ROW_COLUMNS,
    clean,
    is_demo_frame,
    normalize_frame,
    to_verdict_row,
)

PARQUET_NAME = "Kodiac_verdicts.parquet"
MANIFEST_NAME = "evidence_manifest.json"
_EXPORT_EXTRAS = ["is_demonstration_data", "notes"]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def export_verdicts(df: pd.DataFrame, out_dir: Path, evidence_root: Path | None = None) -> Path:
    """Write ``Kodiac_verdicts.parquet`` and ``evidence_manifest.json`` into ``out_dir``.

    Every row is validated against ``VerdictRow`` first (invalid rows raise). The manifest lists
    each evidence URI with its SHA-256 when the file is found under ``evidence_root``.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frame = normalize_frame(df)

    for rec in frame.to_dict("records"):
        to_verdict_row(rec)

    export = frame[VERDICT_ROW_COLUMNS + _EXPORT_EXTRAS].copy()
    export["is_demonstration_data"] = export["is_demonstration_data"].map(
        lambda v: bool(clean(v))
    )
    export["notes"] = export["notes"].map(lambda v: clean(v) or "")
    path = out_dir / PARQUET_NAME
    export.to_parquet(path, index=False)

    entries = []
    for rec in frame.to_dict("records"):
        uri = clean(rec["evidence_uri"])
        if not uri:
            continue
        entry: dict[str, object] = {
            "dataset": str(rec["dataset"]),
            "episode_index": int(rec["episode_index"]),
            "camera": str(rec["camera"]),
            "evidence_uri": str(uri),
            "sha256": None,
        }
        if evidence_root is not None:
            candidate = Path(evidence_root) / str(uri)
            if candidate.is_file():
                entry["sha256"] = _sha256(candidate)
        entries.append(entry)

    demo = is_demo_frame(frame)
    manifest = {
        "schema": "kodiac.audit.evidence_manifest/1",
        "is_demonstration_data": demo,
        "demonstration_banner": DEMO_BANNER if demo else None,
        "n_rows": len(frame),
        "evidence": entries,
    }
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return path


__all__ = ["MANIFEST_NAME", "PARQUET_NAME", "export_verdicts"]
