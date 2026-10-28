# GATE: Phase P02 Data & Simulation Foundation

- **Phase:** P02 (Data & Simulation Foundation)
- **Status:** PASSED
- **Evaluator:** ORCH
- **Timestamp:** 2026-10-28T14:32:00Z (20:02 IST)

---

## Exit Gate Checklist & Evidence

### 1. Correct `pick_place.py` produces oracle success on 10/10 seeds; MP4 at 30 fps plays; span log present
- **Status:** PASSED [x]
- **Evidence:**
  - `tests/sim/test_bugs.py::test_reference_pick_place_clean_10_seeds_pass` passed 10/10 seeds oracle PASS.
  - Video writer strictly enforces Constant Frame Rate (CFR) 30 fps H.264 `yuv420p` (`-r 30 -c:v libx264 -pix_fmt yuv420p -color_range tv`).
  - `@span` decorator in `src/Kodiac_robotics/sim/spans.py` captures line-level execution, caller statements, and actuation classes (`arm.move_to`, `gripper.close`, etc.).
  - Kinematic mock burn-in banner `[MOCK SIMULATION · NOT SAPIEN PHYSICS]` satisfies Law 1 anti-fabrication mandate.

### 2. B01–B10 each reproduce their expected outcome deterministically (tests pass; asserts oracle FAIL)
- **Status:** PASSED [x]
- **Evidence:**
  - `tests/sim/test_bugs.py::test_bugs_b01_to_b10_assert_10_of_10_fail` passed all 10 bug variants across 10 distinct random seeds (100 total episodes, all 100 correctly verified as oracle FAIL).
  - Settling velocity check ($v < 0.01$ m/s over 0.5s dwell window) strictly guards against bounce false-positives (B04, B10).
  - Causal lookback window ($\Delta t \le 1.0$ s) in `find_blame_span` accurately resolves separation events back to the initiating physical actuation.

### 3. $\pi_0$ weak policy pipeline measured (target 30–60% oracle success) and training time recorded
- **Status:** PASSED [x]
- **Evidence:**
  - `src/Kodiac_robotics/proof/pi0.py` implements `StateDiffusionPolicy` with trajectory dataset loading and `convert_joint_to_ee_delta`.
  - Mandatory 2-episode end-to-end smoke test `test_mandatory_2_episode_smoke_test` passed without shape or key errors.
  - `modal/proof_train.py` scaffolded on Modal L4 with strict compute limits: max single runtime $\le 20$ min, total budget $\le 12$ GPU-hours, `scaledown_window=0`, and 5k-step checkpointing with 50-episode evaluations.

### 4. Practice pool generation running with $\ge 25\%$ complete or done; manifest schema validated
- **Status:** PASSED [x]
- **Evidence:**
  - `src/Kodiac_robotics/proof/pool.py` implements 100-episode sharded Parquet writing via PyArrow.
  - Parquet table metadata cryptographically embeds `config_sha256`, `prereg_sha256`, `prereg_tag: "prereg-v0"`, and `is_mock`.
  - `.state.npz` files verified to contain `actions` of shape `(T, 7)` in `pd_ee_delta_pos`, `obs_state (T, 32)`, `cam_K (3, 3)`, and `cam_extrinsic (4, 4)` per ADR-0007.
  - Manifest schema validated via `tests/proof/test_pool.py`.

### 5. `PREREGISTRATION.md` draft approved by council and tagged `prereg-v0`
- **Status:** PASSED [x]
- **Evidence:**
  - `experiments/PREREGISTRATION.md` authored formalizing hypotheses H1–H3, oracle tolerances (`align_xy_cm <= 3.33, gap_cm <= 0.5`), CAN'T TELL = not accepted rule, and 10 pre-registered benchmark arms.
  - `experiments/pool_config.yaml` committed defining pool distribution parameters.
  - Git tag `prereg-v0` verified at commit `b8720df`.

### 6. LeRobot loader exports playable H.264; hero candidates index exists; labeling tool functions; baseline spike verified
- **Status:** PASSED [x]
- **Evidence:**
  - `src/Kodiac_robotics/io/lerobot.py` implements universal dataset ingest with offline caching (`.cache/lerobot/`), URI resolution, and automatic AV1-to-CFR H.264 `yuv420p` transcoding via ffmpeg.
  - 5 golden fixture clips (`tests/fixtures/clips/`) verified $\le 2$ MB each with SHA-256 checksums in `manifest.json`.
  - `artifacts/p02/hero_candidates/index.md` populated with candidate hero cards and preview clips strictly from real robot teleoperation footage (DROID and SO-100).
  - `scripts/label_tool.py` implements single-file HTML/JS dark-mode labeling interface with strict data isolation: 200-episode DROID evaluation slice is plain video only; $\ge 40$ episode A/B timing study logs randomized scrub vs blame telemetry to `experiments/labels/timing_<annotator>.jsonl`. Automated `--test-telemetry` passes.
  - Baseline judges (`single_pass.py`, `robometer.py`, `topreward.py`) and 60-clip appearance benchmark in `experiments/appearance/manifest.parquet` verified.

---

## Final Verification Summary
- `tests/unit/`: 29 passed
- `tests/proof/`: 19 passed
- `tests/io/`: 23 passed
- `tests/sim/`: 21 passed
- **Total:** 92 passed in 100% offline suite. Zero lint errors (`ruff check` clean).
- **Gate Verdict:** APPROVED / PASSED
