"""Common utilities and schemas for ST01-ST13 smoke test suite.

Enforces Law 1 (anti-fabrication):
- When an API key or environment dependency is missing, latency_ms MUST be None/null,
  is_fixture MUST be True, and live_verified MUST be False.
- Live verified tests MUST record real measured execution time.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class SmokeResult:
    """Standardized result for Kodiac smoke tests ST01–ST13."""

    test_id: str
    name: str
    ok: bool
    status: str
    is_fixture: bool
    live_verified: bool
    latency_ms: float | None
    notes: str
    evidence_path: str | None = None

    def __post_init__(self) -> None:
        # Enforce Law 1 guard strictly
        if self.is_fixture and self.latency_ms is not None:
            raise ValueError(
                f"Law 1 violation in {self.test_id}: latency_ms must be None when is_fixture=True (got {self.latency_ms})"
            )
        if self.live_verified and self.latency_ms is None:
            raise ValueError(
                f"Invalid result in {self.test_id}: live_verified=True requires measured latency_ms"
            )

    def to_dict(self) -> dict:
        return asdict(self)

    def write_artifact(self, output_path: Path | str | None = None) -> Path:
        if output_path is None:
            output_path = Path("artifacts/p01/smoke") / f"{self.test_id.lower()}.json"
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return p


def generate_synthetic_clip(
    output_path: Path | str = "artifacts/p01/smoke/synthetic_50f.mp4",
    num_frames: int = 50,
    fps: int = 10,
    width: int = 320,
    height: int = 240,
) -> Path:
    """Generate a 50-frame synthetic H.264 yuv420p red/green block test clip.

    Guarantees deterministic, valid MP4 video without external downloads.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_size > 0:
        return out

    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        cmd = [
            ffmpeg_bin,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={width}x{height}:d={num_frames/fps}:r={fps}",
            "-vf",
            "drawbox=x=40:y=40:w=60:h=60:color=red@1:t=fill,drawbox=x=160:y=100:w=60:h=60:color=green@1:t=fill",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-frames:v",
            str(num_frames),
            str(out.resolve()),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0 and out.exists():
            return out

    # Fallback to OpenCV VideoWriter
    import cv2
    import numpy as np

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(str(out.resolve()), fourcc, float(fps), (width, height))
    for i in range(num_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        # Red block in BGR (0, 0, 255)
        cv2.rectangle(frame, (40, 40), (100, 100), (0, 0, 255), -1)
        # Green block in BGR (0, 255, 0)
        cv2.rectangle(frame, (160 + (i % 10), 100), (220 + (i % 10), 160), (0, 255, 0), -1)
        vw.write(frame)
    vw.release()

    return out
