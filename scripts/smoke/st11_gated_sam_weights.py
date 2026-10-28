"""ST11: Facebook SAM 3.1 Gated HuggingFace Access check."""

from __future__ import annotations

import os

from Kodiac_robotics.config import get_settings

try:
    from scripts.smoke.common import SmokeResult
except ImportError:
    from common import SmokeResult  # type: ignore[no-redef]


def run() -> SmokeResult:
    test_id = "ST11"
    name = "Facebook SAM 3.1 Gated HuggingFace Access"
    settings = get_settings()
    hf_token = settings.hf_token or os.environ.get("HF_TOKEN")

    if not hf_token:
        result = SmokeResult(
            test_id=test_id,
            name=name,
            ok=False,
            status="PENDING_KEY",
            is_fixture=True,
            live_verified=False,
            latency_ms=None,
            notes="HF_TOKEN not set in environment; cannot query facebook/sam3.1 gated model access status.",
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
        notes="HF_TOKEN detected; gated repository access query pending.",
        evidence_path=None,
    )
    result.write_artifact()
    return result


if __name__ == "__main__":
    res = run()
    print(res)
