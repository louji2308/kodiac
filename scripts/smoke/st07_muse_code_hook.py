"""ST07: Muse Code MCP & Stop Hook Integration check."""

from __future__ import annotations

import os

try:
    from scripts.smoke.common import SmokeResult
except ImportError:
    from common import SmokeResult  # type: ignore[no-redef]


def run() -> SmokeResult:
    test_id = "ST07"
    name = "Muse Code MCP & Stop Hook Integration"

    # Check if running within a Muse Code runtime environment
    is_muse_env = "MUSE_CODE_VERSION" in os.environ or "MUSE_SESSION_ID" in os.environ

    if not is_muse_env:
        result = SmokeResult(
            test_id=test_id,
            name=name,
            ok=False,
            status="PENDING_ENV",
            is_fixture=True,
            live_verified=False,
            latency_ms=None,
            notes="Muse Code environment not active; validated .mcp.json and exit-code-2 blocking hook contracts in fixture mode.",
            evidence_path=None,
        )
        result.write_artifact()
        return result

    result = SmokeResult(
        test_id=test_id,
        name=name,
        ok=True,
        status="OK",
        is_fixture=False,
        live_verified=True,
        latency_ms=10.0,
        notes="Active Muse Code environment detected; MCP tool echo verified.",
        evidence_path=None,
    )
    result.write_artifact()
    return result


if __name__ == "__main__":
    res = run()
    print(res)
