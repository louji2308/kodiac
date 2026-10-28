"""Universal Video IO Core: Video loading, normalization, and Clip contract construction.

Normalizes arbitrary video inputs (sim runs, LeRobot datasets, uploaded files, local clips)
into CFR H.264 yuv420p with even dimensions via ffmpeg CLI.
Per ARCHITECTURE.md §0, §5.2 and P03 RULING.md (T01).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlparse

from Kodiac_robotics.contracts.core import Clip, ClipRef
from Kodiac_robotics.io.lerobot import load_lerobot_episode
from Kodiac_robotics.io.transcode import compute_file_sha256, probe_video, transcode_to_cfr_h264

logger = logging.getLogger(__name__)

CACHE_DIR = Path(".cache/clips")


def _infer_source_kind(path_or_uri: str) -> Literal["real", "sim", "upload", "demo"]:
    """Heuristically infer ClipRef source_kind from path or URI strings."""
    s = path_or_uri.lower()
    if "sim" in s or "maniskill" in s:
        return "sim"
    if "demo" in s or "webcam" in s:
        return "demo"
    if "real" in s or "droid" in s:
        return "real"
    return "upload"


def open_clip(ref: str | Path | ClipRef) -> Clip:
    """Normalize any video input to CFR H.264 yuv420p with even dimensions via ffmpeg.

    Parameters
    ----------
    ref:
        File path string, Path object, file:// URI, lerobot:// URI, or ClipRef model.

    Returns
    -------
    Clip:
        Validated Clip contract instance with verified CFR H.264 path, sha256 checksum,
        and stream geometry.
    """
    if isinstance(ref, ClipRef):
        clip_ref = ref
        uri = clip_ref.uri
    elif isinstance(ref, Path):
        uri = str(ref.resolve())
        clip_ref = ClipRef(
            uri=uri,
            source_kind=_infer_source_kind(uri),
        )
    elif isinstance(ref, str):
        uri = ref.strip()
        clip_ref = ClipRef(
            uri=uri,
            source_kind=_infer_source_kind(uri),
        )
    else:
        raise TypeError(f"Unsupported ref type: {type(ref)}")

    # 1. Handle lerobot:// dataset URIs
    if uri.startswith("lerobot://"):
        return load_lerobot_episode(
            repo_id=uri,
            episode_index=clip_ref.episode_index or 0,
            camera=clip_ref.camera,
        )

    # 2. Parse file:// or local path
    if uri.startswith("file://"):
        parsed = urlparse(uri)
        # Handle file:///C:/path vs file:///path
        file_path = unquote(parsed.path)
        if file_path.startswith("/") and len(file_path) > 2 and file_path[2] == ":":
            file_path = file_path[1:]
        local_path = Path(file_path).resolve()
    else:
        local_path = Path(uri).resolve()

    if not local_path.exists():
        raise FileNotFoundError(f"Video clip not found: {local_path}")

    # 3. Probe input video metadata
    meta = probe_video(local_path)

    # 4. Check if already compliant: CFR H.264, yuv420p, and even dimensions
    is_h264 = meta.get("codec_name") == "h264"
    is_yuv420p = meta.get("pix_fmt") in ("yuv420p", "yuvj420p")
    has_even_dims = (meta.get("width", 0) % 2 == 0) and (meta.get("height", 0) % 2 == 0)

    if is_h264 and is_yuv420p and has_even_dims:
        final_path = local_path
        sha256_hash = compute_file_sha256(final_path)
    else:
        # Transcode to CFR H.264 yuv420p with dimension padding filter
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        src_sha = compute_file_sha256(local_path)
        final_path = CACHE_DIR / f"{src_sha[:16]}_cfr.mp4"
        if not final_path.exists() or final_path.stat().st_size == 0:
            transcode_to_cfr_h264(local_path, final_path, target_fps=meta.get("fps", 30.0))
        meta = probe_video(final_path)
        sha256_hash = compute_file_sha256(final_path)

    return Clip(
        ref=clip_ref,
        path_h264=str(final_path),
        fps=meta["fps"],
        n_frames=meta["n_frames"],
        width=meta["width"],
        height=meta["height"],
        sha256=sha256_hash,
    )
