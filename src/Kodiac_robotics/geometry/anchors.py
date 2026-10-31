"""Geometric anchor calculation from object masks.

Extracts centroid, top anchor, bottom anchor (support contact point beta),
area, and occlusion fraction per ARCHITECTURE.md §7.1 and IMPLEMENTATION_PLAN.md P04.S01.
"""

from __future__ import annotations

import numpy as np

from Kodiac_robotics.contracts.core import ObjMask
from Kodiac_robotics.segment.rle import _decode_counts, rle_to_mask

_ANCHORS_CACHE: dict[tuple[str, int, str, tuple[float, float, float, float]], tuple[tuple[float, float], tuple[float, float], tuple[float, float], int]] = {}


def compute_anchors(
    mask: ObjMask,
    base_area_px: int | None = None,
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float], int, float]:
    """Extracts geometric anchors from an ObjMask.

    Returns: ((cx, cy), bottom_anchor, top_anchor, area_px, occlusion_fraction).
    - bottom_anchor: (median column of lowest 5% of mask rows, lowest row).
    - top_anchor: (median column of highest 5% of mask rows, highest row).
    - occlusion_fraction: 0.0 if base_area_px is None else max(0.0, 1.0 - area_px / base_area_px).
    """
    cache_key = (
        mask.obj,
        mask.frame,
        mask.rle[:32] if mask.rle else "",
        mask.bbox_xyxy,
    )
    if cache_key in _ANCHORS_CACHE:
        (c_xy, b_anc, t_anc, a_px) = _ANCHORS_CACHE[cache_key]
        occ = 0.0 if (base_area_px is None or base_area_px <= 0) else max(0.0, 1.0 - a_px / base_area_px)
        return (c_xy, b_anc, t_anc, a_px, occ)
    bbox = mask.bbox_xyxy
    fallback_cx = float((bbox[0] + bbox[2]) / 2.0)
    fallback_cy = float((bbox[1] + bbox[3]) / 2.0)
    fallback_bottom = (fallback_cx, float(bbox[3]))
    fallback_top = (fallback_cx, float(bbox[1]))

    if not mask.rle or mask.area_px == 0:
        occ = 0.0 if (base_area_px is None or base_area_px <= 0) else 1.0
        return ((fallback_cx, fallback_cy), fallback_bottom, fallback_top, 0, occ)

    # Determine canvas shape
    if mask.rle_size and mask.rle_size != (0, 0):
        shape = mask.rle_size
    else:
        cnts = _decode_counts(mask.rle)
        total = sum(cnts)
        if total == 480 * 640 and int(bbox[3]) <= 480 and int(bbox[2]) <= 640:
            shape = (480, 640)
        elif total == 512 * 512 and int(bbox[3]) <= 512 and int(bbox[2]) <= 512:
            shape = (512, 512)
        else:
            h_est = max(int(np.ceil(bbox[3])) + 1, 1)
            w_est = max(int(np.ceil(bbox[2])) + 1, 1)
            shape = (h_est, w_est)

    bin_mask = rle_to_mask(mask.rle, shape)
    ys, xs = np.where(bin_mask > 0)

    if len(ys) == 0:
        occ = 0.0 if (base_area_px is None or base_area_px <= 0) else 1.0
        return ((fallback_cx, fallback_cy), fallback_bottom, fallback_top, 0, occ)

    area_px = int(len(ys))
    cx = float(np.mean(xs))
    cy = float(np.mean(ys))

    y_min = int(np.min(ys))
    y_max = int(np.max(ys))
    h_span = y_max - y_min

    if h_span == 0:
        med_x = float(np.median(xs))
        bottom_anchor = (med_x, float(y_max))
        top_anchor = (med_x, float(y_min))
    else:
        # Lowest 5% of mask rows (physically bottom, largest row indices)
        cutoff_low = y_max - 0.05 * h_span
        cols_low = xs[ys >= cutoff_low]
        med_x_low = float(np.median(cols_low)) if len(cols_low) > 0 else float(np.median(xs))
        bottom_anchor = (med_x_low, float(y_max))

        # Highest 5% of mask rows (physically top, smallest row indices)
        cutoff_high = y_min + 0.05 * h_span
        cols_high = xs[ys <= cutoff_high]
        med_x_high = float(np.median(cols_high)) if len(cols_high) > 0 else float(np.median(xs))
        top_anchor = (med_x_high, float(y_min))

    if base_area_px is None or base_area_px <= 0:
        occlusion_fraction = 0.0
    else:
        occlusion_fraction = float(np.clip(1.0 - float(area_px) / float(base_area_px), 0.0, 1.0))

    if len(_ANCHORS_CACHE) > 50000:
        _ANCHORS_CACHE.clear()
    _ANCHORS_CACHE[cache_key] = ((cx, cy), bottom_anchor, top_anchor, area_px)

    return ((cx, cy), bottom_anchor, top_anchor, area_px, occlusion_fraction)
