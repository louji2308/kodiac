"""Configuration settings for Kodiac.

Provides environment variable and file-based settings with secret masking.
Per ARCHITECTURE.md §2, §3.1, §4 and TOOLS_AND_REQUIREMENTS.md §8.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import Field
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
        validation_alias="MODEL_API_KEY",
        description="Meta Model API key for SAM 3.1, Spark, Wonder, and Voice.",
    )
    hf_token: str | None = Field(
        default=None,
        validation_alias="HF_TOKEN",
        description="Hugging Face token for gated models and datasets.",
    )
    modal_token_id: str | None = Field(
        default=None,
        validation_alias="MODAL_TOKEN_ID",
        description="Modal token ID for remote execution.",
    )
    modal_token_secret: str | None = Field(
        default=None,
        validation_alias="MODAL_TOKEN_SECRET",
        description="Modal token secret.",
    )
    baseten_api_key: str | None = Field(
        default=None,
        validation_alias="BASETEN_API_KEY",
        description="Baseten API key for open-weights models.",
    )
    fireworks_api_key: str | None = Field(
        default=None,
        validation_alias="FIREWORKS_API_KEY",
        description="Fireworks API key fallback.",
    )

    # Backends & Runtime Choices
    sam_backend: Literal["api", "modal", "fixture"] = Field(
        default="api",
        description="Perception segmenter backend: api, modal, or fixture.",
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
