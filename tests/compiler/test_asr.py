"""Unit and integration tests for Multi-Modal Voice ASR (P05.S03).

Validates VoiceTurn schema, WAV duration inspection, proportional word interpolation,
fixture replay, API transport mocking, dynamic MMS-FA guards, and zero uninstalled imports.
Per ARCHITECTURE.md §6.1-§6.3, ADR-0011, and P05.S03.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from Kodiac_robotics.compiler.asr import (
    VoiceTurn,
    align_with_mms_fa,
    get_wav_duration,
    interpolate_turn_by_words,
    interpolate_turns_to_count,
    transcribe_demo_audio,
)


def test_zero_uninstalled_imports():
    """Assert zero top-level imports of torchaudio or openai."""
    assert "torchaudio" not in sys.modules, "torchaudio must not be imported at top level"
    assert "openai" not in sys.modules, "openai must not be imported at top level"


def test_voice_turn_schema_validation():
    """Validate VoiceTurn Pydantic schema constraints and defaults."""
    # Valid instance
    turn = VoiceTurn(
        transcript="pick up the cube",
        t_start=1.2,
        t_end=3.4,
        source="voice",
    )
    assert turn.transcript == "pick up the cube"
    assert turn.t_start == 1.2
    assert turn.t_end == 3.4
    assert turn.source == "voice"

    # Default source
    turn_default = VoiceTurn(
        transcript="test",
        t_start=0.0,
        t_end=1.0,
    )
    assert turn_default.source == "voice"

    # Invalid negative timestamp
    with pytest.raises(ValidationError):
        VoiceTurn(
            transcript="invalid start",
            t_start=-0.5,
            t_end=2.0,
        )

    # Invalid source literal
    with pytest.raises(ValidationError):
        VoiceTurn(
            transcript="invalid source",
            t_start=0.0,
            t_end=1.0,
            source="unknown",  # type: ignore[arg-type]
        )


def test_get_wav_duration():
    """Verify get_wav_duration correctly parses duration of bundled synthetic fixture."""
    fixture_wav = Path("tests/fixtures/audio/voice_demo.wav")
    assert fixture_wav.is_file(), "Bundled voice_demo.wav fixture must exist"

    dur = get_wav_duration(fixture_wav)
    assert 8.4 <= dur <= 8.6, f"Expected ~8.5s duration, got {dur}s"

    # Non-existent file returns 0.0 without crashing
    assert get_wav_duration(Path("non_existent_file.wav")) == 0.0


def test_proportional_word_interpolation_single_turn():
    """Verify proportional word interpolation splits continuous speech across clauses."""
    parent_turn = VoiceTurn(
        transcript="pick up the red cube and put it on the green cube then let go",
        t_start=1.0,
        t_end=7.0,
        source="voice",
    )
    clauses = [
        "pick up the red cube",  # 5 words
        "and put it on the green cube",  # 7 words
        "then let go",  # 3 words
    ]  # Total: 15 words, duration: 6.0s (0.4s/word)

    sub_turns = interpolate_turn_by_words(parent_turn, clauses)
    assert len(sub_turns) == 3

    # Check that source is marked compiler-default per Law 1 & ADR-0012
    for st in sub_turns:
        assert st.source == "compiler-default"

    # Check monotonic bounds
    assert sub_turns[0].t_start == 1.0
    assert sub_turns[0].t_end == 3.0  # 1.0 + 5 * 0.4
    assert sub_turns[1].t_start == 3.0
    assert sub_turns[1].t_end == 5.8  # 3.0 + 7 * 0.4
    assert sub_turns[2].t_start == 5.8
    assert sub_turns[2].t_end == 7.0  # Reaches parent end


def test_interpolate_turns_to_count():
    """Verify interpolate_turns_to_count when turn count != step count."""
    parent = VoiceTurn(
        transcript="grasp the block lift it up and place it on target",
        t_start=0.0,
        t_end=10.0,
        source="voice",
    )
    # Target 3 steps
    interpolated = interpolate_turns_to_count([parent], target_count=3)
    assert len(interpolated) == 3
    assert interpolated[0].t_start == 0.0
    assert interpolated[-1].t_end == 10.0
    for t in interpolated:
        assert t.source == "compiler-default"


def test_transcribe_demo_audio_fixture_mode():
    """Verify transcribe_demo_audio replaying from bundled fixture."""
    fixture_wav = Path("tests/fixtures/audio/voice_demo.wav")
    turns = transcribe_demo_audio(fixture_wav, backend="fixture")

    assert len(turns) == 3
    assert turns[0].transcript == "pick up cubeA and lift it"
    assert turns[0].t_start == 0.5
    assert turns[0].t_end == 2.5
    assert turns[0].source == "fixture"

    assert turns[1].transcript == "place cubeA on cubeB"
    assert turns[2].transcript == "release gripper and dwell"


def test_transcribe_demo_audio_api_missing_key(monkeypatch, tmp_path):
    """Verify transcribe_demo_audio raises ValueError when MODEL_API_KEY is missing."""
    empty_env = tmp_path / "empty.env"
    empty_env.touch()
    monkeypatch.setenv("KODIAC_ENV_FILE", str(empty_env))
    monkeypatch.delenv("KODIAC_MODEL_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)

    fixture_wav = Path("tests/fixtures/audio/voice_demo.wav")
    with pytest.raises(ValueError, match="MODEL_API_KEY is not set"):
        transcribe_demo_audio(fixture_wav, backend="api")


def test_transcribe_demo_audio_api_mocked(monkeypatch, tmp_path):
    """Verify transcribe_demo_audio parses verbose JSON segments from mocked API."""
    monkeypatch.setenv("MODEL_API_KEY", "mock_meta_key_12345")
    monkeypatch.setenv("KODIAC_MODEL_API_KEY", "mock_meta_key_12345")

    mock_response_data = {
        "text": "pick up cubeA and lift it. place cubeA on cubeB.",
        "segments": [
            {"text": "pick up cubeA and lift it", "start": 0.5, "end": 2.5},
            {"text": "place cubeA on cubeB", "start": 3.0, "end": 5.5},
        ],
    }

    class MockResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return mock_response_data

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, headers=None, files=None, data=None):
            assert "audio/transcriptions" in url
            assert headers["Authorization"] == "Bearer mock_meta_key_12345"
            return MockResponse()

    monkeypatch.setattr(httpx, "Client", MockClient)

    fixture_wav = Path("tests/fixtures/audio/voice_demo.wav")
    turns = transcribe_demo_audio(fixture_wav, backend="api")

    assert len(turns) == 2
    assert turns[0].transcript == "pick up cubeA and lift it"
    assert turns[0].t_start == 0.5
    assert turns[0].t_end == 2.5
    assert turns[0].source == "voice"
    assert turns[1].transcript == "place cubeA on cubeB"


def test_mms_fa_dynamic_guard():
    """Verify align_with_mms_fa safely raises RuntimeError when torchaudio is absent."""
    with pytest.raises(RuntimeError, match="torchaudio and MMS-FA are not installed"):
        align_with_mms_fa(Path("test.wav"), "test transcript")
