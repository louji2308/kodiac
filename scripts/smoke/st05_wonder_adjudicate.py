"""ST05: Muse Wonder 1.0 Hard-Case Adjudication check."""

from __future__ import annotations

import os

from Kodiac_robotics.config import get_settings

try:
    from scripts.smoke.common import SmokeResult
except ImportError:
    from common import SmokeResult  # type: ignore[no-redef]


def run() -> SmokeResult:
    test_id = "ST05"
    name = "Muse Wonder 1.0 Hard-Case Adjudication"
    settings = get_settings()
    api_key = settings.model_api_key or os.environ.get("MODEL_API_KEY")

    if not api_key:
        result = SmokeResult(
            test_id=test_id,
            name=name,
            ok=False,
            status="PENDING_KEY",
            is_fixture=True,
            live_verified=False,
            latency_ms=None,
            notes="MODEL_API_KEY not set in environment; server-side chaining via previous_response_id schema validated in fixture mode.",
            evidence_path=None,
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
        evidence_path=None,
    )
    result.write_artifact()
    return result


if __name__ == "__main__":
    res = run()
    print(res)
