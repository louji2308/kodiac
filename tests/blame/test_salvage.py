"""Prefix-salvage tests: cut boundaries, chunk-safe mask, lerobot/h5 roundtrips (mock-sim data)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest

from Kodiac_robotics.blame.salvage import chunk_safe_start_mask, export_prefix, salvage_cut

_REPO_ROOT = Path(__file__).resolve().parents[2]
_POOL_EP = _REPO_ROOT / "experiments" / "pool" / "episodes" / "ep_00004_train.state.npz"


def _episode(path: Path, n: int = 60) -> Path:
    rng = np.random.default_rng(0)
    np.savez_compressed(
        path,
        actions=rng.normal(size=(n, 7)).astype(np.float32),
        obs_state=rng.normal(size=(n, 5)).astype(np.float32),
        fps=np.float64(30.0),
        seed=np.int64(7),
        is_mock=np.bool_(True),
        oracle_success=np.bool_(False),
        perturbation_type=np.str_("B01"),
    )
    return path


# ------------------------------------------------------------------ salvage_cut
def test_cut_none_when_prefix_shorter_than_min_keep() -> None:
    assert salvage_cut(1.4, 30.0) is None
    assert salvage_cut(0.2, 30.0) is None
    assert salvage_cut(0.0, 30.0) is None


def test_cut_exact_frame_at_boundary() -> None:
    assert salvage_cut(1.5, 30.0) == 30  # cut_s == min_keep_s keeps the prefix
    assert salvage_cut(3.8, 30.0) == 99  # 3.3 s * 30 fps
    assert salvage_cut(1.6, 30.0) == 33  # float noise must not drop a frame (1.1*30=33.000000000000004)
    assert salvage_cut(1.55, 30.0) == 31


def test_cut_custom_margin_and_fps() -> None:
    assert salvage_cut(5.0, 10.0, margin_s=1.0, min_keep_s=2.0) == 40
    assert salvage_cut(2.5, 10.0, margin_s=1.0, min_keep_s=2.0) is None


def test_cut_rejects_bad_fps() -> None:
    with pytest.raises(ValueError):
        salvage_cut(3.0, 0.0)


# ---------------------------------------------------------------- chunk mask
def test_chunk_mask_requires_whole_chunk_before_cut() -> None:
    mask = chunk_safe_start_mask(n_kept=31, cut_frame=30, chunk_h=8)
    assert mask[22] and not mask[23]  # 22 + 8 == 30 <= cut, 23 + 8 > cut
    assert mask.sum() == 23
    assert chunk_safe_start_mask(5, 4, None).all()


def test_chunk_mask_longer_than_prefix_has_no_valid_start() -> None:
    assert not chunk_safe_start_mask(10, 9, chunk_h=16).any()


# ------------------------------------------------------------------ export
def test_lerobot_roundtrip(tmp_path: Path) -> None:
    src = _episode(tmp_path / "ep.state.npz")
    manifest = export_prefix(src, 29, tmp_path / "out", fmt="lerobot", chunk_h=8)
    assert manifest["n_frames_kept"] == 30 and manifest["written_format"] == "lerobot_parquet"
    assert manifest["is_mock"] is True and manifest["seed"] == 7
    table = pq.read_table(tmp_path / "out" / "data" / "chunk-000" / "episode_000000.parquet")
    orig = np.load(src)
    np.testing.assert_allclose(np.array(table["action"].to_pylist()), orig["actions"][:30])
    np.testing.assert_allclose(np.array(table["observation.state"].to_pylist()), orig["obs_state"][:30])
    assert table["frame_index"].to_pylist() == list(range(30))
    mask = table["chunk_safe_start"].to_pylist()
    assert mask == manifest["chunk_safe_start_mask"]
    assert mask[21] and not mask[22]  # 21 + 8 == 29 <= cut
    info = json.loads((tmp_path / "out" / "meta" / "info.json").read_text(encoding="utf-8"))
    assert info["total_frames"] == 30 and info["layout_validated_against_lerobot"] is False
    saved = json.loads((tmp_path / "out" / "prefix_manifest.json").read_text(encoding="utf-8"))
    assert saved["cut_frame"] == 29


def test_maniskill_manifest_roundtrip_or_labelled_fallback(tmp_path: Path) -> None:
    src = _episode(tmp_path / "ep.state.npz")
    manifest = export_prefix(src, 19, tmp_path / "out_ms", fmt="maniskill_h5", chunk_h=4)
    orig = np.load(src)
    path = Path(manifest["files"][0])
    assert path.is_file()
    if manifest["written_format"] == "maniskill_h5":
        h5py = pytest.importorskip("h5py")
        with h5py.File(path, "r") as f:
            np.testing.assert_allclose(f["traj_0/actions"][:], orig["actions"][:20])
    else:
        assert manifest["written_format"] == "npz_fallback" and manifest["h5py_available"] is False
        assert "h5py not installed" in manifest["note"]
        with np.load(path) as z:
            np.testing.assert_allclose(z["actions"], orig["actions"][:20])
            np.testing.assert_allclose(z["obs"], orig["obs_state"][:20])


def test_export_cut_bounds_and_format_validation(tmp_path: Path) -> None:
    src = _episode(tmp_path / "ep.state.npz", n=20)
    with pytest.raises(ValueError):
        export_prefix(src, 20, tmp_path / "o")
    with pytest.raises(ValueError):
        export_prefix(src, -1, tmp_path / "o")
    with pytest.raises(ValueError):
        export_prefix(src, 5, tmp_path / "o", fmt="hdf5")  # type: ignore[arg-type]


@pytest.mark.skipif(not _POOL_EP.is_file(), reason="practice-pool episode not present")
def test_real_pool_episode_prefix(tmp_path: Path) -> None:
    """ADR-0007 pool episodes (kinematic mock, is_mock) export cleanly; labelled as mock."""
    cut = salvage_cut(4.0, 30.0)
    assert cut == 105
    manifest = export_prefix(_POOL_EP, cut, tmp_path / "pool", chunk_h=16)
    assert manifest["n_frames_kept"] == 106 and manifest["is_mock"] is True
    assert manifest["n_chunk_safe_starts"] == 90  # starts 0..89: s + 16 <= 105
