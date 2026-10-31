"""Tests for cryptographic GreenLock sidecar generator and verification."""

from __future__ import annotations

import ast
from pathlib import Path

from Kodiac_robotics.compiler.lock import (
    compute_test_sha256,
    generate_lockfile,
    load_lockfile,
    verify_lockfile,
    write_lockfile,
)
from Kodiac_robotics.compiler.parser import parse_green
from Kodiac_robotics.contracts.core import Clip, ClipRef, Event, GreenLock, RunResult, Verdict


def _make_dummy_clip() -> Clip:
    return Clip(
        ref=ClipRef(uri="demos/stack_demo.mp4", source_kind="demo"),
        path_h264="demos/stack_demo.mp4",
        fps=30.0,
        n_frames=300,
        width=640,
        height=480,
        sha256="dummy-clip-sha",
    )


def _make_dummy_run_result() -> RunResult:
    events = [
        Event(
            step=1,
            step_name="grasp",
            kind="grasped",
            t_s=1.2,
            frame=36,
            fps=30.0,
            source="demo",
            verdict=Verdict.PASS,
        ),
        Event(
            step=2,
            step_name="place",
            kind="settled",
            t_s=4.5,
            frame=135,
            fps=30.0,
            source="demo",
            verdict=Verdict.PASS,
        ),
    ]
    return RunResult(
        run_id="demo-calibration-run",
        test_name="stackcube",
        test_sha256="sha-test",
        config_sha256="sha-config",
        clip=ClipRef(uri="demos/stack_demo.mp4", source_kind="demo"),
        verdict=Verdict.PASS,
        exit_code=0,
        events=events,
        badges=["[GEOMETRY: TIER B · GROUND-PLANE FIT]"],
        nonce="0123456789abcdef",
        trace_path="trace.json",
        created_at="2026-10-31T00:00:00Z",
    )


def test_generate_lockfile_schema_and_slack_summary(tmp_path: Path) -> None:
    """Verifies that generate_lockfile preserves the frozen GreenLock schema

    and stores slack_summary in object_baselines['_slack_summary'].
    """
    test_path = Path("examples/stack_blocks.green")
    test = parse_green(test_path)
    clip = _make_dummy_clip()
    demo_run = _make_dummy_run_result()
    model_ids = {
        "sam": "sam-3.1",
        "compiler": "muse-spark-1.3",
        "voice": "muse-voice-transcribe-1.0",
    }
    slack_summary = {
        "h_max_cm": 3.8,
        "delta_xy_cm": 0.8,
        "z_gap_cm": 0.3,
        "v_settle_cm_s": 0.4,
        "calibrated_thresholds": {
            "align_xy_cm": 1.5,
            "gap_cm": 0.5,
            "min_cm": 2.0,
        },
    }

    lock = generate_lockfile(
        test=test,
        test_path=test_path,
        clip=clip,
        demo_run=demo_run,
        model_ids=model_ids,
        slack_summary=slack_summary,
    )

    assert isinstance(lock, GreenLock)
    assert lock.geometry_tier == "B"
    assert lock.model_ids["sam"] == "sam-3.1"
    assert len(lock.demo_events) == 2
    assert len(lock.transcript) == 3

    # Check slack summary placement in object_baselines
    assert "_slack_summary" in lock.object_baselines
    assert lock.object_baselines["_slack_summary"]["h_max_cm"] == 3.8
    assert "gripper" in lock.object_baselines
    assert "red_block" in lock.object_baselines

    # Check lockfile persistence and round-trip load
    lock_file = tmp_path / "stack_blocks.green.lock"
    write_lockfile(lock, lock_file)
    assert lock_file.is_file()

    loaded_lock = load_lockfile(lock_file)
    assert loaded_lock == lock

    # Verification passes on matching file
    assert verify_lockfile(test, test_path, loaded_lock)


def test_lockfile_hash_mismatch() -> None:
    """Verifies that altering the test breaks verify_lockfile."""
    test_path = Path("examples/stackcube.green")
    test = parse_green(test_path)
    clip = _make_dummy_clip()
    demo_run = _make_dummy_run_result()

    lock = generate_lockfile(
        test=test,
        test_path=test_path,
        clip=clip,
        demo_run=demo_run,
        model_ids={"compiler": "template-fallback"},
    )

    # Mutate test
    mutated_test = test.model_copy(deep=True)
    mutated_test.steps[0].name = "mutated_grasp"

    # Mutated test compute_test_sha256 should mismatch
    assert compute_test_sha256(mutated_test) != lock.test_sha256


def test_zero_uninstalled_dependency_imports() -> None:
    """AST audit asserting zero top-level imports of torchaudio or openai

    across all files in src/Kodiac_robotics/compiler/.
    """
    compiler_dir = Path("src/Kodiac_robotics/compiler")
    banned_modules = {"torchaudio", "openai"}

    for py_file in compiler_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0]
                    assert root_mod not in banned_modules, (
                        f"Banned top-level import '{root_mod}' in {py_file}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_mod = node.module.split(".")[0]
                    assert root_mod not in banned_modules, (
                        f"Banned top-level import '{root_mod}' in {py_file}"
                    )
