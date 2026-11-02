"""Operations guards (F57): per-client token bucket, upload retention reaper, PII-free logging."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path

logger = logging.getLogger("kodiac.app")


def hash_token(value: str, salt: str) -> str:
    """Short salted hash used wherever a client address or filename would otherwise be logged."""
    return hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()[:12]


def log_event(event: str, **fields: object) -> None:
    """Emit one structured JSON log line. Callers pass only hashed/aggregate values (no PII)."""
    payload = {"event": event, **fields}
    logger.info(json.dumps(payload, sort_keys=True, default=str))


class TokenBucket:
    """Per-key token bucket: ``capacity`` tokens, refilled at ``rate_per_min`` per minute."""

    def __init__(
        self,
        rate_per_min: float,
        capacity: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.rate_per_s = max(rate_per_min, 0.0) / 60.0
        self.capacity = float(capacity if capacity is not None else max(rate_per_min, 1.0))
        self._clock = clock
        self._state: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def take(self, key: str) -> tuple[bool, float]:
        """Try to spend one token. Returns (allowed, retry_after_seconds)."""
        now = self._clock()
        with self._lock:
            tokens, last = self._state.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate_per_s)
            if tokens >= 1.0:
                self._state[key] = (tokens - 1.0, now)
                self._prune(now)
                return True, 0.0
            self._state[key] = (tokens, now)
            wait = (1.0 - tokens) / self.rate_per_s if self.rate_per_s > 0 else 60.0
            return False, wait

    def _prune(self, now: float) -> None:
        if len(self._state) <= 10_000:
            return
        stale = [k for k, (_, last) in self._state.items() if now - last > 3600]
        for k in stale:
            del self._state[k]


def reap_old_files(dirs: Iterable[Path], max_age_s: float, now: float | None = None) -> int:
    """Delete files (and emptied sub-directories) older than ``max_age_s`` under each directory."""
    cutoff = (time.time() if now is None else now) - max_age_s
    removed = 0
    for root in dirs:
        root = Path(root)
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
                elif path.is_dir() and not any(path.iterdir()) and path.stat().st_mtime < cutoff:
                    path.rmdir()
            except OSError:
                continue
    return removed


__all__ = ["TokenBucket", "hash_token", "log_event", "logger", "reap_old_files"]
