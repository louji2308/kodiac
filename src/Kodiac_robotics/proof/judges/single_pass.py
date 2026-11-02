"""Single-pass Muse Spark 1.3 (2 fps) baseline judge (PREREGISTRATION §4 arm 6).

The judge samples the episode video at 2 fps and asks the model one question: did the robot complete the
task? It returns a label only from a real model reply. Without an API key, a video file, or ffmpeg it
raises :class:`JudgeUnavailable`; it never returns a constant or a ground-truth-derived decision.

Request shape: reused from ``judge/client.py`` / ``compiler/spark_compile.py`` (POST
``{judge_base_url}/chat/completions``, Bearer auth, ``response_format`` json_object, images as base64
data URLs). Sending *several* ``image_url`` parts in one user message is [UNVERIFIED] against the real
Muse Spark API: it is the standard OpenAI-compatible multi-image form but has not been exercised live.
``cost_usd`` is not metered (no verified price list); 0.0 means *unmetered*, not free.

Provenance: a reply obtained over the real network sets ``is_mock=False, evidence_type="live"``. If a
test transport or frame extractor is injected, the label is ``is_mock=True, evidence_type="fixture"``.
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from Kodiac_robotics.contracts.core import JudgeLabel, Verdict
from Kodiac_robotics.judge.client import JSON_INSTRUCTION, parse_answer
from Kodiac_robotics.proof.judges.base import JudgeUnavailable

JUDGE_NAME = "single_pass_spark_1.3"
SYSTEM_PROMPT = (
    "You judge robot manipulation videos. You see frames sampled in time order from one episode. "
    "Decide whether the robot completed the stated task."
)

FrameExtractor = Callable[[Path, float], list[bytes]]


def extract_frames_ffmpeg(video_path: Path, fps: float) -> list[bytes]:
    """Decode ``video_path`` at ``fps`` frames/second into PNG bytes with the ffmpeg CLI."""
    exe = shutil.which("ffmpeg")
    if exe is None:
        raise JudgeUnavailable("ffmpeg is not on PATH: cannot sample frames for the single-pass judge")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "f_%04d.png"
        proc = subprocess.run(
            [exe, "-y", "-i", str(video_path), "-vf", f"fps={fps}", str(out)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise JudgeUnavailable(f"ffmpeg failed to sample frames from {video_path}: {proc.stderr[-300:]}")
        frames = [p.read_bytes() for p in sorted(Path(tmp).glob("f_*.png"))]
    if not frames:
        raise JudgeUnavailable(f"no frames could be sampled from {video_path}")
    return frames


class SinglePassSparkJudge:
    """Baseline judge querying Muse Spark 1.3 with 2 fps subsampled frames."""

    def __init__(
        self,
        api_key: str | None = None,
        fps_sample: float = 2.0,
        model_id: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        frame_extractor: FrameExtractor | None = None,
    ) -> None:
        self._api_key = api_key
        self.fps_sample = fps_sample
        self.model_id = model_id
        self.base_url = base_url
        self.timeout = timeout
        self._transport = transport
        self._frame_extractor = frame_extractor

    def __repr__(self) -> str:
        return f"SinglePassSparkJudge(model_id={self.model_id!r}, fps_sample={self.fps_sample})"

    def _resolve(self) -> tuple[str, str, str]:
        from Kodiac_robotics.config import Settings

        settings = Settings.load()
        key = (
            self._api_key
            or settings.model_api_key
            or os.environ.get("MODEL_API_KEY")
            or os.environ.get("KODIAC_MODEL_API_KEY")
        )
        if not key:
            raise JudgeUnavailable(
                "single-pass Muse Spark judge not run: no MODEL_API_KEY / KODIAC_MODEL_API_KEY is set"
            )
        base = (self.base_url or settings.judge_base_url).rstrip("/")
        model = self.model_id or settings.judge_model or "muse-spark-1.3"
        return key, base, model

    def build_payload(self, frames: list[bytes], task_instruction: str, model: str) -> dict[str, Any]:
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    f"Task: {task_instruction}\nThe frames below are sampled at {self.fps_sample:g} fps. "
                    f"Did the robot complete the task?\n{JSON_INSTRUCTION}"
                ),
            }
        ]
        for png in frames:
            url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": url}})
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
        }

    def evaluate_episode(
        self,
        episode_id: str,
        video_path: str | Path | None = None,
        task_instruction: str = "Pick up Cube A and place it on Cube B.",
    ) -> JudgeLabel:
        """Judge one episode video. Raises :class:`JudgeUnavailable` if it cannot really be run."""
        key, base, model = self._resolve()
        if video_path is None or not Path(video_path).is_file():
            raise JudgeUnavailable(f"video for episode {episode_id!r} not found: {video_path!r}")

        extractor = self._frame_extractor or extract_frames_ffmpeg
        frames = extractor(Path(video_path), self.fps_sample)
        if not frames:
            raise JudgeUnavailable(f"no frames sampled for episode {episode_id!r}")

        start = time.perf_counter()
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
            resp = client.post(
                f"{base}/chat/completions",
                headers=headers,
                json=self.build_payload(frames, task_instruction, model),
            )
            resp.raise_for_status()
            body = resp.json()
        latency_ms = max(1, int((time.perf_counter() - start) * 1000))

        try:
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise JudgeUnavailable(f"malformed model response for episode {episode_id!r}") from exc
        answer = parse_answer(text if isinstance(text, str) else str(text))

        injected = self._transport is not None or self._frame_extractor is not None
        if answer.answer == "yes":
            verdict, accept = Verdict.PASS, True
        elif answer.answer == "no":
            verdict, accept = Verdict.FAIL, False
        else:
            verdict, accept = Verdict.CANT_TELL, False
        return JudgeLabel(
            judge=JUDGE_NAME,
            episode_id=episode_id,
            accept=accept,
            score=None,
            verdict=verdict,
            latency_ms=latency_ms,
            cost_usd=0.0,
            calibration_threshold=None,
            is_mock=injected,
            evidence_type="fixture" if injected else "live",
        )

    def evaluate_batch(self, episodes: list[dict[str, Any]]) -> list[JudgeLabel]:
        """Judge a list of ``{"episode_id", "video_uri"}`` dicts; any unavailable input raises."""
        return [
            self.evaluate_episode(ep["episode_id"], video_path=ep.get("video_uri"))
            for ep in episodes
        ]
