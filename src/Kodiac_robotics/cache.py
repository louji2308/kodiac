"""Content-hash disk cache with atomic writes.

Guarantees determinism, offline test replay, and idempotent caching across runs.
Per KD-10, ARCHITECTURE.md §2 and TOOLS_AND_REQUIREMENTS.md §8.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable


def compute_key_hash(key_parts: dict[str, Any], payload: bytes | None = None) -> str:
    """Compute deterministic SHA-256 hash over canonical JSON key parts and optional payload."""
    canonical_json = json.dumps(
        key_parts,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")

    hasher = hashlib.sha256()
    hasher.update(canonical_json)
    if payload is not None:
        hasher.update(payload)
    return hasher.hexdigest()


def _atomic_write(target_path: Path, data: bytes) -> None:
    """Write data to target_path atomically using a temp file and atomic rename."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = target_path.parent

    # Write to a named temporary file in the same filesystem directory to ensure atomic os.replace
    with tempfile.NamedTemporaryFile(dir=temp_dir, delete=False, mode="wb") as tf:
        temp_name = tf.name
        tf.write(data)
        tf.flush()
        os.fsync(tf.fileno())

    try:
        os.replace(temp_name, target_path)
    except Exception:
        if os.path.exists(temp_name):
            os.remove(temp_name)
        raise


class DiskCache:
    """Thread-safe disk cache keyed by content SHA-256."""

    def __init__(self, root_dir: Path | str = ".cache/Kodiac") -> None:
        self.root_dir = Path(root_dir)

    def _path_for(self, key_hash: str, ext: str = ".json") -> Path:
        return self.root_dir / key_hash[:2] / f"{key_hash}{ext}"

    def get(self, key_parts: dict[str, Any], payload: bytes | None = None) -> Any | None:
        """Retrieve cached value if present, else None."""
        key_hash = compute_key_hash(key_parts, payload)
        json_path = self._path_for(key_hash, ".json")
        bin_path = self._path_for(key_hash, ".bin")

        if json_path.exists():
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        if bin_path.exists():
            with open(bin_path, "rb") as f:
                return f.read()
        return None

    def set(
        self,
        key_parts: dict[str, Any],
        value: Any,
        payload: bytes | None = None,
    ) -> str:
        """Atomically cache value. Returns key_hash."""
        key_hash = compute_key_hash(key_parts, payload)

        if isinstance(value, bytes):
            target = self._path_for(key_hash, ".bin")
            _atomic_write(target, value)
        else:
            target = self._path_for(key_hash, ".json")
            data = json.dumps(value, indent=2, sort_keys=True).encode("utf-8")
            _atomic_write(target, data)

        return key_hash


def cached_call(
    key_parts: dict[str, Any],
    fn: Callable[[], Any],
    cache_dir: Path | str | None = None,
    payload: bytes | None = None,
) -> Any:
    """Execute fn() if not already cached in cache_dir, saving the result atomically."""
    from Kodiac_robotics.config import get_settings

    if cache_dir is None:
        cache_dir = get_settings().cache_dir

    cache = DiskCache(cache_dir)
    cached_val = cache.get(key_parts, payload)
    if cached_val is not None:
        return cached_val

    val = fn()
    cache.set(key_parts, val, payload)
    return val
