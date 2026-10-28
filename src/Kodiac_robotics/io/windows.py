"""Temporal window cutting with symmetric padding and sparse keyframe packing.

Guarantees SAM 3.1 50-frame minimum billing constraint satisfaction while preserving
exact unpadded query intervals (valid_f0, valid_f1) and frame rate.
Per ARCHITECTURE.md §0, §5.2 and P03 RULING.md (T01).
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import cv2
from pydantic import BaseModel

from Kodiac_robotics.contracts.core import Clip
from Kodiac_robotics.io.transcode import cut_video_frames, write_frames_to_mp4

logger = logging.getLogger(__name__)

CACHE_DIR_WINDOWS = Path(".cache/windows")
CACHE_DIR_PACKED = Path(".cache/packed")


class WindowCut(BaseModel):
    """Padded video segment meeting SAM 3.1 50-frame minimum constraint."""

    path: Path
    valid_f0: int  # Requested start frame index in parent clip
    valid_f1: int  # Requested end frame index in parent clip
    padded_f0: int  # Actual start frame index after symmetric padding
    padded_f1: int  # Actual end frame index after symmetric padding
    n_frames: int  # Total frames in cut video (>= 50)
    fps: float
    parent_sha256: str


class PackedKeyframes(BaseModel):
    """Sparse keyframes packed into contiguous MP4 for batch API prompting."""

    path: Path
    original_indices: list[int]
    index_map: dict[int, int]  # packed_frame_idx -> original_frame_idx
    n_frames: int


def cut_window(clip: Clip, f0: int, f1: int, min_frames: int = 50) -> WindowCut:
    """Extract frame window [f0, f1], padding symmetrically to >= min_frames.

    When window duration f1 - f0 + 1 < min_frames, symmetrically expands backwards
    and forwards, clamping to [0, clip.n_frames - 1].
    Preserves exact requested query interval in (valid_f0, valid_f1).

    Parameters
    ----------
    clip:
        Parent normalized Clip contract instance.
    f0:
        Inclusive start frame index in parent clip.
    f1:
        Inclusive end frame index in parent clip.
    min_frames:
        Minimum frame threshold required by SAM 3.1 (default: 50).

    Returns
    -------
    WindowCut:
        Container with cut MP4 path, frame bounds, and parent clip SHA-256.
    """
    if f0 > f1:
        raise ValueError(f"f0 ({f0}) cannot be greater than f1 ({f1})")

    n_total = clip.n_frames
    if n_total <= 0:
        raise ValueError(f"Parent clip has invalid n_frames: {n_total}")

    # Clamp requested bounds to parent clip boundaries
    valid_f0 = max(0, min(n_total - 1, f0))
    valid_f1 = max(0, min(n_total - 1, f1))
    req_len = valid_f1 - valid_f0 + 1

    if req_len >= min_frames:
        padded_f0 = valid_f0
        padded_f1 = valid_f1
    else:
        deficit = min_frames - req_len
        pad_left = deficit // 2
        pad_right = deficit - pad_left

        cand_f0 = valid_f0 - pad_left
        cand_f1 = valid_f1 + pad_right

        if cand_f0 < 0:
            overflow_left = -cand_f0
            padded_f0 = 0
            cand_f1 += overflow_left
        else:
            padded_f0 = cand_f0

        if cand_f1 > n_total - 1:
            overflow_right = cand_f1 - (n_total - 1)
            padded_f1 = n_total - 1
            padded_f0 = max(0, padded_f0 - overflow_right)
        else:
            padded_f1 = cand_f1

    n_frames = padded_f1 - padded_f0 + 1

    CACHE_DIR_WINDOWS.mkdir(parents=True, exist_ok=True)
    out_name = f"{clip.sha256[:16]}_w_{padded_f0}_{padded_f1}.mp4"
    out_path = (CACHE_DIR_WINDOWS / out_name).resolve()

    if not out_path.exists() or out_path.stat().st_size == 0:
        cut_video_frames(
            input_path=clip.path_h264,
            output_path=out_path,
            start_frame=padded_f0,
            end_frame=padded_f1,
            fps=clip.fps,
        )

    return WindowCut(
        path=out_path,
        valid_f0=valid_f0,
        valid_f1=valid_f1,
        padded_f0=padded_f0,
        padded_f1=padded_f1,
        n_frames=n_frames,
        fps=clip.fps,
        parent_sha256=clip.sha256,
    )


def pack_frames(clip: Clip, indices: list[int]) -> PackedKeyframes:
    """Assemble sparse keyframes into an MP4 with 3-frame repeated duration per keyframe at 10 fps.

    Preserves temporal cross-attention stability in SAM 3.1 batch prompting and builds
    bidirectional index map (packed_frame_idx -> original_frame_idx).

    Parameters
    ----------
    clip:
        Parent normalized Clip contract instance.
    indices:
        List of keyframe indices to extract and assemble.

    Returns
    -------
    PackedKeyframes:
        Container with packed MP4 path, original indices, and index map.
    """
    if not indices:
        raise ValueError("Keyframe indices list cannot be empty")

    n_total = clip.n_frames
    for idx in indices:
        if not (0 <= idx < n_total):
            raise ValueError(f"Keyframe index {idx} out of range [0, {n_total - 1}]")

    cap = cv2.VideoCapture(clip.path_h264)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video source: {clip.path_h264}")

    packed_frames = []
    index_map: dict[int, int] = {}
    packed_counter = 0

    try:
        for orig_idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, orig_idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                raise RuntimeError(f"Failed reading frame {orig_idx} from {clip.path_h264}")

            # Repeat frame 3 times to stabilize SAM 3.1 temporal cross-attention
            for _ in range(3):
                packed_frames.append(frame.copy())
                index_map[packed_counter] = orig_idx
                packed_counter += 1
    finally:
        cap.release()

    CACHE_DIR_PACKED.mkdir(parents=True, exist_ok=True)
    indices_str = "_".join(str(i) for i in indices)
    indices_hash = hashlib.sha256(indices_str.encode()).hexdigest()[:12]
    out_name = f"{clip.sha256[:16]}_pack_{indices_hash}.mp4"
    out_path = (CACHE_DIR_PACKED / out_name).resolve()

    if not out_path.exists() or out_path.stat().st_size == 0:
        write_frames_to_mp4(
            frames=packed_frames,
            output_path=out_path,
            fps=10.0,
        )

    return PackedKeyframes(
        path=out_path,
        original_indices=list(indices),
        index_map=index_map,
        n_frames=len(packed_frames),
    )
