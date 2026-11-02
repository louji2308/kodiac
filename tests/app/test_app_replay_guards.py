"""Replay store integrity and operations guards (token bucket, reaper)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from Kodiac_robotics.app.guards import TokenBucket, hash_token, reap_old_files
from Kodiac_robotics.app.replay import ReplayStore


def test_store_roundtrip_metadata_and_integrity(seeded_replay_dir: Path, tmp_path: Path) -> None:
    store = ReplayStore(seeded_replay_dir)
    entries = store.list()
    assert {e.id for e in entries} == {"stackcube__b01_early_release", "stackcube__occluded_clip"}
    entry, run, card = store.get("stackcube__b01_early_release") or (None, None, None)
    assert entry is not None and run is not None and card is not None
    assert entry.is_fixture is True and run.is_fixture is True
    assert entry.backend == "cached_replay"
    assert entry.created_at and entry.source_commit
    assert entry.verdict == "FAIL" and card[:8] == b"\x89PNG\r\n\x1a\n"
    assert "C:" not in run.model_dump_json() and "tests/fixtures" not in run.model_dump_json()

    other = ReplayStore(tmp_path / "other")
    other.put("x1", run, card, title="t")
    assert other.get("x1") is not None
    assert other.get("missing") is None
    with pytest.raises(ValueError):
        other.put("../evil", run, card)


def test_store_refuses_tampered_blob(seeded_replay_dir: Path, tmp_path: Path) -> None:
    import shutil

    root = tmp_path / "copy"
    shutil.copytree(seeded_replay_dir, root)
    store = ReplayStore(root)
    entry = store.entry("stackcube__b01_early_release")
    assert entry is not None
    (root / "blobs" / f"{entry.card_sha256}.png").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="content-hash"):
        store.get("stackcube__b01_early_release")


def test_store_prune_removes_orphans(seeded_replay_dir: Path, tmp_path: Path) -> None:
    import shutil

    root = tmp_path / "copy2"
    shutil.copytree(seeded_replay_dir, root)
    (root / "blobs" / "orphan.png").write_bytes(b"x")
    assert ReplayStore(root).prune() == 1
    assert len(ReplayStore(root).list()) == 2


def test_token_bucket_limits_and_refills() -> None:
    now = [0.0]
    bucket = TokenBucket(rate_per_min=6, clock=lambda: now[0])
    assert all(bucket.take("a")[0] for _ in range(6))
    allowed, wait = bucket.take("a")
    assert not allowed and wait == pytest.approx(10.0)
    assert bucket.take("b")[0], "buckets are per client"
    now[0] += 10.0
    assert bucket.take("a")[0]
    assert not bucket.take("a")[0]


def test_reaper_deletes_only_old_files(tmp_path: Path) -> None:
    up = tmp_path / "uploads"
    (up / "sub").mkdir(parents=True)
    old, fresh = up / "old.mp4", up / "sub" / "fresh.mp4"
    old.write_bytes(b"1")
    fresh.write_bytes(b"2")
    t_old = time.time() - 25 * 3600
    os.utime(old, (t_old, t_old))
    assert reap_old_files([up], 24 * 3600) == 1
    assert not old.exists() and fresh.exists()


def test_hash_token_is_stable_salted_and_hides_input() -> None:
    a = hash_token("203.0.113.9", "salt")
    assert a == hash_token("203.0.113.9", "salt") != hash_token("203.0.113.9", "other")
    assert "203" not in a and len(a) == 12
