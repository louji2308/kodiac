"""Occlusion brush: black-out rectangles applied to every frame before grading (F55).

Rectangles are ``(x0, y0, x1, y1)`` in pixel coordinates of the original frame (x1/y1 exclusive).
Two honest effects are provided:

* ``apply_rects`` / ``occlude_video`` blacken the real pixels (the card's decisive frame shows the occluder).
* ``occlude_tracks`` removes the covered pixels from *cached* masks. It exists only because the
  keyless fixture backend cannot re-segment an edited video; it emulates what a segmenter would lose
  and is always surfaced to the user with the ``OCCLUSION_EMULATION_BADGE``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import numpy as np

from Kodiac_robotics.contracts.core import ObjMask, Track
from Kodiac_robotics.segment.rle import mask_to_rle, rle_to_mask

Rect = tuple[int, int, int, int]

OCCLUSION_EMULATION_BADGE = "[OCCLUSION EMULATED ON CACHED MASKS]"
OCCLUSION_APPLIED_BADGE = "[OCCLUDER APPLIED TO ALL FRAMES]"


def normalize_rects(rects: list[Rect] | list[list[int]] | None, width: int, height: int) -> list[Rect]:
    """Clip rectangles to the frame, order the corners, and drop empty ones."""
    out: list[Rect] = []
    for r in rects or []:
        if len(r) != 4:
            raise ValueError(f"occlusion rect needs 4 numbers (x0,y0,x1,y1), got {r!r}")
        xa, ya, xb, yb = (int(round(float(v))) for v in r)
        x0, x1 = sorted((xa, xb))
        y0, y1 = sorted((ya, yb))
        x0, x1 = max(0, x0), min(width, x1)
        y0, y1 = max(0, y0), min(height, y1)
        if x1 > x0 and y1 > y0:
            out.append((x0, y0, x1, y1))
    return out


def apply_rects(frames_bgr: np.ndarray, rects: list[Rect]) -> np.ndarray:
    """Black out ``rects`` on ALL frames. Accepts (N,H,W,3) or a single (H,W,3) frame; returns a copy."""
    arr = np.array(frames_bgr, copy=True)
    if arr.ndim not in (3, 4):
        raise ValueError(f"expected (N,H,W,C) or (H,W,C) frames, got shape {arr.shape}")
    h, w = (arr.shape[1], arr.shape[2]) if arr.ndim == 4 else (arr.shape[0], arr.shape[1])
    for x0, y0, x1, y1 in normalize_rects(rects, w, h):
        if arr.ndim == 4:
            arr[:, y0:y1, x0:x1, :] = 0
        else:
            arr[y0:y1, x0:x1, :] = 0
    return arr


def occlude_video(src: Path | str, dst: Path | str, rects: list[Rect], fps: float) -> Path:
    """Stream ``src`` through ``apply_rects`` into an H.264 yuv420p MP4 at ``dst`` (constant memory)."""
    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        raise RuntimeError("could not open video for occlusion")
    out_p = Path(dst).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    proc: subprocess.Popen[bytes] | None = None
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if proc is None:
                h, w = frame.shape[:2]
                proc = subprocess.Popen(
                    [
                        "ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
                        "-s", f"{w}x{h}", "-r", f"{fps:.4f}", "-i", "-",
                        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                        "-pix_fmt", "yuv420p", "-an", str(out_p),
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                norm = normalize_rects(rects, w, h)
            assert proc.stdin is not None
            for x0, y0, x1, y1 in norm:
                frame[y0:y1, x0:x1, :] = 0
            proc.stdin.write(frame.tobytes())
    finally:
        cap.release()
    if proc is None:
        raise RuntimeError("video has no decodable frames")
    assert proc.stdin is not None
    proc.stdin.close()
    stderr = proc.stderr.read() if proc.stderr else b""
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg occlusion encode failed: {stderr.decode(errors='replace')[-300:]}")
    return out_p


def occlude_tracks(
    tracks: dict[str, Track],
    rects: list[Rect],
    frame_hw: tuple[int, int],
) -> tuple[dict[str, Track], dict[str, float]]:
    """Remove rectangle-covered pixels from cached masks (emulation, see module docstring).

    Returns the edited tracks and, per object, the maximum fraction of its original mask area
    that the occluder covered on any frame (0..1).
    """
    h, w = frame_hw
    norm = normalize_rects(rects, w, h)
    if not norm:
        return dict(tracks), {name: 0.0 for name in tracks}

    cover = np.zeros((h, w), dtype=bool)
    for x0, y0, x1, y1 in norm:
        cover[y0:y1, x0:x1] = True

    out: dict[str, Track] = {}
    worst: dict[str, float] = {}
    for name, track in tracks.items():
        new_frames: dict[int, ObjMask] = {}
        max_cov = 0.0
        for f_idx, m in track.frames.items():
            shape = m.rle_size if m.rle_size and m.rle_size[0] > 0 else (h, w)
            if tuple(shape) != (h, w):
                new_frames[f_idx] = m
                continue
            mask = rle_to_mask(m.rle, (h, w)).astype(bool)
            area0 = int(mask.sum())
            if area0 == 0:
                new_frames[f_idx] = m
                continue
            kept = mask & ~cover
            area1 = int(kept.sum())
            max_cov = max(max_cov, 1.0 - area1 / area0)
            if area1 == 0:
                continue
            if area1 == area0:
                new_frames[f_idx] = m
                continue
            ys, xs = np.nonzero(kept)
            new_frames[f_idx] = m.model_copy(
                update={
                    "rle": mask_to_rle(kept),
                    "area_px": area1,
                    "bbox_xyxy": (float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)),
                }
            )
        out[name] = track.model_copy(update={"frames": new_frames})
        worst[name] = round(max_cov, 4)
    return out, worst


__all__ = [
    "OCCLUSION_APPLIED_BADGE",
    "OCCLUSION_EMULATION_BADGE",
    "Rect",
    "apply_rects",
    "normalize_rects",
    "occlude_tracks",
    "occlude_video",
]
