"""ST02: SAM 3.1 hosted forward prompting check."""

from __future__ import annotations

import os

from Kodiac_robotics.config import get_settings

try:
    from scripts.smoke.common import SmokeResult, generate_synthetic_clip
except ImportError:
    from common import SmokeResult, generate_synthetic_clip  # type: ignore[no-redef]


def run() -> SmokeResult:
    test_id = "ST02"
    name = "SAM 3.1 Hosted Forward Prompting"
    settings = get_settings()
    api_key = settings.model_api_key or os.environ.get("MODEL_API_KEY")

    # Always ensure the synthetic clip exists
    clip_path = generate_synthetic_clip()

    if not api_key:
        result = SmokeResult(
            test_id=test_id,
            name=name,
            ok=False,
            status="PENDING_KEY",
            is_fixture=True,
            live_verified=False,
            latency_ms=None,
            notes=f"MODEL_API_KEY not set in environment; synthetic 50-frame H.264 clip generated at {clip_path.as_posix()}.",
            evidence_path=clip_path.as_posix(),
        )
        result.write_artifact()
        return result

    # When live key is present, execute SAM 3.1 forward prompt API call
    # (per TOOLS_AND_REQUIREMENTS.md §2.1)
    result = SmokeResult(
        test_id=test_id,
        name=name,
        ok=False,
        status="NOT_IMPLEMENTED_LIVE",
        is_fixture=True,
        live_verified=False,
        latency_ms=None,
        notes="Live call handler pending integration with OpenAI response endpoint.",
        evidence_path=clip_path.as_posix(),
    )
    result.write_artifact()
    return result


if __name__ == "__main__":
    res = run()
    print(res)
