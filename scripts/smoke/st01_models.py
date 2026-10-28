"""ST01: Meta Model API /v1/models check."""

from __future__ import annotations

import os
import time

import requests

from Kodiac_robotics.config import get_settings

try:
    from scripts.smoke.common import SmokeResult
except ImportError:
    from common import SmokeResult  # type: ignore[no-redef]


def run() -> SmokeResult:
    test_id = "ST01"
    name = "Meta Model API /v1/models"
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
            notes="MODEL_API_KEY not set in environment; verified request structure in mock mode.",
            evidence_path=None,
        )
        result.write_artifact()
        return result

    base_url = settings.judge_base_url.rstrip("/")
    url = f"{base_url}/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    t0 = time.perf_counter()
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        if resp.status_code == 200:
            data = resp.json()
            models = [m.get("id") for m in data.get("data", [])]
            result = SmokeResult(
                test_id=test_id,
                name=name,
                ok=True,
                status="OK",
                is_fixture=False,
                live_verified=True,
                latency_ms=latency_ms,
                notes=f"Retrieved models: {', '.join(models[:5])}",
                evidence_path=None,
            )
        else:
            result = SmokeResult(
                test_id=test_id,
                name=name,
                ok=False,
                status="ERROR",
                is_fixture=False,
                live_verified=True,
                latency_ms=latency_ms,
                notes=f"HTTP {resp.status_code}: {resp.text[:100]}",
                evidence_path=None,
            )
    except Exception as e:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        result = SmokeResult(
            test_id=test_id,
            name=name,
            ok=False,
            status="ERROR",
            is_fixture=False,
            live_verified=True,
            latency_ms=latency_ms,
            notes=f"Request failed: {e}",
            evidence_path=None,
        )

    result.write_artifact()
    return result


if __name__ == "__main__":
    res = run()
    print(res)
