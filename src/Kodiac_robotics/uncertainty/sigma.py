"""Pixel jitter estimation via robust second-difference MAD over static segments.

Per ARCHITECTURE.md §7.4 and IMPLEMENTATION_PLAN.md P04.S05.
"""

from __future__ import annotations

import numpy as np

from Kodiac_robotics.contracts.core import Track
from Kodiac_robotics.geometry.anchors import compute_anchors


def estimate_pixel_jitter(
    tracks: dict[str, Track],
    static_window: tuple[int, int] = (0, 15),
) -> float:
    """Estimates pixel jitter sigma_px via second-difference MAD over static segments.

    sigma_px = max(0.5, 1.4826 * MAD(Delta^2 x) / sqrt(6)).
    """
    diffs_all: list[float] = []
    w_start, w_end = static_window

    for track in tracks.values():
        available_frames = sorted([f for f in track.frames.keys() if w_start <= f <= w_end])
        if len(available_frames) < 3:
            continue

        # Check consecutive frames
        xs: list[float] = []
        ys: list[float] = []
        for f in available_frames:
            mask = track.frames[f]
            (cx, cy), _, _, _, _ = compute_anchors(mask)
            xs.append(cx)
            ys.append(cy)

        # Compute second differences where frames are strictly consecutive
        xs_arr = np.array(xs, dtype=np.float64)
        ys_arr = np.array(ys, dtype=np.float64)
        frames_arr = np.array(available_frames, dtype=np.int64)

        # Detect gaps in frame numbers
        frame_diffs = np.diff(frames_arr)
        # Find contiguous chunks of step 1
        chunk_start = 0
        for i in range(len(frame_diffs)):
            if frame_diffs[i] != 1:
                # Process chunk from chunk_start to i
                if (i - chunk_start + 1) >= 3:
                    diffs_all.extend(np.diff(xs_arr[chunk_start : i + 1], n=2).tolist())
                    diffs_all.extend(np.diff(ys_arr[chunk_start : i + 1], n=2).tolist())
                chunk_start = i + 1
        # Process last chunk
        if (len(available_frames) - chunk_start) >= 3:
            diffs_all.extend(np.diff(xs_arr[chunk_start:], n=2).tolist())
            diffs_all.extend(np.diff(ys_arr[chunk_start:], n=2).tolist())

    if not diffs_all:
        return 0.5

    diffs_np = np.asarray(diffs_all, dtype=np.float64)
    med = float(np.median(diffs_np))
    mad = float(np.median(np.abs(diffs_np - med)))
    sigma_est = float(1.4826 * mad / np.sqrt(6.0))

    return max(0.5, sigma_est)
