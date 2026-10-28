"""ST12: Partner Sponsor Credits Verification (Baseten/Fireworks)."""

from __future__ import annotations

import os

from Kodiac_robotics.config import get_settings

try:
    from scripts.smoke.common import SmokeResult
except ImportError:
    from common import SmokeResult  # type: ignore[no-redef]


def run() -> SmokeResult:
    test_id = "ST12"
    name = "Partner Sponsor Credits Verification (Baseten/Fireworks)"
    settings = get_settings()
    baseten_key = settings.baseten_api_key or os.environ.get("BASETEN_API_KEY")
    fireworks_key = settings.fireworks_api_key or os.environ.get("FIREWORKS_API_KEY")

    if not baseten_key and not fireworks_key:
        result = SmokeResult(
            test_id=test_id,
            name=name,
            ok=False,
            status="PENDING_KEY",
            is_fixture=True,
            live_verified=False,
            latency_ms=None,
            notes="Neither BASETEN_API_KEY nor FIREWORKS_API_KEY set in environment; partner open-weights judge rows in fixture mode.",
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
        notes="Partner API key(s) detected; live balance validation query pending.",
        evidence_path=None,
    )
    result.write_artifact()
    return result


if __name__ == "__main__":
    res = run()
    print(res)
