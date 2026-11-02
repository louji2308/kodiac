"""Object crop generation for the two-way VLM judge (ARCHITECTURE.md §8.1).

Crops the decisive frame to the object's mask bounding box with padding, upscales to a
minimum side length, and draws the mask outline so the judge answers about the outlined
region only. Output is deterministic PNG bytes (content-hashable for caching).
"""

from __future__ import annotations

import cv2
import numpy as np

from Kodiac_robotics.segment.rle import rle_to_mask

OUTLINE_BGR: tuple[int, int, int] = (255, 0, 255)
MAX_SIDE_PX = 2048


def make_crop(
    frame_bgr: np.ndarray,
    mask_rle: str,
    rle_size: tuple[int, int],
    *,
    pad: float = 0.25,
    min_px: int = 512,
) -> bytes:
    """Return a PNG crop of the masked object with its outline drawn.

    The crop covers the mask bbox expanded by ``pad`` of its width/height on each side,
    clamped to the frame. It is upscaled so the shorter side is >= ``min_px`` (the longer
    side is capped at 2048 px for extreme aspect ratios), and the outline is drawn after
    upscaling so it stays crisp. ``rle_size`` is (H, W); (0, 0) means "frame size".
    """
    if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
        raise ValueError("frame_bgr must be an (H, W, 3) BGR array")
    h, w = frame_bgr.shape[:2]
    mask_shape = (int(rle_size[0]), int(rle_size[1])) if tuple(rle_size) != (0, 0) else (h, w)
    mask = rle_to_mask(mask_rle, mask_shape)
    if mask.shape != (h, w):
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        raise ValueError("empty mask: nothing to crop")

    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    px = int(round((x1 - x0) * pad))
    py = int(round((y1 - y0) * pad))
    cx0, cx1 = max(0, x0 - px), min(w, x1 + px)
    cy0, cy1 = max(0, y0 - py), min(h, y1 + py)

    crop = np.ascontiguousarray(frame_bgr[cy0:cy1, cx0:cx1])
    crop_mask = np.ascontiguousarray(mask[cy0:cy1, cx0:cx1]).astype(np.uint8)
    ch, cw = crop.shape[:2]

    scale = max(1.0, min_px / float(min(ch, cw)))
    scale = min(scale, max(1.0, MAX_SIDE_PX / float(max(ch, cw))))
    if scale > 1.0:
        new_w, new_h = int(round(cw * scale)), int(round(ch * scale))
        crop = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
        crop_mask = cv2.resize(crop_mask, (new_w, new_h), interpolation=cv2.INTER_NEAREST)

    contours, _ = cv2.findContours(crop_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    thickness = max(2, int(round(min(crop.shape[:2]) / 160)))
    cv2.drawContours(crop, contours, -1, OUTLINE_BGR, thickness, lineType=cv2.LINE_8)

    ok, buf = cv2.imencode(".png", crop)
    if not ok:
        raise RuntimeError("PNG encoding of crop failed")
    return buf.tobytes()
