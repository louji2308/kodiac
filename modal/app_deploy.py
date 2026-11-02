"""Modal deployment of the hosted demo (CPU only; F53, F57). Deploying is a human action.

    modal deploy modal/app_deploy.py          # needs a Modal token; never run by agents
    KODIAC_MIN_CONTAINERS=1 modal deploy ...  # the Nov 4-16 warm setting, applied by a human/ORCH at release

This file has NOT been deployed from the build environment (no Modal token exists there), so the image recipe
below is unverified until the first real deploy. ``modal`` is imported lazily: without it the module still imports
and the pure helpers (unit-tested) work; ``app`` is then ``None``.

Design: FastAPI + Gradio ASGI app, concurrency 20 per container, one scheduled ``upload_reaper`` that deletes
uploads older than 24 h from the shared uploads volume. ``min_containers`` comes from the environment and defaults
to 0. No GPU is ever requested: the heavy models are hosted APIs (or replayed fixtures).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import types

REPO_ROOT = Path(__file__).resolve().parents[1]

APP_NAME = "Kodiac-demo"
MAX_INPUTS = 20
UPLOAD_RETENTION_HOURS = 24.0
MAX_MIN_CONTAINERS = 2
APT_PACKAGES: list[str] = ["ffmpeg", "git"]
PIP_PACKAGES: list[str] = [
    "pydantic>=2.0",
    "numpy",
    "opencv-python-headless",
    "pillow>=10.0",
    "scipy",
    "shapely>=2.0",
    "lark>=1.1",
    "ruamel.yaml>=0.18",
    "orjson>=3.9",
    "structlog>=24.0",
    "tenacity>=8.0",
    "requests>=2.31",
    "openai>=1.0",
    "typer>=0.12",
    "rich>=13.0",
    "fastapi>=0.110.0",
    "uvicorn>=0.30.0",
    "python-multipart",
    "gradio>=5.0.0",
]
UPLOADS_MOUNT = "/data/uploads"
UPLOADS_VOLUME = "gl-uploads"


def min_containers_from_env(environ: Mapping[str, str] | None = None) -> int:
    """``KODIAC_MIN_CONTAINERS`` clamped to ``[0, MAX_MIN_CONTAINERS]``; anything unparsable means 0."""
    env = os.environ if environ is None else environ
    raw = env.get("KODIAC_MIN_CONTAINERS", "0").strip()
    try:
        value = int(raw)
    except ValueError:
        return 0
    return max(0, min(value, MAX_MIN_CONTAINERS))


def build_function_kwargs(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Keyword arguments for the ASGI function. Never contains a GPU request."""
    kwargs: dict[str, Any] = {
        "cpu": 2.0,
        "memory": 2048,
        "timeout": 300,
        "min_containers": min_containers_from_env(environ),
        "scaledown_window": 300,
    }
    assert_cpu_only(kwargs)
    return kwargs


def assert_cpu_only(kwargs: Mapping[str, Any]) -> None:
    """Refuse any configuration that would reserve a GPU (cost rule: never a warm GPU)."""
    if kwargs.get("gpu"):
        raise ValueError("the hosted demo must be CPU-only; remove the 'gpu' argument")


def container_env(upload_dir: str = UPLOADS_MOUNT) -> dict[str, str]:
    """Environment baked into the image so ``AppSettings.from_env`` finds the packaged assets."""
    return {
        "KODIAC_APP_BACKEND": "fixture",
        "KODIAC_APP_MODE": "live",
        "KODIAC_APP_REPLAY_DIR": "/root/site/replays",
        "KODIAC_APP_CLIPS_DIR": "/root/fixtures/clips",
        "KODIAC_APP_TRACKS_DIR": "/root/fixtures/tracks",
        "KODIAC_APP_UPLOAD_DIR": f"{upload_dir}/in",
        "KODIAC_APP_RUN_DIR": "/tmp/kodiac/runs",
        "KODIAC_APP_TRUST_PROXY": "1",
    }


def reap_uploads(
    upload_dirs: list[Path | str],
    retention_hours: float = UPLOAD_RETENTION_HOURS,
    now: float | None = None,
) -> int:
    """Delete files older than ``retention_hours`` under each directory; returns the number removed."""
    from Kodiac_robotics.app.guards import reap_old_files

    return reap_old_files([Path(d) for d in upload_dirs], retention_hours * 3600.0, now=now)


def _load_modal() -> "types.ModuleType | None":
    """Return the real ``modal`` package, or None (also None for the local shim in ``modal/__init__.py``)."""
    try:
        import modal as candidate
    except ImportError:
        return None
    if not (hasattr(candidate, "concurrent") and hasattr(candidate, "asgi_app")):
        return None
    return candidate


def build_app(modal: "types.ModuleType | None" = None, environ: Mapping[str, str] | None = None) -> Any:
    """Declare the Modal app. Returns None when the real ``modal`` package is unavailable."""
    modal = modal or _load_modal()
    if modal is None:
        return None

    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install(*APT_PACKAGES)
        .pip_install(*PIP_PACKAGES)
        .env(container_env())
        .add_local_python_source("Kodiac_robotics")
        .add_local_dir(str(REPO_ROOT / "tests" / "fixtures" / "clips"), "/root/fixtures/clips")
        .add_local_dir(str(REPO_ROOT / "tests" / "fixtures" / "tracks"), "/root/fixtures/tracks")
        .add_local_dir(str(REPO_ROOT / "examples"), "/root/examples")
        .add_local_dir(str(REPO_ROOT / "site" / "replays"), "/root/site/replays")
    )
    uploads = modal.Volume.from_name(UPLOADS_VOLUME, create_if_missing=True)
    app = modal.App(APP_NAME)
    kwargs = build_function_kwargs(environ)

    @app.function(image=image, volumes={UPLOADS_MOUNT: uploads}, **kwargs)
    @modal.concurrent(max_inputs=MAX_INPUTS)
    @modal.asgi_app()
    def web() -> Any:
        from Kodiac_robotics.app.server import create_app
        from Kodiac_robotics.app.settings import AppSettings

        return create_app(AppSettings.from_env())

    @app.function(
        image=image,
        volumes={UPLOADS_MOUNT: uploads},
        schedule=modal.Period(hours=1),
    )
    def upload_reaper() -> int:
        uploads.reload()
        removed = reap_uploads([UPLOADS_MOUNT])
        uploads.commit()
        return removed

    return app


app = build_app()

__all__ = [
    "APP_NAME",
    "MAX_INPUTS",
    "UPLOAD_RETENTION_HOURS",
    "app",
    "assert_cpu_only",
    "build_app",
    "build_function_kwargs",
    "container_env",
    "min_containers_from_env",
    "reap_uploads",
]
