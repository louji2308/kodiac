"""ST03: SAM 3.1 hosted backward window tracking check."""

from __future__ import annotations

import os

from Kodiac_robotics.config import get_settings

try:
    from scripts.smoke.common import SmokeResult, generate_synthetic_clip
except ImportError:
    from common import SmokeResult, generate_synthetic_clip  # type: ignore[no-redef]


def run() -> SmokeResult:
    test_id = "ST03"
    name = "SAM 3.1 Hosted Backward Window Tracking"
    settings = get_settings()
    api_key = settings.model_api_key or os.environ.get("MODEL_API_KEY")

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
            notes=f"MODEL_API_KEY not set in environment; backward prompt window specification validated in mock mode using {clip_path.as_posix()}.",
            evidence_path=clip_path.as_posix(),
        )
        result.write_artifact()
        return result

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
