"""FFmpeg CLI subprocess wrappers for video normalization and frame operations.

Guarantees constant frame rate (CFR) H.264 yuv420p output with even dimensions,
zero external C-library codec bindings, and full compatibility with SAM 3.1.
Per ARCHITECTURE.md §0, §5.2 and P03 RULING.md (T01).
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def compute_file_sha256(path: Path | str, chunk_size: int = 65536) -> str:
    """Compute standard SHA-256 hex digest for a file on disk."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def probe_video(path: Path | str) -> dict[str, Any]:
    """Probe video stream geometry, duration, frame count, and codec metadata via ffprobe.

    Parameters
    ----------
    path:
        Path to local video file.

    Returns
    -------
    dict[str, Any]:
        Dictionary with keys: width, height, fps, n_frames, duration, codec_name, pix_fmt.
    """
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Video file not found: {p}")

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,avg_frame_rate,nb_frames,codec_name,pix_fmt",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(p),
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(proc.stdout)
    except Exception as e:
        logger.warning("ffprobe failed on %s: %s", p, e)
        raise RuntimeError(f"ffprobe failed for {p}: {e}") from e

    streams = data.get("streams", [])
    if not streams:
        raise ValueError(f"No video streams found in {p}")

    stream = streams[0]
    width = int(stream.get("width", 0))
    height = int(stream.get("height", 0))
    codec_name = stream.get("codec_name", "unknown")
    pix_fmt = stream.get("pix_fmt", "unknown")

    # Parse fps from r_frame_rate or avg_frame_rate
    fps_str = stream.get("r_frame_rate") or stream.get("avg_frame_rate") or "30/1"
    if "/" in fps_str:
        num, denom = fps_str.split("/")
        fps = float(num) / float(denom) if float(denom) != 0 else 30.0
    else:
        fps = float(fps_str)

    fmt = data.get("format", {})
    duration = float(fmt.get("duration", 0.0))

    nb_frames_raw = stream.get("nb_frames")
    if nb_frames_raw and nb_frames_raw != "N/A":
        n_frames = int(nb_frames_raw)
    elif duration > 0 and fps > 0:
        n_frames = int(round(duration * fps))
    else:
        # Fallback: count frames with ffprobe
        count_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            str(p),
        ]
        count_proc = subprocess.run(count_cmd, capture_output=True, text=True)
        try:
            n_frames = int(count_proc.stdout.strip())
        except (ValueError, TypeError):
            n_frames = 1

    return {
        "width": width,
        "height": height,
        "fps": fps,
        "n_frames": n_frames,
        "duration": duration,
        "codec_name": codec_name,
        "pix_fmt": pix_fmt,
    }


def transcode_to_cfr_h264(
    input_path: Path | str,
    output_path: Path | str,
    target_fps: float | None = None,
    crf: int = 18,
    preset: str = "fast",
) -> Path:
    """Normalize any video input to CFR H.264 yuv420p with even dimensions via ffmpeg.

    Applies dimension padding filter ('pad=ceil(iw/2)*2:ceil(ih/2)*2') to guarantee
    even width and height, enforces constant frame rate with -vsync cfr, and strips audio.
    """
    in_p = Path(input_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    fps = target_fps
    if fps is None:
        meta = probe_video(in_p)
        fps = meta["fps"] if meta["fps"] > 0 else 30.0

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(in_p),
        "-vf",
        "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-vsync",
        "cfr",
        "-r",
        f"{fps:.4f}",
        "-an",
        str(out_p),
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as err:
        # Fallback for newer ffmpeg versions deprecating -vsync in favor of -fps_mode:v
        fallback_cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(in_p),
            "-vf",
            "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            "-fps_mode:v",
            "cfr",
            "-r",
            f"{fps:.4f}",
            "-an",
            str(out_p),
        ]
        proc = subprocess.run(fallback_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg transcoding failed for {in_p} -> {out_p}:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
            ) from err

    return out_p


def cut_video_frames(
    input_path: Path | str,
    output_path: Path | str,
    start_frame: int,
    end_frame: int,
    fps: float,
    crf: int = 18,
    preset: str = "fast",
) -> Path:
    """Extract inclusive frame range [start_frame, end_frame] to CFR H.264 MP4.

    Uses frame-accurate select filter and resets timestamps.
    """
    in_p = Path(input_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    filter_expr = (
        f"select='between(n\\,{start_frame}\\,{end_frame})',setpts=PTS-STARTPTS,pad=ceil(iw/2)*2:ceil(ih/2)*2"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(in_p),
        "-vf",
        filter_expr,
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-vsync",
        "cfr",
        "-r",
        f"{fps:.4f}",
        "-an",
        str(out_p),
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as err:
        fallback_cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(in_p),
            "-vf",
            filter_expr,
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            "-fps_mode:v",
            "cfr",
            "-r",
            f"{fps:.4f}",
            "-an",
            str(out_p),
        ]
        proc = subprocess.run(fallback_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg frame cut failed for {in_p} -> {out_p}:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
            ) from err

    return out_p


def write_frames_to_mp4(
    frames: list[np.ndarray],
    output_path: Path | str,
    fps: float = 10.0,
    crf: int = 18,
    preset: str = "fast",
) -> Path:
    """Encode an in-memory sequence of BGR frames into CFR H.264 yuv420p MP4 via ffmpeg stdin pipe.

    Ensures zero temporary image files written to disk and guarantees even dimensions.
    """
    if not frames:
        raise ValueError("Cannot write empty frame sequence to MP4")

    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    h, w = frames[0].shape[:2]

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-s",
        f"{w}x{h}",
        "-pix_fmt",
        "bgr24",
        "-r",
        f"{fps:.4f}",
        "-i",
        "-",
        "-vf",
        "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-vsync",
        "cfr",
        "-an",
        str(out_p),
    ]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        for f in frames:
            proc.stdin.write(f.tobytes())
        stdout, stderr = proc.communicate()
    except Exception as e:
        proc.kill()
        raise RuntimeError(f"Failed piping raw frames to ffmpeg: {e}") from e

    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg write_frames_to_mp4 exited with code {proc.returncode}:\n{stderr.decode(errors='replace')}"
        )

    return out_p
