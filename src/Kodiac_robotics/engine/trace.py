"""Audit trace writer for streaming execution events and predicate records.

Uses orjson for fast, line-delimited JSONL serialization to runs/<id>/trace.jsonl.
Per ARCHITECTURE.md §4.4 and P04 RULING.md (T03).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import orjson

from Kodiac_robotics.contracts.core import Event, PredFrame

logger = logging.getLogger(__name__)


class TraceWriter:
    """High-performance JSONL audit trace logger for Kodiac execution records."""

    def __init__(self, trace_path: Path | str) -> None:
        self.trace_path = Path(trace_path).resolve()
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.trace_path, "ab")

    def __enter__(self) -> TraceWriter:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def write_record(self, record: dict[str, Any]) -> None:
        """Write an arbitrary serializable record dictionary as a JSONL row."""
        line = orjson.dumps(record, option=orjson.OPT_NON_STR_KEYS) + b"\n"
        self._file.write(line)
        self._file.flush()

    def write_event(self, event: Event) -> None:
        """Serialize and log a physical event transition record."""
        payload = {
            "record_type": "event",
            "data": event.model_dump(mode="json"),
        }
        self.write_record(payload)

    def write_pred_frame(
        self,
        frame_idx: int,
        atom_name: str,
        pred_frame: PredFrame,
    ) -> None:
        """Serialize and log a per-frame predicate state record."""
        payload = {
            "record_type": "pred_frame",
            "frame": frame_idx,
            "atom": atom_name,
            "trace_id": pred_frame.trace_id,
            "tri": pred_frame.tri.value,
            "components": [c.model_dump(mode="json") for c in pred_frame.components],
        }
        self.write_record(payload)

    def close(self) -> None:
        """Flush buffers and safely close file handle."""
        if hasattr(self, "_file") and self._file and not self._file.closed:
            self._file.flush()
            self._file.close()


__all__ = ["TraceWriter"]
