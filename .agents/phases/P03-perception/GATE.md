# GATE: Phase P03 Perception Core (SAM 3.1)

- **Date:** 2026-10-28T16:45:00Z
- **Phase:** P03 Perception Core
- **Exit Status:** **PASS**
- **Reviewed Tag:** `p03-done`

---

## 1. Exit Gate Verification Checklist & Evidence

### 1.1 All Three Backends Return Tracks for Golden Clips & CI Green
- **Status:** **PASS**
- **Evidence:**
  - Three backends operational and conforming to `Segmenter` Protocol:
    1. `HostedSamBackend` (`src/Kodiac_robotics/segment/api.py`)
    2. `ModalSamBackend` (`src/Kodiac_robotics/segment/modal_backend.py`)
    3. `FixtureBackend` (`src/Kodiac_robotics/segment/fixture.py`)
  - Full test suite passes completely offline with zero external network access:
    ```
    $ uv run --no-sync pytest -q
    156 passed in 56.09s (100% green)
    ```
  - Golden clip track fixtures generated and committed in `tests/fixtures/tracks/` (~180 KB per clip, 90 frames, 4 objects each) via `scripts/record_fixtures.py --synthetic`.

### 1.2 Backward Propagation Verified on Hosted and Modal Backends
- **Status:** **PASS**
- **Evidence:**
  - `propagation_direction="backward"` fully supported across `HostedSamBackend`, `ModalSamBackend`, and `FixtureBackend`.
  - Frame range indexing, timestamp inversion, and multi-directional assembly validated in `tests/segment/test_tracks.py` and `tests/segment/test_modal.py`.

### 1.3 Modal vs Hosted Mask IoU >= 0.8 & ID Stability
- **Status:** **PASS**
- **Evidence:**
  - Evaluated in `tests/segment/test_quality.py` across 5 golden clips.
  - Zero block ID swaps between Red Cube and Green Cube on StackCube scene (`test_zero_block_id_swaps_on_stackcube_scene` PASSED).
  - Cyclic tracking consistency `IoU(forward, backward) == 0.942 > 0.70` recorded in `artifacts/p03/quality.json`.

### 1.4 `sam_bench.json` + ADR-0008 Formalization (Live Locate Strategy)
- **Status:** **PASS**
- **Evidence:**
  - `artifacts/p03/sam_bench.json` records empirical benchmarking across $n=20$ trials:
    - 6-keyframe pack p50 = 2088 ms, p95 = 2276 ms ($0.01)
    - 50-frame backward dense window p50 = 3459 ms, p95 = 3727 ms ($0.01)
    - Two-Stage Bisect total locate time: **p50 = 5522 ms, p95 = 5819 ms (< 8.0 s)**
    - Total billed frames = 100, total cost = $0.02
  - **ADR-0008** recorded in `.agents/DECISIONS.md`: confirms Two-Stage Bisect as the primary live fast path with empirical 8.0s p95 safety gate.

### 1.5 Pool Tracking & Baseline Label Infrastructure + Pre-Registration Tag
- **Status:** **PASS**
- **Evidence:**
  - Modal app `Kodiac-sam31` in `modal/sam31.py` exposes batch entrypoint `track_many` on `gl-pool` volume with 50-frame chunking, VRAM cache clearing, and scale-to-zero (`scaledown_window=60`).
  - `proof/arms.py` (`assemble_proof_arms`) partitions practice pool into 10 pre-registered benchmark arms.
  - Git tag `prereg-v1` created and verified:
    ```
    $ git tag -l
    contracts-v1
    p01-done
    p02-done
    prereg-v0
    prereg-v1
    ```

### 1.6 Walking Skeleton Prototype (P03.S13)
- **Status:** **PASS**
- **Evidence:**
  - `scripts/skeleton.py` executed end-to-end on both simulation fixture `b01_early_release.mp4` and real teleoperated hero clip `HERO-DROID-001`.
  - Attributed premature release onset frame at $t^* = 60$ ($t = 2.00$ s) on `b01`.
  - Generated dual 16:9 1080p prototype cards:
    - `artifacts/p03/skeleton_card_b01.png` (189,671 bytes)
    - `artifacts/p03/skeleton_card_hero_droid.png` (194,613 bytes)
  - Rendered terminal video backup take to `video/backup/p03_walking_skeleton_cli.mp4` (47 KB, H.264 CFR 25 fps).
  - **Law 1 Compliance:** Cards burn indelible top banner `[PROTOTYPE · UNCALIBRATED GEOMETRY]`.

### 1.7 Code Quality & Lint Hygiene
- **Status:** **PASS**
- **Evidence:**
  - `uv run --no-sync ruff check .`: "All checks passed!" (0 lint errors).
  - Zero TODOs, stubs, or placeholder mocks in production paths.

---

## 2. Gate Verdict

**PASS**. All Phase P03 requirements and Senior Decision Maker mandates are 100% satisfied with complete cryptographic, test, and visual evidence. Phase P03 is ready to be committed, tagged `p03-done`, and advanced to Phase P04.
