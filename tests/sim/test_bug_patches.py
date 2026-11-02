"""Regression test: every registered bug patch must apply to the current sim script.

Prevents patch rot: examples/sim/bugs/B01-B10.patch each flip the default of the
`bug_id` parameter of `execute_pick_place` in examples/sim/pick_place.py. If the
script layout changes, these patches stop applying and the loop-eval harness
silently falls back to the `bug_id_pin` injection mode; this test catches it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _git_available() -> bool | str:
    try:
        proc = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return "git executable not found or not runnable"
    return False if proc.returncode == 0 else f"git --version failed: {proc.returncode}"


@pytest.mark.parametrize(
    "patch_rel",
    [f"examples/sim/bugs/B{i:02d}.patch" for i in range(1, 11)],
)
def test_bug_patch_applies_to_current_sim_script(patch_rel: str) -> None:
    """`git apply --check` must succeed for every shipped bug patch (else skip if git missing)."""
    skip = _git_available()
    if skip:
        pytest.skip(skip)

    patch = _REPO_ROOT / patch_rel
    assert patch.is_file() and patch.stat().st_size > 0

    # Apply check against the current working tree from the repo root; --check
    # touches nothing, so this is safe to run while other tests use the script.
    proc = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "apply", "--check", "--", patch_rel],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=_REPO_ROOT,
    )
    detail = (proc.stderr or proc.stdout or "").strip()
    assert proc.returncode == 0, f"{patch_rel} does not apply to examples/sim/pick_place.py: {detail}"
