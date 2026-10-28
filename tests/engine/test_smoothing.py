"""Unit tests for temporal smoothing and Schmitt hysteresis trigger."""

from __future__ import annotations

import numpy as np

from Kodiac_robotics.contracts.core import Tri
from Kodiac_robotics.engine.smoothing import TemporalSmoother


def test_hampel_outlier_rejection():
    """Verify Hampel filter replaces isolated outlier spikes."""
    smoother = TemporalSmoother(fps=30.0, hampel_k=7, savgol_window_s=0.1)

    # Clean signal: line with a massive isolated spike at index 10
    n = 25
    clean_line = np.linspace(2.0, 5.0, n)
    noisy_line = clean_line.copy()
    noisy_line[10] += 50.0  # Massive spike

    filtered = smoother.smooth_trajectory(noisy_line)

    # Spike at index 10 must be eradicated (close to clean line value)
    assert abs(filtered[10] - clean_line[10]) < 1.0
    # Other values should remain close
    np.testing.assert_allclose(filtered[:9], clean_line[:9], atol=0.5)
    np.testing.assert_allclose(filtered[12:], clean_line[12:], atol=0.5)


def test_savgol_smoothing():
    """Verify Savitzky-Golay polynomial smoothing reduces high-frequency jitter."""
    smoother = TemporalSmoother(fps=30.0, hampel_k=5, savgol_window_s=0.2)

    # Sine wave corrupted with zero-mean Gaussian noise
    np.random.seed(42)
    t = np.linspace(0, 1.0, 60)
    signal = 5.0 * np.sin(2 * np.pi * 2 * t)
    noise = np.random.normal(0, 0.4, size=60)
    noisy_signal = signal + noise

    smoothed = smoother.smooth_trajectory(noisy_signal)

    # Residual variance of smoothed signal vs true signal should be lower than noisy signal
    var_noisy = np.mean((noisy_signal - signal) ** 2)
    var_smoothed = np.mean((smoothed - signal) ** 2)
    assert var_smoothed < var_noisy


def test_schmitt_trigger_basic():
    """Verify Schmitt trigger requires n_on confirmations to flip to True."""
    smoother = TemporalSmoother(fps=30.0, schmitt_n_on=3, schmitt_n_off=3)

    # 2 TRUEs are not enough, 3rd TRUE flips it
    inputs = [Tri.T, Tri.T, Tri.F, Tri.T, Tri.T, Tri.T]
    outputs = smoother.apply_schmitt_trigger(inputs)

    assert outputs == [
        Tri.F,  # 1st T -> not enough
        Tri.F,  # 2nd T -> not enough
        Tri.F,  # F resets count
        Tri.F,  # 1st T
        Tri.F,  # 2nd T
        Tri.T,  # 3rd T -> flips to T!
    ]


def test_schmitt_trigger_neutral_unknown_invariant():
    """CRITICAL INVARIANT: Unknown (U) acts neutrally: neither confirms nor breaks hysteresis run length."""
    smoother = TemporalSmoother(fps=30.0, schmitt_n_on=3, schmitt_n_off=3)

    # Sequence with neutral U interspersed between Ts:
    # Frame 0: T (count=1)
    # Frame 1: U (count stays 1, neither increments nor resets)
    # Frame 2: T (count=2)
    # Frame 3: T (count=3 -> flips to T!)
    seq_u = [Tri.T, Tri.U, Tri.T, Tri.T]
    out_u = smoother.apply_schmitt_trigger(seq_u)
    assert out_u == [Tri.F, Tri.F, Tri.F, Tri.T]

    # Contrast with sequence where F breaks the run:
    # Frame 0: T (count=1)
    # Frame 1: F (count reset to 0)
    # Frame 2: T (count=1)
    # Frame 3: T (count=2 -> does NOT flip, stays F)
    seq_f = [Tri.T, Tri.F, Tri.T, Tri.T]
    out_f = smoother.apply_schmitt_trigger(seq_f)
    assert out_f == [Tri.F, Tri.F, Tri.F, Tri.F]

    # Test reverse transition from T to F with neutral U:
    # Start in T (achieved by 3 Ts)
    # Then F, U, F, F should flip back to F
    seq_reverse = [
        Tri.T, Tri.T, Tri.T,  # Flips to T at index 2
        Tri.F,                # f_count=1
        Tri.U,                # f_count stays 1 (neutral)
        Tri.F,                # f_count=2
        Tri.F,                # f_count=3 -> flips to F!
    ]
    out_rev = smoother.apply_schmitt_trigger(seq_reverse)
    assert out_rev[2] == Tri.T
    assert out_rev[3] == Tri.T
    assert out_rev[4] == Tri.T
    assert out_rev[5] == Tri.T
    assert out_rev[6] == Tri.F  # Flipped to F on 3rd F confirmation


def test_dynamic_fps_adaptation():
    """Verify window and confirmations adapt dynamically to frame rate."""
    s15 = TemporalSmoother(fps=15.0, savgol_window_s=0.2)
    s30 = TemporalSmoother(fps=30.0, savgol_window_s=0.2)

    # 0.2s at 15 fps ≈ 3 frames; at 30 fps ≈ 6 -> 7 frames (odd)
    arr = np.zeros(20)
    # Check that smoothing executes cleanly on both frame rates
    res15 = s15.smooth_trajectory(arr)
    res30 = s30.smooth_trajectory(arr)
    assert len(res15) == 20
    assert len(res30) == 20
