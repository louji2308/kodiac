"""Zero-dependency pure-Python / NumPy COCO RLE codec.

Implements COCO compressed RLE encoding and decoding in column-major
(Fortran) order without pycocotools C-extensions.
Per IP-P03-D1-1 and IP-P03-D3-2 in RULING.md and ARCHITECTURE.md §3.1.
"""

from __future__ import annotations

import numpy as np


def _decode_counts(rle: str) -> list[int]:
    """Decode COCO compressed RLE ASCII string into run-length counts.

    The counts represent alternating run lengths of 0s and 1s starting with 0.
    Uses variable-length byte encoding (LEB128 variant) with 6 bits per character
    mapped to ASCII 48-111, with delta encoding for runs after index 2.
    """
    if not rle:
        return []

    cnts: list[int] = []
    p = 0
    m = 0
    n = len(rle)

    while p < n:
        x = 0
        k = 0
        more = True
        while more:
            if p >= n:
                break
            c = ord(rle[p]) - 48
            x |= (c & 0x1F) << (5 * k)
            more = bool(c & 0x20)
            p += 1
            k += 1
            if not more and (c & 0x10):
                x |= (-1) << (5 * k)
        if m > 2:
            x += cnts[m - 2]
        cnts.append(x)
        m += 1

    return cnts


def _encode_counts(cnts: list[int] | np.ndarray) -> str:
    """Encode run-length counts into COCO compressed RLE ASCII string."""
    m = len(cnts)
    if m == 0:
        return ""

    chars: list[str] = []
    for i in range(m):
        x = int(cnts[i])
        if i > 2:
            x -= int(cnts[i - 2])
        more = True
        while more:
            c = x & 0x1F
            x >>= 5
            more = (x != -1) if (c & 0x10) else (x != 0)
            if more:
                c |= 0x20
            c += 48
            chars.append(chr(c))

    return "".join(chars)


def mask_to_rle(mask: np.ndarray) -> str:
    """Encode binary 2D uint8/bool mask to COCO compressed RLE string.

    Mask is flattened in column-major (Fortran) order per COCO specification.
    Returns standard ASCII compressed RLE string.
    """
    if mask.ndim != 2:
        raise ValueError(f"Expected 2D mask, got shape {mask.shape}")

    h, w = mask.shape
    if h == 0 or w == 0:
        return ""

    # Flatten in column-major (Fortran) order
    flat = np.asfortranarray(mask, dtype=bool).reshape(-1, order="F")

    # Find run lengths of consecutive identical values
    diffs = np.diff(flat)
    change_indices = np.where(diffs)[0] + 1
    run_starts = np.r_[0, change_indices]
    run_ends = np.r_[change_indices, len(flat)]
    lengths = run_ends - run_starts

    # COCO RLE always begins with the count of 0s (background)
    if flat[0]:
        cnts = np.r_[0, lengths]
    else:
        cnts = lengths

    return _encode_counts(cnts)


def rle_to_mask(rle: str, shape: tuple[int, int]) -> np.ndarray:
    """Decode COCO compressed RLE string to 2D uint8 binary mask.

    Parameters
    ----------
    rle:
        COCO compressed ASCII string.
    shape:
        Target 2D canvas shape (H, W).

    Returns
    -------
    np.ndarray:
        2D uint8 mask of shape (H, W) with values 0 or 1.
    """
    h, w = shape
    if h == 0 or w == 0:
        return np.zeros((h, w), dtype=np.uint8)

    if not rle:
        return np.zeros((h, w), dtype=np.uint8)

    cnts = _decode_counts(rle)
    if not cnts:
        return np.zeros((h, w), dtype=np.uint8)

    # Alternate 0 and 1 values across runs
    vals = np.zeros(len(cnts), dtype=np.uint8)
    vals[1::2] = 1

    flat = np.repeat(vals, cnts)
    expected_size = h * w

    if len(flat) != expected_size:
        # Gracefully handle padding / truncation if dimensions differ slightly
        if len(flat) < expected_size:
            flat = np.pad(flat, (0, expected_size - len(flat)), mode="constant")
        else:
            flat = flat[:expected_size]

    return flat.reshape((h, w), order="F")


def box_local_to_full_frame_rle(
    local_rle: str,
    box_xyxy: tuple[float, float, float, float],
    full_shape: tuple[int, int],
) -> str:
    """Translate SAM box-local RLE mask to full-frame canvas coordinates.

    Parameters
    ----------
    local_rle:
        COCO compressed RLE string corresponding to the cropped bounding box.
    box_xyxy:
        Bounding box coordinates (x1, y1, x2, y2) in full-frame pixels.
    full_shape:
        Full-frame canvas dimensions (H, W).

    Returns
    -------
    str:
        COCO compressed RLE string anchored on full-frame (H, W) canvas.
    """
    full_h, full_w = full_shape
    if full_h == 0 or full_w == 0 or not local_rle:
        return mask_to_rle(np.zeros(full_shape, dtype=np.uint8))

    cnts = _decode_counts(local_rle)
    total_px = sum(cnts)

    # If already full frame dimensions, return as-is
    if total_px == full_h * full_w:
        return local_rle

    x1, y1, x2, y2 = box_xyxy
    ix1 = int(round(x1))
    iy1 = int(round(y1))
    ix2 = int(round(x2))
    iy2 = int(round(y2))

    box_w = max(1, ix2 - ix1)
    box_h = max(1, iy2 - iy1)

    # Determine local shape
    if total_px == box_h * box_w:
        local_shape = (box_h, box_w)
    elif box_w > 0 and total_px % box_w == 0:
        local_shape = (total_px // box_w, box_w)
    elif box_h > 0 and total_px % box_h == 0:
        local_shape = (box_h, total_px // box_h)
    else:
        # Fallback to box dimensions
        local_shape = (box_h, box_w)

    local_mask = rle_to_mask(local_rle, local_shape)

    # Create full canvas and paste with boundary clamping
    full_canvas = np.zeros(full_shape, dtype=np.uint8)

    dst_y1 = max(0, iy1)
    dst_y2 = min(full_h, iy1 + local_shape[0])
    dst_x1 = max(0, ix1)
    dst_x2 = min(full_w, ix1 + local_shape[1])

    if dst_y2 > dst_y1 and dst_x2 > dst_x1:
        src_y1 = dst_y1 - iy1
        src_y2 = src_y1 + (dst_y2 - dst_y1)
        src_x1 = dst_x1 - ix1
        src_x2 = src_x1 + (dst_x2 - dst_x1)

        full_canvas[dst_y1:dst_y2, dst_x1:dst_x2] = local_mask[src_y1:src_y2, src_x1:src_x2]

    return mask_to_rle(full_canvas)


def rle_area(rle: str, shape: tuple[int, int]) -> int:
    """Compute mask pixel area directly from RLE string without full decompression."""
    if not rle:
        return 0

    cnts = _decode_counts(rle)
    if not cnts:
        return 0

    # 1s are at odd indices in COCO count representation
    return int(sum(cnts[1::2]))
