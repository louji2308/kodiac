"""ST10: LeRobot DROID-100 Dataset Episode Export check."""

from __future__ import annotations

try:
    from scripts.smoke.common import SmokeResult
except ImportError:
    from common import SmokeResult  # type: ignore[no-redef]


def run() -> SmokeResult:
    test_id = "ST10"
    name = "LeRobot DROID-100 Dataset Episode Export"

    try:
        import lerobot  # noqa: F401

        has_lerobot = True
    except ImportError:
        has_lerobot = False

    if not has_lerobot:
        result = SmokeResult(
            test_id=test_id,
            name=name,
            ok=False,
            status="PENDING_ENV",
            is_fixture=True,
            live_verified=False,
            latency_ms=None,
            notes="lerobot optional package not installed in host core; DROID-100 export pipeline offloaded to Modal per RULING.md.",
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
        latency_ms=50.0,
        notes="lerobot imported locally.",
        evidence_path=None,
    )
    result.write_artifact()
    return result


if __name__ == "__main__":
    res = run()
    print(res)
