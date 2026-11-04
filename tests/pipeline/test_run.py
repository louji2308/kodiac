"""Unit tests for the end-to-end Kodiac run pipeline."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from PIL import Image

from Kodiac_robotics.contracts.core import ReasonCode, RunResult, Verdict
from Kodiac_robotics.io.clip import open_clip
from Kodiac_robotics.pipeline.run import run
from Kodiac_robotics.segment.fixture import FixtureBackend


def test_run_pipeline_fail_on_b01() -> None:
    """b01_early_release.mp4 must return Verdict.FAIL and exit code 1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "run_b01"
        res = run(
            test="examples/stackcube.green",
            clip="tests/fixtures/clips/b01_early_release.mp4",
            camera="tier_a",
            output_dir=out_dir,
        )

        assert res.verdict == Verdict.FAIL
        assert res.exit_code == 1
        assert len(res.nonce) == 16
        assert res.run_id == res.nonce

        # Verify disk outputs
        result_file = out_dir / "result.json"
        trace_file = out_dir / "trace.jsonl"
        last_verdict_file = Path(".Kodiac") / "last_verdict.json"

        assert result_file.is_file()
        assert trace_file.is_file()
        assert last_verdict_file.is_file()

        # Validate result.json matches RunResult model
        saved_data = json.loads(result_file.read_text(encoding="utf-8"))
        validated = RunResult.model_validate(saved_data)
        assert validated.run_id == res.run_id
        assert validated.verdict == Verdict.FAIL
        assert validated.exit_code == 1


def test_run_pipeline_cant_tell_on_occluded() -> None:
    """occluded_clip.mp4 must return Verdict.CANT_TELL, exit code 2, and OCCLUDED reason."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "run_occ"
        res = run(
            test="examples/stackcube.green",
            clip="tests/fixtures/clips/occluded_clip.mp4",
            output_dir=out_dir,
        )

        assert res.verdict == Verdict.CANT_TELL
        assert res.exit_code == 2
        assert ReasonCode.OCCLUDED in res.reasons

        # Verify result.json
        result_file = out_dir / "result.json"
        assert result_file.is_file()
        saved_data = json.loads(result_file.read_text(encoding="utf-8"))
        assert saved_data["verdict"] == "CANT_TELL"
        assert saved_data["exit_code"] == 2
        assert "occluded" in saved_data["reasons"]


def test_run_direct_stored_track_replay() -> None:
    """Stored-track replay sets is_fixture=True, adds badge, and bypasses segmenter."""
    clip = open_clip("tests/fixtures/clips/b01_early_release.mp4")
    fb = FixtureBackend()
    preloaded_tracks = fb._load_tracks(clip)

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "run_replay"
        res = run(
            test="examples/stackcube.green",
            clip=clip,
            tracks=preloaded_tracks,
            output_dir=out_dir,
        )

        assert res.is_fixture is True
        assert "[REPLAY: CACHED SAM 3.1 TRACKS]" in res.badges
        assert res.timings_ms["segment_ms"] == 0
        assert res.backends.get("perception") == "cached_replay"


def test_run_fixture_backend_badges_both_replay_labels() -> None:
    """backend='fixture' carries both the fixture and cached-track badges, without duplicates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        res = run(
            test="examples/stackcube.green",
            clip="tests/fixtures/clips/b01_early_release.mp4",
            backend="fixture",
            output_dir=Path(tmpdir) / "run_fixture_badges",
        )

        assert res.is_fixture is True
        assert "[FIXTURE REPLAY]" in res.badges
        assert "[REPLAY: CACHED SAM 3.1 TRACKS]" in res.badges
        assert len(res.badges) == len(set(res.badges))


def test_run_stored_track_replay_with_synthetic_perception_label() -> None:
    """Tracks supplied with an explicit synthetic-from-sim-state label must not carry the cached-SAM replay badge."""
    clip = open_clip("tests/fixtures/clips/b01_early_release.mp4")
    fb = FixtureBackend()
    preloaded_tracks = fb._load_tracks(clip)

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "run_replay_synth"
        res = run(
            test="examples/stackcube.green",
            clip=clip,
            tracks=preloaded_tracks,
            perception_label="SYNTHETIC TRACKS FROM SIM STATE · NOT PERCEPTION",
            output_dir=out_dir,
        )

        assert res.is_fixture is True
        assert "[REPLAY: CACHED SAM 3.1 TRACKS]" not in res.badges
        assert "[SYNTHETIC TRACKS FROM SIM STATE · NOT PERCEPTION]" in res.badges
        assert res.backends.get("perception") == "synthetic_from_sim_state"
        assert res.timings_ms["segment_ms"] == 0


def test_run_dense_frames_full_set_matches_default_evaluation() -> None:
    """dense_frames = all frames must reproduce the default full evaluation (bit-identical verdict)."""
    clip = open_clip("tests/fixtures/clips/b01_early_release.mp4")
    fb = FixtureBackend()
    tracks = fb._load_tracks(clip)

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        res_full = run(
            test="examples/stackcube.green",
            clip=clip,
            tracks=tracks,
            camera="tier_a",
            output_dir=out_dir / "run_dense_full",
        )
        res_dense = run(
            test="examples/stackcube.green",
            clip=clip,
            tracks=tracks,
            camera="tier_a",
            dense_frames=set(range(clip.n_frames)),
            output_dir=out_dir / "run_dense_all",
        )

    assert res_full.verdict == Verdict.FAIL
    assert res_dense.verdict == Verdict.FAIL
    assert res_dense.verdict == res_full.verdict


def test_run_dense_frames_untracked_frames_are_cant_tell() -> None:
    """With dense_frames holding a single frame, temporal atoms lose their history -> CANT_TELL (fail closed)."""
    clip = open_clip("tests/fixtures/clips/b01_early_release.mp4")
    fb = FixtureBackend()
    tracks = fb._load_tracks(clip)

    with tempfile.TemporaryDirectory() as tmpdir:
        res = run(
            test="examples/stackcube.green",
            clip=clip,
            tracks=tracks,
            dense_frames={int(clip.n_frames) - 1},
            output_dir=Path(tmpdir) / "run_dense_one",
        )

        assert res.verdict == Verdict.CANT_TELL
        assert ReasonCode.NOT_VISIBLE in res.reasons or ReasonCode.BELOW_NOISE_FLOOR in res.reasons


def test_run_with_verdict_card_rendering() -> None:
    """render_card=True generates a 1280x720 card.png artifact."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "run_card"
        res = run(
            test="examples/stackcube.green",
            clip="tests/fixtures/clips/b01_early_release.mp4",
            render_card=True,
            output_dir=out_dir,
        )

        assert res.card_path is not None
        card_p = Path(res.card_path)
        assert card_p.is_file()

        with Image.open(card_p) as img:
            assert img.size == (1280, 720)
            assert img.format == "PNG"
