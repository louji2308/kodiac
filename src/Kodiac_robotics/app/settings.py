"""Runtime settings for the hosted app (env-configurable, no secrets stored here)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[3]


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


class AppSettings(BaseModel):
    """Configuration for `create_app`. Defaults describe the keyless fixture deployment."""

    backend: Literal["fixture", "api", "modal"] = "fixture"
    mode: Literal["live", "cache-only"] = "live"

    clips_dir: Path = REPO_ROOT / "tests" / "fixtures" / "clips"
    tracks_dir: Path = REPO_ROOT / "tests" / "fixtures" / "tracks"
    examples_dir: Path = REPO_ROOT / "examples"
    replay_dir: Path = REPO_ROOT / "site" / "replays"
    upload_dir: Path = REPO_ROOT / ".cache" / "app" / "uploads"
    run_dir: Path = REPO_ROOT / ".cache" / "app" / "runs"

    rate_per_min: float = Field(default_factory=lambda: _env_float("KODIAC_RATE_PER_MIN", 6.0))
    max_upload_mb: float = 50.0
    max_clip_seconds: float = 20.0
    retention_hours: float = 24.0
    trust_proxy: bool = False
    log_salt: str = Field(default_factory=lambda: os.environ.get("KODIAC_LOG_SALT", "kodiac-app"))
    mount_ui: bool = True

    @classmethod
    def from_env(cls) -> "AppSettings":
        """Build settings from KODIAC_APP_* environment variables (used by the Modal entrypoint)."""
        kwargs: dict[str, object] = {}
        backend = os.environ.get("KODIAC_APP_BACKEND")
        if backend in ("fixture", "api", "modal"):
            kwargs["backend"] = backend
        mode = os.environ.get("KODIAC_APP_MODE")
        if mode in ("live", "cache-only"):
            kwargs["mode"] = mode
        for env_name, field in (
            ("KODIAC_APP_REPLAY_DIR", "replay_dir"),
            ("KODIAC_APP_UPLOAD_DIR", "upload_dir"),
            ("KODIAC_APP_RUN_DIR", "run_dir"),
            ("KODIAC_APP_CLIPS_DIR", "clips_dir"),
            ("KODIAC_APP_TRACKS_DIR", "tracks_dir"),
        ):
            val = os.environ.get(env_name)
            if val:
                kwargs[field] = Path(val)
        if os.environ.get("KODIAC_APP_TRUST_PROXY") == "1":
            kwargs["trust_proxy"] = True
        return cls(**kwargs)  # type: ignore[arg-type]


__all__ = ["AppSettings", "REPO_ROOT"]
