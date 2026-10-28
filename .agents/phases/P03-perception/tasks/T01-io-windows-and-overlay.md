# T01: Universal Video IO Core, Window Padding & Perception Debug Overlay
phase: P03 · owner: IMPL-1 · status: DONE
plan_ref: IMPLEMENTATION_PLAN.md P03.S01, P03.S09
depends_on: [] · blocks: [P03-GATE]
owns_paths: [
  "src/Kodiac_robotics/io/clip.py",
  "src/Kodiac_robotics/io/transcode.py",
  "src/Kodiac_robotics/io/windows.py",
  "src/Kodiac_robotics/render/overlay.py",
  "tests/io/test_clip.py",
  "tests/io/test_windows.py",
  "tests/render/test_overlay.py"
]
reads_only: [
  "src/Kodiac_robotics/contracts/core.py",
  "tests/fixtures/clips/**",
  "ARCHITECTURE.md"
]
timebox: 90 min (3-strike rule applies)

## Micro-plan (IMPL-1)
1. Step 1: Implement `src/Kodiac_robotics/io/transcode.py` (ffmpeg subprocess wrappers, CFR H.264 yuv420p, pad even dimensions, probe metadata, write_frames).
2. Step 2: Implement `src/Kodiac_robotics/io/clip.py` (`open_clip` resolving paths/URIs/ClipRefs, ffprobe metadata extraction, SHA-256 verification) & `tests/io/test_clip.py`.
3. Step 3: Implement `src/Kodiac_robotics/io/windows.py` (`cut_window` symmetric padding logic, `pack_frames` repeating 3x at 10 fps) & `tests/io/test_windows.py`.
4. Step 4: Implement `src/Kodiac_robotics/render/overlay.py` (`OverlayRenderer` with alpha mask blend, 2px contours, crosshairs, bottom anchors beta, watermark banner, render_video) & `tests/render/test_overlay.py`.
5. Step 5: Verify all tests offline with `uv run --no-sync pytest tests/io/ tests/render/ -v`, ensure `ruff check` is clean, update task card report, commit changes and notify ORCH.

## Mission
Deliver bulletproof, zero-external-codec video IO and normalization for the entire perception pipeline. Normalize arbitrary video sources (sim runs, LeRobot datasets, files) into CFR H.264 `yuv420p` using ffmpeg CLI. Symmetrically pad short query windows to meet SAM 3.1's mandatory $\ge 50$ frame billing minimum while preserving exact query bounds. Render high-contrast, anti-aliased perception debug overlays (masks, bounding boxes, centroid crosshairs, and bottom anchors $\beta$) at native resolution.

## Interface Contracts (FROZEN)

```python
from pathlib import Path
from typing import Any, Literal
import numpy as np
from pydantic import BaseModel
from Kodiac_robotics.contracts.core import Clip, ClipRef, ObjMask, Track

class WindowCut(BaseModel):
    """Padded video segment meeting SAM 3.1 50-frame minimum constraint."""
    path: Path
    valid_f0: int              # Requested start frame index in parent clip
    valid_f1: int              # Requested end frame index in parent clip
    padded_f0: int             # Actual start frame index after symmetric padding
    padded_f1: int             # Actual end frame index after symmetric padding
    n_frames: int              # Total frames in cut video (>= 50)
    fps: float
    parent_sha256: str

class PackedKeyframes(BaseModel):
    """Sparse keyframes packed into contiguous MP4 for batch API prompting."""
    path: Path
    original_indices: list[int]
    index_map: dict[int, int]  # packed_frame_idx -> original_frame_idx
    n_frames: int

def open_clip(ref: str | Path | ClipRef) -> Clip:
    """Normalize any video input to CFR H.264 yuv420p with even dimensions via ffmpeg."""
    ...

def cut_window(clip: Clip, f0: int, f1: int, min_frames: int = 50) -> WindowCut:
    """Extract frame window [f0, f1], padding symmetrically to >= min_frames."""
    ...

def pack_frames(clip: Clip, indices: list[int]) -> PackedKeyframes:
    """Assemble sparse keyframes into an MP4 (with 3-frame repeated duration per keyframe at 10 fps)."""
    ...

class OverlayRenderer:
    """Perception debug overlay renderer (masks, bboxes, anchors)."""
    def __init__(self, alpha: float = 0.35, line_width: int = 2): ...
    def render_frame(
        self,
        frame_bgr: np.ndarray,
        masks: dict[str, ObjMask],
        color_palette: dict[str, tuple[int, int, int]] | None = None,
        bottom_anchors: dict[str, tuple[float, float]] | None = None,
        watermark: str | None = None,
    ) -> np.ndarray: ...
    def render_video(
        self,
        clip: Clip,
        tracks: dict[str, Track],
        output_path: Path | str,
        color_palette: dict[str, tuple[int, int, int]] | None = None,
        watermark: str | None = None,
    ) -> Path: ...
```

## Steps
1. **`src/Kodiac_robotics/io/transcode.py`:** Wrap `ffmpeg` subprocess calls with explicit CFR filters (`-vsync cfr -r {fps}`), pixel format (`-pix_fmt yuv420p`), codec (`-c:v libx264 -crf 18 -preset fast`), and dimension padding filter (`-vf "pad=ceil(iw/2)*2:ceil(ih/2)*2"`).
2. **`src/Kodiac_robotics/io/clip.py`:** Implement `open_clip(ref)`. Resolve local paths, URIs, and verify file SHA-256. Probe duration, frame count, width, height, and FPS via `ffprobe`.
3. **`src/Kodiac_robotics/io/windows.py`:** Implement `cut_window` and `pack_frames`. When window duration $f_1 - f_0 + 1 < \text{min\_frames}$, symmetrically expand backwards and forwards, clamping to $[0, N-1]$. In `pack_frames`, assemble keyframes repeating each frame 3 times to preserve temporal cross-attention stability in SAM 3.1.
4. **`src/Kodiac_robotics/render/overlay.py`:** Implement `OverlayRenderer`. Decode RLE masks, apply alpha blending with distinct high-contrast hues per object role (e.g., Red for gripper, Green for target block, Blue for container), draw 2px contours, centroid crosshair markers, and bottom anchor ($\beta$) circles. If `watermark` string is provided, render high-contrast text banner across top.
5. **Unit Tests:**
   - `tests/io/test_clip.py`: Test opening and transcoding local clips, verify CFR 30 fps, even dimensions, SHA-256 matching.
   - `tests/io/test_windows.py`: Test `cut_window` symmetric padding logic, boundaries clamp at start/end of video, verify $N \ge 50$. Test `pack_frames` frame count and bidirectional index mapping.
   - `tests/render/test_overlay.py`: Test single-frame and video overlay generation against synthetic masks, assert output frame shapes and pixel modifications.

## Definition of Done
- [x] Behavior: `open_clip`, `cut_window`, `pack_frames`, and `OverlayRenderer` operational with zero C-library dependencies (ffmpeg subprocess + OpenCV).
- [x] Tests: `uv run pytest tests/io/ tests/render/ -v` passes completely green (42/42 tests pass).
- [x] Lint: `uv run --no-sync ruff check src/Kodiac_robotics/io/ src/Kodiac_robotics/render/ tests/io/ tests/render/` clean.
- [x] No stubs or TODOs in owned paths.
- [x] Staged and committed only owned paths with message `feat(p03/t01): universal video io, windowing and debug overlay`.

## Report (filled by owner at DONE)
- **What was built:**
  1. `src/Kodiac_robotics/io/transcode.py`: ffmpeg & ffprobe CLI subprocess wrappers (`probe_video`, `transcode_to_cfr_h264`, `cut_video_frames`, `write_frames_to_mp4`, `compute_file_sha256`) enforcing CFR H.264 `yuv420p` with dimension padding `pad=ceil(iw/2)*2:ceil(ih/2)*2`.
  2. `src/Kodiac_robotics/io/clip.py`: `open_clip(ref)` resolving `str`, `Path`, `file://` URIs, `lerobot://` URIs, and `ClipRef` instances, verifying SHA-256 and stream geometry.
  3. `src/Kodiac_robotics/io/windows.py`: `cut_window` with exact symmetric padding to $\ge 50$ frames, clamping at video boundaries $[0, N-1]$, and `pack_frames` duplicating keyframes 3x at 10 fps with bidirectional index mapping for SAM 3.1 temporal cross-attention stability.
  4. `src/Kodiac_robotics/render/overlay.py`: `OverlayRenderer` with `render_frame` and `render_video`, supporting RLE mask alpha blending, 2px anti-aliased contours, centroid crosshair markers, bottom anchor ($\beta$) circles, role-based high-contrast palettes, and top banner watermark.
  5. Test suites in `tests/io/test_clip.py` (6 tests), `tests/io/test_windows.py` (8 tests), and `tests/render/test_overlay.py` (5 tests).
- **Evidence:**
  - `uv run --no-sync pytest tests/io/ tests/render/ -v`: 42/42 tests passed in 11.93s.
  - `uv run --no-sync ruff check src/Kodiac_robotics/io/ src/Kodiac_robotics/render/ tests/io/ tests/render/`: 0 errors.
  - Zero `TODO` or `NotImplemented` entries across all owned files.
- **Deviations:** None. All contracts followed strictly as frozen.
- **Known limits:** Clips with total parent frame count $N < 50$ will clamp to full parent bounds $[0, N-1]$ (per contract specification); standard robotic clips in practice are $\ge 50$ frames (e.g. 90-150 frames).
- **Time spent:** ~35 minutes.
