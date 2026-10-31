"""Lockfile generation and verification for .green test specifications.

Generates and validates <name>.green.lock sidecar files binding .green tests
to calibration baselines, empirical events, model IDs, and cryptographic SHA-256 hashes.
Per ARCHITECTURE.md §6.1, ADR-0012, and ADR-0013:
- Stores slack_summary under object_baselines["_slack_summary"] to preserve frozen GreenLock schema.
- Records template-fallback model IDs when deterministic fallback was used.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from Kodiac_robotics.compiler.printer import print_green
from Kodiac_robotics.contracts.core import Clip, GreenLock, GreenTest, RunResult


def compute_test_sha256(test: GreenTest, test_path: Path | None = None) -> str:
    """Computes cryptographic SHA-256 hash of canonical .green test text."""
    if test_path is not None and test_path.is_file():
        content = test_path.read_bytes()
    else:
        canonical_text = print_green(test)
        content = canonical_text.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def generate_lockfile(
    test: GreenTest,
    test_path: Path,
    clip: Clip,
    demo_run: RunResult,
    model_ids: dict[str, str],
    slack_summary: dict[str, Any] | None = None,
) -> GreenLock:
    """Generates GreenLock sidecar JSON binding test to demonstration baseline measurements.

    - SHA-256 hash of canonical test specification
    - Transcript turns linked to steps
    - Object baselines and empirical calibration metrics
    - Stores slack_summary under object_baselines['_slack_summary'] to preserve frozen GreenLock schema
    - Demonstrator event transitions
    - Scale geometry tier and model identifiers
    """
    # 1. SHA-256 Hash
    sha256_hash = compute_test_sha256(test, test_path)

    # 2. Extract Transcript Turns
    transcript: list[dict[str, Any]] = []
    for step in test.steps:
        if step.provenance.quote or step.provenance.t_start is not None:
            transcript.append(
                {
                    "step": step.index + 1,
                    "step_name": step.name,
                    "quote": step.provenance.quote,
                    "t_start": step.provenance.t_start,
                    "t_end": step.provenance.t_end,
                    "source": step.provenance.source,
                }
            )

    # 3. Object Baselines
    object_baselines: dict[str, dict[str, Any]] = {}
    for obj in test.objects:
        base_info: dict[str, Any] = {
            "name": obj.name,
            "role": obj.role,
        }
        if obj.size_cm is not None:
            base_info["size_cm"] = obj.size_cm
        if obj.height_cm is not None:
            base_info["height_cm"] = obj.height_cm
        if obj.prompt is not None:
            base_info["prompt"] = obj.prompt
        if obj.aliases:
            base_info["aliases"] = obj.aliases
        object_baselines[obj.name] = base_info

    # Preserve frozen schema: embed slack_summary under '_slack_summary'
    if slack_summary is not None:
        object_baselines["_slack_summary"] = slack_summary

    # 4. Geometry Tier Detection
    tier: Literal["A", "B", "C"] = "B"
    for badge in demo_run.badges:
        if "TIER A" in badge:
            tier = "A"
            break
        elif "TIER C" in badge:
            tier = "C"
            break
        elif "TIER B" in badge:
            tier = "B"
            break

    # 5. Timestamp (UTC ISO 8601)
    now_iso = datetime.now(timezone.utc).isoformat()

    # 6. Construct Frozen GreenLock
    return GreenLock(
        test_sha256=sha256_hash,
        transcript=transcript,
        object_baselines=object_baselines,
        demo_events=list(demo_run.events),
        geometry_tier=tier,
        model_ids=dict(model_ids),
        created_at=now_iso,
    )


def write_lockfile(lock: GreenLock, lock_path: Path | str) -> Path:
    """Serializes GreenLock model to JSON sidecar file."""
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    json_data = lock.model_dump_json(indent=2)
    path.write_text(json_data, encoding="utf-8")
    return path


def load_lockfile(lock_path: Path | str) -> GreenLock:
    """Loads and validates a GreenLock sidecar JSON file."""
    path = Path(lock_path)
    content = path.read_text(encoding="utf-8")
    return GreenLock.model_validate_json(content)


def verify_lockfile(
    test: GreenTest,
    test_path: Path,
    lock: GreenLock,
) -> bool:
    """Verifies that lockfile SHA-256 matches test file content."""
    current_sha = compute_test_sha256(test, test_path)
    return current_sha == lock.test_sha256
