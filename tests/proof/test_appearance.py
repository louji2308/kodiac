"""Unit tests for appearance benchmark dataset and manifest builder.

Verifies >= 60 clips, schema compliance, and balanced labels per IMPLEMENTATION_PLAN §P02.S16.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pyarrow.parquet as pq

from Kodiac_robotics.proof.appearance import (
    build_appearance_benchmark_manifest,
    generate_appearance_records,
)


def test_generate_appearance_records_count_and_balance() -> None:
    """Verify generated appearance records count and flush/ajar label distribution."""
    records = generate_appearance_records(total_clips=60)
    assert len(records) == 60

    flush_count = sum(1 for r in records if r.is_flush)
    ajar_count = sum(1 for r in records if not r.is_flush)

    # Approximately balanced
    assert flush_count == 30
    assert ajar_count == 30

    sim_count = sum(1 for r in records if r.source == "sim_articulated")
    droid_count = sum(1 for r in records if r.source == "droid_real")
    assert sim_count >= 35
    assert droid_count >= 15


def test_build_appearance_benchmark_manifest() -> None:
    """Verify Parquet export, schema, and metadata for appearance benchmark."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        manifest_path = build_appearance_benchmark_manifest(output_dir=out_dir, total_clips=60)

        assert manifest_path.is_file()
        assert manifest_path.name == "manifest.parquet"

        table = pq.read_table(manifest_path)
        assert len(table) == 60

        metadata = table.schema.metadata
        assert b"benchmark_name" in metadata
        assert metadata[b"total_clips"] == b"60"
        assert b"looks(drawer" in metadata[b"predicate"]

        # Check required columns
        expected_cols = {
            "clip_id",
            "clip_uri",
            "source",
            "object_name",
            "expected_state",
            "ground_truth_joint_pos_m",
            "ground_truth_label",
            "is_flush",
            "split",
            "is_mock",
        }
        assert set(table.column_names) == expected_cols
