"""Practice pool generator and pre-registration metadata anchoring.

Implements 100-episode sharded Parquet generation, cryptographic pre-registration
hash embedding, action-state trajectory logging in pd_ee_delta_pos space,
and mock kinematic generation for 100% offline CI.
Per ARCHITECTURE.md §5.7, ADR-0006, ADR-0007, and P02 RULING.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from pydantic import BaseModel, Field

# ==============================================================================
# Interface Contracts
# ==============================================================================


class PoolEpisodeRecord(BaseModel):
    """Metadata record for a single episode in the practice pool."""

    episode_id: str
    split: Literal["calibration", "train"]
    video_uri: str
    state_uri: str
    oracle_success: bool
    perturbation_type: str | None = None
    onset_frame: int | None = None
    seed: int
    n_frames: int
    fps: float = 30.0
    is_mock: bool = False


# ==============================================================================
# Pre-Registration Verification Helpers (ADR-0006)
# ==============================================================================


def find_repo_root(start: Path | None = None) -> Path:
    """Locate the git repository root."""
    cur = (start or Path.cwd()).resolve()
    for parent in [cur, *cur.parents]:
        if (parent / ".git").is_dir() or (parent / "pyproject.toml").is_file():
            return parent
    return cur


def compute_file_sha256(filepath: Path) -> str:
    """Calculate hex-encoded SHA-256 checksum of a file."""
    if not filepath.is_file():
        raise FileNotFoundError(f"Required file not found: {filepath}")
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_prereg_hashes(repo_root: Path | None = None) -> tuple[str, str]:
    """Compute SHA-256 hashes for PREREGISTRATION.md and pool_config.yaml."""
    root = find_repo_root(repo_root)
    prereg_path = root / "experiments" / "PREREGISTRATION.md"
    config_path = root / "experiments" / "pool_config.yaml"

    prereg_sha = compute_file_sha256(prereg_path)
    config_sha = compute_file_sha256(config_path)
    return prereg_sha, config_sha


def verify_preregistration_tag(
    repo_root: Path | None = None,
    required_tag: str = "prereg-v0",
) -> bool:
    """Check whether the required pre-registration git tag exists."""
    root = find_repo_root(repo_root)
    try:
        res = subprocess.run(
            ["git", "tag", "-l", required_tag],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0 and required_tag in res.stdout.split():
            return True
    except Exception:
        pass

    # Check direct tag ref on disk if git command fails or in sandboxed git
    tag_ref = root / ".git" / "refs" / "tags" / required_tag
    if tag_ref.is_file():
        return True

    packed_refs = root / ".git" / "packed-refs"
    if packed_refs.is_file():
        try:
            content = packed_refs.read_text(encoding="utf-8")
            if f"refs/tags/{required_tag}" in content:
                return True
        except Exception:
            pass

    return False


def assert_preregistration_ready(
    repo_root: Path | None = None,
    required_tag: str = "prereg-v0",
    allow_untagged: bool = False,
) -> tuple[str, str, str]:
    """Validate pre-registration invariant I8 before generation.

    Returns:
        (prereg_sha256, config_sha256, required_tag)
    Raises:
        RuntimeError if prereg-v0 tag is missing and allow_untagged is False.
    """
    root = find_repo_root(repo_root)
    prereg_sha, config_sha = compute_prereg_hashes(root)

    tag_exists = verify_preregistration_tag(root, required_tag)
    if not tag_exists and not allow_untagged:
        raise RuntimeError(
            f"Pre-registration invariant I8 violated: {required_tag} tag missing. "
            "Pre-registration document and pool config must be tagged before pool generation."
        )

    return prereg_sha, config_sha, required_tag


# ==============================================================================
# PyArrow Schema & Table Builders
# ==============================================================================

PYARROW_EPISODE_SCHEMA = pa.schema(
    [
        ("episode_id", pa.string()),
        ("split", pa.string()),
        ("video_uri", pa.string()),
        ("state_uri", pa.string()),
        ("oracle_success", pa.bool_()),
        ("perturbation_type", pa.string()),
        ("onset_frame", pa.int64()),
        ("seed", pa.int64()),
        ("n_frames", pa.int64()),
        ("fps", pa.float64()),
        ("is_mock", pa.bool_()),
    ]
)


def records_to_pyarrow_table(
    records: list[PoolEpisodeRecord],
    config_sha256: str,
    prereg_sha256: str,
    prereg_tag: str = "prereg-v0",
    is_mock: bool = False,
) -> pa.Table:
    """Convert a list of PoolEpisodeRecord to a PyArrow Table with embedded metadata."""
    data: dict[str, list[Any]] = {
        "episode_id": [r.episode_id for r in records],
        "split": [r.split for r in records],
        "video_uri": [r.video_uri for r in records],
        "state_uri": [r.state_uri for r in records],
        "oracle_success": [r.oracle_success for r in records],
        "perturbation_type": [r.perturbation_type or "" for r in records],
        "onset_frame": [r.onset_frame if r.onset_frame is not None else -1 for r in records],
        "seed": [r.seed for r in records],
        "n_frames": [r.n_frames for r in records],
        "fps": [r.fps for r in records],
        "is_mock": [r.is_mock for r in records],
    }

    table = pa.Table.from_pydict(data, schema=PYARROW_EPISODE_SCHEMA)

    # Attach cryptographic pre-registration provenance metadata
    metadata = {
        b"config_sha256": config_sha256.encode("utf-8"),
        b"prereg_sha256": prereg_sha256.encode("utf-8"),
        b"prereg_tag": prereg_tag.encode("utf-8"),
        b"created_at": datetime.datetime.now(datetime.timezone.utc).isoformat().encode("utf-8"),
        b"total_episodes": str(len(records)).encode("utf-8"),
        b"is_mock": (b"true" if is_mock else b"false"),
    }
    return table.replace_schema_metadata(metadata)


# ==============================================================================
# Practice Pool Generator Class
# ==============================================================================


class PracticePoolGenerator:
    """Orchestrates practice pool generation and sharded Parquet persistence."""

    def __init__(
        self,
        output_dir: Path | str,
        config_path: Path | str | None = None,
        allow_untagged: bool = False,
        repo_root: Path | None = None,
    ) -> None:
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.shards_dir = self.output_dir / "shards"
        self.shards_dir.mkdir(parents=True, exist_ok=True)
        self.episodes_dir = self.output_dir / "episodes"
        self.episodes_dir.mkdir(parents=True, exist_ok=True)

        self.repo_root = find_repo_root(repo_root)
        self.config_path = (
            Path(config_path).resolve()
            if config_path
            else self.repo_root / "experiments" / "pool_config.yaml"
        )
        self.allow_untagged = allow_untagged

        # Verify pre-registration integrity (ADR-0006)
        self.prereg_sha, self.config_sha, self.prereg_tag = assert_preregistration_ready(
            repo_root=self.repo_root,
            allow_untagged=self.allow_untagged,
        )

        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        self.shard_size = int(self.config.get("sharding", {}).get("shard_size", 100))
        self.records: list[PoolEpisodeRecord] = []

    def save_episode_state(
        self,
        episode_id: str,
        actions: np.ndarray,
        obs_state: np.ndarray,
        cam_K: np.ndarray,
        cam_extrinsic: np.ndarray,
        oracle_success: bool,
        perturbation_type: str | None = None,
        onset_frame: int | None = None,
        seed: int = 0,
        fps: float = 30.0,
        is_mock: bool = True,
    ) -> Path:
        """Write episode trajectory arrays to compressed NPZ following ADR-0007."""
        # Tripwire check: verify actions shape is (T, 7)
        if actions.ndim != 2 or actions.shape[1] != 7:
            raise ValueError(
                f"Episode {episode_id} action array must have shape (T, 7) in pd_ee_delta_pos, "
                f"got shape {actions.shape}"
            )
        if obs_state.ndim != 2 or obs_state.shape[0] != actions.shape[0]:
            raise ValueError(
                f"Episode {episode_id} obs_state length ({obs_state.shape[0]}) must match "
                f"actions length ({actions.shape[0]})"
            )

        state_path = self.episodes_dir / f"{episode_id}.state.npz"
        np.savez_compressed(
            state_path,
            actions=actions.astype(np.float32),
            obs_state=obs_state.astype(np.float32),
            cam_K=cam_K.astype(np.float32),
            cam_extrinsic=cam_extrinsic.astype(np.float32),
            oracle_success=bool(oracle_success),
            perturbation_type=str(perturbation_type or ""),
            onset_frame=int(onset_frame if onset_frame is not None else -1),
            seed=int(seed),
            fps=float(fps),
            is_mock=bool(is_mock),
        )
        return state_path

    def add_record(self, record: PoolEpisodeRecord) -> None:
        """Register a completed episode record and persist shards when boundary reached."""
        self.records.append(record)
        if len(self.records) % self.shard_size == 0:
            shard_idx = (len(self.records) // self.shard_size) - 1
            shard_records = self.records[shard_idx * self.shard_size : (shard_idx + 1) * self.shard_size]
            self._write_shard(shard_idx, shard_records)

    def _write_shard(self, shard_idx: int, shard_records: list[PoolEpisodeRecord]) -> Path:
        """Write a 100-episode shard Parquet file."""
        shard_path = self.shards_dir / f"shard_{shard_idx:04d}.parquet"
        is_mock = any(r.is_mock for r in shard_records)
        table = records_to_pyarrow_table(
            shard_records,
            config_sha256=self.config_sha,
            prereg_sha256=self.prereg_sha,
            prereg_tag=self.prereg_tag,
            is_mock=is_mock,
        )
        pq.write_table(table, shard_path, compression="zstd")
        return shard_path

    def finalize(self) -> Path:
        """Flush remaining episodes into final shard and write master manifest.parquet."""
        # Write any trailing records not aligned to shard_size
        written_count = (len(self.records) // self.shard_size) * self.shard_size
        if len(self.records) > written_count:
            shard_idx = len(self.records) // self.shard_size
            trailing_records = self.records[written_count:]
            self._write_shard(shard_idx, trailing_records)

        # Write master consolidated manifest
        manifest_path = self.output_dir / "manifest.parquet"
        is_mock = any(r.is_mock for r in self.records)
        master_table = records_to_pyarrow_table(
            self.records,
            config_sha256=self.config_sha,
            prereg_sha256=self.prereg_sha,
            prereg_tag=self.prereg_tag,
            is_mock=is_mock,
        )
        pq.write_table(master_table, manifest_path, compression="zstd")
        return manifest_path


# ==============================================================================
# Synthetic Mock Kinematic Generator (for 100% offline CI / unit tests)
# ==============================================================================


def generate_mock_episode(
    episode_idx: int,
    split: Literal["calibration", "train"],
    is_pi0: bool,
    perturbation_type: str | None,
    seed: int,
    output_dir: Path,
    fps: float = 30.0,
) -> tuple[PoolEpisodeRecord, Path]:
    """Generate a single mock kinematic episode adhering strictly to ADR-0004 and ADR-0007."""
    rng = np.random.default_rng(seed)
    T = rng.integers(120, 180)  # 4 to 6 seconds @ 30 fps

    episode_id = f"ep_{episode_idx:05d}_{split}"

    # Determine oracle success and onset frame based on perturbation
    if perturbation_type is None:
        if is_pi0:
            # pi0 weak policy: ~45% success
            oracle_success = bool(rng.random() < 0.45)
            onset_frame = None if oracle_success else rng.integers(int(T * 0.4), int(T * 0.8))
        else:
            oracle_success = True
            onset_frame = None
    else:
        oracle_success = False
        if perturbation_type == "early_open":
            onset_frame = int(T * rng.uniform(0.60, 0.85))
        elif perturbation_type == "xy_offset":
            onset_frame = int(T * 0.75)
        elif perturbation_type == "low_lift":
            onset_frame = int(T * 0.35)
        elif perturbation_type == "short_dwell":
            onset_frame = int(T * 0.90)
        else:
            onset_frame = int(T * 0.50)

    # Generate realistic delta actions (T, 7) in pd_ee_delta_pos space
    # [dx, dy, dz, dr, dp, dy, gripper]
    actions = np.zeros((T, 7), dtype=np.float32)
    t_reach = int(T * 0.30)
    t_lift = int(T * 0.55)
    t_place = int(T * 0.85)

    # Reach: downward movement, gripper open (+1.0)
    actions[:t_reach, 2] = -0.05 + rng.normal(0, 0.005, t_reach)
    actions[:t_reach, 6] = 1.0

    # Lift: upward movement, gripper closed (-1.0)
    actions[t_reach:t_lift, 2] = 0.08 + rng.normal(0, 0.005, t_lift - t_reach)
    actions[t_reach:t_lift, 6] = -1.0

    # Place: lateral move toward Cube B
    actions[t_lift:t_place, 0] = 0.03 + rng.normal(0, 0.005, t_place - t_lift)
    actions[t_lift:t_place, 2] = -0.04 + rng.normal(0, 0.005, t_place - t_lift)
    actions[t_lift:t_place, 6] = -1.0

    # Release and dwell
    actions[t_place:, 6] = 1.0  # Gripper opens
    actions[t_place:, :3] = rng.normal(0, 0.002, (T - t_place, 3))  # Settling dwell

    # Apply perturbation to actions
    if perturbation_type == "early_open" and onset_frame:
        actions[onset_frame:, 6] = 1.0
    elif perturbation_type == "xy_offset" and onset_frame:
        actions[onset_frame:t_place, 1] += 0.05
    elif perturbation_type == "low_lift" and onset_frame:
        actions[t_reach:t_lift, 2] = 0.01

    # Observation state: 32-dim vector (proprio: 9 + 9 + 7 + 1 = 26, objects: 7 + 7 = 14) -> e.g. 40-dim
    obs_dim = 32
    obs_state = np.zeros((T, obs_dim), dtype=np.float32)
    for t in range(T):
        # Progressively update simulated EE pose and cube poses
        obs_state[t, :7] = np.array([0.1 + 0.001 * t, 0.0, 0.2, 1.0, 0.0, 0.0, 0.0])  # EE pose
        obs_state[t, 7] = actions[t, 6]  # Gripper position
        obs_state[t, 8:15] = np.array([0.2, 0.0, 0.05, 1.0, 0.0, 0.0, 0.0])  # Cube A pose
        obs_state[t, 15:22] = np.array([0.25, 0.0, 0.02, 1.0, 0.0, 0.0, 0.0])  # Cube B pose

    # Known ManiSkill Camera calibration matrices
    cam_K = np.array(
        [[500.0, 0.0, 320.0], [0.0, 500.0, 240.0], [0.0, 0.0, 1.0]],
        dtype=np.float32,
    )
    cam_extrinsic = np.eye(4, dtype=np.float32)

    # Save state npz
    ep_dir = output_dir / "episodes"
    ep_dir.mkdir(parents=True, exist_ok=True)
    state_path = ep_dir / f"{episode_id}.state.npz"
    np.savez_compressed(
        state_path,
        actions=actions,
        obs_state=obs_state,
        cam_K=cam_K,
        cam_extrinsic=cam_extrinsic,
        oracle_success=oracle_success,
        perturbation_type=str(perturbation_type or ""),
        onset_frame=int(onset_frame if onset_frame is not None else -1),
        seed=seed,
        fps=fps,
        is_mock=True,
    )

    # Video placeholder URI (in mock mode, relative URI)
    video_uri = f"episodes/{episode_id}.mp4"

    record = PoolEpisodeRecord(
        episode_id=episode_id,
        split=split,
        video_uri=video_uri,
        state_uri=f"episodes/{episode_id}.state.npz",
        oracle_success=oracle_success,
        perturbation_type=perturbation_type,
        onset_frame=onset_frame,
        seed=seed,
        n_frames=T,
        fps=fps,
        is_mock=True,
    )
    return record, state_path


def generate_mock_pool(
    output_dir: Path | str,
    n_episodes: int = 20,
    calibration_ratio: float = 0.20,
    pi0_ratio: float = 0.70,
    base_seed: int = 42,
    allow_untagged: bool = True,
    repo_root: Path | None = None,
) -> Path:
    """Generate a complete mock pool for offline validation and CI."""
    out = Path(output_dir).resolve()
    generator = PracticePoolGenerator(
        output_dir=out,
        allow_untagged=allow_untagged,
        repo_root=repo_root,
    )

    perturbation_types = ["early_open", "xy_offset", "low_lift", "short_dwell", "regrasp"]
    rng = np.random.default_rng(base_seed)

    n_cal = int(n_episodes * calibration_ratio)

    for i in range(n_episodes):
        split: Literal["calibration", "train"] = "calibration" if i < n_cal else "train"
        is_pi0 = bool(rng.random() < pi0_ratio)
        pert = None if is_pi0 else rng.choice(perturbation_types)
        seed = int(base_seed + i * 17)

        record, _ = generate_mock_episode(
            episode_idx=i,
            split=split,
            is_pi0=is_pi0,
            perturbation_type=pert,
            seed=seed,
            output_dir=out,
        )
        generator.add_record(record)

    return generator.finalize()
