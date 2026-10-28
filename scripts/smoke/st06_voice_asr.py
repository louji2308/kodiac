"""ST06: Muse Voice Transcribe 1.0 Instruction ASR check."""

from __future__ import annotations

import os

from Kodiac_robotics.config import get_settings

try:
    from scripts.smoke.common import SmokeResult
except ImportError:
    from common import SmokeResult  # type: ignore[no-redef]


def run() -> SmokeResult:
    test_id = "ST06"
    name = "Muse Voice Transcribe 1.0 Instruction ASR"
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
            notes="MODEL_API_KEY not set in environment; validated ENDPOINTING mode multipart/form-data audio request format in fixture mode.",
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
        notes="Live call handler pending integration with Meta ASR endpoint.",
        evidence_path=None,
    )
    result.write_artifact()
    return result


if __name__ == "__main__":
    res = run()
    print(res)
