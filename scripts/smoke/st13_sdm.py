"""ST13: SDM Channel Readiness (OpenCode CLI check).

Verifies the OpenCode CLI runtime for Senior Decision Maker (SDM) DeepSeek V4.1 Flash routing.
"""

from __future__ import annotations

import shutil
import subprocess
import time

try:
    from scripts.smoke.common import SmokeResult
except ImportError:
    from common import SmokeResult  # type: ignore[no-redef]


def run() -> SmokeResult:
    test_id = "ST13"
    name = "SDM Channel Readiness (OpenCode CLI)"

    opencode_bin = shutil.which("opencode")
    if not opencode_bin:
        result = SmokeResult(
            test_id=test_id,
            name=name,
            ok=False,
            status="PENDING_ENV",
            is_fixture=True,
            live_verified=False,
            latency_ms=None,
            notes="opencode CLI not found on system PATH; SDM routing requires OpenCode or Antigravity/Gemini route per ADR-0002.",
            evidence_path=None,
        )
        result.write_artifact()
        return result

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [opencode_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        if proc.returncode == 0:
            version_str = proc.stdout.strip() or "unknown"
            result = SmokeResult(
                test_id=test_id,
                name=name,
                ok=True,
                status="OK",
                is_fixture=False,
                live_verified=True,
                latency_ms=latency_ms,
                notes=f"OpenCode CLI v{version_str} verified live on local system; ready for SDM DeepSeek V4.1 Flash routing.",
                evidence_path="artifacts/p01/smoke/st13.json",
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
                notes=f"opencode CLI returned error code {proc.returncode}: {proc.stderr[:100]}",
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
            notes=f"Failed to execute opencode: {e}",
            evidence_path=None,
        )

    result.write_artifact()
    return result


if __name__ == "__main__":
    res = run()
    print(res)
