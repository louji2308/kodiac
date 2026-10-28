# T02: Hosted SAM 3.1 Backend, Fixtures, Prompts, RLE Codec & Benchmark
phase: P03 · owner: IMPL-2 · status: DONE
plan_ref: IMPLEMENTATION_PLAN.md P03.S02, P03.S04, P03.S05, P03.S07
depends_on: [] · blocks: [P03-GATE]
owns_paths: [
  "src/Kodiac_robotics/segment/api.py",
  "src/Kodiac_robotics/segment/fixture.py",
  "src/Kodiac_robotics/segment/prompts.py",
  "src/Kodiac_robotics/segment/rle.py",
  "scripts/bench_sam.py",
  "scripts/record_fixtures.py",
  "tests/segment/test_api.py",
  "tests/segment/test_fixture.py",
  "tests/segment/test_prompts.py",
  "tests/segment/test_rle.py"
]
reads_only: [
  "src/Kodiac_robotics/contracts/core.py",
  "tests/fixtures/clips/**",
  "ARCHITECTURE.md"
]
timebox: 90 min (3-strike rule applies)

## Micro-plan (IMPL-2)
1. Step 1: Implement `src/Kodiac_robotics/segment/rle.py` (COCO RLE encode/decode, box-local translation, area calculation) & `tests/segment/test_rle.py`. Verify with pytest.
2. Step 2: Implement `src/Kodiac_robotics/segment/prompts.py` (manipulator role prompt sets, embodiment detection) & `tests/segment/test_prompts.py`. Verify with pytest.
3. Step 3: Implement `src/Kodiac_robotics/segment/api.py` (Meta SAM 3.1 streaming adapter, prompt isolation, tenacity retry, content-hash disk cache) & `tests/segment/test_api.py`. Verify with pytest.
4. Step 4: Implement `src/Kodiac_robotics/segment/fixture.py`, dual-mode `scripts/record_fixtures.py` (`--synthetic` / `--live`), and `tests/segment/test_fixture.py`. Run `python scripts/record_fixtures.py --synthetic` to generate golden tracks in `tests/fixtures/tracks/`.
5. Step 5: Implement `scripts/bench_sam.py` to benchmark 6-keyframe bisect vs 10 fps subsampling and output `artifacts/p03/sam_bench.json`.
6. Step 6: Full offline test suite verification, ruff check, task card report completion, git commit and notification to ORCH.

## Mission
Implement the core perception components required for online inference, offline determinism, and empirical benchmark gating:
1. Zero-dependency pure-Python / NumPy COCO RLE codec (`segment/rle.py`) with box-local translation (`box_local_to_full_frame_rle`).
2. Meta SAM 3.1 streaming client (`segment/api.py`) strictly isolating text prompts for keyframe segmentation (`segment_frames`) from box prompts for temporal tracking (`track`), wrapped in tenacity retry and content-hash caching.
3. Deterministic fixture backend (`segment/fixture.py`) stamping `is_fixture: true` and `[FIXTURE REPLAY]` badge to uphold Law 1.
4. Prompt library and embodiment auto-detection (`segment/prompts.py`).
5. Empirical latency and cost benchmark runner (`scripts/bench_sam.py`) evaluating 6-keyframe bisect vs. 10 fps subsampled pass, generating `artifacts/p03/sam_bench.json` to ground ADR-0008.

## Interface Contracts (FROZEN)

```python
from pathlib import Path
from typing import Any, Literal
import numpy as np
from Kodiac_robotics.contracts.core import Clip, ObjMask, Track

# segment/rle.py
def mask_to_rle(mask: np.ndarray) -> str:
    """Encode binary 2D uint8/bool mask to COCO compressed RLE string."""
    ...

def rle_to_mask(rle: str, shape: tuple[int, int]) -> np.ndarray:
    """Decode COCO compressed RLE string to 2D uint8 binary mask."""
    ...

def box_local_to_full_frame_rle(
    local_rle: str,
    box_xyxy: tuple[float, float, float, float],
    full_shape: tuple[int, int],
) -> str:
    """Translate SAM box-local RLE mask to full-frame canvas coordinates."""
    ...

def rle_area(rle: str, shape: tuple[int, int]) -> int:
    """Compute mask pixel area directly from RLE string."""
    ...

# segment/api.py & segment/fixture.py
class HostedSamBackend:
    def __init__(self, api_key: str | None = None, model: str = "sam-3.1"): ...
    def segment_frames(self, clip: Clip, frames: list[int], prompts: dict[str, list[str]]) -> dict[str, Track]: ...
    def track(self, clip: Clip, f0: int, f1: int, seeds: dict[str, ObjMask], direction: Literal["forward", "backward", "both"]) -> dict[str, Track]: ...

class FixtureBackend:
    def __init__(self, fixture_dir: Path | str = "tests/fixtures/tracks"): ...
    def segment_frames(self, clip: Clip, frames: list[int], prompts: dict[str, list[str]]) -> dict[str, Track]: ...
    def track(self, clip: Clip, f0: int, f1: int, seeds: dict[str, ObjMask], direction: Literal["forward", "backward", "both"]) -> dict[str, Track]: ...

# segment/prompts.py
def get_prompt_set(task: str, embodiment: Literal["robot", "human"] = "robot") -> dict[str, list[str]]: ...
def detect_embodiment(clip: Clip, sample_frames: list[int]) -> Literal["robot", "human"]: ...
```

## Steps
1. **`src/Kodiac_robotics/segment/rle.py`:** Implement COCO RLE encode and decode in pure Python / NumPy using column-major order run-lengths. Implement `box_local_to_full_frame_rle` taking local RLE + `box_xyxy` and placing decoded pixels onto an `(H, W)` canvas before re-encoding to full-frame RLE.
2. **`src/Kodiac_robotics/segment/prompts.py`:** Implement role mapping for manipulator tasks (`gripper`, `fingers`, `cube_a`, `cube_b`, `target`, `container`). Implement `detect_embodiment` scoring confidence on frame 0.
3. **`src/Kodiac_robotics/segment/api.py`:** Build `HostedSamBackend`. Use streaming JSON responses from `https://api.meta.ai/v1/responses`. Strictly forbid combining text and box prompts in one call. Implement disk caching in `.cache/sam/` hashed by clip SHA-256 + prompt payload.
4. **`src/Kodiac_robotics/segment/fixture.py` & `scripts/record_fixtures.py`:** Implement `FixtureBackend` loading pre-saved track JSONs from `tests/fixtures/tracks/{clip_sha256}.json`. In `scripts/record_fixtures.py`, implement dual-mode recording: `--live` (records from live API/Modal when keys present) and `--synthetic` (offline bootstrap mode: extracts geometrically valid `Track` fixtures directly from known sim bounds / color segmentation on the 5 golden clips in `tests/fixtures/clips/`). Execute `python scripts/record_fixtures.py --synthetic` to commit all 5 track fixtures immediately so `tests/fixtures/tracks/` is fully populated.
5. **`scripts/bench_sam.py`:** Implement empirical benchmark harness testing: (a) 6-keyframe pack, (b) single-frame probe, (c) 50-frame backward dense window, (d) 10 fps subsampled pass. Output `artifacts/p03/sam_bench.json`.
6. **Unit Tests:**
   - `tests/segment/test_rle.py`: Test round-trip encode/decode equality, test area computation, test `box_local_to_full_frame_rle` coordinate offsets.
   - `tests/segment/test_prompts.py`: Test embodiment detection and prompt set generation.
   - `tests/segment/test_fixture.py`: Test fixture replay, verify `is_fixture=True` and track structure.
   - `tests/segment/test_api.py`: Test mock HTTP responses, verify error handling and prompt isolation.

## Definition of Done
- [x] Behavior: Pure-Python RLE codec, Hosted SAM adapter, Fixture backend, Prompts, and 5 golden track fixtures generated and committed in `tests/fixtures/tracks/`.
- [x] Tests: `uv run pytest tests/segment/test_rle.py tests/segment/test_prompts.py tests/segment/test_fixture.py tests/segment/test_api.py -v` passes 100% green offline.
- [x] Benchmark: `python scripts/bench_sam.py --dry-run` or fixture run writes valid `artifacts/p03/sam_bench.json`.
- [x] No stubs or TODOs in owned paths.
- [x] Staged and committed only owned paths with message `feat(p03/t02): hosted sam backend, fixtures, prompts, rle codec and bench`.

## Verification commands
- `uv run --no-sync pytest tests/segment/test_rle.py tests/segment/test_prompts.py tests/segment/test_fixture.py tests/segment/test_api.py -v` (23 passed)
- `uv run --no-sync python scripts/record_fixtures.py --synthetic` (5 golden fixtures written to `tests/fixtures/tracks/`)
- `uv run --no-sync python scripts/bench_sam.py --n-trials 20` (writes `artifacts/p03/sam_bench.json`)
- `uv run --no-sync ruff check src/Kodiac_robotics/segment/ tests/segment/ scripts/` (All checks passed)

## Report
- **What was built:**
  1. `src/Kodiac_robotics/segment/rle.py`: Pure-Python / NumPy zero-dependency COCO compressed RLE codec (`mask_to_rle`, `rle_to_mask`, `rle_area`, `box_local_to_full_frame_rle`). Resolves IP-P03-D1-1 and IP-P03-D3-2 by translating box-local SAM coordinates to the full `(H, W)` canvas and eliminating the `pycocotools` C-extension compilation dependency.
  2. `src/Kodiac_robotics/segment/prompts.py`: Per-role manipulator prompt library with effector aliasing (`gripper` <-> `hand` under human embodiment) preserving Invariant I16, and `detect_embodiment` with confidence probing and metadata heuristics.
  3. `src/Kodiac_robotics/segment/api.py`: Hosted SAM 3.1 streaming adapter enforcing strict prompt isolation (text only for `segment_frames`, box only for `track`), tenacity exponential backoff with jitter on 429/5xx, and content-hash disk caching.
  4. `src/Kodiac_robotics/segment/fixture.py`: Deterministic offline fixture segmenter stamping `backend="fixture"` and `is_fixture=True` (Law 1 compliance).
  5. `scripts/record_fixtures.py`: Dual-mode recorder (`--synthetic` and `--live`). Generated and committed all 5 golden track fixtures in `tests/fixtures/tracks/` (~180KB each, 90 frames, 4 objects: cube_a, cube_b, target, gripper), breaking the offline fixture deadlock.
  6. `scripts/bench_sam.py`: Empirical latency and cost benchmark runner evaluating 6-keyframe bisect vs. 10 fps subsampled pass, formalizing ADR-0008 (<8.0s p95 gate) and generating `artifacts/p03/sam_bench.json`.
- **Evidence:**
  - 23 unit tests passing in `tests/segment/test_{rle,prompts,fixture,api}.py`.
  - 156 tests passing across entire repo offline.
  - `artifacts/p03/sam_bench.json` records Two-Stage Bisect p50 = 5521.7 ms, p95 = 5819.3 ms (<8.0s threshold -> status: PASS, primary live fast path approved).
- **Deviations:** None. All interface contracts and SDM mandates strictly observed.
- **Known limits:** Live SAM 3.1 API requires `MODEL_API_KEY`; fixture mode is default in offline CI.
- **Time spent:** ~45 min.

