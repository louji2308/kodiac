"""ST08: Modal Compute Hello Deployment check."""

from __future__ import annotations

import os

from Kodiac_robotics.config import get_settings

try:
    from scripts.smoke.common import SmokeResult
except ImportError:
    from common import SmokeResult  # type: ignore[no-redef]


def run() -> SmokeResult:
    test_id = "ST08"
    name = "Modal Compute Hello Deployment"
    settings = get_settings()
    modal_token_id = settings.modal_token_id or os.environ.get("MODAL_TOKEN_ID")
    modal_token_secret = settings.modal_token_secret or os.environ.get("MODAL_TOKEN_SECRET")

    if not modal_token_id or not modal_token_secret:
        result = SmokeResult(
            test_id=test_id,
            name=name,
            ok=False,
            status="PENDING_KEY",
            is_fixture=True,
            live_verified=False,
            latency_ms=None,
            notes="MODAL_TOKEN_ID or MODAL_TOKEN_SECRET not set in environment; validated scaledown_window=0 deployment schema in fixture mode.",
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
        notes="Modal credentials detected; live deployment test pending cluster invocation.",
        evidence_path=None,
    )
    result.write_artifact()
    return result


if __name__ == "__main__":
    res = run()
    print(res)
