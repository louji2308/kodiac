"""Configuration settings for Kodiac.

Provides environment variable and file-based settings with secret masking.
Per ARCHITECTURE.md §2, §3.1, §4 and TOOLS_AND_REQUIREMENTS.md §8.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration settings for Kodiac robotics runtime."""

    model_config = SettingsConfigDict(
        env_prefix="KODIAC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        protected_namespaces=(),
        populate_by_name=True,
    )

    # API Keys & Secrets
    model_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("model_api_key", "MODEL_API_KEY", "KODIAC_MODEL_API_KEY"),
        description="Meta Model API key for SAM 3.1, Spark, Wonder, and Voice.",
    )
    hf_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("hf_token", "HF_TOKEN", "KODIAC_HF_TOKEN"),
        description="Hugging Face token for gated models and datasets.",
    )
    modal_token_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("modal_token_id", "MODAL_TOKEN_ID", "KODIAC_MODAL_TOKEN_ID"),
        description="Modal token ID for remote execution.",
    )
    modal_token_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("modal_token_secret", "MODAL_TOKEN_SECRET", "KODIAC_MODAL_TOKEN_SECRET"),
        description="Modal token secret.",
    )
    baseten_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("baseten_api_key", "BASETEN_API_KEY", "KODIAC_BASETEN_API_KEY"),
        description="Baseten API key for open-weights models.",
    )
    fireworks_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("fireworks_api_key", "FIREWORKS_API_KEY", "KODIAC_FIREWORKS_API_KEY"),
        description="Fireworks API key fallback.",
    )

    # Backends & Runtime Choices
    sam_backend: Literal["api", "modal", "fixture", "auto"] = Field(
        default="auto",
        validation_alias=AliasChoices("sam_backend", "SAM_BACKEND", "KODIAC_SAM_BACKEND"),
        description="Perception segmenter backend: api, modal, fixture, or auto.",
    )
    compiler_backend: Literal["api", "fixture", "template", "auto"] = Field(
        default="auto",
        validation_alias=AliasChoices("compiler_backend", "COMPILER_BACKEND", "KODIAC_COMPILER_BACKEND"),
        description="Compiler backend: api, fixture, template, or auto.",
    )
    judge_base_url: str = Field(
        default="https://api.meta.ai/v1",
        description="Base URL for OpenAI-compatible VLM judge client.",
    )
    judge_model: str = Field(
        default="muse-spark-1.3",
        description="Default judge model ID.",
    )
    judge_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("judge_key", "JUDGE_KEY", "KODIAC_JUDGE_KEY"),
        description="Specific judge API key if different from model_api_key.",
    )

    # Storage & Cache Directories
    cache_dir: Path = Field(
        default=Path(".cache/Kodiac"),
        description="Root directory for content-hashed caching.",
    )
    log_level: str = Field(default="INFO", description="Default logging level.")

    @classmethod
    def load(cls, env_path: Path | str | None = None) -> Settings:
        """Load settings from optional explicit env file, environment, or default .env."""
        if env_path is not None:
            return cls(_env_file=str(env_path))
        env_from_var = os.environ.get("KODIAC_ENV_FILE")
        if env_from_var:
            return cls(_env_file=env_from_var)
        return cls()

    def masked_dict(self) -> dict[str, Any]:
        """Return a copy of settings with all secret keys masked for safe logging/display."""
        data = self.model_dump()
        secret_fields = {
            "model_api_key",
            "hf_token",
            "modal_token_id",
            "modal_token_secret",
            "baseten_api_key",
            "fireworks_api_key",
            "judge_key",
        }
        for k, v in data.items():
            if k in secret_fields and v:
                val_str = str(v)
                if len(val_str) > 6:
                    data[k] = f"{val_str[:3]}...{val_str[-3:]}"
                else:
                    data[k] = "***"
        return data


_global_settings: Settings | None = None


def get_settings() -> Settings:
    """Get the active global Settings instance (cached)."""
    global _global_settings
    if _global_settings is None:
        _global_settings = Settings.load()
    return _global_settings


def resolve_sam_backend(
    requested: str | None = None, settings: Settings | None = None
) -> Literal["api", "fixture", "modal"]:
    """Resolve the effective SAM 3.1 perception backend.

    Priority:
    1. Explicit requested argument if in ('api', 'fixture', 'modal').
    2. Environment variable KODIAC_SAM_BACKEND or SAM_BACKEND.
    3. Settings configuration (if not 'auto').
    4. Auto-promotion: 'api' if MODEL_API_KEY is configured, else 'fixture'.
    """
    cfg = settings or get_settings()
    req = (requested or "").lower().strip()
    if req in ("api", "fixture", "modal"):
        return req  # type: ignore[return-value]

    env_choice = (
        os.environ.get("KODIAC_SAM_BACKEND")
        or os.environ.get("SAM_BACKEND")
        or (cfg.sam_backend if getattr(cfg, "sam_backend", "auto") not in (None, "", "auto") else None)
    )
    if env_choice:
        env_norm = env_choice.lower().strip()
        if env_norm in ("api", "fixture", "modal"):
            return env_norm  # type: ignore[return-value]

    has_key = bool(
        cfg.model_api_key
        or os.environ.get("MODEL_API_KEY")
        or os.environ.get("KODIAC_MODEL_API_KEY")
    )
    if has_key:
        return "api"
    return "fixture"


def resolve_compiler_backend(
    requested: str | None = None, settings: Settings | None = None
) -> Literal["api", "fixture", "template"]:
    """Resolve the effective .green compiler backend.

    Priority:
    1. Explicit requested argument if in ('api', 'fixture', 'template').
    2. Environment variable KODIAC_COMPILER_BACKEND or COMPILER_BACKEND.
    3. Settings configuration (if not 'auto').
    4. Auto-promotion: 'api' if MODEL_API_KEY is configured, else 'template'.
    """
    cfg = settings or get_settings()
    req = (requested or "").lower().strip()
    if req in ("api", "fixture", "template"):
        return req  # type: ignore[return-value]

    env_choice = (
        os.environ.get("KODIAC_COMPILER_BACKEND")
        or os.environ.get("COMPILER_BACKEND")
        or (cfg.compiler_backend if getattr(cfg, "compiler_backend", "auto") not in (None, "", "auto") else None)
    )
    if env_choice:
        env_norm = env_choice.lower().strip()
        if env_norm in ("api", "fixture", "template"):
            return env_norm  # type: ignore[return-value]

    has_key = bool(
        cfg.model_api_key
        or os.environ.get("MODEL_API_KEY")
        or os.environ.get("KODIAC_MODEL_API_KEY")
    )
    if has_key:
        return "api"
    return "template"

