"""Unit tests for PracticePoolGenerator, sharded Parquet export, and metadata anchoring.

Tests ADR-0006 metadata embedding and ADR-0007 action space contracts.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest

from Kodiac_robotics.proof.pool import (
    PoolEpisodeRecord,
    PracticePoolGenerator,
    generate_mock_episode,
    generate_mock_pool,
)


def test_pool_episode_record_validation() -> None:
    """Verify PoolEpisodeRecord contract validation."""
    record = PoolEpisodeRecord(
        episode_id="ep_00001_train",
        split="train",
        video_uri="episodes/ep_00001_train.mp4",
        state_uri="episodes/ep_00001_train.state.npz",
        oracle_success=True,
        seed=42,
        n_frames=150,
        fps=30.0,
        is_mock=True,
    )
    assert record.episode_id == "ep_00001_train"
    assert record.split == "train"
    assert record.is_mock is True


def test_generate_mock_pool_and_parquet_metadata() -> None:
    """Verify mock pool generation, sharding, Parquet schema, and embedded metadata."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        manifest_path = generate_mock_pool(
            output_dir=out_dir,
            n_episodes=25,
            calibration_ratio=0.20,
            allow_untagged=True,
        )

        assert manifest_path.is_file()
        assert manifest_path.name == "manifest.parquet"

        # Read manifest Parquet table and inspect schema & metadata
        table = pq.read_table(manifest_path)
        assert len(table) == 25

        metadata = table.schema.metadata
        assert b"config_sha256" in metadata
        assert b"prereg_sha256" in metadata
        assert metadata[b"prereg_tag"] == b"prereg-v0"
        assert metadata[b"is_mock"] == b"true"
        assert metadata[b"total_episodes"] == b"25"

        # Check column names
        expected_cols = {
            "episode_id",
            "split",
            "video_uri",
            "state_uri",
            "oracle_success",
            "perturbation_type",
            "onset_frame",
            "seed",
            "n_frames",
            "fps",
            "is_mock",
        }
        assert set(table.column_names) == expected_cols

        # Verify splits
        splits = table["split"].to_pylist()
        n_cal = sum(1 for s in splits if s == "calibration")
        n_train = sum(1 for s in splits if s == "train")
        assert n_cal == 5
        assert n_train == 20


def test_state_npz_trajectory_schema_and_action_dimensions() -> None:
    """Verify that every episode .state.npz contains actions (T, 7) in pd_ee_delta_pos (ADR-0007)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        record, state_path = generate_mock_episode(
            episode_idx=1,
            split="train",
            is_pi0=True,
            perturbation_type=None,
            seed=42,
            output_dir=out_dir,
        )

        assert state_path.is_file()
        with np.load(state_path) as data:
            # 1. Action array contract
            assert "actions" in data
            actions = np.array(data["actions"])
            assert actions.ndim == 2
            assert actions.shape[1] == 7  # 7-DoF pd_ee_delta_pos
            assert actions.dtype == np.float32

            # 2. Observation state contract
            assert "obs_state" in data
            obs_state = np.array(data["obs_state"])
            assert obs_state.ndim == 2
            assert obs_state.shape[0] == actions.shape[0]

            # 3. Camera calibration matrices
            assert "cam_K" in data
            assert data["cam_K"].shape == (3, 3)
            assert "cam_extrinsic" in data
            assert data["cam_extrinsic"].shape == (4, 4)

            # 4. Anti-fabrication flag
            assert "is_mock" in data
            assert bool(data["is_mock"]) is True


def test_pool_generator_sharding_boundary() -> None:
    """Verify that PracticePoolGenerator flushes 10-episode shards when configured."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        generator = PracticePoolGenerator(output_dir=out_dir, allow_untagged=True)
        generator.shard_size = 10  # Reduced for test

        # Add 25 records
        for i in range(25):
            rec, _ = generate_mock_episode(
                episode_idx=i,
                split="train",
                is_pi0=False,
                perturbation_type="early_open",
                seed=100 + i,
                output_dir=out_dir,
            )
            generator.add_record(rec)

        manifest = generator.finalize()
        assert manifest.is_file()

        # Check shards directory: 2 full shards (10 each) + 1 trailing shard (5)
        shards = sorted(list((out_dir / "shards").glob("*.parquet")))
        assert len(shards) == 3

        # Verify first shard has 10 rows
        s0 = pq.read_table(shards[0])
        assert len(s0) == 10
        # Verify trailing shard has 5 rows
        s2 = pq.read_table(shards[2])
        assert len(s2) == 5
