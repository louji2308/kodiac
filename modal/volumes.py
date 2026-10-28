"""Modal Volumes and Secrets configuration for Kodiac.

Defines persistent volumes and secrets references used across all Modal compute
jobs (perception, sim, and eval) with zero-warm-cost defaults.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List

try:
    from modal import Secret, Volume
except ImportError:
    # If run directly as a script where sys.path[0] is modal/
    try:
        from __init__ import Secret, Volume  # type: ignore
    except ImportError:
        class Volume:  # type: ignore
            def __init__(self, name: str, create_if_missing: bool = True):
                self.name = name
                self.create_if_missing = create_if_missing

            @classmethod
            def from_name(cls, name: str, create_if_missing: bool = True):
                return cls(name, create_if_missing)

        class Secret:  # type: ignore
            def __init__(self, name: str):
                self.name = name

            @classmethod
            def from_name(cls, name: str):
                return cls(name)


# Volume definitions
VOLUME_NAMES = [
    "hf-cache",      # HuggingFace model weights and transformers cache
    "gl-cache",      # Glimmer / LLM weights cache
    "gl-replays",    # Instant cached replay artifacts and videos
    "gl-pool",       # Sim pool and rollout dataset storage
    "gl-uploads",    # User-uploaded demo videos and audio clips
]

SECRET_NAMES = [
    "meta-model-api",  # Sponsor API credentials (MODEL_API_KEY)
    "huggingface",     # HF_TOKEN for gated model access (SAM 3.1)
]

# Standard container mount locations
VOLUME_MOUNTS: Dict[str, str] = {
    "/root/.cache/huggingface": "hf-cache",
    "/cache": "gl-cache",
    "/replays": "gl-replays",
    "/pool": "gl-pool",
    "/uploads": "gl-uploads",
}


def get_volume(name: str) -> Any:
    """Retrieve or construct a Modal Volume reference."""
    return Volume.from_name(name, create_if_missing=True)


def get_secret(name: str) -> Any:
    """Retrieve or construct a Modal Secret reference."""
    return Secret.from_name(name)


# Instantiated volume objects
hf_cache = get_volume("hf-cache")
gl_cache = get_volume("gl-cache")
gl_replays = get_volume("gl-replays")
gl_pool = get_volume("gl-pool")
gl_uploads = get_volume("gl-uploads")

VOLUMES: Dict[str, Any] = {
    "/root/.cache/huggingface": hf_cache,
    "/cache": gl_cache,
    "/replays": gl_replays,
    "/pool": gl_pool,
    "/uploads": gl_uploads,
}

# Instantiated secret objects
secret_meta = get_secret("meta-model-api")
secret_hf = get_secret("huggingface")

SECRETS: List[Any] = [secret_meta, secret_hf]


def check() -> bool:
    """Verify structural validity of volumes and secrets definitions."""
    assert len(VOLUME_NAMES) == 5, f"Expected 5 volumes, got {len(VOLUME_NAMES)}"
    for name in ["hf-cache", "gl-cache", "gl-replays", "gl-pool", "gl-uploads"]:
        assert name in VOLUME_NAMES, f"Missing volume: {name}"

    assert len(SECRET_NAMES) == 2, f"Expected 2 secrets, got {len(SECRET_NAMES)}"
    for name in ["meta-model-api", "huggingface"]:
        assert name in SECRET_NAMES, f"Missing secret: {name}"

    assert len(VOLUMES) == 5, "Volumes mapping count mismatch"
    assert len(SECRETS) == 2, "Secrets list count mismatch"
    return True


if __name__ == "__main__":
    if "--check" in sys.argv:
        if check():
            print("[CHECK PASS] modal/volumes.py: 5 volumes and 2 secrets verified.")
            sys.exit(0)
    print("modal/volumes.py: Run with --check to validate.")
