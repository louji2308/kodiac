"""Shared helpers for audit tests (stub run function, episode loading)."""

from __future__ import annotations

import json
from pathlib import Path

from Kodiac_robotics.audit.run import AuditEpisode
from Kodiac_robotics.contracts.core import (
    ClipRef,
    Component,
    ReasonCode,
    RunResult,
    StepResult,
    Tri,
    Verdict,
)

FIXTURE_EPISODES = Path("tests/fixtures/audit/episodes.json")
STACK_GREEN = Path("examples/stackcube.green")


def load_episodes() -> list[AuditEpisode]:
    raw = json.loads(FIXTURE_EPISODES.read_text(encoding="utf-8"))
    return [AuditEpisode(**r) for r in raw]


def make_result(
    verdict: Verdict,
    *,
    step: str = "release",
    predicate: str = "moves_with.slip",
    margin: float = -2.5,
    sigma: float = 1.0,
    card: Path | None = None,
) -> RunResult:
    steps = []
    if verdict != Verdict.PASS:
        steps.append(
            StepResult(
                index=1,
                name=step,
                verdict=verdict,
                t_s=1.5,
                frame=45,
                decisive=[
                    Component(
                        name=predicate,
                        value=0.0,
                        threshold=1.0,
                        margin=margin,
                        sigma=sigma,
                        unit="cm",
                        tri=Tri.F if verdict == Verdict.FAIL else Tri.U,
                    )
                ],
            )
        )
    return RunResult(
        run_id="0" * 16,
        test_name="stub",
        test_sha256="0" * 64,
        config_sha256="0" * 64,
        clip=ClipRef(uri="stub.mp4", source_kind="demo"),
        verdict=verdict,
        exit_code=0 if verdict == Verdict.PASS else (1 if verdict == Verdict.FAIL else 2),
        steps=steps,
        reasons=[ReasonCode.OCCLUDED] if verdict == Verdict.CANT_TELL else [],
        badges=["[FIXTURE REPLAY]"],
        backends={"perception": "fixture"},
        nonce="0" * 16,
        is_fixture=True,
        card_path=str(card) if card else None,
        trace_path="trace.jsonl",
        created_at="2026-11-02T00:00:00+00:00",
    )


def stub_run_fn(verdicts_by_index: dict[int, Verdict], calls: list[int] | None = None):
    """run_fn whose verdict is keyed by the episode index parsed from the evidence dir name."""

    def run_fn(test_path: Path, clip_path: Path, out_dir: Path, is_fixture: bool) -> RunResult:
        idx = int(out_dir.name.rsplit("__", 1)[1])
        if calls is not None:
            calls.append(idx)
        verdict = verdicts_by_index[idx]
        card = None
        if verdict == Verdict.FAIL:
            card = out_dir / "card.png"
            card.write_bytes(b"\x89PNG stub")
        return make_result(verdict, card=card)

    return run_fn
