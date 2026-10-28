# T03: Modal SAM 3.1 Backend, Re-ID Engine, Track Assembly & Proof Arms
phase: P03 · owner: IMPL-3 · status: DONE
plan_ref: IMPLEMENTATION_PLAN.md P03.S03, P03.S06, P03.S08, P03.S14
depends_on: [] · blocks: [P03-GATE]
owns_paths: [
  "src/Kodiac_robotics/segment/modal_backend.py",
  "src/Kodiac_robotics/segment/reid.py",
  "src/Kodiac_robotics/segment/tracks.py",
  "src/Kodiac_robotics/proof/arms.py",
  "modal/sam31.py",
  "tests/segment/test_modal.py",
  "tests/segment/test_reid.py",
  "tests/segment/test_tracks.py",
  "tests/segment/test_quality.py"
]
reads_only: [
  "src/Kodiac_robotics/contracts/core.py",
  "tests/fixtures/clips/**",
  "ARCHITECTURE.md"
]
timebox: 90 min (3-strike rule applies)

## Micro-Plan
1. Recon & Setup: Verified frozen contracts, dependencies (OpenCV, NumPy, PyArrow), and golden fixture clips.
2. Modal SAM 3.1 Service (`modal/sam31.py`): Implement App `Kodiac-sam31` with L4 GPU, `use_fa3=False`, `torch.bfloat16`, 50-frame chunking, `torch.cuda.empty_cache()`, `scaledown_window=60`, `handle_request`/`handle_stream_request`, and batch `track_many`.
3. Modal Client (`src/Kodiac_robotics/segment/modal_backend.py`): Implement `ModalSamBackend` conforming to `Segmenter` protocol with input validation, sliding window chunking, and deterministic offline double adhering to `rle_size == (clip.height, clip.width)`.
4. Re-ID Engine (`src/Kodiac_robotics/segment/reid.py`): Implement `ReIdEngine` with `compute_eroded_hsv_hist` (`cv2.erode` 5x5 kernel), $L_2$ centroid velocity continuity, categorical Hue gating ($\Delta \text{Hue} > 60^\circ \to \infty$ penalty), and Hungarian assignment. Strictly reject destructive mask subtraction.
5. Track Assembler (`src/Kodiac_robotics/segment/tracks.py`): Implement `assemble_tracks` with temporal window stitching, cyclic consistency validation (`IoU(fwd, bwd) < 0.70` confidence degradation), and $\le 16$ objects per call API limit enforcement. Implement batch `track_many` dispatcher.
6. Proof Benchmark Arms (`src/Kodiac_robotics/proof/arms.py`): Implement `assemble_proof_arms` grouping the 10 pre-registered benchmark arms per `PREREGISTRATION.md`.
7. Test Suite (`tests/segment/`):
   - `test_modal.py`: Modal backend validation, chunking, and mock fallback.
   - `test_reid.py`: Eroded-core HSV extraction, red vs green cube swap prevention under proximity.
   - `test_tracks.py`: Window stitching, cyclic consistency, $\le 16$ objects limit.
   - `test_quality.py`: Tracking quality on golden fixture clips, zero ID swaps, cyclic consistency.
8. Full verification: `uv run pytest` offline and `ruff check` clean. Report and commit.

## Mission
Deliver the heavy-compute and spatio-temporal assembly infrastructure:
1. Modal self-hosted SAM 3.1 service (`modal/sam31.py`) and client (`segment/modal_backend.py`) on L4 GPU (`nvidia-l4`, `use_fa3=False`, `torch.bfloat16`), bounded to 50-frame sliding windows with `torch.cuda.empty_cache()` to prevent CUDA OOMs and scale-to-zero (`scaledown_window=60`).
2. Robust `ReIdEngine` in `src/Kodiac_robotics/segment/reid.py` combining eroded-core HSV color histograms (`cv2.erode`), $L_2$ centroid velocity continuity, and coarse categorical Hue gating ($\Delta \text{Hue} > 60^\circ$ infinite penalty for distinct colored blocks), rejecting destructive mask subtraction.
3. Spatio-temporal track assembler (`segment/tracks.py`) merging forward and backward tracking windows, computing cyclic consistency `IoU(fwd, bwd)`, and enforcing the $\le 16$ objects per call API limit.
4. Proof benchmark arm episode partitioner (`src/Kodiac_robotics/proof/arms.py`) assembling accepted episode splits for the 10 benchmark arms per pre-registered protocols.
5. Quality verification suite (`tests/segment/test_quality.py`) measuring mask IoU, ID stability (zero block swaps on StackCube), and cyclic tracking consistency.

## Interface Contracts (FROZEN)

```python
from pathlib import Path
from typing import Any, Literal
import numpy as np
from Kodiac_robotics.contracts.core import Clip, ObjMask, Track

# segment/modal_backend.py
class ModalSamBackend:
    def __init__(self, app_name: str = "Kodiac-sam31"): ...
    def segment_frames(self, clip: Clip, frames: list[int], prompts: dict[str, list[str]]) -> dict[str, Track]: ...
    def track(self, clip: Clip, f0: int, f1: int, seeds: dict[str, ObjMask], direction: Literal["forward", "backward", "both"]) -> dict[str, Track]: ...

# segment/reid.py
class ReIdEngine:
    """Spatio-temporal re-identification across keyframes and tracking windows."""
    def __init__(self, hist_bins: tuple[int, int] = (16, 8)): ...
    def compute_eroded_hsv_hist(self, frame_bgr: np.ndarray, mask: np.ndarray, erode_ksize: int = 5) -> np.ndarray: ...
    def match_masks(
        self,
        candidates: list[ObjMask],
        targets: dict[str, ObjMask],
        frame_bgr: np.ndarray,
    ) -> dict[str, ObjMask]: ...

# segment/tracks.py
def assemble_tracks(
    window_cuts: list[Any],
    raw_tracks: list[dict[str, Track]],
    reid: ReIdEngine,
) -> dict[str, Track]: ...

def track_many(
    jobs: list[dict[str, Any]],
    backend: Literal["modal", "hosted", "fixture"] = "modal",
) -> list[dict[str, Track]]: ...

# proof/arms.py
def assemble_proof_arms(manifest_path: Path | str, labels_dir: Path | str) -> dict[str, list[str]]: ...
```

## Steps
1. **`modal/sam31.py` & `src/Kodiac_robotics/segment/modal_backend.py`:** Define Modal App `Kodiac-sam31` with `Image.debian_slim().pip_install(...)` running on `gpu="L4"`. Implement 50-frame chunking, `torch.cuda.empty_cache()`, and `handle_stream_request`. Implement client wrapper with mock/offline fallback.
2. **`src/Kodiac_robotics/segment/reid.py`:** Implement `ReIdEngine`. In `compute_eroded_hsv_hist`, erode binary mask by 5x5 kernel before extracting HSV pixels. In `match_masks`, compute spatial distance $\|c_1 - c_2\|_2$; apply infinite cost if categorical Hue difference $> 60^\circ$ for rigid objects.
3. **`src/Kodiac_robotics/segment/tracks.py`:** Implement `assemble_tracks` reconciling multiple temporal windows, assigning persistent object IDs (`obj_id`), validating cyclic consistency, and enforcing $\le 16$ objects per frame.
4. **`src/Kodiac_robotics/proof/arms.py`:** Implement `assemble_proof_arms` grouping episodes by benchmark arm (Arm 1 Baseline Single-Pass, Arm 2 Robometer-4B, Arm 3 TOPReward, Arm 4 Ground Truth, Arm 5 Kodiac-Kinematic, Arm 6 Kodiac-SAM31, etc.) per pre-registered acceptance thresholds.
5. **Unit & Quality Tests:**
   - `tests/segment/test_modal.py`: Test Modal client parameter validation and mock fallback.
   - `tests/segment/test_reid.py`: Test eroded-core HSV extraction, test that red and green blocks do not swap IDs despite close proximity.
   - `tests/segment/test_tracks.py`: Test multi-window stitching and cyclic consistency flag.
   - `tests/segment/test_quality.py`: Test tracking accuracy on fixture clips; assert zero block ID swaps.

## Definition of Done
- [x] Behavior: Modal SAM backend, Re-ID engine, track assembly, and proof arms functioning.
- [x] Tests: `uv run pytest tests/segment/test_modal.py tests/segment/test_reid.py tests/segment/test_tracks.py tests/segment/test_quality.py -v` passes 100% green offline.
- [x] No stubs or TODOs in owned paths.
- [x] Staged and committed only owned paths with message `feat(p03/t03): modal sam backend, reid engine, track assembly and proof arms`.

## Report
- **What was built:**
  - `modal/sam31.py`: Modal App `Kodiac-sam31` configured for L4 GPU (`use_fa3=False`, `torch.bfloat16`, 50-frame chunking, `torch.cuda.empty_cache()`, `scaledown_window=60`, `handle_request`/`handle_stream_request`, `track_many` batch runner, and vectorized NumPy RLE).
  - `src/Kodiac_robotics/segment/modal_backend.py`: Client for `Kodiac-sam31` implementing `Segmenter` protocol, strict parameter validation (bounds, <= 16 objects, direction), and deterministic offline fallback adhering to `rle_size == (clip.height, clip.width)`.
  - `src/Kodiac_robotics/segment/reid.py`: `ReIdEngine` with eroded-core HSV histograms (`cv2.erode` 5x5 kernel), circular mean dominant Hue, coarse categorical Hue gating ($\Delta \text{Hue} > 60^\circ \to \infty$ penalty), $L_2$ centroid velocity continuity, and Hungarian matching with zero block ID swaps. Strictly non-destructive.
  - `src/Kodiac_robotics/segment/tracks.py`: Spatio-temporal track assembler (`assemble_tracks`) and batch dispatcher (`track_many`), merging multi-window tracks, evaluating forward-backward cyclic consistency (IoU < 0.70 flags score < 0.50), and enforcing the <= 16 objects API limit.
  - `src/Kodiac_robotics/proof/arms.py`: Benchmark arm episode partitioner (`assemble_proof_arms`) grouping accepted episode splits for the 10 pre-registered benchmark arms per `PREREGISTRATION.md`.
  - Unit & Quality test suite in `tests/segment/test_modal.py`, `tests/segment/test_reid.py`, `tests/segment/test_tracks.py`, `tests/segment/test_quality.py`.
- **Evidence:**
  - `uv run pytest tests/segment/test_modal.py tests/segment/test_reid.py tests/segment/test_tracks.py tests/segment/test_quality.py -v`: 22 passed in 25s (100% green).
  - Full test suite: 156 passed in 70s.
  - `uv run ruff check .`: clean (All checks passed).
  - Zero TODOs and zero NotImplemented in owned paths.
- **Deviations:** None.
- **Known limits:** Live model execution on Modal depends on user-provided Modal token and gated HF SAM 3.1 access; deterministic offline fixture doubles and mock fallbacks run seamlessly.
- **Time spent:** ~45 min.
