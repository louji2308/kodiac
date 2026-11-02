"""Prefix salvage: keep the good part of a failed trajectory for retraining. ARCHITECTURE.md section 9.

`cut = t* - margin_s` (default 0.5 s), kept only if the prefix lasts >= `min_keep_s` (1.0 s).
For chunked policies, only chunk starts with `s + H_a <= cut` are sampled, so no training
chunk ever reaches the failure onset.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Literal

import numpy as np


def salvage_cut(
    t_star_s: float,
    fps: float,
    *,
    margin_s: float = 0.5,
    min_keep_s: float = 1.0,
) -> int | None:
    """Last kept frame index (inclusive), or None when the clean prefix is shorter than min_keep_s."""
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    cut_s = t_star_s - margin_s
    if cut_s < min_keep_s - 1e-9:
        return None
    return int(math.floor(cut_s * fps + 1e-9))


def chunk_safe_start_mask(n_kept: int, cut_frame: int, chunk_h: int | None) -> np.ndarray:
    """Boolean mask over kept frames: start s is usable iff `s + chunk_h <= cut_frame`."""
    starts = np.arange(n_kept)
    if chunk_h is None:
        return np.ones(n_kept, dtype=bool)
    if chunk_h < 1:
        raise ValueError(f"chunk_h must be >= 1, got {chunk_h}")
    return starts + chunk_h <= cut_frame


def _scalar(npz: Any, key: str, default: Any) -> Any:
    return npz[key].item() if key in npz.files else default


def export_prefix(
    episode_state_npz: Path,
    cut_frame: int,
    out_dir: Path,
    fmt: Literal["maniskill_h5", "lerobot"] = "lerobot",
    chunk_h: int | None = None,
) -> dict[str, Any]:
    """Write frames [0, cut_frame] of a `.state.npz` episode and return its manifest.

    `lerobot`: LeRobot-v2.0-style layout (parquet + meta json; the `lerobot` library is not
    installed here, so the layout is written by hand and not validated against it).
    `maniskill_h5`: `trajectory.h5` when h5py is importable, otherwise an npz with the same
    arrays; `written_format` in the manifest says which one was produced.
    """
    src = Path(episode_state_npz)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with np.load(src, allow_pickle=False) as npz:
        actions = np.asarray(npz["actions"], dtype=np.float32)
        obs = np.asarray(npz["obs_state"], dtype=np.float32)
        fps = float(_scalar(npz, "fps", 30.0))
        meta = {
            "seed": int(_scalar(npz, "seed", -1)),
            "is_mock": bool(_scalar(npz, "is_mock", True)),
            "source_oracle_success": bool(_scalar(npz, "oracle_success", False)),
            "perturbation_type": str(_scalar(npz, "perturbation_type", "")),
        }
    total = min(len(actions), len(obs))
    if cut_frame < 0 or cut_frame >= total:
        raise ValueError(f"cut_frame {cut_frame} outside episode of {total} frames")
    n_kept = cut_frame + 1
    acts, observations = actions[:n_kept], obs[:n_kept]
    mask = chunk_safe_start_mask(n_kept, cut_frame, chunk_h)

    manifest: dict[str, Any] = {
        "format": fmt,
        "source": str(src),
        "source_n_frames": int(total),
        "cut_frame": int(cut_frame),
        "n_frames_kept": int(n_kept),
        "fps": fps,
        "duration_kept_s": n_kept / fps,
        "chunk_h": chunk_h,
        "chunk_safe_start_mask": [bool(b) for b in mask],
        "n_chunk_safe_starts": int(mask.sum()),
        **meta,
        "note": (
            "Prefix of a FAILED episode cut before the blamed onset; not a success label. "
            + ("Source is a kinematic-mock rollout (is_mock)." if meta["is_mock"] else "")
        ).strip(),
    }

    if fmt == "lerobot":
        data_dir = out / "data" / "chunk-000"
        meta_dir = out / "meta"
        data_dir.mkdir(parents=True, exist_ok=True)
        meta_dir.mkdir(parents=True, exist_ok=True)
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.table(
            {
                "frame_index": pa.array(np.arange(n_kept, dtype=np.int64)),
                "timestamp": pa.array(np.arange(n_kept, dtype=np.float32) / np.float32(fps)),
                "episode_index": pa.array(np.zeros(n_kept, dtype=np.int64)),
                "index": pa.array(np.arange(n_kept, dtype=np.int64)),
                "task_index": pa.array(np.zeros(n_kept, dtype=np.int64)),
                "observation.state": pa.array(list(observations)),
                "action": pa.array(list(acts)),
                "chunk_safe_start": pa.array(mask),
            }
        )
        parquet_path = data_dir / "episode_000000.parquet"
        pq.write_table(table, parquet_path)
        info = {
            "codebase_version": "v2.0",
            "robot_type": "franka_panda_sim",
            "total_episodes": 1,
            "total_frames": n_kept,
            "fps": fps,
            "features": {
                "observation.state": {"dtype": "float32", "shape": [int(observations.shape[1])]},
                "action": {"dtype": "float32", "shape": [int(acts.shape[1])]},
            },
            "layout_validated_against_lerobot": False,
        }
        (meta_dir / "info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
        (meta_dir / "episodes.jsonl").write_text(
            json.dumps({"episode_index": 0, "tasks": ["stackcube prefix"], "length": n_kept}) + "\n",
            encoding="utf-8",
        )
        (meta_dir / "tasks.jsonl").write_text(
            json.dumps({"task_index": 0, "task": "stackcube prefix"}) + "\n", encoding="utf-8"
        )
        manifest.update(written_format="lerobot_parquet", files=[str(parquet_path)])
    elif fmt == "maniskill_h5":
        try:
            import h5py
        except ImportError:
            h5py = None
        if h5py is not None:
            h5_path = out / "trajectory.h5"
            with h5py.File(h5_path, "w") as f:
                grp = f.create_group("traj_0")
                grp.create_dataset("actions", data=acts)
                grp.create_dataset("obs", data=observations)
                grp.create_dataset("chunk_safe_start", data=mask)
            manifest.update(written_format="maniskill_h5", files=[str(h5_path)])
        else:
            npz_path = out / "trajectory_prefix.npz"
            np.savez_compressed(npz_path, actions=acts, obs=observations, chunk_safe_start=mask)
            manifest.update(
                written_format="npz_fallback",
                files=[str(npz_path)],
                h5py_available=False,
                note=manifest["note"] + " h5py not installed: wrote an npz with the same arrays.",
            )
    else:
        raise ValueError(f"unknown fmt {fmt!r}")

    manifest_path = out / "prefix_manifest.json"
    manifest["manifest_path"] = str(manifest_path)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
