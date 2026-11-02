"""Grading core for the hosted app: clip/test resolution, occlusion, `pipeline.run.run`, sanitising.

HTTP concerns (rate limits, upload caps, status codes) live in ``server.py``.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from Kodiac_robotics.app.errors import AppError, object_not_found
from Kodiac_robotics.app.guards import log_event, reap_old_files
from Kodiac_robotics.app.occlusion import (
    OCCLUSION_APPLIED_BADGE,
    OCCLUSION_EMULATION_BADGE,
    Rect,
    normalize_rects,
    occlude_tracks,
    occlude_video,
)
from Kodiac_robotics.app.replay import ReplayStore
from Kodiac_robotics.app.settings import AppSettings
from Kodiac_robotics.compiler.printer import print_green
from Kodiac_robotics.compiler.text_compile import text_compile
from Kodiac_robotics.contracts.core import Clip, GreenTest, RunResult, Track, Verdict
from Kodiac_robotics.io.clip import open_clip
from Kodiac_robotics.pipeline.loader import load_green_test
from Kodiac_robotics.pipeline.run import _harmonize_track_keys, run
from Kodiac_robotics.render.card import render_verdict_card_v1
from Kodiac_robotics.segment.fixture import FixtureBackend

FIXTURE_BADGE = "[FIXTURE REPLAY]"
TEMPLATE_COMPILER_BADGE = "[COMPILER: DETERMINISTIC TEMPLATE FALLBACK · LLM OFFLINE]"
MAX_INSTRUCTION_CHARS = 280


@dataclass
class CuratedClip:
    id: str
    path: Path
    description: str
    sha256: str
    width: int
    height: int
    n_frames: int
    fps: float


@dataclass
class GradeContext:
    """Everything a blame/fast-path hook needs; passed to ``GradeService.blame_hook``."""

    test: GreenTest
    clip: Clip
    tracks: dict[str, Track] | None
    run_dir: Path
    clip_id: str | None
    occlusion_rects: list[Rect] = field(default_factory=list)


BlameHook = Callable[[RunResult, GradeContext], RunResult]


@dataclass
class GradeOutcome:
    run: RunResult
    card_path: Path | None
    test_id: str | None
    clip_id: str | None
    compiled_green: str | None = None
    occlusion: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)


class GradeService:
    """Resolves inputs and runs the real pipeline. ``blame_hook`` is where ORCH wires blame/fast path."""

    def __init__(
        self,
        settings: AppSettings,
        store: ReplayStore | None = None,
        blame_hook: BlameHook | None = None,
    ) -> None:
        self.settings = settings
        self.store = store or ReplayStore(settings.replay_dir)
        self.blame_hook = blame_hook
        self._last_reap = 0.0
        self._reap_lock = threading.Lock()

    # ---- catalogue -------------------------------------------------------------------------
    def curated_clips(self) -> dict[str, CuratedClip]:
        manifest = self.settings.clips_dir / "manifest.json"
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        out: dict[str, CuratedClip] = {}
        for filename, meta in data.get("clips", {}).items():
            path = self.settings.clips_dir / filename
            if not path.is_file():
                continue
            cid = Path(filename).stem
            out[cid] = CuratedClip(
                id=cid,
                path=path,
                description=str(meta.get("description", "")),
                sha256=str(meta.get("sha256", "")),
                width=int(meta.get("width", 0)),
                height=int(meta.get("height", 0)),
                n_frames=int(meta.get("n_frames", 0)),
                fps=float(meta.get("fps", 30.0)),
            )
        return out

    def curated_tests(self) -> dict[str, Path]:
        from Kodiac_robotics.app.content import EXAMPLE_TESTS

        found: dict[str, Path] = {}
        for tid, meta in EXAMPLE_TESTS.items():
            p = self.settings.examples_dir / meta["file"]
            if p.is_file():
                found[tid] = p
        return found

    # ---- compile ---------------------------------------------------------------------------
    def compile_instruction(self, text: str) -> tuple[GreenTest, list[str]]:
        """Typed-instruction fallback (template compiler). Typed errors on failure, never a guess."""
        text = (text or "").strip()
        if not text:
            raise AppError("E_EMPTY_INSTRUCTION", "Type an instruction first, e.g. 'stack cubeA on cubeB'.")
        if len(text) > MAX_INSTRUCTION_CHARS:
            raise AppError(
                "E_INSTRUCTION_TOO_LONG",
                f"Keep the instruction under {MAX_INSTRUCTION_CHARS} characters.",
            )
        try:
            test = text_compile(text, backend="template")
        except ValueError as err:
            msg = str(err)
            if msg.startswith("E001"):
                raise AppError(
                    "E001",
                    f"We couldn't find any object in '{text}'. Try Teach it or an example test.",
                    hint="Name the objects, e.g. 'stack cubeA on cubeB'.",
                ) from err
            raise AppError(
                "E003",
                "That instruction uses an action we don't support yet. "
                "Try pick up / place / stack / insert, or use an example test.",
            ) from err
        except Exception as err:  # compile failures must fall back to the typed-instruction message
            raise AppError(
                "E_COMPILE",
                "We couldn't compile that instruction. Rephrase it or use an example test.",
            ) from err
        return test, [TEMPLATE_COMPILER_BADGE]

    def resolve_test(
        self, test_id: str | None, typed_instruction: str | None
    ) -> tuple[GreenTest, str | None, list[str], str | None]:
        """Return (test, test_id, extra_badges, compiled_green_text)."""
        if typed_instruction and typed_instruction.strip():
            test, badges = self.compile_instruction(typed_instruction)
            return test, None, badges, print_green(test)
        tid = test_id or "stackcube"
        tests = self.curated_tests()
        if tid not in tests:
            raise AppError(
                "E_UNKNOWN_TEST",
                f"Unknown example test '{tid}'. Choose one of: {', '.join(sorted(tests)) or 'none available'}.",
            )
        test, _ = load_green_test(tests[tid])
        return test, tid, [], None

    # ---- grading ---------------------------------------------------------------------------
    def grade(
        self,
        *,
        clip_id: str | None = None,
        upload_path: Path | None = None,
        test_id: str | None = None,
        typed_instruction: str | None = None,
        occlusion_rects: list[Rect] | None = None,
    ) -> GradeOutcome:
        test, resolved_test_id, extra_badges, compiled = self.resolve_test(test_id, typed_instruction)

        clips = self.curated_clips()
        if upload_path is None:
            if not clip_id or clip_id not in clips:
                raise AppError(
                    "E_UNKNOWN_CLIP",
                    f"Unknown example clip. Choose one of: {', '.join(sorted(clips)) or 'none available'}.",
                )
            clip_path = clips[clip_id].path
        else:
            clip_path = upload_path
        try:
            clip = open_clip(clip_path)
        except Exception as err:
            raise AppError(
                "E_BAD_VIDEO",
                "We couldn't read that video. Try an H.264 .mp4 up to 20 s.",
            ) from err

        tracks: dict[str, Track] | None = None
        if self.settings.backend == "fixture":
            tracks = self._fixture_tracks(clip, uploaded=upload_path is not None)
            harmonized = _harmonize_track_keys(tracks, test)
            for decl in test.objects:
                if decl.role != "effector" and decl.name not in harmonized:
                    raise object_not_found(decl.name.replace("_", " "))

        rects = normalize_rects(occlusion_rects, clip.width, clip.height)
        work = self.settings.run_dir / f"pending-{uuid.uuid4().hex}"
        work.mkdir(parents=True, exist_ok=True)
        occlusion_info: dict[str, Any] | None = None
        run_clip: Clip = clip
        extra_badges = list(extra_badges)
        try:
            if rects:
                stem = Path(clip.path_h264).stem
                occluded = occlude_video(clip.path_h264, work / f"{stem}_occluded.mp4", rects, clip.fps)
                run_clip = open_clip(occluded).model_copy(update={"ref": clip.ref})
                extra_badges.append(OCCLUSION_APPLIED_BADGE)
                occlusion_info = {
                    "rects": [list(r) for r in rects],
                    "emulated_on_cached_masks": tracks is not None,
                    "max_covered_fraction": {},
                }
                if tracks is not None:
                    tracks, worst = occlude_tracks(tracks, rects, (clip.height, clip.width))
                    occlusion_info["max_covered_fraction"] = worst
                    extra_badges.append(OCCLUSION_EMULATION_BADGE)

            try:
                result = run(
                    test,
                    run_clip,
                    tracks=tracks,
                    backend="fixture" if tracks is not None else self.settings.backend,
                    render_card=True,
                    output_dir=work,
                )
            except AppError:
                raise
            except Exception as err:
                log_event("grade_failed", error_type=type(err).__name__)
                if self.settings.backend == "fixture":
                    raise AppError(
                        "E_GRADE_FAILED",
                        "The engine could not grade this clip. Try a curated example or open a cached replay.",
                        status=500,
                    ) from err
                raise AppError(
                    "E_BACKEND_UNAVAILABLE",
                    "The perception backend is unavailable right now. Open a cached replay instead.",
                    status=503,
                ) from err

            result = self._finalize(result, test, clip_id, upload_path is not None, extra_badges)
            notes: list[str] = []
            if self.blame_hook is not None:
                ctx = GradeContext(
                    test=test,
                    clip=run_clip,
                    tracks=tracks,
                    run_dir=work,
                    clip_id=clip_id,
                    occlusion_rects=rects,
                )
                try:
                    result = self.blame_hook(result, ctx)
                except Exception as err:
                    log_event("blame_hook_failed", error_type=type(err).__name__)
                    notes.append("blame/diff unavailable for this run")

            self._rewrite_artifacts(result, run_clip, work)
            final_dir = self.settings.run_dir / result.run_id
            if final_dir.exists():
                shutil.rmtree(final_dir, ignore_errors=True)
            os.replace(work, final_dir)
            card = final_dir / "card.png"
            return GradeOutcome(
                run=result,
                card_path=card if card.is_file() else None,
                test_id=resolved_test_id,
                clip_id=clip_id,
                compiled_green=compiled,
                occlusion=occlusion_info,
                notes=notes,
            )
        finally:
            if work.exists():
                shutil.rmtree(work, ignore_errors=True)

    def _fixture_tracks(self, clip: Clip, uploaded: bool) -> dict[str, Track]:
        try:
            return FixtureBackend(self.settings.tracks_dir)._load_tracks(clip)
        except FileNotFoundError as err:
            raise AppError(
                "E_NO_LIVE_BACKEND",
                "This deployment has no perception API key, so it can only grade the curated example clips "
                "(it replays recorded SAM 3.1 tracks). Your clip was not segmented and no verdict was invented."
                if uploaded
                else "No recorded tracks exist for that clip on this deployment.",
                status=503,
                hint="Pick a curated clip, or open a cached replay.",
            ) from err

    def _finalize(
        self,
        result: RunResult,
        test: GreenTest,
        clip_id: str | None,
        uploaded: bool,
        extra_badges: list[str],
    ) -> RunResult:
        badges = list(result.badges)
        if result.is_fixture and FIXTURE_BADGE not in badges:
            badges.insert(0, FIXTURE_BADGE)
        for b in extra_badges:
            if b not in badges:
                badges.append(b)
        label = f"curated:{clip_id}" if clip_id and not uploaded else f"upload:{result.nonce[:8]}"
        return result.model_copy(
            update={
                "badges": badges,
                "clip": result.clip.model_copy(update={"uri": label}),
                "card_path": "card.png",
                "trace_path": "trace.jsonl",
            }
        )

    def _rewrite_artifacts(self, result: RunResult, clip: Clip, work: Path) -> None:
        """Re-render the card and result.json from the final (sanitised, fully badged) result."""
        (work / "result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        decisive = 0
        for s in result.steps:
            if s.frame is not None:
                decisive = s.frame
                if s.verdict in (Verdict.FAIL, Verdict.CANT_TELL):
                    break
        frame = None
        cap = cv2.VideoCapture(clip.path_h264)
        try:
            cap.set(cv2.CAP_PROP_POS_FRAMES, decisive)
            ok, img = cap.read()
            if ok:
                frame = img
        finally:
            cap.release()
        if frame is None:
            frame = np.full((clip.height, clip.width, 3), 40, dtype=np.uint8)
        render_verdict_card_v1(result, clip, frame, work / "card.png")

    # ---- retention -------------------------------------------------------------------------
    def reap(self, now: float | None = None) -> int:
        """Delete uploads and run artefacts older than the retention window."""
        return reap_old_files(
            [self.settings.upload_dir, self.settings.run_dir],
            self.settings.retention_hours * 3600.0,
            now=now,
        )

    def maybe_reap(self, every_s: float = 600.0) -> None:
        now = time.monotonic()
        with self._reap_lock:
            if now - self._last_reap < every_s:
                return
            self._last_reap = now
        try:
            self.reap()
        except OSError:
            pass


__all__ = [
    "FIXTURE_BADGE",
    "TEMPLATE_COMPILER_BADGE",
    "BlameHook",
    "CuratedClip",
    "GradeContext",
    "GradeOutcome",
    "GradeService",
]
