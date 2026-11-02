"""Batch dataset-audit runner (F49): per-episode ``run`` -> VerdictRow-conformant DataFrame.

Offline by construction: perception backend is the recorded-track fixture backend for fixture
episodes; no network client is imported here. Everything derived from fixture clips is labelled
``is_demonstration_data=True``. Resumable (one JSON per episode) and failure-isolated.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel

from Kodiac_robotics import __version__
from Kodiac_robotics.audit.rows import (
    DEMO_BANNER,
    TEMPLATE_FALLBACK_BADGE,
    normalize_frame,
    write_verdicts,
)
from Kodiac_robotics.contracts.core import Component, RunResult, StepResult, Tri, Verdict

RunFn = Callable[[Path, Path, Path, bool], RunResult]


class AuditEpisode(BaseModel):
    dataset: str
    episode_index: int
    camera: str
    task: str
    clip_path: str
    is_fixture: bool


def default_run_fn(test_path: Path, clip_path: Path, out_dir: Path, is_fixture: bool) -> RunResult:
    """Full-path run. Fixture episodes use recorded tracks; others require the Modal backend."""
    from Kodiac_robotics.pipeline.run import run

    return run(
        test_path,
        clip_path,
        backend="fixture" if is_fixture else "modal",
        render_card=True,
        output_dir=out_dir,
    )


def text_compile_resolver(cache_dir: Path) -> Callable[[str], Path]:
    """Return ``test_for_task`` that text-compiles a task string once and caches the .green file."""

    def resolve(task: str) -> Path:
        from Kodiac_robotics.compiler.printer import print_green
        from Kodiac_robotics.compiler.text_compile import text_compile

        digest = hashlib.sha256(task.strip().encode("utf-8")).hexdigest()[:16]
        target = Path(cache_dir) / f"{digest}.green"
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(print_green(text_compile(task)), encoding="utf-8")
        return target

    return resolve


def _safe(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_") or "x"


def _episode_key(ep: AuditEpisode) -> str:
    return f"{_safe(ep.dataset)}__{_safe(ep.camera)}__{ep.episode_index:06d}"


def _sha256_files(*chunks: bytes | Path) -> str:
    h = hashlib.sha256()
    for chunk in chunks:
        if isinstance(chunk, Path):
            with chunk.open("rb") as fh:
                for block in iter(lambda: fh.read(1 << 20), b""):
                    h.update(block)
        else:
            h.update(chunk)
    return h.hexdigest()


def _is_demo(ep: AuditEpisode, result_is_fixture: bool) -> bool:
    path = ep.clip_path.replace("\\", "/")
    return bool(ep.is_fixture or result_is_fixture or "tests/fixtures/" in path)


def _decisive(step: StepResult) -> Component | None:
    if not step.decisive:
        return None
    failing = [c for c in step.decisive if c.tri == Tri.F]
    pool = failing or list(step.decisive)
    return min(pool, key=lambda c: (c.margin, c.name))


def _model_ids(result: RunResult) -> str:
    return ";".join(f"{k}={v}" for k, v in sorted(result.backends.items())) or "unknown"


def _base_row(ep: AuditEpisode) -> dict[str, Any]:
    return {
        "dataset": ep.dataset,
        "episode_index": ep.episode_index,
        "camera": ep.camera,
        "task": ep.task,
        "clip_path": ep.clip_path,
        "Kodiac_version": __version__,
        "human_verified": None,
        "review_decision": None,
        "reviewer": None,
        "error": None,
        "evidence_uri": None,
    }


def _row_from_result(
    ep: AuditEpisode, result: RunResult, green_text: str, evidence_dir: Path, out_dir: Path
) -> dict[str, Any]:
    row = _base_row(ep)
    demo = _is_demo(ep, result.is_fixture)
    notes = list(result.badges)
    if "DETERMINISTIC TEMPLATE FALLBACK" in green_text:
        notes.append(TEMPLATE_FALLBACK_BADGE)
    if demo:
        notes.append(DEMO_BANNER)
    row.update(
        verdict=result.verdict.value,
        reasons=[r.value for r in result.reasons],
        model_ids=_model_ids(result),
        is_fixture=bool(ep.is_fixture or result.is_fixture),
        is_demonstration_data=demo,
        t_star_s=None,
        frame=None,
        step=None,
        predicate=None,
        margin=None,
        sigma=None,
    )
    target = Verdict.FAIL if result.verdict == Verdict.FAIL else Verdict.CANT_TELL
    if result.verdict != Verdict.PASS:
        step = next((s for s in result.steps if s.verdict == target), None)
        if step is not None:
            comp = _decisive(step)
            row.update(
                step=step.name,
                frame=step.frame,
                t_star_s=step.t_s,
                predicate=comp.name if comp else None,
                margin=float(comp.margin) if comp else None,
                sigma=float(comp.sigma) if comp else None,
            )
            notes.append("t_star_s is the decisive-step decision time from `run`, not a blame onset")
    card = Path(result.card_path) if result.card_path else evidence_dir / "card.png"
    if card.is_file():
        try:
            row["evidence_uri"] = card.resolve().relative_to(out_dir.resolve()).as_posix()
        except ValueError:
            row["evidence_uri"] = card.as_posix()
    row["notes"] = "; ".join(notes)
    return row


def _error_row(ep: AuditEpisode, exc: BaseException) -> dict[str, Any]:
    row = _base_row(ep)
    demo = _is_demo(ep, False)
    msg = re.sub(r"\s+", " ", f"{type(exc).__name__}: {exc}").strip()[:300]
    row.update(
        verdict=Verdict.CANT_TELL.value,
        reasons=["run_error"],
        model_ids="none",
        is_fixture=ep.is_fixture,
        is_demonstration_data=demo,
        t_star_s=None,
        frame=None,
        step=None,
        predicate=None,
        margin=None,
        sigma=None,
        error=msg,
        notes="episode not evaluated (run error)" + (f"; {DEMO_BANNER}" if demo else ""),
    )
    return row


def audit_run(
    dataset: str,
    task_filter: str,
    camera: str,
    limit: int,
    *,
    episodes: Iterable[AuditEpisode],
    out_dir: Path,
    test_for_task: Callable[[str], Path],
    run_fn: RunFn | None = None,
) -> pd.DataFrame:
    """Run the audit over matching episodes and write ``out_dir/verdicts.parquet``.

    Episodes are filtered by dataset, exact camera key and a case-insensitive regex on the task
    string, ordered by episode index, truncated to ``limit``. Each episode is isolated: an
    exception yields a CANT_TELL row with reason ``run_error`` (never cached, so a rerun retries).
    Completed episodes are cached under ``out_dir/episodes`` and reused when the clip bytes and
    compiled test are unchanged.
    """
    if limit < 1:
        raise ValueError("limit must be >= 1")
    out_dir = Path(out_dir)
    pattern = re.compile(task_filter, re.IGNORECASE)
    runner = run_fn or default_run_fn
    selected = sorted(
        (
            e
            for e in episodes
            if e.dataset == dataset and e.camera == camera and pattern.search(e.task)
        ),
        key=lambda e: e.episode_index,
    )[:limit]

    cache_dir = out_dir / "episodes"
    cache_dir.mkdir(parents=True, exist_ok=True)
    compiled: dict[tuple[str, str], Path | BaseException] = {}
    rows: list[dict[str, Any]] = []

    for ep in selected:
        key = _episode_key(ep)
        cache_file = cache_dir / f"{key}.json"
        try:
            memo_key = (ep.dataset, ep.task)
            if memo_key not in compiled:
                try:
                    compiled[memo_key] = Path(test_for_task(ep.task))
                except Exception as exc:  # noqa: BLE001 - isolated per (dataset, task)
                    compiled[memo_key] = exc
            test_path = compiled[memo_key]
            if isinstance(test_path, BaseException):
                raise test_path
            green_text = test_path.read_text(encoding="utf-8")
            clip = Path(ep.clip_path)
            fingerprint = _sha256_files(green_text.encode("utf-8"), clip)

            if cache_file.is_file():
                try:
                    cached = json.loads(cache_file.read_text(encoding="utf-8"))
                    if cached.get("fingerprint") == fingerprint:
                        rows.append(cached["row"])
                        continue
                except (json.JSONDecodeError, KeyError):
                    pass

            evidence_dir = out_dir / "evidence" / key
            evidence_dir.mkdir(parents=True, exist_ok=True)
            result = runner(test_path, clip, evidence_dir, ep.is_fixture)
            row = _row_from_result(ep, result, green_text, evidence_dir, out_dir)
            cache_file.write_text(
                json.dumps({"fingerprint": fingerprint, "row": row}, sort_keys=True),
                encoding="utf-8",
            )
            rows.append(row)
        except Exception as exc:  # noqa: BLE001 - per-episode failure isolation
            rows.append(_error_row(ep, exc))

    base = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["dataset", "episode_index", "camera"])
    df = normalize_frame(base)
    write_verdicts(df, out_dir / "verdicts.parquet")
    return df


__all__ = [
    "AuditEpisode",
    "RunFn",
    "audit_run",
    "default_run_fn",
    "text_compile_resolver",
]
