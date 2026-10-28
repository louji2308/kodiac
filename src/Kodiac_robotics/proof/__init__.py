"""Proof of Value module for Kodiac.

Implements practice pool generation, pre-registration integrity verification,
baseline judge spikes, policy training scaffolding, and appearance benchmarks
per ARCHITECTURE.md §5.7 and P02 RULING.
"""

from __future__ import annotations

from Kodiac_robotics.proof.pool import (
    PoolEpisodeRecord,
    PracticePoolGenerator,
    compute_prereg_hashes,
    generate_mock_pool,
    verify_preregistration_tag,
)

__all__ = [
    "PoolEpisodeRecord",
    "PracticePoolGenerator",
    "compute_prereg_hashes",
    "generate_mock_pool",
    "verify_preregistration_tag",
]
