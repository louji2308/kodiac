"""Transport-independent request handling shared by the HTTP server and the in-process UI client.

Honesty contract (Law 1):
* ``grade`` always runs the engine now and reports the measured wall-clock in ``timer_ms``; ``cached`` is false.
* ``replay`` never computes: ``cached`` is true with the ``⚡ CACHED`` badge and ``timer_ms`` is the lookup time only.
* ``badges`` are the run's own badges (e.g. ``[FIXTURE REPLAY]``) plus exactly one serving badge.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, BinaryIO

from Kodiac_robotics import __version__
from Kodiac_robotics.app.errors import AppError
from Kodiac_robotics.app.guards import TokenBucket, hash_token, log_event
from Kodiac_robotics.app.occlusion import Rect
from Kodiac_robotics.app.replay import CACHED_BADGE, ReplayStore, valid_replay_id
from Kodiac_robotics.app.service import BlameHook, GradeOutcome, GradeService
from Kodiac_robotics.app.settings import AppSettings
from Kodiac_robotics.compiler.printer import print_green
from Kodiac_robotics.io.transcode import probe_video

LIVE_BADGE = "▶ ENGINE RUN (not cached)"
_CHUNK = 1024 * 1024


def parse_rects(raw: str | list | None) -> list[Rect]:
    """Parse ``[[x0,y0,x1,y1], ...]`` (JSON text or a list) into integer pixel rectangles."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        rects = [tuple(int(round(float(v))) for v in r) for r in data]
        if any(len(r) != 4 for r in rects) or len(rects) > 16:
            raise ValueError("bad rect list")
        return rects  # type: ignore[return-value]
    except (ValueError, TypeError) as err:
        raise AppError(
            "E_BAD_OCCLUSION",
            "The occluder must be a JSON list of [x0, y0, x1, y1] pixel rectangles (at most 16).",
        ) from err


class AppCore:
    """Owns the grade service, replay store, and rate limiter; every transport calls into this."""

    def __init__(self, settings: AppSettings, blame_hook: BlameHook | None = None) -> None:
        self.settings = settings
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        settings.run_dir.mkdir(parents=True, exist_ok=True)
        self.store = ReplayStore(settings.replay_dir)
        self.service = GradeService(settings, store=self.store, blame_hook=blame_hook)
        self.bucket = TokenBucket(settings.rate_per_min)

    # ---- small helpers ---------------------------------------------------------------------
    def client_key(self, address: str) -> str:
        return hash_token(address or "unknown", self.settings.log_salt)

    def first_replay_url(self) -> str | None:
        entries = self.store.list()
        return f"/replay/{entries[0].id}" if entries else None

    def health(self) -> dict[str, Any]:
        s = self.settings
        return {
            "ok": True,
            "version": __version__,
            "backend": s.backend,
            "mode": s.mode,
            "replays": len(self.store.list()),
            "limits": {
                "rate_per_min": s.rate_per_min,
                "max_upload_mb": s.max_upload_mb,
                "max_clip_seconds": s.max_clip_seconds,
                "retention_hours": s.retention_hours,
            },
        }

    def catalog(self) -> dict[str, Any]:
        return {
            "clips": [
                {"id": c.id, "description": c.description, "width": c.width, "height": c.height}
                for c in self.service.curated_clips().values()
            ],
            "tests": sorted(self.service.curated_tests()),
            "replays": [e.model_dump() for e in self.store.list()],
            "backend": self.settings.backend,
            "mode": self.settings.mode,
        }

    def compile(self, instruction: str) -> dict[str, Any]:
        t0 = time.perf_counter()
        test, badges = self.service.compile_instruction(instruction)
        return {
            "test_name": test.name,
            "green": print_green(test),
            "objects": [o.name for o in test.objects],
            "badges": badges,
            "timer_ms": int(round((time.perf_counter() - t0) * 1000)),
        }

    # ---- uploads ---------------------------------------------------------------------------
    def save_upload(self, stream: BinaryIO, filename: str | None) -> Path:
        s = self.settings
        suffix = re.sub(r"[^a-z0-9]", "", Path(filename or "").suffix.lower())[:5] or "mp4"
        path = s.upload_dir / f"{uuid.uuid4().hex}.{suffix}"
        limit = int(s.max_upload_mb * 1024 * 1024)
        total = 0
        with path.open("wb") as fh:
            while True:
                chunk = stream.read(_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    fh.close()
                    path.unlink(missing_ok=True)
                    raise AppError(
                        "E_TOO_LARGE",
                        f"That file is over the {s.max_upload_mb:g} MB limit. Trim or compress it and try again.",
                        status=413,
                        replay_url=self.first_replay_url(),
                    )
                fh.write(chunk)
        if total == 0:
            path.unlink(missing_ok=True)
            raise AppError("E_EMPTY_UPLOAD", "That upload was empty. Choose a video file.")
        try:
            meta = probe_video(path)
            duration = float(meta["n_frames"]) / float(meta["fps"]) if meta.get("fps") else 0.0
        except Exception as err:
            path.unlink(missing_ok=True)
            raise AppError(
                "E_BAD_VIDEO", "We couldn't read that video. Try an H.264 .mp4 up to 20 s."
            ) from err
        if duration > s.max_clip_seconds:
            path.unlink(missing_ok=True)
            raise AppError(
                "E_TOO_LONG",
                f"That clip is {duration:.0f} s long; the limit is {s.max_clip_seconds:g} s. "
                "Trim it and try again.",
                status=413,
                replay_url=self.first_replay_url(),
            )
        return path

    # ---- payloads --------------------------------------------------------------------------
    def _live_payload(self, outcome: GradeOutcome, timer_ms: int) -> dict[str, Any]:
        run = outcome.run
        return {
            "run": run.model_dump(mode="json"),
            "card_url": f"/card/live/{run.run_id}" if outcome.card_path else None,
            "trace_url": f"/trace/{run.run_id}",
            "timer_ms": timer_ms,
            "badges": [*run.badges, LIVE_BADGE],
            "cached": False,
            "mode": self.settings.mode,
            "test_id": outcome.test_id,
            "clip_id": outcome.clip_id,
            "compiled_green": outcome.compiled_green,
            "occlusion": outcome.occlusion,
            "notes": outcome.notes,
        }

    def replay(self, replay_id: str) -> dict[str, Any]:
        t0 = time.perf_counter()
        if not valid_replay_id(replay_id):
            raise AppError("E_BAD_REPLAY_ID", "That replay id isn't valid.", status=404)
        try:
            got = self.store.get(replay_id)
        except ValueError:
            raise AppError(
                "E_REPLAY_CORRUPT",
                "That cached replay failed its integrity check, so we won't show it.",
                status=500,
            ) from None
        if got is None:
            raise AppError(
                "E_REPLAY_NOT_FOUND",
                "No cached replay with that id.",
                status=404,
                replay_url=self.first_replay_url(),
            )
        entry, run, _card = got
        return {
            "run": run.model_dump(mode="json"),
            "card_url": f"/card/replay/{replay_id}",
            "trace_url": None,
            "timer_ms": int(round((time.perf_counter() - t0) * 1000)),
            "badges": [*run.badges, CACHED_BADGE],
            "cached": True,
            "mode": self.settings.mode,
            "replay": entry.model_dump(),
            "original_run_total_ms": entry.run_total_ms,
        }

    # ---- grade -----------------------------------------------------------------------------
    def grade(
        self,
        client: str,
        *,
        upload: tuple[BinaryIO, str | None] | None = None,
        clip_id: str | None = None,
        test_id: str | None = None,
        typed_instruction: str | None = None,
        occlusion_rects: str | list | None = None,
    ) -> dict[str, Any]:
        s = self.settings
        t0 = time.perf_counter()
        allowed, retry_after = self.bucket.take(client)
        if not allowed:
            log_event("rate_limited", client=client)
            raise AppError(
                "E_RATE_LIMIT",
                f"You're grading faster than we allow ({s.rate_per_min:g}/min). "
                f"Try again in about {int(retry_after) + 1} s, or open a cached replay now.",
                status=429,
                replay_url=self.first_replay_url(),
                extra={"retry_after_s": int(retry_after) + 1},
            )
        self.service.maybe_reap()
        rects = parse_rects(occlusion_rects)

        if s.mode == "cache-only":
            rid = f"{test_id or 'stackcube'}__{clip_id}" if clip_id else None
            if upload or rects or (typed_instruction or "").strip() or rid is None:
                raise AppError(
                    "E_CACHE_ONLY",
                    "This deployment is in cache-only mode (live grading is paused), so only the cached "
                    "replays can be opened.",
                    status=503,
                    replay_url=self.first_replay_url(),
                )
            try:
                payload = self.replay(rid)
            except AppError:
                raise AppError(
                    "E_CACHE_ONLY",
                    "Live grading is paused and there is no cached replay for that selection.",
                    status=503,
                    replay_url=self.first_replay_url(),
                ) from None
            log_event("grade", client=client, cached=True, mode="cache-only", replay=rid)
            return payload

        upload_path: Path | None = None
        name_hash = hash_token(upload[1] or "", s.log_salt) if upload else None
        try:
            if upload is not None:
                upload_path = self.save_upload(upload[0], upload[1])
            outcome = self.service.grade(
                clip_id=None if upload_path else clip_id,
                upload_path=upload_path,
                test_id=test_id,
                typed_instruction=typed_instruction,
                occlusion_rects=rects,
            )
        except AppError as err:
            if err.replay_url is None and (err.status >= 500 or err.code in ("E_NO_LIVE_BACKEND", "E001")):
                err.replay_url = self.first_replay_url()
            log_event("grade_error", client=client, code=err.code, name_hash=name_hash)
            raise
        finally:
            if upload_path is not None:
                upload_path.unlink(missing_ok=True)

        timer_ms = int(round((time.perf_counter() - t0) * 1000))
        log_event(
            "grade",
            client=client,
            cached=False,
            backend=s.backend,
            verdict=outcome.run.verdict.value,
            test=outcome.test_id or "typed",
            clip="upload" if upload else outcome.clip_id,
            occluded=bool(outcome.occlusion),
            name_hash=name_hash,
            timer_ms=timer_ms,
        )
        return self._live_payload(outcome, timer_ms)


__all__ = ["LIVE_BADGE", "AppCore", "parse_rects"]
