"""Multi-modal Voice ASR Ingestion Layer for Kodiac.

Transcribes human demonstration audio into typed VoiceTurn windows via
Muse Voice Transcribe 1.0 (via httpx) or deterministic offline fixtures.
Uses stdlib wave for duration and metadata, and system ffmpeg for audio extraction.
Mandates zero top-level imports of torchaudio or openai.
Per ARCHITECTURE.md §6.1-§6.3, ADR-0011, and P05.S03.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from Kodiac_robotics.config import Settings


class VoiceTurn(BaseModel):
    """Normalized turn of human spoken demonstration instruction."""

    transcript: str
    t_start: float = Field(..., ge=0.0, description="Start timestamp in seconds")
    t_end: float = Field(..., ge=0.0, description="End timestamp in seconds")
    source: Literal["voice", "text", "fixture", "compiler-default"] = "voice"


def get_wav_duration(wav_path: Path) -> float:
    """Return the duration of a PCM WAV file in seconds using stdlib wave."""
    try:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate > 0:
                return float(frames) / float(rate)
    except (wave.Error, EOFError, OSError):
        pass
    return 0.0


def extract_audio_from_media(media_path: Path, output_wav_path: Path | None = None) -> Path:
    """Extract 16kHz mono 16-bit PCM WAV from media container using system ffmpeg.

    Args:
        media_path: Input video or audio file.
        output_wav_path: Optional destination path. If None, creates a temporary file.

    Returns:
        Path to the extracted WAV file.
    """
    if output_wav_path is None:
        temp_dir = Path(tempfile.gettempdir()) / "kodiac_audio"
        temp_dir.mkdir(parents=True, exist_ok=True)
        output_wav_path = temp_dir / f"{media_path.stem}_{os.getpid()}_{id(media_path)}.wav"

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(media_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(output_wav_path),
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as err:
        raise RuntimeError("ffmpeg is not installed or not found in system PATH.") from err
    except subprocess.CalledProcessError as err:
        raise RuntimeError(f"ffmpeg audio extraction failed: {err.stderr}") from err

    return output_wav_path


def interpolate_turn_by_words(
    turn: VoiceTurn,
    sub_phrases: list[str],
) -> list[VoiceTurn]:
    """Proportionally interpolate timestamps across multiple clauses for a single turn.

    Allocates audio duration proportionally based on word counts.
    Enforces Law 1 & ADR-0012: tags source='compiler-default'.
    """
    if not sub_phrases:
        return [turn]
    if len(sub_phrases) == 1:
        return [
            VoiceTurn(
                transcript=sub_phrases[0],
                t_start=turn.t_start,
                t_end=turn.t_end,
                source=turn.source,
            )
        ]

    word_counts = [max(1, len(p.strip().split())) for p in sub_phrases]
    total_words = sum(word_counts)
    total_duration = max(0.0, turn.t_end - turn.t_start)

    result: list[VoiceTurn] = []
    current_time = turn.t_start
    for i, (phrase, count) in enumerate(zip(sub_phrases, word_counts)):
        clause_dur = total_duration * (count / total_words)
        end_time = turn.t_end if i == len(sub_phrases) - 1 else round(current_time + clause_dur, 3)
        result.append(
            VoiceTurn(
                transcript=phrase.strip(),
                t_start=round(current_time, 3),
                t_end=round(end_time, 3),
                source="compiler-default",
            )
        )
        current_time = end_time

    return result


def interpolate_turns_to_count(
    turns: list[VoiceTurn],
    target_count: int,
) -> list[VoiceTurn]:
    """Ensure turn count matches target step count via proportional word interpolation.

    When Muse Voice returns fewer turns than compiled steps, interpolates across
    the parent turn's verified audio span without inventing arbitrary timestamps.
    """
    if not turns or target_count <= 0:
        return turns
    if len(turns) == target_count:
        return turns

    if len(turns) == 1:
        parent = turns[0]
        words = parent.transcript.split()
        if target_count > len(words):
            target_count = max(1, len(words))

        # Split words into target_count roughly equal chunks
        chunk_size = len(words) // target_count
        remainder = len(words) % target_count
        chunks: list[str] = []
        idx = 0
        for i in range(target_count):
            take = chunk_size + (1 if i < remainder else 0)
            chunks.append(" ".join(words[idx : idx + take]))
            idx += take

        return interpolate_turn_by_words(parent, chunks)

    # If turns > target_count or general mismatch, preserve verified audio bounds
    return turns[:target_count]


def align_with_mms_fa(audio_path: Path, transcript: str) -> list[VoiceTurn]:
    """Optional dynamic alignment via torchaudio MMS-FA.

    Guarded dynamically: raises RuntimeError if torchaudio is not installed.
    """
    try:
        import torchaudio  # noqa: F401
    except ImportError as e:
        raise RuntimeError("torchaudio and MMS-FA are not installed in the active environment.") from e

    raise NotImplementedError("torchaudio is installed but MMS-FA alignment model weights are not loaded.")


def transcribe_demo_audio(
    audio_path: Path,
    backend: Literal["api", "fixture"] = "fixture",
) -> list[VoiceTurn]:
    """Transcribe demonstration audio using Muse Voice API or offline fixtures.

    Args:
        audio_path: Path to .wav or media file.
        backend: "fixture" for offline deterministic playback; "api" for live Muse Voice API.

    Returns:
        List of typed VoiceTurn windows with timestamps and provenance.
    """
    audio_path = Path(audio_path)

    if backend == "fixture":
        # 1. Check for dedicated sidecar JSON (<stem>.json)
        sidecar_json = audio_path.with_suffix(".json")
        if sidecar_json.is_file():
            data = json.loads(sidecar_json.read_text(encoding="utf-8"))
            return [VoiceTurn(**item) for item in data]

        # 2. Check bundled voice_demo fixture
        bundled_json = Path("tests/fixtures/audio/voice_demo.json")
        if bundled_json.is_file() and (audio_path.name == "voice_demo.wav" or not audio_path.exists()):
            data = json.loads(bundled_json.read_text(encoding="utf-8"))
            return [VoiceTurn(**item) for item in data]

        # 3. Fallback: inspect actual audio file duration if available
        dur = get_wav_duration(audio_path) if audio_path.is_file() else 8.5
        if dur <= 0.0:
            dur = 8.5

        return [
            VoiceTurn(
                transcript="pick up cubeA and lift it",
                t_start=round(0.06 * dur, 2),
                t_end=round(0.3 * dur, 2),
                source="fixture",
            ),
            VoiceTurn(
                transcript="place cubeA on cubeB",
                t_start=round(0.35 * dur, 2),
                t_end=round(0.65 * dur, 2),
                source="fixture",
            ),
            VoiceTurn(
                transcript="release gripper and dwell",
                t_start=round(0.7 * dur, 2),
                t_end=round(0.95 * dur, 2),
                source="fixture",
            ),
        ]

    if backend == "api":
        settings = Settings.load()
        api_key = (
            settings.model_api_key
            or os.environ.get("MODEL_API_KEY")
            or os.environ.get("KODIAC_MODEL_API_KEY")
        )
        if not api_key:
            raise ValueError(
                "MODEL_API_KEY is not set. Set KODIAC_MODEL_API_KEY or MODEL_API_KEY, "
                "or switch to backend='fixture'."
            )

        # Ensure we have a valid WAV file to send
        temp_wav: Path | None = None
        if audio_path.suffix.lower() != ".wav":
            temp_wav = extract_audio_from_media(audio_path)
            upload_path = temp_wav
        else:
            upload_path = audio_path

        try:
            dur = get_wav_duration(upload_path)
            wav_bytes = upload_path.read_bytes()

            url = f"{settings.judge_base_url.rstrip('/')}/audio/transcriptions"
            headers = {"Authorization": f"Bearer {api_key}"}
            files = {"file": (upload_path.name, wav_bytes, "audio/wav")}
            data = {
                "model": "muse-voice-transcribe-1.0",
                "response_format": "verbose_json",
            }

            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, headers=headers, files=files, data=data)
                resp.raise_for_status()
                payload = resp.json()

            # Parse segments or turns from API response
            segments = payload.get("segments") or payload.get("turns")
            if segments and isinstance(segments, list):
                turns: list[VoiceTurn] = []
                for s in segments:
                    text = s.get("text", s.get("transcript", "")).strip()
                    if not text:
                        continue
                    t_start = float(s.get("start", s.get("t_start", 0.0)))
                    t_end = float(s.get("end", s.get("t_end", t_start + 1.0)))
                    turns.append(VoiceTurn(transcript=text, t_start=t_start, t_end=t_end, source="voice"))
                if turns:
                    return turns

            text = payload.get("text", payload.get("transcript", "")).strip()
            return [VoiceTurn(transcript=text, t_start=0.0, t_end=dur, source="voice")]
        finally:
            if temp_wav and temp_wav.exists():
                temp_wav.unlink(missing_ok=True)

    raise ValueError(f"Unknown ASR backend '{backend}'. Must be 'api' or 'fixture'.")
