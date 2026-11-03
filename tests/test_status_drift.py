"""Tests to ensure the README status block does not drift from docs/features.yaml."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.gen_status_table import (
    BEGIN,
    END,
    _replace,
    _rows,
    main,
    render,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_status_table_generation_in_sync():
    """Assert that the committed README status block matches gen_status_table.render output."""
    readme_path = REPO_ROOT / "README.md"
    features_path = REPO_ROOT / "docs" / "features.yaml"

    assert readme_path.exists(), f"README.md not found at {readme_path}"
    assert features_path.exists(), f"features.yaml not found at {features_path}"

    current_readme = readme_path.read_text(encoding="utf-8")
    rows = _rows(features_path)
    generated_block = render(rows)

    assert BEGIN in current_readme, f"BEGIN marker missing in {readme_path}"
    assert END in current_readme, f"END marker missing in {readme_path}"

    # Verify that replacing the block results in the exact same content (no drift)
    expected_readme = _replace(current_readme, generated_block)
    assert current_readme == expected_readme, (
        "README.md status block has drifted from docs/features.yaml. "
        "Run `python scripts/gen_status_table.py` to synchronize."
    )


def test_gen_status_table_check_cli():
    """Assert that `python scripts/gen_status_table.py --check` exits with 0."""
    script_path = REPO_ROOT / "scripts" / "gen_status_table.py"
    res = subprocess.run(
        [sys.executable, str(script_path), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert res.returncode == 0, (
        f"`gen_status_table.py --check` failed (exit {res.returncode}):\n"
        f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    )


def test_gen_status_table_main_check():
    """Assert programmatic main(['--check']) returns 0."""
    code = main(["--check"])
    assert code == 0
