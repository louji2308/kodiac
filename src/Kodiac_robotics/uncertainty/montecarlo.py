"""Vectorized Monte Carlo uncertainty propagation with physical parameter clipping.

Per ARCHITECTURE.md §7.4, ADR-0009, and IMPLEMENTATION_PLAN.md P04.S05.
Evaluates 300 frames in < 8 ms using NumPy vectorized broadcasting.
"""

from __future__ import annotations

import numpy as np


def propagate_uncertainty_mc(
    val_nom: float,
    sigma_px: float,
    scale_k: float,
    sigma_k: float,
    n_samples: int = 256,
    seed: int | None = 42,
) -> float:
    """Vectorized Monte Carlo error propagation with physical parameter clipping.

    - Samples k_sample = np.maximum(np.random.normal(scale_k, sigma_k, n_samples), 0.1)
    - Returns finite, non-negative standard deviation sigma_m >= 0.001.
    """
    rng = np.random.default_rng(seed)
    k_samples = np.maximum(rng.normal(loc=scale_k, scale=max(1e-6, sigma_k), size=n_samples), 0.1)
    p_nom = val_nom * scale_k
    p_samples = rng.normal(loc=p_nom, scale=max(1e-6, sigma_px), size=n_samples)

    m_samples = p_samples / k_samples
    sigma_m = float(np.std(m_samples))
    return max(0.001, sigma_m)


def propagate_uncertainty_mc_vectorized(
    val_nom: np.ndarray,
    sigma_px: float,
    scale_k: np.ndarray | float,
    sigma_k: np.ndarray | float,
    n_samples: int = 256,
    seed: int | None = 42,
) -> np.ndarray:
    """Vectorized Monte Carlo error propagation across (T,) frame arrays in NumPy (<8 ms).

    Parameters
    ----------
    val_nom:
        (T,) array of nominal metric measurements (cm).
    sigma_px:
        Pixel jitter standard deviation.
    scale_k:
        (T,) array or scalar scale factor (px/cm).
    sigma_k:
        (T,) array or scalar scale uncertainty (px/cm).
    n_samples:
        Number of Monte Carlo samples per frame (default 256).
    seed:
        RNG seed for reproducibility.

    Returns
    -------
    np.ndarray:
        (T,) array of propagated metric uncertainties (cm) clipped to >= 0.001.
    """
    rng = np.random.default_rng(seed)
    vals = np.asarray(val_nom, dtype=np.float64)
    t_len = vals.shape[0]

    k_arr = np.broadcast_to(np.asarray(scale_k, dtype=np.float64), (t_len,))
    sig_k_arr = np.broadcast_to(np.asarray(sigma_k, dtype=np.float64), (t_len,))

    # Draw standard normal variables for both noise sources in a single vectorized block
    eps_k = rng.standard_normal(size=(t_len, n_samples))
    eps_p = rng.standard_normal(size=(t_len, n_samples))

    # Physical clipping: k >= 0.1 px/cm
    k_samples = np.maximum(k_arr[:, None] + np.maximum(sig_k_arr[:, None], 1e-6) * eps_k, 0.1)

    p_nom = vals[:, None] * k_arr[:, None]
    p_samples = p_nom + max(1e-6, sigma_px) * eps_p

    m_samples = p_samples / k_samples
    sigma_m = np.std(m_samples, axis=-1)
    return np.maximum(sigma_m, 0.001)
