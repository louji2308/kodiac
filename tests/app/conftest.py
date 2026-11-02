"""Shared fixtures for the hosted-app tests (fixture backend only; no network, no keys)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from Kodiac_robotics.app.precompute import CURATED_SPECS, precompute_replays
from Kodiac_robotics.app.settings import AppSettings

REPO_ROOT = Path(__file__).resolve().parents[2]
CLIPS = REPO_ROOT / "tests" / "fixtures" / "clips"
TEST_SPEC_IDS = {"stackcube__b01_early_release", "stackcube__occluded_clip"}


@pytest.fixture(scope="session")
def seeded_replay_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A replay store holding two genuinely computed replays (B1 FAIL, occluded CAN'T TELL)."""
    root = tmp_path_factory.mktemp("seeded")
    settings = AppSettings(
        replay_dir=root / "replays",
        upload_dir=root / "uploads",
        run_dir=root / "runs",
        mount_ui=False,
    )
    specs = [s for s in CURATED_SPECS if s.replay_id in TEST_SPEC_IDS]
    precompute_replays(settings, specs)
    return root / "replays"


@pytest.fixture
def make_settings(tmp_path: Path, seeded_replay_dir: Path):
    def _make(**overrides: object) -> AppSettings:
        replay_dir = tmp_path / "replays"
        if not replay_dir.exists():
            shutil.copytree(seeded_replay_dir, replay_dir)
        base: dict[str, object] = {
            "replay_dir": replay_dir,
            "upload_dir": tmp_path / "uploads",
            "run_dir": tmp_path / "runs",
            "mount_ui": False,
            "rate_per_min": 60.0,
        }
        base.update(overrides)
        return AppSettings(**base)  # type: ignore[arg-type]

    return _make
