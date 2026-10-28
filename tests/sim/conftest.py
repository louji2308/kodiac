"""Pytest configuration for sim tests.

Ensures repository root is available in sys.path so examples.sim can be imported.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to sys.path
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
