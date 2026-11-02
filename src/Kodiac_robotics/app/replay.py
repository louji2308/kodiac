"""Content-addressed replay store: instant, clearly-labelled cached results (F56).

Layout under ``root``::

    index.json                  {entry_id: ReplayEntry}
    blobs/<sha256>.json         RunResult JSON
    blobs/<sha256>.png          Verdict card PNG

Every entry records ``is_fixture``, the perception ``backend``, ``created_at`` and the source commit,
and ``get`` re-hashes the blobs so a tampered or corrupted replay is refused instead of shown.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from Kodiac_robotics.contracts.core import RunResult

CACHED_BADGE = "⚡ CACHED"
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,79}$")


def valid_replay_id(replay_id: str) -> bool:
    return bool(_ID_RE.match(replay_id))


def current_commit() -> str:
    """Short git commit of the source tree, or ``KODIAC_COMMIT`` / ``unknown``."""
    env = os.environ.get("KODIAC_COMMIT")
    if env:
        return env
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=Path(__file__).resolve().parent,
        )
        sha = out.stdout.strip()
        if out.returncode == 0 and sha:
            return sha
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown"


class ReplayEntry(BaseModel):
    id: str
    title: str = ""
    verdict: str
    test_name: str
    clip_label: str
    is_fixture: bool
    backend: str
    created_at: str
    source_commit: str
    result_sha256: str
    card_sha256: str
    run_total_ms: int
    badges: list[str]
    note: str = ""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ReplayStore:
    """Filesystem replay store; safe for concurrent readers and in-process concurrent writers."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self._lock = threading.Lock()

    @property
    def _index_path(self) -> Path:
        return self.root / "index.json"

    @property
    def _blobs(self) -> Path:
        return self.root / "blobs"

    def _read_index(self) -> dict[str, dict]:
        try:
            return json.loads(self._index_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write_atomic(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_bytes(data)
        for attempt in range(12):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 11:
                    path.write_bytes(data)
                    try:
                        tmp.unlink(missing_ok=True)
                    except OSError:
                        pass
                    return
                time.sleep(0.05 * (attempt + 1))

    def put(
        self,
        replay_id: str,
        run_result: RunResult,
        card_png: bytes,
        *,
        title: str = "",
        clip_label: str = "",
        note: str = "",
        source_commit: str | None = None,
    ) -> ReplayEntry:
        if not valid_replay_id(replay_id):
            raise ValueError(f"invalid replay id: {replay_id!r}")
        result_bytes = run_result.model_dump_json(indent=2).encode("utf-8")
        result_sha = _sha256(result_bytes)
        card_sha = _sha256(card_png)
        entry = ReplayEntry(
            id=replay_id,
            title=title or replay_id,
            verdict=run_result.verdict.value,
            test_name=run_result.test_name,
            clip_label=clip_label or replay_id,
            is_fixture=run_result.is_fixture,
            backend=run_result.backends.get("perception", "unknown"),
            created_at=datetime.now(timezone.utc).isoformat(),
            source_commit=source_commit or current_commit(),
            result_sha256=result_sha,
            card_sha256=card_sha,
            run_total_ms=int(run_result.timings_ms.get("total_ms", 0)),
            badges=list(run_result.badges),
            note=note,
        )
        with self._lock:
            self._write_atomic(self._blobs / f"{result_sha}.json", result_bytes)
            self._write_atomic(self._blobs / f"{card_sha}.png", card_png)
            index = self._read_index()
            index[replay_id] = entry.model_dump()
            self._write_atomic(
                self._index_path, json.dumps(index, indent=2, sort_keys=True).encode("utf-8")
            )
        return entry

    def entry(self, replay_id: str) -> ReplayEntry | None:
        raw = self._read_index().get(replay_id)
        return ReplayEntry.model_validate(raw) if raw else None

    def get(self, replay_id: str) -> tuple[ReplayEntry, RunResult, bytes] | None:
        """Return (entry, run_result, card_png), or None when absent. Raises ValueError on hash mismatch."""
        entry = self.entry(replay_id)
        if entry is None:
            return None
        try:
            result_bytes = (self._blobs / f"{entry.result_sha256}.json").read_bytes()
            card = (self._blobs / f"{entry.card_sha256}.png").read_bytes()
        except FileNotFoundError:
            return None
        if _sha256(result_bytes) != entry.result_sha256 or _sha256(card) != entry.card_sha256:
            raise ValueError(f"replay {replay_id!r} failed its content-hash check")
        return entry, RunResult.model_validate_json(result_bytes), card

    def card_bytes(self, replay_id: str) -> bytes | None:
        got = self.get(replay_id)
        return got[2] if got else None

    def prune(self) -> int:
        """Delete blobs no index entry references (left behind when an entry id is re-recorded)."""
        with self._lock:
            keep: set[str] = set()
            for raw in self._read_index().values():
                keep.add(f"{raw['result_sha256']}.json")
                keep.add(f"{raw['card_sha256']}.png")
            removed = 0
            if self._blobs.is_dir():
                for p in self._blobs.iterdir():
                    if p.is_file() and p.name not in keep:
                        p.unlink()
                        removed += 1
            return removed

    def list(self) -> list[ReplayEntry]:
        entries = [ReplayEntry.model_validate(v) for v in self._read_index().values()]
        return sorted(entries, key=lambda e: e.id)


__all__ = ["CACHED_BADGE", "ReplayEntry", "ReplayStore", "current_commit", "valid_replay_id"]
