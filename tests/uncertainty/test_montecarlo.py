"""Unit tests for vectorized Monte Carlo uncertainty propagation."""

from __future__ import annotations

import time

import numpy as np

from Kodiac_robotics.uncertainty.montecarlo import (
    propagate_uncertainty_mc,
    propagate_uncertainty_mc_vectorized,
)


def test_scalar_monte_carlo():
    """Scalar Monte Carlo returns positive standard deviation respecting clipping."""
    sig_m = propagate_uncertainty_mc(
        val_nom=4.0, sigma_px=0.5, scale_k=10.0, sigma_k=0.5, n_samples=256
    )
    assert isinstance(sig_m, float)
    assert sig_m >= 0.001
    assert 0.01 <= sig_m <= 1.0


def test_vectorized_monte_carlo_latency_and_correctness():
    """300-frame vectorized evaluation MUST finish in < 50 ms (target < 10 ms)."""
    t_frames = 300
    vals = np.linspace(0.0, 10.0, t_frames)
    scale_k = np.full(t_frames, 10.0)
    sigma_k = np.full(t_frames, 0.4)

    start_time = time.perf_counter()
    sigmas = propagate_uncertainty_mc_vectorized(
        val_nom=vals,
        sigma_px=0.5,
        scale_k=scale_k,
        sigma_k=sigma_k,
        n_samples=256,
    )
    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    assert sigmas.shape == (300,)
    assert np.all(sigmas >= 0.001)
    assert np.all(np.isfinite(sigmas))
    # Latency tripwire check (< 50 ms budget)
    assert elapsed_ms < 50.0, f"Vectorized MC took {elapsed_ms:.2f} ms (> 50 ms tripwire)"


def test_physical_scale_clipping():
    """Scale k sample must be clipped to >= 0.1 px/cm even with negative scale sample."""
    # scale_k = 0.0 with huge sigma_k would produce negative samples if unclipped
    sig_m = propagate_uncertainty_mc(
        val_nom=1.0, sigma_px=1.0, scale_k=0.05, sigma_k=2.0, n_samples=512
    )
    assert np.isfinite(sig_m)
    assert sig_m >= 0.001
