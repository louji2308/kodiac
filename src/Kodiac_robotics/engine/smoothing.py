"""Temporal smoothing and hysteresis trigger for trajectory and predicate signals."""

from __future__ import annotations

import numpy as np
from scipy.signal import savgol_filter

from Kodiac_robotics.contracts.core import Tri


class TemporalSmoother:
    """3-stage temporal filtering: Hampel outlier filter -> Savitzky-Golay -> Schmitt trigger."""

    def __init__(
        self,
        fps: float,
        hampel_k: int = 7,
        savgol_window_s: float = 0.2,
        schmitt_n_on: int = 3,
        schmitt_n_off: int | None = None,
    ) -> None:
        """Initialize temporal smoother with dynamic time-base conversion.

        Args:
            fps: Video clip frame rate (frames per second).
            hampel_k: Total window size for Hampel filter (default 7).
            savgol_window_s: Time window in seconds for Savitzky-Golay smoothing (default 0.2 s).
            schmitt_n_on: Number of consecutive confirmations required to flip to TRUE (default 3).
            schmitt_n_off: Number of consecutive confirmations required to flip to FALSE (defaults to schmitt_n_on).
        """
        self.fps = float(fps)
        self.hampel_k = max(3, int(hampel_k))
        self.savgol_window_s = float(savgol_window_s)
        self.schmitt_n_on = max(1, int(schmitt_n_on))
        self.schmitt_n_off = (
            max(1, int(schmitt_n_off)) if schmitt_n_off is not None else self.schmitt_n_on
        )

    def smooth_trajectory(self, raw_values: np.ndarray) -> np.ndarray:
        """Apply Hampel outlier rejection followed by Savitzky-Golay polynomial smoothing.

        Args:
            raw_values: 1D array of trajectory or physical measurement values.

        Returns:
            Smoothed 1D numpy array with the same length.
        """
        arr = np.asarray(raw_values, dtype=float).copy()
        n = len(arr)
        if n < 3:
            return arr

        # Stage 1: Hampel outlier rejection
        hampel_filtered = arr.copy()
        half_k = self.hampel_k // 2

        for i in range(n):
            start = max(0, i - half_k)
            end = min(n, i + half_k + 1)
            window = arr[start:end]
            med = float(np.median(window))
            mad = 1.4826 * float(np.median(np.abs(window - med)))
            threshold = 3.0 * mad

            if mad > 1e-6 and abs(arr[i] - med) > threshold:
                hampel_filtered[i] = med

        # Stage 2: Savitzky-Golay polynomial filter (polyorder=2)
        # Dynamic window conversion from seconds to frames
        sg_window_frames = max(3, int(round(self.savgol_window_s * self.fps)))
        if sg_window_frames % 2 == 0:
            sg_window_frames += 1

        # Bound window by array length
        if sg_window_frames > n:
            sg_window_frames = n if n % 2 == 1 else n - 1

        if sg_window_frames >= 3:
            smoothed = savgol_filter(hampel_filtered, window_length=sg_window_frames, polyorder=2)
        else:
            smoothed = hampel_filtered

        return np.asarray(smoothed, dtype=float)

    def apply_schmitt_trigger(self, tri_states: list[Tri]) -> list[Tri]:
        """Applies tri-state hysteresis to a sequence of Tri states.

        Requires n_on consecutive TRUE confirmations to flip from FALSE to TRUE.
        Requires n_off consecutive FALSE confirmations to flip from TRUE to FALSE.
        UNKNOWN (U) acts neutrally: it neither confirms nor breaks hysteresis run lengths.

        Args:
            tri_states: Sequential list of Tri states across frames.

        Returns:
            Smoothed list of Tri states after applying hysteresis.
        """
        if not tri_states:
            return []

        current_state = Tri.F
        t_run = 0
        f_run = 0
        result: list[Tri] = []

        for s in tri_states:
            if s == Tri.T:
                t_run += 1
                f_run = 0  # Reset False run
                if current_state == Tri.F and t_run >= self.schmitt_n_on:
                    current_state = Tri.T
            elif s == Tri.F:
                f_run += 1
                t_run = 0  # Reset True run
                if current_state == Tri.T and f_run >= self.schmitt_n_off:
                    current_state = Tri.F
            elif s == Tri.U:
                # UNKNOWN acts neutrally: does not increment and does not reset runs
                pass

            result.append(current_state)

        return result
