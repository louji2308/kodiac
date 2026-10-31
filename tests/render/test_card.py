"""Unit tests for Verdict Card v1 renderer."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from Kodiac_robotics.contracts.core import (
    Clip,
    ClipRef,
    Component,
    ReasonCode,
    RunResult,
    StepResult,
    Tri,
    Verdict,
)
from Kodiac_robotics.render.card import render_verdict_card_v1


def _create_mock_run_result(verdict: Verdict) -> tuple[RunResult, Clip, np.ndarray]:
    clip = Clip(
        ref=ClipRef(uri="tests/fixtures/clips/b01_early_release.mp4", source_kind="sim"),
        path_h264="tests/fixtures/clips/b01_early_release.mp4",
        fps=30.0,
        n_frames=90,
        width=640,
        height=480,
        sha256="fa7c591ac6d788f2e5af5594b060f903c1c4f96a2a4d2ec18ab4c2c0b3d96baf",
    )
    comp = Component(
        name="on.align_xy",
        value=3.4,
        threshold=1.5,
        margin=-1.9,
        sigma=0.2,
        unit="cm",
        tri=Tri.F if verdict == Verdict.FAIL else (Tri.T if verdict == Verdict.PASS else Tri.U),
        reason=ReasonCode.OCCLUDED if verdict == Verdict.CANT_TELL else None,
    )
    step = StepResult(
        index=0,
        name="grasp",
        verdict=verdict,
        t_s=1.2,
        frame=36,
        decisive=[comp],
        reasons=[ReasonCode.OCCLUDED] if verdict == Verdict.CANT_TELL else [],
    )
    reasons = [ReasonCode.OCCLUDED] if verdict == Verdict.CANT_TELL else []
    run = RunResult(
        run_id="a1b2c3d4e5f60718",
        test_name="stackcube",
        test_sha256="fa7c591ac6d788f2e5af5594b060f903c1c4f96a2a4d2ec18ab4c2c0b3d96baf",
        config_sha256="0000000000000000000000000000000000000000000000000000000000000000",
        clip=clip.ref,
        verdict=verdict,
        exit_code=0 if verdict == Verdict.PASS else (1 if verdict == Verdict.FAIL else 2),
        steps=[step],
        reasons=reasons,
        nonce="a1b2c3d4e5f60718",
        badges=["[REPLAY: CACHED SAM 3.1 TRACKS]", "[GEOMETRY: TIER C · UNCALIBRATED CAMERA]"],
        trace_path="runs/test/trace.jsonl",
        created_at="2026-10-31T12:00:00Z",
    )
    frame = np.full((480, 640, 3), 120, dtype=np.uint8)
    return run, clip, frame


@pytest.mark.parametrize("verdict", [Verdict.PASS, Verdict.FAIL, Verdict.CANT_TELL])
def test_render_verdict_card_v1_dimensions_and_output(verdict: Verdict) -> None:
    """Verifies that render_verdict_card_v1 produces a valid 1280x720 PNG."""
    run, clip, frame = _create_mock_run_result(verdict)
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "card.png"
        saved = render_verdict_card_v1(run, clip, frame, out_path)
        assert saved.is_file()

        with Image.open(saved) as img:
            assert img.size == (1280, 720)
            assert img.format == "PNG"
