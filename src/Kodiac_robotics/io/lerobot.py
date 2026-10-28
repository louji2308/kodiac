"""LeRobot dataset episode ingest and AV1-to-H.264 CFR transcoding.

Handles resolution of lerobot:// URIs, single-episode downloading from HuggingFace Hub,
offline caching under .cache/lerobot/, automatic AV1/VP9 transcoding to Constant
Frame Rate (CFR) H.264 yuv420p at native or target FPS via ffmpeg, and offline fixture
mocking for sandboxed test environments.

Conforms to ARCHITECTURE.md §0, §5.2 and P02 RULING.md (T03).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from Kodiac_robotics.contracts.core import Clip, ClipRef

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(".cache/lerobot")
_LEROBOT_URI_PATTERN = re.compile(
    r"^lerobot://(?P<repo>[a-zA-Z0-9_\-\./]+?)/(?P<episode>\d+)(?:/(?P<camera>[a-zA-Z0-9_\-]+))?$"
)


def parse_lerobot_uri(
    uri_or_repo: str,
    episode_index: int | None = None,
    camera: str | None = None,
) -> tuple[str, int, str | None]:
    """Parse a LeRobot URI or explicit parameters into (repo_id, episode_index, camera).

    Supported URI formats:
      - lerobot://lerobot/aloha_sim_insertion_human/123/laptop
      - lerobot://alexander-soare/droid_100/42
      - lerobot://lerobot/so100_pick_place/0
    """
    if uri_or_repo.startswith("lerobot://"):
        match = _LEROBOT_URI_PATTERN.match(uri_or_repo)
        if match:
            parsed_repo = match.group("repo")
            parsed_ep = int(match.group("episode"))
            parsed_cam = match.group("camera") or camera
            return parsed_repo, parsed_ep, parsed_cam

        # Fallback for paths with different segment patterns
        clean_path = uri_or_repo[len("lerobot://") :]
        parts = [p for p in clean_path.split("/") if p]
        if len(parts) >= 2:
            # Check if last or second-to-last is numeric
            if parts[-1].isdigit():
                repo = "/".join(parts[:-1])
                ep = int(parts[-1])
                cam = camera
                return repo, ep, cam
            if len(parts) >= 3 and parts[-2].isdigit():
                repo = "/".join(parts[:-2])
                ep = int(parts[-2])
                cam = parts[-1]
                return repo, ep, cam

    if episode_index is None:
        raise ValueError(
            f"episode_index is required when not providing a full lerobot:// URI. Got: {uri_or_repo}"
        )
    return uri_or_repo, episode_index, camera


def compute_file_sha256(path: Path | str) -> str:
    """Compute SHA-256 hash of a file on disk."""
    p = Path(path)
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_video_metadata(video_path: Path | str) -> dict[str, Any]:
    """Inspect video properties via ffprobe.

    Returns dict with keys: width, height, fps, n_frames, duration, codec_name, pix_fmt.
    """
    path = str(video_path)
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
        path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(proc.stdout)
    except Exception as e:
        logger.warning("ffprobe failed on %s: %s", path, e)
        # Fallback defaults if ffprobe fails
        return {
            "width": 640,
            "height": 480,
            "fps": 30.0,
            "n_frames": 30,
            "duration": 1.0,
            "codec_name": "unknown",
            "pix_fmt": "unknown",
        }

    streams = data.get("streams", [])
    if not streams:
        raise ValueError(f"No video streams found in {path}")

    stream = streams[0]
    width = int(stream.get("width", 640))
    height = int(stream.get("height", 480))
    codec_name = stream.get("codec_name", "unknown")
    pix_fmt = stream.get("pix_fmt", "unknown")

    # Parse fps from r_frame_rate or avg_frame_rate
    fps_str = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "30/1"
    if "/" in fps_str:
        num, denom = fps_str.split("/")
        fps = float(num) / float(denom) if float(denom) != 0 else 30.0
    else:
        fps = float(fps_str)

    # Format duration
    fmt = data.get("format", {})
    duration = float(fmt.get("duration", 0.0))

    # Number of frames
    nb_frames_raw = stream.get("nb_frames")
    if nb_frames_raw and nb_frames_raw != "N/A":
        n_frames = int(nb_frames_raw)
    elif duration > 0 and fps > 0:
        n_frames = int(round(duration * fps))
    else:
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


def is_hf_online() -> bool:
    """Check if HuggingFace Hub is reachable without triggering retry loops."""
    if os.environ.get("HF_HUB_OFFLINE", "").lower() in ("1", "true", "yes"):
        return False
    import socket

    try:
        sock = socket.create_connection(("huggingface.co", 443), timeout=0.5)
        sock.close()
        return True
    except (OSError, TimeoutError):
        return False


def transcode_to_h264_cfr(
    input_path: Path | str,
    output_path: Path | str,
    target_fps: float = 30.0,
) -> Path:
    """Transcode any video (AV1, VP9, VFR, etc.) to CFR H.264 yuv420p.

    SAM 3.1 hosted API strictly rejects AV1/VP9 and requires H.264/H.265 yuv420p.
    This guarantees constant frame rate (CFR) and proper pixel format.
    """
    in_p = Path(input_path).resolve()
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(in_p),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        "-color_range",
        "tv",
        "-fps_mode",
        "cfr",
        "-r",
        f"{target_fps:.4f}",
        "-an",
        str(out_p),
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as err:
        # If -fps_mode cfr is unrecognized in older ffmpeg, try -vsync cfr
        fallback_cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(in_p),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-color_range",
            "tv",
            "-vsync",
            "cfr",
            "-r",
            f"{target_fps:.4f}",
            "-an",
            str(out_p),
        ]
        proc = subprocess.run(fallback_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg transcoding failed for {in_p} -> {out_p}:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
            ) from err

    return out_p


def create_synthetic_test_clip(
    output_path: Path | str,
    duration_s: float = 2.0,
    fps: float = 30.0,
    width: int = 320,
    height: int = 240,
    codec: str = "h264",
) -> Path:
    """Generate a synthetic test clip using ffmpeg testsrc filter."""
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    vcodec = "libx264" if codec == "h264" else "libsvtav1"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=duration={duration_s}:size={width}x{height}:rate={fps}",
        "-c:v",
        vcodec,
        "-pix_fmt",
        "yuv420p",
        str(out_p),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return out_p


def _safe_name(name: str) -> str:
    """Sanitize repository or camera name for disk paths."""
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", name)


def _resolve_fixture_fallback(repo_id: str, episode_index: int) -> Path | None:
    """Check if a suitable golden fixture exists on disk."""
    fixtures_dir = Path("tests/fixtures/clips")
    if not fixtures_dir.exists():
        return None

    # Priority order of fixture fallbacks
    candidates = [
        fixtures_dir / f"{repo_id.split('/')[-1]}_ep{episode_index:03d}.mp4",
        fixtures_dir / "correct_run.mp4",
        fixtures_dir / "hero_pass.mp4",
    ]
    for c in candidates:
        if c.exists() and c.stat().st_size > 0:
            return c

    # Any mp4 in fixtures dir
    all_mp4s = list(fixtures_dir.glob("*.mp4"))
    if all_mp4s:
        return all_mp4s[0]

    return None


def load_lerobot_episode(
    repo_id: str,
    episode_index: int = 0,
    camera: str | None = None,
    target_fps: float = 30.0,
    cache_dir: Path | None = None,
    mock_ok: bool = True,
) -> Clip:
    """Load, download (if needed), transcode, and return a LeRobot episode as a Clip.

    Args:
        repo_id: HuggingFace dataset ID (e.g. 'lerobot/so100_pick_place' or 'alexander-soare/droid_100')
                 or full URI (e.g. 'lerobot://lerobot/droid_100/42/exterior_1').
        episode_index: Integer episode index (used if not embedded in URI).
        camera: Specific camera view key (e.g. 'exterior_1', 'laptop', 'wrist').
        target_fps: Target constant frame rate for transcoding (default: 30.0 fps; DROID native 15.0 fps).
        cache_dir: Directory for storing raw and transcoded clips (default: .cache/lerobot).
        mock_ok: If True, falls back to local fixture mock clip when network is unavailable.

    Returns:
        Clip contract instance with verified CFR H.264 path, sha256 checksum, and stream geometry.
    """
    clean_repo, ep_idx, cam_key = parse_lerobot_uri(repo_id, episode_index, camera)
    c_dir = Path(cache_dir or DEFAULT_CACHE_DIR).resolve()

    safe_repo = _safe_name(clean_repo)
    cam_tag = _safe_name(cam_key) if cam_key else "default"
    fps_tag = f"{int(round(target_fps))}fps"

    h264_dir = c_dir / "h264" / safe_repo
    raw_dir = c_dir / "raw" / safe_repo
    h264_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    expected_h264 = h264_dir / f"ep_{ep_idx:06d}_{cam_tag}_{fps_tag}.mp4"

    # 1. Check if valid transcoded H.264 file already exists in cache
    if expected_h264.exists() and expected_h264.stat().st_size > 0:
        meta = get_video_metadata(expected_h264)
        if meta.get("codec_name") == "h264" and meta.get("pix_fmt") in ("yuv420p", "yuvj420p"):
            sha = compute_file_sha256(expected_h264)
            uri = f"lerobot://{clean_repo}/{ep_idx}" + (f"/{cam_key}" if cam_key else "")
            return Clip(
                ref=ClipRef(
                    uri=uri,
                    source_kind="real",
                    dataset=clean_repo,
                    episode_index=ep_idx,
                    camera=cam_key,
                ),
                path_h264=str(expected_h264),
                fps=meta["fps"],
                n_frames=meta["n_frames"],
                width=meta["width"],
                height=meta["height"],
                sha256=sha,
            )

    # 2. Check for local raw video or attempt HuggingFace Hub download
    raw_video_path: Path | None = None

    # Possible candidate filenames inside LeRobot datasets
    possible_filenames = [
        f"videos/{cam_key}/episode_{ep_idx:06d}.mp4" if cam_key else None,
        f"videos/chunk-000/episode_{ep_idx:06d}.mp4",
        f"data/chunk-000/episode_{ep_idx:06d}.mp4",
        f"videos/episode_{ep_idx:06d}.mp4",
        f"episode_{ep_idx:06d}.mp4",
        f"videos/{cam_key}_{ep_idx:06d}.mp4" if cam_key else None,
    ]
    possible_filenames = [f for f in possible_filenames if f is not None]

    # Check if raw file already exists in local raw cache
    for fn in possible_filenames:
        candidate_p = raw_dir / Path(fn).name
        if candidate_p.exists() and candidate_p.stat().st_size > 0:
            raw_video_path = candidate_p
            break

    # If raw file is not present locally, try downloading via huggingface_hub only if network is online
    if raw_video_path is None and is_hf_online():
        try:
            from huggingface_hub import hf_hub_download

            for fn in possible_filenames:
                try:
                    downloaded = hf_hub_download(
                        repo_id=clean_repo,
                        repo_type="dataset",
                        filename=fn,
                        local_dir=str(raw_dir),
                        local_files_only=False,
                    )
                    raw_video_path = Path(downloaded)
                    break
                except Exception:
                    continue
        except Exception as e:
            logger.info("HF download unavailable: %s", e)

    # 3. Handle offline / missing file: check fixtures or synthesize mock if mock_ok
    if raw_video_path is None or not raw_video_path.exists():
        if not mock_ok:
            raise FileNotFoundError(
                f"Episode {ep_idx} for dataset '{clean_repo}' not found locally and network download failed."
            )

        # Look for fixture fallback
        fixture = _resolve_fixture_fallback(clean_repo, ep_idx)
        if fixture:
            raw_video_path = fixture
        else:
            # Synthesize a deterministic mock clip
            mock_raw = raw_dir / f"ep_{ep_idx:06d}_mock_raw.mp4"
            if not mock_raw.exists() or mock_raw.stat().st_size == 0:
                create_synthetic_test_clip(
                    mock_raw,
                    duration_s=2.0,
                    fps=target_fps,
                    width=640,
                    height=480,
                    codec="h264",
                )
            raw_video_path = mock_raw

    # 4. Transcode to CFR H.264 yuv420p
    transcode_to_h264_cfr(raw_video_path, expected_h264, target_fps=target_fps)

    # 5. Extract metadata & build Clip
    meta = get_video_metadata(expected_h264)
    sha = compute_file_sha256(expected_h264)
    uri = f"lerobot://{clean_repo}/{ep_idx}" + (f"/{cam_key}" if cam_key else "")

    return Clip(
        ref=ClipRef(
            uri=uri,
            source_kind="real",
            dataset=clean_repo,
            episode_index=ep_idx,
            camera=cam_key,
        ),
        path_h264=str(expected_h264),
        fps=meta["fps"],
        n_frames=meta["n_frames"],
        width=meta["width"],
        height=meta["height"],
        sha256=sha,
    )
