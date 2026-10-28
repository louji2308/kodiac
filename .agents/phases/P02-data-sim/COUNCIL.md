# COUNCIL: P02 Data & Simulation Foundation
Inputs: BRIEF.md · REVIEW(P01) status: SHIP-AS-IS · Hours to deadline: ~174.5

## R0/R1: D1 Architect
[2026-10-28T10:45:00Z · D1]

- **Phase goal as I understand it (≤3 lines):**
  Deliver the physical simulation and real-robot data backbone: a deterministic Panda `StackCube-v1` harness with `@span` line-level logging, the 10 seeded bug patches (B01–B10), pre-registered protocol (`prereg-v0`), the background practice pool generator (BG-A), and LeRobot/DROID loaders with hero-clip and time-saved labeling tools.

- **Evidence gathered:**
  - `uv run --no-sync pytest tests/ -q` → 29 passed in 21.50s (15 contract tests with 15-level recursive AST serialization, 7 CLI doctor tests, 7 infra tests; 100% green offline baseline).
  - `python -V` → 3.11.9 (AMD64 Windows). Local host has NO GPU.
  - `python -c "import ..."` → `torch` 2.13.0+cpu, `cv2` 5.0.0, `pyarrow` 25.0.0 installed locally; `mani_skill`, `sapien`, `av`, `lerobot` are NOT installed locally.
  - `ffmpeg -version` → ffmpeg 8.1-full_build on PATH with `libx264` support (enables native H.264 `yuv420p` video encoding without requiring PyAV wheel).
  - `python -c "import modal..."` → Modal SDK available; `modal/volumes.py` defines persistent volumes (`gl-pool`, `gl-replays`, `gl-cache`, `hf-cache`).
  - `artifacts/p01/smoke/st09.json` → ST09 confirms `status: PENDING_SIM_ENV`, offloaded to Modal per ADR-0003.
  - `docs/DEMO_FILMING_GUIDE.md` → 140 lines published in P01 specifying 30°–50° elevation, 720p/30 fps, 4 cm cube prior, $\ge 0.7$ s pause.
  - `src/Kodiac_robotics/contracts/core.py:287` → `Clip` and `ClipRef` require `path_h264`, `fps`, `n_frames`, `width`, `height`, `sha256`.

- **Proposed approach:**
  - **S01–S03 (Sim Env Wrapper, Video Writer, Robot API & Spans):**
    - ⚠ *Dual-Backend Sim Architecture:* Implement `SimEnv` Protocol with two interchangeable backends: `ManiSkillEnv` (runs on Modal L4 with CUDA/Vulkan for 1,000-episode pool generation) and `KinematicMockEnv` (deterministic Python/numpy kinematic simulation for local tests/CI with zero GPU dependency).
    - Camera rendering: fixed 512×512, `sim_freq=120, control_freq=30`, producing exact 30 fps frames. Expose `privileged_state(t)` and `oracle_success()` (`align_xy_cm <= 3.33, gap_cm <= 0.5`).
    - Video writer (`sim/video.py`): encodes frames to H.264 `yuv420p` MP4 at 30 fps via OpenCV/ffmpeg CLI. Saves `{episode}.mp4`, `{episode}.state.npz`, and `{episode}.meta.json`.
    - Robot API (`sim/robot.py`): `arm.move_to()`, `arm.lift()`, `arm.retract()`, `gripper.open()`, `gripper.close()`, `wait()`.
    - Span logger (`sim/spans.py`): `@span(actuation_class=...)` captures caller `file`, `line`, `code`, `step_start`, `step_end`, `t_start_s`, `t_end_s` via `inspect.stack()`.
  - **S04–S05 (Pick-and-place & Seeded Bug Registry B01–B10):**
    - `examples/sim/pick_place.py`: Reference expert script stacking red cube on green cube. Verified oracle success 10/10 seeds.
    - `sim/bugs.py` + `examples/sim/bugs/B01.patch` … `B10.patch`:
      - B01: Early release (`gripper.open()` before reaching green block; expected fail: dropped red block, `moves_with` T→F).
      - B02: XY offset (+3.0 cm error in place target; expected fail: misaligned stack, `on.align_xy` fails).
      - B03: Low lift (lift height 1 cm instead of 10 cm; expected fail: collision/table drag, `lifted` fails).
      - B04: Short dwell / no wait (omits settling wait; expected fail: `dwell` < 0.5 s).
      - B05: Lift before close (calls `arm.lift()` before `gripper.close()`; expected fail: empty lift).
      - B06: Grasp Z too high (grasps cube top edge, slips during transit; expected fail: `moves_with` breaks).
      - B07: Missing close (omits `gripper.close()` completely; expected fail: no grasp).
      - B08: Wrong object (picks green cube instead of red cube; expected fail: wrong object/order).
      - B09: Never opens (omits `gripper.open()` at place; expected fail: `not moves_with` fails).
      - B10: Release Z too high (releases 6 cm above target; expected fail: bounce/topple, `gap_cm` fails).
    - Each bug script asserts deterministic oracle FAIL and generates a span log containing the faulty actuation span.
  - **S06–S09 (Proof Pool & Pre-Registration):**
    - S06: $\pi_0$ weak policy pipeline in `proof/pi0.py` and `modal/proof_train.py` (ManiSkill state-based Diffusion Policy or BC, target 30–60% oracle success).
    - S07: 🔁 Background practice pool generator (`proof/pool.py`): ~70% $\pi_0$ rollouts + ~30% perturbed-expert near-misses (early open, xy offset U(1,6) cm, low lift, short dwell, regrasp). Total ~600–1,000 episodes saved to `gl-pool` volume. Manifest written incrementally via `pyarrow.parquet`.
    - S08: `experiments/PREREGISTRATION.md`: Hypotheses H1–H3, oracle-matched thresholds (`align_xy_cm <= 3.33, gap_cm <= 0.5`), CAN'T TELL = not accepted rule, fixed gradient steps, 3 seeds, $\ge 200$ eval episodes. Tagged `prereg-v0` BEFORE pool generation launches (Invariant I8).
    - S09: `examples/stackcube.green` (matching PREREGISTRATION.md) and `examples/stack_blocks.green` (spec standard).
  - **S10–S12, S14–S16 (Dataset Loaders, Real Footage, Spikes, Fixtures):**
    - S10: `io/lerobot.py`: `lerobot://repo/episode[/camera]` loader using `huggingface_hub` with local caching and ffmpeg transcode to H.264 `yuv420p` `Clip`.
    - S11: `scripts/find_hero_clips.py`: Scans DROID and LeRobot pick/place datasets, exports candidate thumbnails + MP4 clips to `artifacts/p02/hero_candidates/index.md`.
    - S12: Real footage prep (BG-C): DROID slice manifest (~200 episodes), `scripts/label_tool.py` (HTML/JS dual-mode labeling: *scrub* vs *blame* with decision timer logging for P-7 time-saved metrics).
    - S13/S13b: Baseline spikes on Modal L4: Robometer-4B, TOPReward, and single-pass Muse Spark 1.3 (2 fps whole clip).
    - S14: Golden fixtures in `tests/fixtures/clips/` ($\le 2$ MB each: correct, B1, B2, B9, occluded) with sha256 checksums.
    - S15: Filming guide verified (`docs/DEMO_FILMING_GUIDE.md`).
    - S16: Appearance benchmark in `proof/appearance.py` ($\ge 60$ clips: ManiSkill drawer flush vs ajar + DROID drawer episodes).

- **Interface contracts:**
  ```python
  # src/Kodiac_robotics/sim/spans.py
  from typing import Literal, Callable, Any
  from pydantic import BaseModel

  ActuationClass = Literal["gripper.open", "gripper.close", "arm.move_to", "arm.lift", "arm.retract", "wait"]

  class SimSpan(BaseModel):
      span_id: int
      func: str
      file: str
      line: int
      code: str
      actuation_class: ActuationClass
      step_start: int
      step_end: int
      t_start_s: float
      t_end_s: float

  def span(actuation_class: ActuationClass) -> Callable[..., Any]: ...
  def find_blame_span(spans: list[SimSpan], frame_idx: int) -> SimSpan | None: ...

  # src/Kodiac_robotics/sim/env.py
  from typing import Protocol, Any
  import numpy as np

  class SimState(BaseModel):
      step: int
      t_s: float
      gripper_width: float
      cubeA_pose: tuple[float, float, float, float, float, float, float]  # xyz + quat
      cubeB_pose: tuple[float, float, float, float, float, float, float]
      in_contact: bool

  class SimEnv(Protocol):
      def reset(self, seed: int | None = None) -> tuple[np.ndarray, dict[str, Any]]: ...
      def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]: ...
      def privileged_state(self) -> SimState: ...
      def oracle_success(self) -> bool: ...
      def render(self) -> np.ndarray: ...  # (512, 512, 3) uint8

  class SimRun(BaseModel):
      run_id: str
      seed: int
      video_path: str
      state_path: str
      meta_path: str
      spans: list[SimSpan]
      oracle_success: bool
      onset_frame: int | None = None
      perturbation_type: str | None = None

  # src/Kodiac_robotics/sim/bugs.py
  class BugDef(BaseModel):
      id: str  # "B01" ... "B10"
      name: str
      description: str
      patch_path: str
      expected_failure_step: int
      expected_broken_predicate: str
      expected_blame_span: ActuationClass
      expected_oracle_success: bool = False

  # src/Kodiac_robotics/io/lerobot.py
  from Kodiac_robotics.contracts.core import Clip
  from pathlib import Path

  def load_lerobot_episode(
      repo_id: str,
      episode_index: int,
      camera: str | None = None,
      target_fps: float = 30.0,
      cache_dir: Path | None = None,
      mock_ok: bool = True,
  ) -> Clip: ...

  # experiments/pool/manifest.parquet schema (pyarrow)
  # [episode_id: string, split: string, video_uri: string, state_uri: string,
  #  oracle_success: boolean, perturbation_type: string, onset_frame: int64,
  #  duration_s: float64, n_frames: int64, control_mode: string]
  ```

- **Proposed task DAG:**
  - **T01 (IMPL-1): Sim Harness, Robot API, Span Logger & Bug Registry** (S01–S05)
    - `owns_paths`: `[src/Kodiac_robotics/sim/**, examples/sim/**, tests/sim/**]`
    - `depends_on`: []
    - Delivers: `SimEnv` dual-backend, `robot.py`, `@span` logger, `pick_place.py` (10/10 seeds oracle PASS), B01–B10 patches and test suite.
  - **T02 (IMPL-2): Proof Pool Generation, Baseline Policies & Pre-Registration** (S06–S09, S13, S13b, S16)
    - `owns_paths`: `[src/Kodiac_robotics/proof/**, modal/proof_*.py, experiments/**, examples/stackcube.green, examples/stack_blocks.green]`
    - `depends_on`: [T01 (for SimEnv/reference trajectory)]
    - Delivers: `PREREGISTRATION.md` (tagged `prereg-v0`), $\pi_0$ weak policy pipeline, BG-A practice pool generator on Modal, `examples/*.green`, baseline spikes (Robometer/TOPReward/Spark 2fps), appearance benchmark.
  - **T03 (IMPL-3): Dataset Loaders, Hero Clip Search, Labeling Tool & Golden Fixtures** (S10–S12, S14, S15)
    - `owns_paths`: `[src/Kodiac_robotics/io/lerobot.py, scripts/find_hero_clips.py, scripts/label_tool.py, tests/fixtures/**, tests/io/**, docs/DEMO_FILMING_GUIDE.md]`
    - `depends_on`: []
    - Delivers: `load_lerobot_episode`, hero-clip search tool + candidate shortlist, HTML/JS dual-mode labeling tool with timer instrumentation (BG-C), golden clips in `tests/fixtures/clips/`.
  - *DAG Parallelism:* T01 and T03 dispatch immediately in parallel. T02 starts pre-registration draft and Modal scripts in parallel with T01, then hooks to T01's simulation wrapper once green.

- **Top risks (3):**
  - **Risk 1: ManiSkill3 headless rendering / SAPIEN dependency failure on local machines.**
    - *Mitigation:* Dual-backend simulation env. Local unit tests, B01–B10 bug validation, and CI execute against `KinematicMockEnv` (deterministic numpy geometry, instant 30 fps H.264 video, zero GPU needed). True ManiSkill3 runs in Docker/Modal L4 for pool generation.
    - *Tripwire:* Any local test fails with `ModuleNotFoundError: No module named 'mani_skill'` or SAPIEN Vulkan initialization error.
  - **Risk 2: $\pi_0$ weak policy convergence outside target 30–60% oracle success window.**
    - *Mitigation:* Calibrate demonstration count (20 vs 50) and training steps on Modal; hedge by using pre-registered ~30% perturbed-expert near-misses as a guaranteed source of realistic borderline failures regardless of $\pi_0$ variance.
    - *Tripwire:* 100-episode evaluation on Modal yields oracle success < 20% or > 75%.
  - **Risk 3: HuggingFace network rate-limiting or network block during LeRobot DROID downloads.**
    - *Mitigation:* Local caching in `~/.cache/Kodiac/lerobot`, chunked streaming, mock fixture fallback for offline CI.
    - *Tripwire:* Episode download fails after 3 retries or stalls > 60 seconds.

- **Improvement proposals:**
  - **IP-P02-D1-1: Dual-Backend Simulation Architecture (Kinematic Mock for local test/CI + ManiSkill3 for Modal GPU).**
    - *Change:* Support both `ManiSkillEnv` (Modal GPU) and `KinematicMockEnv` (local CPU) under a unified `SimEnv` Protocol.
    - *Evidence:* Local host has no GPU and lacks `mani_skill`/`sapien` wheels. Local CI must run in seconds without Vulkan/CUDA.
    - *Judge impact:* Technical Depth (+0.3), Demo (+0.4) — guarantees 100% offline test reproducibility and zero flaky sim crashes.
    - *Cost:* ~1.5 hours in IMPL-1.
    - *Invariant check:* Preserves I13 (100% software, sim clearly labeled) and I8.
  - **IP-P02-D1-2: Standardized Spans Schema & Frame-to-Span Query Contract (`find_blame_span`).**
    - *Change:* Formalize `SimSpan` with `step_start`, `step_end`, `actuation_class`, and explicit `find_blame_span(spans, frame_idx)` lookup.
    - *Evidence:* Invariant I4 / F35b requires mapping $t^*$ directly to code line `pick_place.py:42 -> gripper.open()`.
    - *Judge impact:* Technical Depth (+0.4), Agentic Use-Case (+0.5).
    - *Cost:* 1 hour in IMPL-1.
    - *Invariant check:* Directly fulfills I4.
  - **IP-P02-D1-3: Sharded Parquet Pool Manifest with Resumable Modal Checkpointing.**
    - *Change:* Write pool episodes in 100-episode shards (`manifest_shard_NNN.parquet`) merged at completion via PyArrow.
    - *Evidence:* Long-running batch generation on Modal can experience transient network interruptions or container preemptions.
    - *Judge impact:* Technical Depth (+0.3), Reliability.
    - *Cost:* 0.5 hours in IMPL-2.
    - *Invariant check:* None touched.

- **Confidence:** 92/100 because the local core is already 100% green (29/29 tests), ffmpeg and pyarrow are verified locally, the contracts in `contracts/core.py` are frozen and sound, and the dual-backend architecture protects the pipeline from local host GPU constraints.

## R0/R1: D2 Judge Advocate
[2026-10-28T10:40:00Z · D2]

- **Phase goal as I understand it (≤3 lines):**
  Establish the physical simulation and real-robot data backbone that powers our two headline demo moments: the 5-second hero failure cold open (real DROID/LeRobot footage) and the downstream retraining proof (Invariant I8), while seeding the deterministic 10-bug benchmark (B01–B10) that enables the Muse Code `/goal` loop.

- **Evidence gathered:**
  - `git status` → On branch `main`, ahead of `origin/main` by 4 commits; tag `p01-done` at `c7ed6d0` verified.
  - `uv run --no-sync pytest tests/ -q` → 29 passed in 33.81s (contracts, CLI doctor, schemas fully green and offline-reproducible).
  - `scripts/smoke/st09_maniskill_render.py` → `mani_skill` optional package not installed in local Windows CPU core; simulation workloads cleanly offloaded to Modal (`modal/proof_train.py`) per RULING.md / ADR-0003. Local sim harness must support CPU/mock mode for fast unit tests.
  - `scripts/smoke/st10_lerobot_droid.py` → `lerobot` package not installed in host core; LeRobot loader in `src/Kodiac_robotics/io/lerobot.py` must support streaming or downloaded parquet index parsing without requiring a local GPU.
  - `docs/DEMO_FILMING_GUIDE.md` → 140 lines already seeded with camera angles (30°–50° pitch down), 4.0 cm block priors, and 0.7 s audio pauses for Muse Voice Transcribe `ENDPOINTING`.
  - `docs/VIDEO_NUMBERS.md` → 4 initial rows registered (Fast path <12s, StackCube 3.33cm, Gap 0.5cm, Block 4.0cm).
  - `HACKATHON.md §9` → Simulated Judge Panel preferences: J1 (FAIR perception) demands metric margins with honest error bars, J2 (robotics researcher) checks citations and pre-registration to verify retraining wasn't p-hacked, J4 (product) needs a 5-second visceral visual hook.

- **Proposed approach:**
  1. **Sim & Bug Harness (S01–S05):** Build `src/Kodiac_robotics/sim/env.py` (Panda, 120Hz sim / 30Hz control, 512×512 camera, deterministic seeds, `oracle_success()` and privileged state). Implement PyAV 30 fps `yuv420p` MP4 video writer (`sim/video.py`). Implement `@span` logger in `sim/robot.py` / `sim/spans.py` capturing file, line, function, and execution span. Deliver reference `examples/sim/pick_place.py` (10/10 seeds oracle PASS). Implement seeded bug registry (`sim/bugs.py`) with 10 deterministic patches (`examples/sim/bugs/B01.patch` … `B10.patch`) asserting oracle FAIL.
  2. **Proof Engine & Pool Generation (S06–S08, S13, S13b, S16):** Implement $\pi_0$ weak policy trainer on Modal (`modal/proof_train.py`, targeting 30–60% oracle success). Pre-register hypotheses H1–H3, arms, thresholds, and stopping rules in `experiments/PREREGISTRATION.md` tagged `prereg-v0`. Generate practice pool (`proof/pool.py`, ~70% $\pi_0$ + ~30% perturbed-expert near-misses) outputting `experiments/pool/manifest.parquet`. Spike baseline judges (Robometer-4B, TOPReward, Muse Spark 2fps single-pass). Build appearance benchmark dataset (`proof/appearance.py`, $\ge 60$ labeled clips).
  3. **Real Footage & Hero Assets (S10–S12, S14–S15):** Build LeRobot dataset loader (`src/Kodiac_robotics/io/lerobot.py`) resolving `lerobot://repo/episode[/camera]` to `Clip`. Implement hero-clip search (`scripts/find_hero_clips.py`) scanning DROID and LeRobot datasets for high-contrast failures. Build local HTML labeling tool (`scripts/label_tool.py`) with randomized A/B timing instrumentation (`scrub` vs `blame`). Assemble golden fixture clips (`tests/fixtures/clips/`) and finalize `docs/DEMO_FILMING_GUIDE.md`.

- **Interface contracts:**
  ```python
  class SpanRecord(BaseModel):
      span_id: int
      file: str
      line: int
      func: str
      code: str
      cls: str
      step_start: int
      step_end: int
      t_start_s: float
      t_end_s: float

  class BugDefinition(BaseModel):
      bug_id: str  # B01..B10
      name: str
      patch_path: str
      expected_blame_class: str
      expected_broken_predicate: str
      expected_failing_span: str
      description: str

  class PoolEpisode(BaseModel):
      episode_id: str
      split: Literal["calibration", "train"]
      video_uri: str
      state_uri: str
      oracle_success: bool
      perturbation_type: str | None
      onset_frame: int | None
      seed: int

  class HeroCandidate(BaseModel):
      candidate_id: str
      dataset: str
      episode_index: int
      camera_key: str
      task_string: str
      failure_type: str
      resolution: tuple[int, int]
      fps: float
      clip_path: str
      thumbnail_path: str
      notes: str

  class TimingRecord(BaseModel):
      session_id: str
      annotator: str
      episode_id: str
      mode: Literal["scrub", "blame"]
      time_to_verdict_ms: float
      verdict: str
      ground_truth: str
      is_correct: bool
  ```

- **Proposed task DAG:**
  - `T01` (IMPL-1): ManiSkill Wrapper, Span Logger, `pick_place.py`, B01–B10 Bugs (S01–S05)
    - `owns_paths`: `src/Kodiac_robotics/sim/**`, `examples/sim/**`, `tests/sim/**`
    - Depends on: None (frozen contracts `src/Kodiac_robotics/contracts/` in place)
  - `T02` (IMPL-2): Proof Practice Pool Generator, $\pi_0$ Policy, Pre-Registration & Appearance Benchmark (S06–S09, S13, S13b, S16)
    - `owns_paths`: `src/Kodiac_robotics/proof/**`, `modal/proof_*.py`, `experiments/**`, `examples/*.green`
    - Depends on: None (pool generator & prereg schemas runnable locally, compute targets Modal)
  - `T03` (IMPL-3): LeRobot Ingest Loader, Hero-Clip Search, Labeling & Timing Tool, Golden Fixtures (S10–S12, S14–S15)
    - `owns_paths`: `src/Kodiac_robotics/io/lerobot.py`, `scripts/find_hero_clips.py`, `scripts/label_tool.py`, `tests/fixtures/clips/**`, `tests/io/**`, `docs/DEMO_FILMING_GUIDE.md`, `artifacts/p02/**`
    - Depends on: None
  - *DAG execution:* T01 ∥ T02 ∥ T03 (DAG width = 3). Disjoint paths. All merge at GATE into `phase/p02-data-sim`.

- **Top risks (3):**
  1. *Risk:* Hero failure clips from DROID are too low-resolution (320×180) or visually ambiguous to deliver a stunning 5-second video cold open.
     - *Mitigation:* Broaden S11 search to include public LeRobot community teleop datasets (e.g. SO-100/SO-101 pick-and-place sets recorded at 720p/30fps) alongside DROID.
     - *Tripwire:* Candidate clips in `artifacts/p02/hero_candidates/` contain < 1 clear high-definition candidate by GATE.
     - *Fallback:* Use high-res SO-100 teleop episode as primary visual hero clip; present DROID as secondary real-world generalization benchmark.
  2. *Risk:* Pre-registration document is delayed or lacks mathematical rigor, undermining Invariant I8 credibility with robotics researchers.
     - *Mitigation:* Freeze `experiments/PREREGISTRATION.md` early in P02 with exact oracle-matched geometric thresholds (`align_xy_cm <= 3.33, gap_cm <= 0.5`) and tag `prereg-v0` immediately before pool generation starts.
     - *Tripwire:* Pool generation launched before `prereg-v0` git tag is created and verified.
     - *Fallback:* Halt pool generation script until `PREREGISTRATION.md` is committed and tagged.
  3. *Risk:* Baseline models (Robometer-4B / TOPReward) OOM or fail to install in Modal L4 containers during S13 spike.
     - *Mitigation:* Pin exact container requirements with pre-built wheel dependencies in `modal/proof_train.py` and fall back to A10G/A100 instances if L4 VRAM is exceeded.
     - *Tripwire:* Baseline spike script `scripts/smoke/st13` fails with CUDA OOM on L4.
     - *Fallback:* Allocate A10G (+$0.30/hr) on Modal; if dependencies fail, fall back to single-pass Spark baseline as primary comparison.

- **Improvement proposals:**
  - `IP-P02-D2-1` (Hero Clip Quality & Curation Protocol): Mandate `scripts/find_hero_clips.py` output structured candidate cards with resolution, camera angle (30°–50°), failure classification, and visual contrast score. At least 3 candidates must come from real public datasets (`droid_100` and LeRobot community datasets) with unoccluded gripper/object views, ready for SAM 3.1 overlay.
    - *Judge impact:* Demo (+1.0), Impact (+0.5). Secures Video Beat 1 (0:00–0:05) cold open and Most Viral bonus.
    - *Cost:* ~1.0h agent work in S11.
    - *Risk:* None.
  - `IP-P02-D2-2` (Pre-Registration Hash & Manifest Timestamping): Embed `experiments/pool_config.yaml` sha256, oracle tolerances, and `prereg_commit_sha` into `experiments/pool/manifest.parquet` metadata. Run `ots stamp experiments/PREREGISTRATION.md` upon tagging `prereg-v0`.
    - *Judge impact:* Technical Depth (+1.0), Impact (+0.5). Destroys skeptical judge objection ("downstream retraining was cherry-picked").
    - *Cost:* ~0.5h in S07/S08.
    - *Risk:* None.
  - `IP-P02-D2-3` (Time-Saved Study Randomized A/B Telemetry): Enforce strict randomized presentation order (`scrub` vs `blame`) with automated millisecond reaction timers logged to `experiments/labels/timing_<annotator>.jsonl` in `scripts/label_tool.py`.
    - *Judge impact:* Impact (+1.0), Technical Depth (+0.5). Powers proof claim P-7 ("reviewing took X s vs Y s, saving Z hours").
    - *Cost:* ~1.0h in S12.
    - *Risk:* None.

- **Judge-impact table:**

  | Criterion (weight) | Baseline P02 Plan | With D2 Proposals (IP-P02-D2-1..3) | Delta Driver |
  |---|---|---|---|
  | **Impact (30%)** | 7.5 | **9.0** | Randomized time-saved study (P-7) gives defensible hours-saved metric; real DROID/LeRobot failure curation establishes immediate industry relevance. |
  | **Use of Meta AI Tooling (25%)** | 8.5 | **9.0** | Prepares clean video inputs for SAM 3.1 backward tracking; establishes ground-truth frame timestamps for Muse Voice `ENDPOINTING` windows. |
  | **Demo (25%)** | 7.5 | **9.0** | High-definition hero clips guarantee a visceral 5-second video cold open (C1); B01–B10 bug patches provide guaranteed deterministic demo for Muse Code `/goal` (C5). |
  | **Technical Depth & Execution (20%)** | 8.0 | **9.5** | Cryptographic pre-registration (`prereg-v0` hash embedded in parquet) eliminates p-hacking suspicion; 10 deterministic physical bugs assert oracle FAIL. |
  | **Weighted Total** | **7.85** | **9.10** | **Crosses the crucial ≥ 9.0 threshold required for the top 5 live finals.** |

- **Demo/video artifacts this phase must produce:**
  1. `artifacts/p02/hero_candidates/`: Index of candidate failure episodes from real public datasets (`droid_100`, LeRobot SO-100) with thumbnails, MP4 clips, and metadata ready for SAM 3.1 overlay.
  2. `examples/sim/pick_place.py` + `artifacts/p02/pick_place_success.mp4`: Clean 30 fps H.264 reference demonstration showing 10/10 oracle pass.
  3. `examples/sim/bugs/B01.patch` … `B10.patch` + `artifacts/p02/bugs/`: 10 reproducible bug patches asserting deterministic oracle FAIL, with span logs linking code lines to physical failure.
  4. `experiments/PREREGISTRATION.md` (tagged `prereg-v0`): Pre-registered hypotheses, oracle-matched tolerances, and stopping rules.
  5. `artifacts/p02/timing_tool_preview.png` + `scripts/label_tool.py`: Working annotation interface demonstrating randomized A/B scrub vs blame telemetry.
  6. `tests/fixtures/clips/`: Golden fixture clip suite (≤2MB each: correct run, B1, B2, B9, occluded) with sha256 checksums.

- **Confidence:** **92/100** because the phase plan is thoroughly grounded in the hackathon rubric, directly delivers the visual assets needed for Video Beats C1 and C5, protects Concept Invariants (I1, I4, I8, I13, I15), and cleanly addresses the local Windows CPU environment by isolating heavy sim rendering to Modal.

## R0/R1: D3 Red Team
*[2026-10-28T10:45Z · D3]*

### 1. Phase Goal As I Understand It (≤3 lines)
Establish the ManiSkill3 simulation harness, 10 deterministic physical bug benchmarks (B01–B10), and `@span`-instrumented robot API; launch background generation of the 600–1,000 episode practice pool on Modal under a pre-registered protocol (`prereg-v0`); and build dataset loaders and real-footage labeling tools for the DROID benchmark.

### 2. Evidence Gathered (Hard Local & Stack Facts)
- **Local Host Environment Constraints:**
  - `uv run --no-sync python -V` -> `Python 3.11.9`.
  - `torch.__version__` -> `2.13.0+cpu` (CPU only; NO local CUDA GPU).
  - Missing critical packages in local Windows environment (`uv run --no-sync python -c ...`):
    - `mani_skill`: `MISSING: No module named 'mani_skill'`
    - `sapien`: `MISSING: No module named 'sapien'`
    - `lerobot`: `MISSING: No module named 'lerobot'`
    - `av` (PyAV): `MISSING: No module named 'av'`
    - `mujoco`: `MISSING: No module named 'mujoco'`
  - Available packages locally: `cv2` (OpenCV), `modal`, `pydantic 2.9.2`, `typer 0.27.0`, `rich 13.9.1`, `shapely 2.1.2`, `lark 1.3.1`, `ffmpeg 8.1-full_build`.
  - Sandbox network boundaries: Sandboxed execution prevents outbound network connections (socket connect error 10013 on PyPI), enforcing `--no-sync` for all local tool calls.
  - SAPIEN / ManiSkill3 Windows reality: SAPIEN requires Vulkan drivers and display device context; headless SAPIEN without a dedicated GPU on Windows fails with `VK_ERROR_INITIALIZATION_FAILED` or requires software Vulkan (lavapipe), which is missing or brittle.
  - Core packaging purity: `pyproject.toml` intentionally isolates `mani-skill` and `lerobot` into optional extras (`[sim]`, `[proof]`) to keep the primary CLI (`Kodiac`) torch-free.
- **External Dependencies & Credentials:**
  - `.agents/STATE.md`: `MODEL_API_KEY` (pending), `MODAL_TOKEN_ID` (pending), `HF_TOKEN` for `facebook/sam3.1` (pending).
  - OpenTimestamps: `ots` binary is `None` (not installed locally). Cryptographic receipt must rely on git commit SHA + signed tag + public push, with `ots` as optional best-effort.
- **Data & Video Codecs:**
  - `lerobot/droid_100` / `droid_1.0.1` format: 15 fps, 320×180, AV1 encoded (`TOOLS_AND_REQUIREMENTS.md §3`).
  - SAM 3.1 API input restriction: Hosted Meta Model API strictly rejects AV1/VP9 and requires H.264/H.265 `yuv420p` (`TOOLS_AND_REQUIREMENTS.md §2.1`).

### 3. Pre-Mortem: Judging Day Failure Modes
1. **Failure Mode 1: Accidental Pass / Physics Bouncing in Seeded Bugs.**
   - *Post-Mortem:* During the live Muse Code `/goal` unedited take or judge evaluation, bug B10 (release z +6 cm) or B02 (xy offset) was evaluated. The cube bounced unpredictably off the table/block and settled inside the oracle tolerance (`align_xy_cm <= 3.33, gap_cm <= 0.5`). The oracle reported PASS on a planted failure. Muse Code made zero code modifications and claimed `/goal` finished. A judge tested B10 and caught the false success, destroying our credibility on Invariant I7.
   - *Root Cause:* SAPIEN contact restitution and overly forgiving tolerance thresholds allowed bouncy dynamics to pass.
2. **Failure Mode 2: Downstream Retraining Budget & Time Explosion.**
   - *Post-Mortem:* Phase P08 attempted to retrain 10+ arms × 3 seeds (30–39 runs) of state-based Diffusion Policy on Modal L4. Each run took 60–90 minutes due to unoptimized diffusion denoising steps. Total compute consumed 45 GPU hours ($36), hitting Modal rate limits and timeout errors. The Nov 2 go/no-go gate was missed, and the proof chart had missing arms and wide confidence intervals that failed to demonstrate statistically significant +Y points.
   - *Root Cause:* Failure in P02.S06 to benchmark training wall-clock time and enforce a strict $\le 15$ min/run training cap.
3. **Failure Mode 3: Span Logger Path & Line Mismatch Across OS Boundaries.**
   - *Post-Mortem:* `@span` ran inside Modal Linux containers, writing absolute Linux paths (`/root/Kodiac/examples/sim/pick_place.py`). When evaluated locally or by Muse Code on Windows, the blame code mapper failed to find the file or misidentified the line due to `CRLF` vs `LF` offset shifts. `blame` returned `pick_place.py:UNKNOWN` instead of `pick_place.py:42 -> gripper.open()`.
   - *Root Cause:* Un-normalized file paths and lack of AST-level node matching in `sim/spans.py`.

### 4. Schedule & Resource Math (174.4h to Internal Deadline)
- **Time to Feature Freeze:** 162.5h | **Time to Nov 2 Go/No-Go:** ~120h | **Phase P02 Budget:** 10–12 agent wall-clock hours.
- **Compute Budget (Modal $100 Credit = 125 L4 GPU-hours @ $0.80/h):**
  - *Pool Generation (BG-A):* 1,000 episodes × ~4s rendering/episode = 4,000s = **1.11 GPU-hours** ($0.89). With 2× re-run/debugging margin: **2.5 GPU-hours** ($2.00).
  - *Policy Benchmark Spike (P02.S06):* 1 run × 20k steps = **0.25 GPU-hours** (15 min, $0.20).
  - *P08 Retraining Forecast (30 runs × 3 seeds):* At 15 min/run: 30 × 0.25h = **7.5 GPU-hours** ($6.00). Evaluation: 30 × 200 eps @ 0.5s = **0.83 GPU-hours** ($0.66).
  - *Total Proof Compute Allocation:* ~11.0 GPU-hours ($8.80) — leaves >$90 Modal credit for SAM 3.1 bulk batch audit and demo hosting.
  - *Constraint:* Training wall-clock time MUST NOT exceed 15 minutes per seed on L4.
- **Storage Footprint:**
  - 1,000 H.264 512×512 MP4s @ 30 fps (~1.2 MB each) = 1.2 GB.
  - 1,000 State `.npz` files (~250 KB each) = 250 MB.
  - Total volume size < 2.0 GB (fits easily in Modal Volume `kodiac-cache`).

### 5. Kill Criteria & Tripwires
- **TRIPWIRE-1 (Local SAPIEN/Vulkan Failure):** If any test or script imports `mani_skill` or invokes SAPIEN rendering locally on Windows without a GPU and fails with `VK_ERROR` or `ImportError`, KILL local execution immediately. Enforce `MockSimEnv` locally and offload all live simulation rendering to Modal (`modal/proof_train.py`).
- **TRIPWIRE-2 (Policy Training > 20 min):** In P02.S06, if 1 training run of $\pi_0$ takes $>20$ minutes on Modal L4, KILL the Diffusion Policy architecture. Immediately switch to a 2-layer MLP BC or lightweight ACT architecture that completes in $\le 12$ minutes.
- **TRIPWIRE-3 (Non-Deterministic Bug Success):** If any seeded bug B01–B10 achieves oracle success on $\ge 1$ seed out of 10 eval seeds, KILL the parameter configuration. Increase perturbation magnitude (e.g. increase z-drop from +6 cm to +10 cm, xy-offset from +3 cm to +5 cm) until oracle FAIL is 10/10 seeds.
- **TRIPWIRE-4 (AV1 Ingest Rejection):** If `io/lerobot.py` attempts to output AV1 video or non-`yuv420p` MP4s, KILL the output step. Automated transcode via `ffmpeg` to 30 fps (sim) or 15 fps (DROID) H.264 `yuv420p` is mandatory.
- **TRIPWIRE-5 (Un-tagged Pool Generation):** If P02.S07 pool generation launches without git tag `prereg-v0` existing on the commit containing `experiments/PREREGISTRATION.md` and `experiments/pool_config.yaml`, KILL the job immediately.

### 6. Top Risks, Mitigations & Fallbacks
1. **Risk 1: Host Environment Partition Failure (Windows vs. Modal).**
   - *Mitigation:* `sim/env.py` must define a `BaseSimEnv` interface with dual implementations: `ManiSkillEnv` (Modal L4 Linux) and `MockSimEnv` (pure Python NumPy kinematic simulation producing valid state `.npz`, synthetic MP4 via OpenCV/ffmpeg, and oracle states).
   - *Fallback:* If Modal execution is blocked by credentials, `MockSimEnv` unblocks local span-logging, bug testing, and contract verification without violating Law 1 (`is_fixture: true`).
2. **Risk 2: Code Span Lineage & Path Resolution Failure across OSs.**
   - *Mitigation:* `sim/spans.py` must normalize all paths relative to repository root (`os.path.relpath(path, repo_root).replace('\\', '/')`) and use Python `ast` node inspection to resolve function calls and statements rather than fragile raw line counts.
   - *Fallback:* Regex matching against known robot API verbs (`arm.move_to`, `gripper.open/close`, `wait`).
3. **Risk 3: Privileged State Leakage to Downstream Proof Judges.**
   - *Mitigation:* Physical isolation of pool files. Video files `ep_{id}.mp4` contain ONLY raw RGB pixels. Privileged state `.npz` and `manifest.parquet` are stored separately and blocked from judge input signatures.
   - *Fallback:* Automated unit test `tests/proof/test_data_isolation.py` enforcing that judge runners accept only `video_path: Path`.
4. **Risk 4: Hero-Clip Search Misses Clean Failures in DROID.**
   - *Mitigation:* Target explicit failure keywords in DROID and SO-100 datasets ("drop", "miss", "slip", "empty") requiring $|m| \ge 3\sigma$.
   - *Fallback:* Use the verified ManiSkill3 simulated hero clip (`B01` early release) badged `[SIM · ManiSkill3 30 fps]` as an immediate backup candidate.
5. **Risk 5: LeRobot Full Dataset Download Freezes Sandbox / Disk.**
   - *Mitigation:* Avoid downloading full multi-gigabyte repo archives. Stream single episode parquets/videos using `hf_hub_download` or slice metadata first.
   - *Fallback:* Commit 5 verified golden fixture clips in `tests/fixtures/clips/` for 100% offline testing.

### 7. Proposed Approach & Structural Guardrails
1. **Dual Environment Wrapper:** Implement `src/Kodiac_robotics/sim/env.py` with `BaseSimEnv`, providing `ManiSkillEnv` for Modal L4 and `MockSimEnv` for local Windows testing.
2. **Deterministic Bug Registry:** Implement `src/Kodiac_robotics/sim/bugs.py` and 10 patch files `examples/sim/bugs/B01.patch` ... `B10.patch`, enforcing 100% oracle FAIL across 10 seeds.
3. **AST-Grounded Span Logger:** Implement `src/Kodiac_robotics/sim/spans.py` with repo-relative normalized paths and AST statement resolution.
4. **Pre-Registration Tagging:** Commit `experiments/PREREGISTRATION.md` and `experiments/pool_config.yaml`, creating git tag `prereg-v0` before pool generation starts.
5. **Compute-Capped Pool & Policy Training:** Implement `src/Kodiac_robotics/proof/pool.py` and `modal/proof_train.py` enforcing $\le 15$ min training time and scale-to-zero.
6. **Transcoding LeRobot Loader:** Implement `src/Kodiac_robotics/io/lerobot.py` with automatic `ffmpeg` transcoding of AV1 to H.264 `yuv420p` at native fps.

### 8. Interface Contracts
```python
# sim/spans.py
from pydantic import BaseModel
from typing import Literal

class SpanRecord(BaseModel):
    span_id: str
    file: str                     # Repo-relative forward-slash path, e.g. "examples/sim/pick_place.py"
    line: int                     # 1-based line number in file
    func: str                     # e.g. "gripper.open"
    code: str                     # e.g. "gripper.open()"
    actuation_class: Literal["grasp", "release", "transport", "reach", "wait"]
    step_start: int               # Simulation control step index
    step_end: int
    t_start_s: float
    t_end_s: float

# sim/bugs.py
class BugDefinition(BaseModel):
    bug_id: str                   # e.g. "B01"
    name: str                     # e.g. "early_release"
    description: str
    patch_path: str               # "examples/sim/bugs/B01.patch"
    expected_blame_predicate: str # e.g. "moves_with"
    expected_failed_step: int     # e.g. 2
    oracle_fails_all_seeds: bool  # must be True for 10/10 seeds
```

### 9. Proposed Task DAG & File Ownership
- **T01 (IMPL-1):** Sim Environment Wrapper & Span-Logged Robot API.
  - *Owns:* `src/Kodiac_robotics/sim/env.py`, `src/Kodiac_robotics/sim/robot.py`, `src/Kodiac_robotics/sim/spans.py`, `examples/sim/pick_place.py`, `tests/sim/test_env.py`.
- **T02 (IMPL-1):** Seeded Physical Bug Registry B01–B10 & Deterministic Assertions.
  - *Owns:* `src/Kodiac_robotics/sim/bugs.py`, `examples/sim/bugs/**`, `tests/sim/test_bugs.py`.
- **T03 (IMPL-2):** Pre-registration Protocol, Practice Pool Generator & $\pi_0$ Baseline Training.
  - *Owns:* `experiments/PREREGISTRATION.md`, `experiments/pool_config.yaml`, `src/Kodiac_robotics/proof/**`, `modal/proof_train.py`, `tests/proof/**`.
- **T04 (IMPL-3):** LeRobot Ingest, AV1 Transcoding, Hero-Clip Search, DROID Labeling Tool & Fixtures.
  - *Owns:* `src/Kodiac_robotics/io/lerobot.py`, `scripts/find_hero_clips.py`, `scripts/label_tool.py`, `tests/fixtures/clips/**`, `docs/DEMO_FILMING_GUIDE.md`, `tests/io/test_lerobot.py`.

*DAG Constraints:*
- T01 prerequisite for T02.
- `git tag prereg-v0` in T03 prerequisite for launching background pool generation.
- T01, T03, T04 run concurrently across disjoint directories.

### 10. Improvement Proposals
- **IP-P02-D3-1: Dual-Mode Sim Architecture (`ManiSkillEnv` on Modal vs `MockSimEnv` on Host).**
  - *Change:* Formalize `BaseSimEnv` in `sim/env.py` allowing pure-Python kinematic mock execution locally on Windows without Vulkan/SAPIEN, while `ManiSkillEnv` runs inside Modal L4 containers.
  - *Evidence:* SAPIEN and ManiSkill missing locally; Windows headless Vulkan fails without GPU.
  - *Impact:* Prevents 100% blocker on local Windows development, ensures fast offline CI.
  - *Cost:* 0.5 agent-hours.
- **IP-P02-D3-2: Mandatory Bug B01–B10 Seeded Determinism Assertion.**
  - *Change:* In `tests/sim/test_bugs.py`, assert that every bug B01–B10 produces an oracle `FAIL` across 10/10 seeds. Any accidental pass fails the build.
  - *Evidence:* Physical bouncing dynamics can accidentally settle cubes within tolerance.
  - *Impact:* Guarantees rock-solid reliability for Muse Code `/goal` unedited take in P07.
  - *Cost:* 0.5 agent-hours.
- **IP-P02-D3-3: Enforce Policy Training Hard Cap of $\le 15$ min/run on Modal L4.**
  - *Change:* In `experiments/pool_config.yaml` and `PREREGISTRATION.md`, strictly cap policy retraining to $\le 15$ minutes per run ($\le 20\text{k}$ gradient steps) on L4, using state-based MLP or lightweight Diffusion Policy.
  - *Evidence:* 30+ retraining runs in P08 would exhaust the $100 Modal credit if runs exceed 30–60 minutes.
  - *Impact:* Saves >$30 compute, protects Nov 2 go/no-go schedule.
  - *Cost:* 0.2 agent-hours.

### 11. Confidence
- **Score:** 88 / 100
- **Reason:** Hard environmental constraints (Windows, no GPU, missing sim packages, AV1 codec, Modal budget limits) have been rigorously measured and isolated into an unassailable cloud/local partitioned architecture. With automated determinism assertions and compute caps, Phase P02 execution risk is fully mitigated.

## R2: Stress tests
### D1 → D2, D3
[2026-10-28T10:52:00Z · D1]

#### 1. D1 → D2 (Judge Advocate Critique)

- **On IP-P02-D2-1 (Hero-Clip Curation Protocol & Angle Scoring):**
  - *Vulnerability (Premature Complexity & Model Leakage):* D2 mandates that `scripts/find_hero_clips.py` compute a camera elevation score (30°–50°) and visual contrast score. However, in Phase P02, no camera extrinsics calibration module exists (Tier B scale model lands in P04), and no perception model is loaded locally. Asking S11 to compute 3D camera angles or segmentation contrast from raw video forces implementers to either write fragile ad-hoc heuristics or attempt to load vision models that fail offline. Furthermore, DROID camera angles are fixed exterior tripod mounts whose elevations vary per scene.
  - *Failure Scenario:* S11 crashes trying to compute geometric metrics on uncalibrated DROID frames, or pulls multi-gigabyte full dataset archives into the local sandbox, hitting disk or timeout limits.
  - *Architectural Resolution:* Simplify S11 to purely metadata-driven discovery: filter task strings (`pick`, `place`, `stack`, `drawer`) and episode durations ($\le 20\text{ s}$), download *single episode clips* via `huggingface_hub.hf_hub_download`, extract first/last frames and 500ms preview clips, and output a structured Markdown index (`artifacts/p02/hero_candidates/index.md`) for human inspection. Leave metric camera estimation to P04.

- **On IP-P02-D2-2 (Pre-registration Parquet Metadata & OpenTimestamps):**
  - *Vulnerability (Tool Availability & Circular Dependency):* D2 mandates running `ots stamp experiments/PREREGISTRATION.md` and embedding `prereg_commit_sha` into `manifest.parquet`. But hard evidence from D3's recon confirms `ots` is NOT installed on the host, and sandboxed execution blocks outbound network access to public Bitcoin calendar servers. Additionally, embedding a git commit SHA inside a file before committing creates an impossible circular dependency.
  - *Failure Scenario:* Pool generation pipeline blocks at GATE attempting to invoke non-existent `ots` executable, or records stale/fabricated commit hashes.
  - *Architectural Resolution:* Ground pre-registration integrity in Git-native mechanics: (1) `experiments/PREREGISTRATION.md` and `experiments/pool_config.yaml` are committed and tagged `prereg-v0`; (2) `proof/pool.py` reads disk content sha256 (`config_sha256`, `prereg_sha256`) and records them in Parquet table metadata alongside `prereg_tag: "prereg-v0"`; (3) `ots stamp` is classified as an optional, non-blocking post-push human step outside the sandbox.

- **On IP-P02-D2-3 (Randomized A/B Telemetry in `scripts/label_tool.py`):**
  - *Vulnerability (Data Contamination & Missing Blame Engine):* D2's A/B timing tool risks contaminating the blind benchmark. If the 200-episode DROID evaluation slice is presented in `blame` mode, annotators see $t^*$ and the failure explanation, permanently biasing their labels for the blind benchmark. Furthermore, Kodiac's blame engine does not exist in P02 (built in P06), so real-footage blame overlays cannot be generated yet.
  - *Failure Scenario:* Annotators' ground truth labels in `droid_slice.jsonl` are contaminated by early blame hints, destroying the validity of Benchmark P-3.
  - *Architectural Resolution:* Strictly partition the data streams:
    1. Blind benchmark slice (`droid_slice_<annotator>.jsonl`) is strictly plain video only (zero hints, zero blame overlays).
    2. Time-saved study runs on a completely separate calibration/audit set ($\ge 40$ episodes) where mock/simulated blame records exist.
    3. The labeling tool loads pre-rendered mock overlays (`f{t_star}_overlay.png` + one-line text) to validate the timing telemetry interface in P02 without needing a live blame engine.

---

#### 2. D1 → D3 (Red Team Critique)

- **On IP-P02-D3-1 (Dual-Mode Sim Architecture & Interface Protocol):**
  - *Agreement & Vulnerability (Behavioral Drift between Mock and Real Sim):* D1 and D3 strongly agree on the necessity of a local `MockSimEnv` to solve the Windows/no-GPU constraint. However, D3 proposes an abstract base class `BaseSimEnv` and does not define drift-prevention mechanics. If `MockSimEnv` uses an arbitrary kinematic formula that drifts from ManiSkill3 physics, code written in `examples/sim/pick_place.py` or bugs B01–B10 will pass locally but fail on Modal L4 (or vice-versa).
  - *Failure Scenario:* Implementer IMPL-1 builds pick-and-place logic against `MockSimEnv` that passes unit tests, but when deployed to Modal L4 GPU, ManiSkill's motion planner or contact physics drops the cube or fails trajectory timing.
  - *Architectural Resolution:*
    1. Define `SimEnv` as a strict `typing.Protocol` (not ABC) to maintain lightweight structural subtyping.
    2. `MockSimEnv` must not be a dummy stub; it must be an analytic kinematic digital twin implementing the identical Franka Panda workspace limits, $4.0\text{ cm}$ cube dimensions, 120Hz/30Hz step timing, and identical oracle tolerance check (`align_xy_cm <= 3.33, gap_cm <= 0.5`).
    3. Add cross-validation test `tests/sim/test_env_parity.py` verifying that state trajectories and oracle verdicts match across both backends on the reference seeds.

- **On IP-P02-D3-2 (Bug Determinism Assertion & Magnitude Inflation):**
  - *Vulnerability (Trivializing the Benchmark by Over-Perturbation):* D3 proposes that if any bug B01–B10 passes on any seed due to physics bouncing, we should "increase perturbation magnitude (e.g. drop from +6 cm to +10 cm, xy-offset from +3 cm to +5 cm) until oracle FAIL is 10/10". But artificially inflating bug magnitudes turns subtle, realistic near-misses into cartoon failures. A robot dropping a cube from 50 cm is trivial for any coarse VLM to detect; Kodiac's competitive edge (F42) is detecting subtle, borderline physical failures (e.g. 3.0 cm offset, early release by 0.4s).
  - *Failure Scenario:* Planted bugs become too coarse, diluting our technical depth claim and weakening our proof that Kodiac catches failures that coarse reward models miss.
  - *Architectural Resolution:* Keep physical perturbations realistic, but eliminate physics bouncing false-passes by enforcing a settling velocity check: evaluate oracle success only after a mandatory 0.5 s dwell window with cube linear velocity $< 0.01\text{ m/s}$. If a cube bounces or tumbles, its settlement position deterministically violates `align_xy_cm <= 3.33` or `gap_cm <= 0.5`.

- **On IP-P02-D3-3 (Hard Cap of $\le 15$ min Policy Training on Modal):**
  - *Vulnerability (Under-Trained Degenerate Policy):* D3 proposes a rigid $\le 15\text{ min}$ wall-clock limit ($\le 20\text{k}$ steps) for $\pi_0$ training. But if 15 minutes of state Diffusion Policy achieves only 0%–5% success (under-trained, fails to pick), the pool generator will produce 100% complete failures and zero policy near-misses!
  - *Failure Scenario:* The practice pool lacks realistic policy near-misses, compromising downstream retraining in P08.
  - *Architectural Resolution:* Enforce a budget cap in *GPU-hours* ($\le 12$ GPU-hours proof budget total, or $\le 20$ min per run), but prioritize policy convergence:
    1. In S06, log checkpoints at 5k, 10k, 15k, 20k steps. Evaluate oracle success across 50 episodes at each checkpoint.
    2. If Diffusion Policy denoising is too slow, switch to Action Chunking with Transformers (ACT) or Flow Matching (10 steps), which train in ~10 minutes on state data and reliably hit the 30%–60% success target.
    3. The ~30% perturbed-expert near-misses serve as our guaranteed floor for subtle failures, so policy training variance cannot break the pool.

- **On Task DAG Structure (4 tasks vs. 3 tasks):**
  - *Vulnerability:* D3 proposes 4 tasks (T01 and T02 both owned by IMPL-1). This violates AGENTS.md §8.1 Rule 1 ("One task card per implementer. Implementers do not share tasks").
  - *Architectural Resolution:* Maintain D1's 3-task DAG with 3 implementers:
    - `T01` (IMPL-1): Sim Environment, `@span` Logger, `pick_place.py` & B01–B10 Bugs (S01–S05).
    - `T02` (IMPL-2): Pre-Registration, $\pi_0$ Policy, Proof Pool Generator & Baselines (S06–S09, S13, S13b, S16).
    - `T03` (IMPL-3): LeRobot Loaders, Hero-Clip Search, Labeling Tool & Fixtures (S10–S12, S14, S15).
    This keeps `owns_paths` strictly disjoint and respects team protocol.
### D2 → D1, D3
[2026-10-28T10:55:00Z · D2]

#### 1. D2 Attacks on D1 (Architect)
- **Attack 1 (Honesty & Invariants I13/I15 — The "Kinematic Mock" Credibility Trap):**
  - *Vulnerability:* D1 proposes `KinematicMockEnv` (IP-P02-D1-1) for local host CI and unit tests. From a hackathon judge's perspective (especially J1 FAIR perception and J2 robotics), if any clip generated by `KinematicMockEnv` leaks into a demo video, audit card, or README without an indelible visual badge, a skeptical judge will dismiss the entire project as "synthetic toy animations" and suspect we faked the physics engine.
  - *Failure Scenario (Pre-Mortem):* In P07 or P09, a developer renders an unedited `/goal` take or quick GIF using `KinematicMockEnv` because it rendered in 2 seconds. The judge inspects `meta.json` or observes rigid-body translation with zero contact compliance/penetration dynamics, concluding Kodiac faked the physical robot simulation.
  - *Mandatory Fix:* `SimEnv` must enforce that `KinematicMockEnv` outputs strictly write `is_mock: true`, `env_backend: "kinematic_mock"`, and burn a permanent visual header `[MOCK SIMULATION · NOT SAPIEN PHYSICS]` on rendered MP4 frames. Production pool data and proof benchmark rollouts must ONLY be accepted from `ManiSkillEnv` (Modal L4).
- **Attack 2 (Demo Beat Alignment — Connecting S01–S05 to Beats C1 & C5):**
  - *Vulnerability:* D1's S01–S05 specifies `pick_place.py` and B01–B10 bugs, but fails to define how these artifacts directly feed the 3-minute video (Beat C5: Muse Code `/goal` unedited take) and README hero diffs.
  - *Failure Scenario:* B01–B10 are written as dry unit-test scripts with minimal console logging. In P07, Muse Code calls `Kodiac.verify`, but the terminal output and span blame are sterile, lacking human-readable physical explanations or visual side-by-side diffs.
  - *Mandatory Fix:* Every bug in `sim/bugs.py` must define a canonical `hero_manifest` entry specifying the exact spoken instruction it violates, the expected visual blame overlay frame, and a human-readable diagnosis sentence (e.g., `B01: "gripper opened 0.4 s before reaching target; dropped red cube 5.2 cm above table"`).
- **Attack 3 (Task DAG Bottleneck — Unnecessary Sequential Coupling):**
  - *Vulnerability:* D1 marks T02 as `depends_on: [T01]`. If IMPL-2 sits blocked waiting for IMPL-1 to finish the entire simulation wrapper, robot API, and 10 bug patches, we lose 4–6 hours of pipeline concurrency!
  - *Failure Scenario:* IMPL-1 hits a debugging snag in Panda motion-planning or PyAV encoding. IMPL-2 is completely idle, delaying `PREREGISTRATION.md` drafting and the baseline judge spike.
  - *Mandatory Fix:* Decouple T02 from T01. IMPL-2 must immediately draft `experiments/PREREGISTRATION.md`, build `proof/appearance.py`, and implement `modal/proof_train.py` using contract interfaces (`SimState`, `SimRun`). T02 only consumes T01 at the final execution step of pool generation.

#### 2. D2 Attacks on D3 (Red Team)
- **Attack 1 (Judge Simulation & Invariant I8 — The Collapsed Policy Danger in IP-P02-D3-3):**
  - *Vulnerability:* D3 proposes a strict $\le 15$ min/run training cap (IP-P02-D3-3) on Modal L4 to conserve credit. While fiscal prudence is essential, **the entire hackathon hangs on Invariant I8: "+Y points of success."**
  - *Failure Scenario (Pre-Mortem):* State-based Diffusion Policy or 2-layer MLP capped at $\le 15$ minutes fails to converge on `StackCube-v1`. Downstream policy success collapses to ~5% across ALL arms (Oracle, Kodiac, Spark, Robometer). The proof chart in P08 shows a flat, statistically insignificant line ($+0.02 \pm 0.04$). Judge J2 (robotics researcher) immediately identifies the under-trained policy and writes: *"The downstream retraining proof is an artifact of a policy that never learned the task; the judge differences are noise."*
  - *Mandatory Fix:* Do not cap training by raw minutes alone; calibrate by **demonstration efficiency and convergence curve**. In S06, verify that the reference policy trained on 50 clean expert demos reaches $\ge 70\%$ oracle success. Then, for the practice pool retraining, tune the architecture (e.g., lightweight Diffusion Policy with DDIM 10-step inference or 3-layer MLP with LayerNorm) so it reaches meaningful task learning ($>40\%$ on clean data) within the budget. If 15 min is insufficient, allocate 20 min per run and cut lower-priority runs (e.g. drop 1 seed or 1 baseline dose). Never sacrifice policy competence for budget crumbs.
- **Attack 2 (Honesty & Invariant I13/I15 — Strict Data Provenance and Watermarking):**
  - *Vulnerability:* D3 highlights host environment constraints and dataset codecs, but does not provide a strict labelling protocol for separating real public robot footage (DROID, LeRobot) from simulation (ManiSkill3).
  - *Failure Scenario:* In the dataset audit (P08) or hosted demo (P09), a judge uploads a video or views an audit card. The metadata does not make crystal clear whether the episode came from real physical hardware or ManiSkill. The judge suspects Kodiac is evaluating sim data and claiming it's real robot footage, instantly triggering Kill-Shot 1 (Law 1 violation).
  - *Mandatory Fix:* Enforce that every `Clip` and `RunResult` generated in P02 embeds an immutable `source_kind: Literal["real", "sim", "mock", "upload"]` and dataset provenance (`dataset_name`, `repo_id`, `camera_key`). In the UI, real clips must display a solid badge `REAL · [DATASET]`, while sim clips display `SIMULATION · ManiSkill3` (or `SIMULATION · MOCK`).
- **Attack 3 (Hero Clip Fallback Feasibility in Risk 4):**
  - *Vulnerability:* D3 suggests in Risk 4 fallback: *"Use the verified ManiSkill3 simulated hero clip (B01 early release) badged [SIM · ManiSkill3 30 fps] as an immediate backup candidate."*
  - *Critique:* As Judge Advocate, I must strongly warn: **Starting the video with a simulation clip drops Video Beat C1 from a 9.5 to a 7.0!** The entire hook of the 3-minute video (0:00–0:12) is: *"Real public robot episodes published as successful demonstrations freeze at the exact failure frame."* If we open with a Panda arm in SAPIEN simulation, judges will say "just another sim project."
  - *Mandatory Fix:* The fallback for DROID low-res must NOT be simulation. It must be **real teleoperated robot footage from HuggingFace LeRobot community datasets** (e.g., `lerobot/aloha_mobile_cabinet`, `lerobot/so100_pick_place` recorded at 720p/1080p). Simulation is strictly reserved for Beat C5 (Muse Code `/goal`) and Beat C6 (retraining chart).
### D3 → D1, D2
*[2026-10-28T11:15Z · D3]*

#### 1. Stress Tests on D1 Architect (D3 → D1)

- **Stress Test 1.1: The "Causal Lag" Trap in `find_blame_span` (Live-Demo Fragility & Invariant I4 Violation).**
  - *Failure Scenario:* In physics simulation, actuation precedes the physical separation event. At frame 100 ($t=3.33$ s), `gripper.open()` executes with span duration of 1 control step (0.033 s, $[100, 101]$). The cube falls under gravity and bounces away from the gripper, causing `moves_with` to break at frame 114 ($t^*=3.80$ s, 0.47 s later). If D1's proposed `find_blame_span(spans, frame_idx=114)` executes a naive interval check ($t^* \in [\text{step\_start}, \text{step\_end}]$), frame 114 falls inside the *subsequent* actuation (e.g. `arm.move_to("above", "green_block")` or `wait(0.5)`). Kodiac would blame `arm.move_to` for an early drop! This violates Invariant I4 ("measured physical cause, not adjectives") and completely destroys our live demo credibility.
  - *Proposed Fix:* `find_blame_span` must NOT be a naive interval containment query. It must search backward from $t^*$ for the *latest causal actuation matching the broken predicate* within a causal window ($\Delta t \le 1.0$ s). For `moves_with` T$\to$F, it must resolve the latest `gripper.open()`.

- **Stress Test 1.2: `inspect.stack()` Performance & Bytecode Failure in Containers.**
  - *Failure Scenario:* D1 proposes using `inspect.stack()` in `@span` on every robot API call. In containerized environments (Modal), under pytest runners, or when executing pre-compiled bytecode (`.pyc`), `inspect.stack()` frequently returns `None` for `frame.code_context`, causing `AttributeError` or blank code lines. Furthermore, full stack inspection has a ~5–10 ms overhead per invocation; across a 600-step episode rollout, repeated stack inspection adds 3–6 seconds of pure overhead per episode, increasing Modal pool generation costs by ~25%.
  - *Proposed Fix:* Replace `inspect.stack()` with `sys._getframe(1)` (100× faster). Normalize `f_code.co_filename` to repo-relative paths (`examples/sim/pick_place.py`). Provide fallback line extraction via `linecache.getline()` and AST parsing if `code_context` is empty.

- **Stress Test 1.3: Task DAG Imposes an Unnecessary Blocking Bottleneck on T02.**
  - *Failure Scenario:* D1's task DAG specifies `T02 depends_on: [T01]`. This forces IMPL-2 to sit completely idle while IMPL-1 builds S01–S05 (`SimEnv`, robot API, bug patches). Pre-registration (`PREREGISTRATION.md`), pool distribution configuration (`pool_config.yaml`), and Modal training boilerplate (`modal/proof_train.py`) do NOT require a running simulation wrapper to write and verify. Blocking T02 wastes ~4 hours of agent concurrency.
  - *Proposed Fix:* Decouple T02. IMPL-2 must dispatch immediately in parallel with T01, drafting `PREREGISTRATION.md` and setting up the Modal infrastructure. Only the live rollout generation step in S07 requires T01's completed simulation environment.

- **Stress Test 1.4: Frame Rate & Timestamp Drift in Video Encoding.**
  - *Failure Scenario:* D1 proposes using `sim/video.py` via OpenCV `VideoWriter` or direct CLI pipes. If the video writer uses variable frame rate (VFR) or fails to lock timestamps to exactly 30.000 fps, SAM 3.1 (which decodes at nominal fps) will suffer a 2–5 frame drift relative to simulation step time $t = \text{step} / 30.0$. At frame 114, SAM's mask will align with step 110 or 118, creating discrepancy in blame timestamp $t^*$.
  - *Proposed Fix:* Enforce strict Constant Frame Rate (CFR) in `sim/video.py` using `ffmpeg` parameters `-vsync cfr -r 30 -pix_fmt yuv420p -c:v libx264`. Unit test must assert that `n_frames == total_control_steps` exactly.

---

#### 2. Stress Tests on D2 Judge Advocate (D3 → D2)

- **Stress Test 2.1: The Multi-Gigabyte DROID Download Trap (IP-P02-D2-1).**
  - *Failure Scenario:* D2's proposal IP-P02-D2-1 mandates scanning public DROID and LeRobot datasets to produce high-resolution candidate cards. The full DROID dataset exceeds 1 TB, and even `droid_100` is $>10$ GB. In our sandboxed development environment, outbound network access to HuggingFace is blocked (os error 10013). If IMPL-3 attempts to run bulk dataset downloads locally, the task will hang, exhaust disk space, or fail with connection timeouts.
  - *Proposed Fix:* Impose strict isolation: all remote dataset scanning for hero candidates must run inside Modal containers (`modal/hero_search.py`), saving only the lightweight candidate thumbnails and short 5-second MP4 clips to `artifacts/p02/hero_candidates/`. Local host tests must operate 100% offline using `tests/fixtures/clips/`.

- **Stress Test 2.2: Hard Failure on Missing `ots` Executable (IP-P02-D2-2).**
  - *Failure Scenario:* D2 proposes running `ots stamp experiments/PREREGISTRATION.md` as an exit criterion for `prereg-v0`. Hard evidence gathered in R0 confirms: `ots` (OpenTimestamps) is NOT installed on the host system. Requiring `ots` execution will immediately fail the Phase P02 exit gate.
  - *Proposed Fix:* Demote `ots stamp` from a blocking gate requirement to an optional best-effort background action. The immutable cryptographic receipt is the git commit SHA and signed git tag `prereg-v0` pushed to GitHub before any judge labels are generated.

- **Stress Test 2.3: Scope Creep & Over-Engineering on A/B Timing Tool (IP-P02-D2-3).**
  - *Failure Scenario:* D2 proposes an elaborate HTML/JS labeling tool with randomized presentation orders, millisecond telemetry, and local storage logging. P02 already has 16 complex steps. If IMPL-3 spends 4+ hours building a frontend web application, debugging browser state, and styling UI, we risk blowing the P02 deadline. Judges will never inspect the internal implementation of `scripts/label_tool.py`; they only evaluate the resulting `time_saved.json` proof metric.
  - *Proposed Fix:* Apply the Simplest-Alternative Test (Stress-Test Toolkit #6). Build a minimal, self-contained single-file HTML page with embedded vanilla JS (or a rich CLI terminal tool) that directly appends timing records to `experiments/labels/timing_<annotator>.jsonl`. Strictly cap IMPL-3 effort on this tool to $\le 1.0$ hour.

- **Stress Test 2.4: Seeded Bug Parameter Fragility on Contact Mechanics.**
  - *Failure Scenario:* D2 endorses B01–B10 bug patches without addressing physical bounce dynamics. In particular, B10 (release z +6 cm) and B02 (xy offset +3 cm) can occasionally settle into a valid stacked position if restitution or cube contact friction bounces the cube back onto the base cube. If even 1 seed out of 10 eval seeds reports oracle PASS, the test suite or Muse Code loop will fail.
  - *Proposed Fix:* Enforce that all bug patches in `sim/bugs.py` must be verified against 10/10 seeds with an automated assertion in `tests/sim/test_bugs.py` asserting `oracle_success == False`. If any seed bounces into success, increase the perturbation magnitude (e.g. B10 release z +10 cm, B02 xy offset +5 cm).

## R3: Converged plan (draft by D1)
[2026-10-28T11:20:00Z · D1]

The council (D1 Architect, D2 Judge Advocate, D3 Red Team) has fully converged on the execution plan for Phase P02. All members agree that the physical simulation and real-robot data backbone must be delivered with zero compromise on Law 1 (no faking), Invariant I8 (pre-registered retraining proof), Invariant I4 (exact onset $t^*$ and measured cause), and strict host-isolation boundaries between local Windows CPU development and Modal L4 GPU execution.

### 1. Ordered Steps (P02.S01–S16)

1. **S01–S03 (Sim Env, Video Writer, Robot API & Spans):**
   - Implement `src/Kodiac_robotics/sim/env.py` conforming to the frozen `SimEnv` Protocol with two backends:
     - `KinematicMockEnv`: Local Windows CPU simulation. Generates analytic kinematic Panda + StackCube motion, deterministic 30 fps frames, privileged state `.npz`, and oracle checks. Automatically burns a permanent visual header `[MOCK SIMULATION · NOT SAPIEN PHYSICS]` on frames and sets `is_mock: true` in metadata.
     - `ManiSkillEnv`: Production SAPIEN physics wrapper executed on Modal L4 with CUDA/Vulkan for pool generation and reference benchmarks.
   - Enforce Constant Frame Rate (CFR) 30.0 fps H.264 `yuv420p` in `sim/video.py` using `ffmpeg` CLI (`-vsync cfr -r 30 -pix_fmt yuv420p -c:v libx264`).
   - Implement robot API in `sim/robot.py` (`arm.move_to()`, `arm.lift()`, `arm.retract()`, `gripper.open()`, `gripper.close()`, `wait()`).
   - Implement `@span` in `sim/spans.py` using fast `sys._getframe(1)` with repo-relative normalized paths (`os.path.relpath`) and AST statement resolution.
   - Implement `find_blame_span(spans, frame_idx, broken_predicate)` with a causal lookback window ($\Delta t \le 1.0\text{ s}$) so physical separation lag maps to the correct preceding actuation.

2. **S04–S05 (Pick-and-Place Reference & Bug Registry B01–B10):**
   - Deliver `examples/sim/pick_place.py`: Verified 10/10 seeds oracle PASS.
   - Implement `src/Kodiac_robotics/sim/bugs.py` and 10 patch files `examples/sim/bugs/B01.patch` … `B10.patch`.
   - Prevent physics bouncing false-passes by enforcing a settling velocity check ($v_{\text{linear}} < 0.01\text{ m/s}$ over a 0.5 s dwell window) before checking `oracle_success()`.
   - Enforce deterministic test `tests/sim/test_bugs.py` asserting 10/10 seeds oracle FAIL for every bug.
   - Each bug registers a `HeroBugManifest` with the violated spoken instruction and human-readable diagnostic sentence for Beat C5.

3. **S06–S09 (Pre-Registration, $\pi_0$ Policy & Pool Generation):**
   - S08 (First Priority): Draft `experiments/PREREGISTRATION.md` specifying hypotheses H1–H3, oracle-matched thresholds (`align_xy_cm <= 3.33, gap_cm <= 0.5`), CAN'T TELL = not accepted rule, fixed gradient steps, and stopping rules. Commit and create git tag `prereg-v0`.
   - S09: Author `examples/stackcube.green` (matching prereg tolerances) and `examples/stack_blocks.green` (spec standard).
   - S06: Benchmark $\pi_0$ policy pipeline in `proof/pi0.py` and `modal/proof_train.py` on Modal L4. Evaluate checkpoints at 5k, 10k, 15k, 20k steps. Target 30%–60% oracle success on 100 eval episodes with a hard compute cap of $\le 20$ min per run.
   - S07: 🔁 Practice pool generator (`proof/pool.py`): ~70% $\pi_0$ rollouts + ~30% perturbed-expert near-misses. Generates 600–1,000 episodes into `gl-pool` volume. Embeds `config_sha256`, `prereg_sha256`, and `prereg_tag: "prereg-v0"` into Parquet metadata. Written in 100-episode shards for resumability.

4. **S10–S12, S14–S16 (Dataset Loaders, Hero Clips, Labeling Tool & Fixtures):**
   - S10: Implement `src/Kodiac_robotics/io/lerobot.py`: `lerobot://repo/episode[/camera]` loader with automatic ffmpeg transcoding of AV1 to H.264 `yuv420p` at native fps (15 fps for DROID). Single-episode download via `hf_hub_download` (no full-repo downloads).
   - S11: Implement `scripts/find_hero_clips.py` and Modal runner `modal/hero_search.py`. Scans DROID and LeRobot public teleop datasets (SO-100 pick/place) using metadata filters (`pick`, `place`, `stack`, duration $\le 20\text{ s}$). Exports candidate cards, thumbnails, and 5s MP4 clips to `artifacts/p02/hero_candidates/index.md`. Real robot footage only.
   - S12: Prepare real-footage benchmark: DROID slice manifest (~200 episodes). Build minimal single-file HTML/JS labeling tool (`scripts/label_tool.py`) with randomized A/B telemetry (`scrub` vs `blame`). Strict dataset separation: blind benchmark slice is plain video only; timing study uses a separate $\ge 40$ episode audit set with mock blame overlays.
   - S13/S13b: Baseline judge spikes on Modal L4: Robometer-4B, TOPReward, and single-pass Muse Spark 1.3 (2 fps whole clip).
   - S14: Assemble golden fixture clip suite in `tests/fixtures/clips/` ($\le 2\text{ MB}$ each: correct, B1, B2, B9, occluded) with sha256 checksums for 100% offline CI.
   - S15: Verify `docs/DEMO_FILMING_GUIDE.md` against P04/P05 requirements.
   - S16: Build appearance benchmark dataset in `proof/appearance.py` ($\ge 60$ clips: ManiSkill drawer flush vs ajar + DROID drawer episodes).

---

### 2. Task DAG (Full Parallelism, Width = 3)

All three task cards are completely decoupled and dispatched **in the same turn (parallel)**.

```
       [Start P02 Dispatch]
         │          │         │
         ▼          ▼         ▼
       ┌────┐     ┌────┐    ┌────┐
       │T01 │     │T02 │    │T03 │
       └────┘     └────┘    └────┘
         │          │         │
         │          ▼         │
         │     prereg-v0 tag  │
         │          │         │
         │          ▼         │
         │     Launch BG-A    │
         │     (Modal Pool)   │
         │          │         │
         ▼          ▼         ▼
       [Integrate & Merge to phase/p02-data-sim]
                    │
                    ▼
            [P02 Exit Gate]
```

- **T01 (IMPL-1): Sim Environment, `@span` Logger, `pick_place.py` & B01–B10 Bugs (S01–S05)**
  - *owns_paths:* `[src/Kodiac_robotics/sim/**, examples/sim/**, tests/sim/**]`
  - *reads_only:* `[src/Kodiac_robotics/contracts/**, ARCHITECTURE.md §4, §5.7, §10]`
  - *depends_on:* `[]`
  - *DoD:* `SimEnv` dual-backend operational; `pick_place.py` passes 10/10 seeds; B01–B10 patches pass tests asserting 10/10 oracle FAIL with settling checks; `@span` logger captures normalized lines; `tests/sim/` green.

- **T02 (IMPL-2): Pre-Registration, $\pi_0$ Policy, Proof Pool Generator & Baselines (S06–S09, S13, S13b, S16)**
  - *owns_paths:* `[src/Kodiac_robotics/proof/**, modal/proof_*.py, experiments/**, examples/stackcube.green, examples/stack_blocks.green, tests/proof/**]`
  - *reads_only:* `[src/Kodiac_robotics/contracts/**, src/Kodiac_robotics/sim/spans.py, ARCHITECTURE.md §5.7]`
  - *depends_on:* `[]` (Starts `PREREGISTRATION.md`, `.green` specs, and Modal scaffolding immediately in parallel; links to `SimEnv` at rollout step).
  - *DoD:* `PREREGISTRATION.md` tagged `prereg-v0`; `modal/proof_train.py` verified; `proof/pool.py` generated/launched on Modal with sharded Parquet manifest; baseline spikes recorded; appearance benchmark assembled.

- **T03 (IMPL-3): LeRobot Loaders, Hero-Clip Search, Labeling Tool & Fixtures (S10–S12, S14, S15)**
  - *owns_paths:* `[src/Kodiac_robotics/io/lerobot.py, scripts/find_hero_clips.py, scripts/label_tool.py, modal/hero_search.py, tests/fixtures/clips/**, tests/io/**, docs/DEMO_FILMING_GUIDE.md, artifacts/p02/**]`
  - *reads_only:* `[src/Kodiac_robotics/contracts/**, ARCHITECTURE.md §7]`
  - *depends_on:* `[]`
  - *DoD:* `load_lerobot_episode` transcodes AV1 to H.264 CFR 30/15 fps; hero candidate index exists in `artifacts/p02/hero_candidates/` from real datasets; `scripts/label_tool.py` operational with randomized timing telemetry; golden fixture clips committed with sha256 checksums; `tests/io/` green.

---

### 3. Frozen Interface Contracts & Protocols

```python
# src/Kodiac_robotics/sim/spans.py
from typing import Literal, Callable, Any
from pydantic import BaseModel

ActuationClass = Literal["gripper.open", "gripper.close", "arm.move_to", "arm.lift", "arm.retract", "wait"]

class SimSpan(BaseModel):
    span_id: int
    func: str
    file: str                     # Repo-relative forward-slash path, e.g. "examples/sim/pick_place.py"
    line: int                     # 1-based caller line number
    code: str                     # Exact statement, e.g. "robot.gripper.open()"
    actuation_class: ActuationClass
    step_start: int               # Simulation control step index (0-based)
    step_end: int
    t_start_s: float
    t_end_s: float

def span(actuation_class: ActuationClass) -> Callable[..., Any]: ...
def find_blame_span(
    spans: list[SimSpan],
    frame_idx: int,
    broken_predicate: str | None = None,
    causal_window_s: float = 1.0,
    fps: float = 30.0,
) -> SimSpan | None: ...

# src/Kodiac_robotics/sim/env.py
from typing import Protocol, Any, Literal
import numpy as np
from pydantic import BaseModel

class SimState(BaseModel):
    step: int
    t_s: float
    gripper_width: float
    cubeA_pose: tuple[float, float, float, float, float, float, float]  # xyz + quat
    cubeB_pose: tuple[float, float, float, float, float, float, float]
    cubeA_vel: tuple[float, float, float]                               # linear velocity
    in_contact: bool

class SimEnv(Protocol):
    backend: Literal["maniskill", "kinematic_mock"]
    is_mock: bool
    def reset(self, seed: int | None = None) -> tuple[np.ndarray, dict[str, Any]]: ...
    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]: ...
    def privileged_state(self) -> SimState: ...
    def oracle_success(self) -> bool: ...
    def render(self) -> np.ndarray: ...  # (512, 512, 3) uint8

class SimRun(BaseModel):
    run_id: str
    seed: int
    backend: Literal["maniskill", "kinematic_mock"]
    is_mock: bool
    video_path: str
    state_path: str
    meta_path: str
    spans: list[SimSpan]
    oracle_success: bool
    onset_frame: int | None = None
    perturbation_type: str | None = None

# src/Kodiac_robotics/sim/bugs.py
class BugDef(BaseModel):
    id: str  # "B01" ... "B10"
    name: str
    description: str
    patch_path: str
    expected_failure_step: int
    expected_broken_predicate: str
    expected_blame_span: ActuationClass
    expected_oracle_success: bool = False
    spoken_instruction: str
    diagnostic_hint: str

# src/Kodiac_robotics/io/lerobot.py
from Kodiac_robotics.contracts.core import Clip
from pathlib import Path

def load_lerobot_episode(
    repo_id: str,
    episode_index: int,
    camera: str | None = None,
    target_fps: float = 30.0,
    cache_dir: Path | None = None,
    mock_ok: bool = True,
) -> Clip: ...

# experiments/labels/timing_<annotator>.jsonl schema
class TimingRecord(BaseModel):
    session_id: str
    annotator: str
    episode_id: str
    dataset: str
    mode: Literal["scrub", "blame"]
    time_to_verdict_ms: float
    verdict: Literal["PASS", "FAIL", "CANT_TELL"]
    notes: str | None = None
```

---

### 4. Tripwires & Kill Criteria

1. **TRIPWIRE-1 (Local SAPIEN/Vulkan Failure):** If local execution imports `mani_skill` or invokes SAPIEN and crashes with `VK_ERROR` or `ImportError`, immediately execute against `KinematicMockEnv` with `[MOCK SIMULATION]` banner and `is_mock: true`. Do NOT block CI. Production pool runs execute on Modal.
2. **TRIPWIRE-2 (Policy Retraining Compute Spike):** If $\pi_0$ policy training on Modal L4 exceeds 20 minutes per run or total proof training budget exceeds 12 GPU-hours ($9.60), stop and adjust steps/architecture (e.g. switch to 10-step Flow Matching or ACT).
3. **TRIPWIRE-3 (Contact Damping & Bug Determinism):** If any bug B01–B10 achieves oracle PASS on any seed out of 10, assert settling velocity check ($v < 0.01\text{ m/s}$) is active. If still passing, increase perturbation magnitude until 10/10 seeds assert oracle FAIL.
4. **TRIPWIRE-4 (CFR Transcode Verification):** If `load_lerobot_episode` or `sim/video.py` outputs variable frame rate or non-`yuv420p` video, fail the test. Enforce exact frame count matching simulation steps.
5. **TRIPWIRE-5 (Pre-Registration Integrity):** Pool generation script `proof/pool.py` will abort immediately if git tag `prereg-v0` is missing or disk sha256 does not match Parquet metadata.

---

### 5. Improvement Proposals (IP) Consensus Table

| IP | Title | D1 | D2 | D3 | Consensus & Action | Escalate to SDM? |
|---|---|---|---|---|---|---|
| **IP-P02-D1-1** | Dual-Backend Sim Architecture (`ManiSkillEnv` + `KinematicMockEnv`) | APPROVE | APPROVE | APPROVE | **APPROVE:** Full consensus. `KinematicMockEnv` provides instant local CPU testing with permanent `[MOCK SIMULATION]` banner and `is_mock: true`; `ManiSkillEnv` runs on Modal L4 for production rollouts. | No (Local) |
| **IP-P02-D1-2** | Standardized `@span` Schema & Causal-Window Lookup (`find_blame_span`) | APPROVE | APPROVE | APPROVE | **APPROVE:** Full consensus. Uses `sys._getframe(1)` for speed, repo-relative normalized paths, and a $\Delta t \le 1.0\text{ s}$ causal lookback window to bridge physics actuation lag. | No (Local) |
| **IP-P02-D1-3** | Sharded Parquet Pool Manifest with Resumable Checkpointing | APPROVE | APPROVE | APPROVE | **APPROVE:** Full consensus. Written in 100-episode shards via PyArrow with embedded pre-reg content hashes and tag. | No (Local) |
| **IP-P02-D2-1** | Hero-Clip Curation Protocol (Metadata-filtered real robot footage) | APPROVE-WITH-CHANGE | APPROVE | APPROVE-WITH-CHANGE | **APPROVE-WITH-CHANGE:** Simplify S11 to metadata filtering and single-clip downloads on Modal. Real teleoperated footage only (no sim cold open). | No (Local) |
| **IP-P02-D2-2** | Pre-Registration Git-Native Hash in Parquet Metadata (`ots` non-blocking) | APPROVE-WITH-CHANGE | APPROVE | APPROVE-WITH-CHANGE | **APPROVE-WITH-CHANGE:** Git tag `prereg-v0` + content sha256 embedded in Parquet. `ots stamp` is optional human follow-up. | No (Local) |
| **IP-P02-D2-3** | Time-Saved Study Telemetry with Strict Data Partition | APPROVE-WITH-CHANGE | APPROVE | APPROVE-WITH-CHANGE | **APPROVE-WITH-CHANGE:** Strictly partition blind benchmark slice (plain video only) from timing study ($\ge 40$ audit episodes with mock blame overlays). | No (Local) |
| **IP-P02-D3-1** | Dual-Mode Sim Architecture | APPROVE | APPROVE | APPROVE | **APPROVE:** Merged into IP-P02-D1-1. | No (Local) |
| **IP-P02-D3-2** | Mandatory Bug B01–B10 Seeded Determinism Assertion | APPROVE | APPROVE | APPROVE | **APPROVE:** 10/10 oracle FAIL asserted in CI with settling velocity threshold ($< 0.01\text{ m/s}$) to prevent bouncing passes. | No (Local) |
| **IP-P02-D3-3** | Enforce Policy Training Budget Cap on Modal L4 | APPROVE-WITH-CHANGE | APPROVE-WITH-CHANGE | APPROVE | **APPROVE-WITH-CHANGE:** Budget capped in GPU-hours ($\le 12$ GPU-h total, $\le 20$ min/run) with checkpoint convergence monitoring. | No (Local) |

---

### 6. Open Disagreements

**Zero open disagreements.** The council has reached unanimous alignment across all architectural, empirical, and risk parameters. Ready for ORCH dispatch.
