"""Unit tests for reference pick-and-place execution and B01–B10 bug determinism.

Per ARCHITECTURE.md §4, §5.7, ADR-0004, ADR-0005, and P02 RULING.
Asserts 10/10 seeds oracle PASS for clean execution, and 10/10 seeds
oracle FAIL for every bug patch B01–B10 with settling velocity checks.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure repository root is on sys.path for examples import
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from examples.sim.pick_place import run_episode  # noqa: E402
from Kodiac_robotics.sim.bugs import BUGS, BugDef, get_bug, list_bugs  # noqa: E402
from Kodiac_robotics.sim.env import KinematicMockEnv  # noqa: E402


def test_bug_registry_completeness() -> None:
    """Verify all 10 bugs B01–B10 are properly registered and patch files exist."""
    bugs = list_bugs()
    assert len(bugs) == 10

    for i in range(1, 11):
        bug_id = f"B{i:02d}"
        assert bug_id in BUGS
        b = get_bug(bug_id)
        assert isinstance(b, BugDef)
        assert b.id == bug_id
        assert b.expected_oracle_success is False
        assert len(b.spoken_instruction) > 0
        assert len(b.diagnostic_hint) > 0

        # Check patch file existence
        patch_path = Path(b.patch_path)
        assert patch_path.is_file(), f"Patch file missing for {bug_id}: {patch_path}"
        assert patch_path.stat().st_size > 0


def test_reference_pick_place_clean_10_seeds_pass() -> None:
    """DoD Requirement: Clean pick_place.py must achieve 10/10 seeds oracle PASS."""
    env = KinematicMockEnv()
    for s in range(10):
        ok = run_episode(env, seed=s, bug_id=None)
        assert ok is True, f"Clean pick_place failed on seed {s}"


@pytest.mark.parametrize("bug_id", [f"B{i:02d}" for i in range(1, 11)])
def test_bugs_b01_to_b10_assert_10_of_10_fail(bug_id: str) -> None:
    """SDM Ruling Tripwire 3: B01–B10 must assert 10/10 seeds oracle FAIL.

    If any bug records oracle_success == True on even 1 seed out of 10,
    the test fails immediately.
    """
    env = KinematicMockEnv()
    for s in range(10):
        ok = run_episode(env, seed=s, bug_id=bug_id)
        assert ok is False, (
            f"False-pass detected! Bug {bug_id} unexpectedly succeeded on seed {s} "
            f"(Tripwire 3 violation)"
        )
