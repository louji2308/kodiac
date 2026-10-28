# REVIEW: Phase P02 Data & Simulation Foundation

- **Reviewed Tag:** `p02-done` (`c2f7b07`)
- **Reviewers:** R1 Verifier, R2 Judge's Eye
- **Status:** COMPLETE
- **Timestamp:** 2026-10-28T14:36:00Z

---

## 1. Executive Summary
Phase P02 (Data & Simulation Foundation) has been reviewed at tag `p02-done` (`c2f7b07`) by R1 Verifier and R2 Judge's Eye.
- **Combined Verdict:** **SHIP-WITH-FIXES** (1 S0 Blocker, 1 S1 Major, 4 S2 Minor, 1 S3 Nit).
- **Core Verification Status:**
  - Full test suite passes 100% offline: `92/92 passed in 89.25s` (`tests/sim/`, `tests/proof/`, `tests/io/`, `tests/unit/`). Zero failures.
  - Clean reference program (`examples/sim/pick_place.py`) achieves 10/10 seeds oracle PASS (verified up to 20/20 seeds).
  - Seeded bugs B01–B10 achieve 10/10 seeds oracle FAIL (verified up to 20/20 seeds, 200/200 episodes failed). Settling velocity check ($v < 0.01$ m/s over 0.5s dwell) strictly prevents bounce false-positives.
  - Pre-registration cryptographic integrity verified: SHA-256 hashes of `experiments/PREREGISTRATION.md` (`cb3c91ef...`) and `experiments/pool_config.yaml` (`ef7dad97...`) match `experiments/pool/manifest.parquet` metadata byte-for-byte; git tag `prereg-v0` exists at `b8720df`.
  - Law 1 anti-fabrication compliance: `KinematicMockEnv` burns indelible visual watermark `[MOCK SIMULATION · NOT SAPIEN PHYSICS]` on every rendered frame; `is_mock: true` embedded in metadata.
  - Git history secret scan: zero leaked keys. Large file scan: zero files > 1 MB.
- **Critical Issues Requiring Action:**
  - **S0 Blocker (`P02-R2-01`):** Preview MP4s in `artifacts/p02/hero_candidates/previews/` are synthetic fixture copies / testsrc patterns despite `index.md` asserting real teleoperation footage. Requires immediate disclosure as `[MOCK PLACEHOLDER]` and a P03 hotfix to fetch true DROID / SO-100 failure clips via Modal.
  - **S1 Major (`P02-R1-01`):** `ManiSkillEnv` does not store `cam_K` or `cam_extrinsic` attributes, causing `save_sim_run` to fall back to identity matrices $(I_3, I_4)$ in `.state.npz`, which will corrupt 3D metric projection in downstream P03/P04 perception.
  - **S2 Minor (`P02-R1-02`, `P02-R1-03`):** B01–B10 `.patch` files fail `git apply --check` due to chunk header and line drift; `sim/video.py` omits `is_mock` from `.state.npz`.

---

## 2. R1 Verifier Review
- **Reviewer:** R1 Verifier
- **Reviewed Tag:** `p02-done` (`c2f7b07`)
- **Review Date:** 2026-10-28T21:15:00Z
- **Verdict:** **SHIP-WITH-FIXES** (0 S0, 1 S1 Major, 2 S2 Minor, 1 S3 Nit; concurring with R2 on S0 `P02-R2-01`)

### 2.1 Code Correctness & Interface Compliance
- **ADR-0004 (Dual-Backend Simulation & Mock Watermarking):** Fully compliant. `KinematicMockEnv` in `src/Kodiac_robotics/sim/env.py` runs 100% offline with pure NumPy/analytic kinematics (Franka Panda 7-DOF tabletop cube stack). Top banner `[MOCK SIMULATION · NOT SAPIEN PHYSICS]` is indelibly burned into pixel arrays via OpenCV or pure NumPy fallback. Metadata JSON records `is_mock: true` and `env_backend: "kinematic_mock"`.
- **ADR-0005 (Causal Span Blame Window for Actuation Delay):** Fully compliant. `@span` decorator in `src/Kodiac_robotics/sim/spans.py` captures repo-relative paths (`examples/sim/pick_place.py`), line numbers, and exact code statements via `sys._getframe(1)`. `find_blame_span` implements a backward causal lookback window ($\Delta t \le 1.0$ s) mapping physical failure events back to initiating actuations (`gripper.open`, `arm.lift`, `arm.move_to`).
- **ADR-0006 (Git-Native Pre-Registration & Parquet Anchoring):** Fully compliant. `experiments/PREREGISTRATION.md` formalizes hypotheses H1–H3, oracle tolerances (`align_xy_cm <= 3.33, gap_cm <= 0.5`), CAN'T TELL rejection rule, and 10 benchmark arms. `experiments/pool_config.yaml` specifies pool distribution parameters. SHA-256 hashes computed at runtime match Parquet metadata byte-for-byte. Git tag `prereg-v0` verified at commit `b8720df`.
- **ADR-0007 (Unified Action Space & State Trajectory Schema):** Compliant. Generated `.state.npz` files contain `actions (T, 7)` in `pd_ee_delta_pos`, `obs_state (T, 32)`, `cam_K (3, 3)`, and `cam_extrinsic (4, 4)`. Weak policy $\pi_0$ pipeline in `src/Kodiac_robotics/proof/pi0.py` loads these trajectories and passes the mandatory 2-episode end-to-end training smoke test with verified loss decrease.

### 2.2 Re-Running Offline Test Suites
All verification commands were executed offline in the clean sandbox environment:
1. `uv run --no-sync pytest tests/sim/ tests/proof/ tests/io/ -v`:
   - **Result:** 63 passed in 18.26s.
   - `tests/sim/`: 21 passed (KinematicMockEnv contract, privileged state, watermark banner, state.npz schema, lazy import isolation, span metadata, causal lookback window, bug completeness, clean 10 seeds, B01–B10 10 seeds).
   - `tests/proof/`: 19 passed (appearance benchmark balance, manifest schema, baseline judge contracts, state diffusion policy, dataset loading, 2-episode smoke test, action space conversion, pool record validation, parquet metadata, preregistration tag tripwires).
   - `tests/io/`: 23 passed (fixture manifest, 5 golden clip integrity checks, timing record schema, blind slice data isolation, test telemetry runner, LeRobot URI parsing, AV1-to-CFR H.264 transcoding, cache reuse, mock fallbacks).
2. `uv run --no-sync pytest tests/ -v`:
   - **Result:** 92 passed in 89.25s across full repository test suite.
3. `uv run --no-sync ruff check .`:
   - **Result:** 0 errors ("All checks passed!").

### 2.3 Reference Program & Bug Registry Verification
- **Reference Pick & Place:** `uv run --no-sync python examples/sim/pick_place.py --backend mock --seeds 10` returned 10/10 PASS. Extended testing across 20 random seeds (0..19) confirmed 20/20 PASS.
- **Seeded Bugs B01–B10:** Executed across 20 distinct seeds (200 total episodes); 200/200 episodes correctly evaluated to `oracle_success == False` (100% fail rate).
- **Settling Velocity Check:** In `KinematicMockEnv.oracle_success()`, lines 484–490 enforce $v_{\text{linear}} < 0.01$ m/s across the full 15-step (0.5s) dwell window. High-drop bounces (B10) and premature retraction tugs (B04) fail deterministically.
- **Causal Blame Attribution:** Verified with physical separation simulations. An early release event at $t=3.8$ s correctly attributes blame to `robot.gripper.open(steps=15)` at $t=3.33$ s within the causal window, preventing false blame on subsequent motion statements.

### 2.4 Pre-Registration & Cryptographic Integrity Check
- `compute_prereg_hashes()` runtime outputs:
  - `experiments/PREREGISTRATION.md`: `cb3c91efd1bd8d8a256b242fbf46e3b99784fb8e495b210dd7bff1b4c455c236`
  - `experiments/pool_config.yaml`: `ef7dad97035a403426fe6cbe12672905723199037b2fd09d99baa8aa3e4ee8af`
- `experiments/pool/manifest.parquet` schema metadata:
  - `config_sha256`: `ef7dad97035a403426fe6cbe12672905723199037b2fd09d99baa8aa3e4ee8af`
  - `prereg_sha256`: `cb3c91efd1bd8d8a256b242fbf46e3b99784fb8e495b210dd7bff1b4c455c236`
  - `prereg_tag`: `prereg-v0`
  - `is_mock`: `true`
- Git tag verification: `git tag -l "prereg-v0"` confirmed at commit `b8720df`. Perfect match.

### 2.5 Security, Big Files, & Code Quality Audit
- **Secrets Scan:** Scanned full git patch history (`git log -p`) with regex for API keys and tokens. Exactly 1 candidate identified: `meta_sec_1234567890abcdef`, verified to be a synthetic fixture string in `test_doctor_secret_redaction`. Zero real credentials leaked.
- **Big Files Scan:** Scanned workspace for files $> 1\text{ MB}$. Found 0 files $> 1\text{ MB}$. Golden fixtures in `tests/fixtures/clips/` are all $\le 32\text{ KB}$, far below the $2\text{ MB}$ cap.
- **Discrepancy Check on `P02-R2-02`:** Re-tested `ruff check .` on tag `p02-done`. All 77 files pass with zero lint errors. `P02-R2-02` is marked resolved/invalid on this tag.

### 2.6 Detailed R1 Findings
1. **Finding `P02-R1-01` (S1 Major): `ManiSkillEnv` camera parameters missing from state trajectory output.**
   - In `src/Kodiac_robotics/sim/env.py:640-705`, `ManiSkillEnv` does not define `cam_K` or `cam_extrinsic` attributes. When `run_episode` / `save_sim_run` saves `.state.npz`, `getattr(env, "cam_K", ...)` silently falls back to identity matrices $(I_3, I_4)$. When ManiSkill runs on Modal for true physics generation in P03/P08, identity camera matrices will corrupt 3D metric projection in downstream perception and scale tier models.
   - *Fix:* Read camera parameters from the underlying ManiSkill camera sensor (`camera.get_params()["intrinsic_cv"]` and `extrinsic_cv`) in `ManiSkillEnv.__init__`, or provide default StackCube third-person camera matrices matching the known view.
2. **Finding `P02-R1-02` (S2 Minor): `examples/sim/bugs/*.patch` unified diffs fail `git apply --check`.**
   - In `examples/sim/bugs/`, all 10 patch files fail `git apply --check`. `B03.patch` and `B04.patch` have corrupt hunk headers (line counts claim 3 lines but contain only 2 lines, exiting code 128), and B01, B02, B05-B10 fail due to line number drift against `pick_place.py`. While the simulation tests pass via internal Python `bug_id` branching, the committed patch files are non-functional for Git patch application.
   - *Fix:* Re-generate all 10 `.patch` files from a pristine reference `pick_place.py` or fix hunk headers and line counts so `git apply --check` exits 0.
3. **Finding `P02-R1-03` (S2 Minor): `sim/video.py:save_sim_run` omits `is_mock` boolean from `.state.npz`.**
   - While `proof/pool.py:save_episode_state` includes `is_mock=bool(is_mock)` in its `.state.npz` files per ADR-0004/ADR-0007, `sim/video.py:save_sim_run` only writes `is_mock` to `.meta.json` and omits it from `np.savez_compressed(state_path, ...)`. Reading `data["is_mock"]` from a sim trajectory `.state.npz` raises `KeyError`.
   - *Fix:* Add `is_mock=bool(is_mock)` into `np.savez_compressed` in `sim/video.py:150`.
4. **Finding `P02-R1-04` (S3 Nit): SinglePassSparkJudge offline fixture latency.**
   - In `src/Kodiac_robotics/proof/judges/single_pass.py:56-66`, when the API key or video file is missing, it returns `latency_ms=450` in `JudgeLabel`. Under ADR-0003 anti-fabrication guidelines, simulated/mock runs should avoid presenting dummy numbers as benchmark latencies.
   - *Fix:* Document that baseline mock labels are fixture references.

---

## 3. R2 Judge's Eye Review
- **Reviewer:** R2 Judge's Eye / Integrator
- **Reviewed Tag:** `p02-done` (`c2f7b07`)
- **Review Date:** 2026-10-28T21:10:00Z
- **Verdict:** **SHIP-WITH-FIXES** (1 S0 Blocker, 1 S1 Major, 2 S2 Minor)

### 3.1 End-to-End Judge Simulation Audit
Audited through the persona lenses from `HACKATHON.md §9.1`:
- **J1 (Perception Researcher - Meta MSL/FAIR):** Would find the pre-registration (`experiments/PREREGISTRATION.md`) and oracle tolerances ($\Delta_{xy} \le 3.33\text{ cm}$, $\Delta_z \le 0.5\text{ cm}$, velocity settling $< 0.01\text{ m/s}$) exemplary. However, auditing `artifacts/p02/hero_candidates/` reveals that candidate previews (`hero_droid_001_preview.mp4`, etc.) are synthetic simulation clips and ffmpeg test patterns despite `index.md` asserting "Source: REAL" and "verified teleoperation hardware". This violates Prime Directive Law 1.
- **J2 (Robotics Researcher - MSL Robotics Studio):** Applauds the dual-backend design, the indelible watermark `[MOCK SIMULATION · NOT SAPIEN PHYSICS]`, the 10 bug variants (`B01`–`B10`), and the AST/lookback causal attribution in `src/Kodiac_robotics/sim/spans.py`. The weak diffusion policy pipeline ($\pi_0$) and 10 benchmark arms provide an unimpeachable experimental setup.
- **J3 (Platform DevRel - Muse/Model API):** Will catch that `GATE.md` claims "Zero lint errors (`ruff check` clean)", whereas running `uv run --no-sync ruff check .` fails with 38 lint errors.

### 3.2 Hero Failure Candidate Audit
- **Status:** **FAILED (S0 Blocker: `P02-R2-01`)**
- **Findings:**
  - `artifacts/p02/hero_candidates/index.md` lines 9–15 and 25 assert that all candidate failure clips are extracted strictly from real-world teleoperated robot demonstrations (`alexander-soare/droid_100` and `lerobot/so100_pick_place`), with `source_kind: real`.
  - Direct inspection of the actual video files in `artifacts/p02/hero_candidates/previews/` reveals:
    1. `hero_droid_001_preview.mp4` (29,668 bytes), `hero_droid_002_preview.mp4` (31,323 bytes), `hero_droid_003_preview.mp4` (31,323 bytes), and `hero_so100_001_preview.mp4` (31,885 bytes) are exact byte-for-byte copies of the synthetic simulation fixture clips (`b01_early_release.mp4`, `b02_xy_misalignment.mp4`, `b09_lift_failure.mp4`).
    2. `hero_so100_002_preview.mp4` (112,128 bytes) was generated via ffmpeg `testsrc` (color bar test pattern).
  - While the metadata catalog references real episodes, the preview assets themselves are synthetic mock files passed off as real teleoperation footage.
  - **Required Action:** Must be explicitly disclosed as `[MOCK PLACEHOLDER]` in `index.md`. A P03 hotfix task must execute `modal/hero_search.py` on Modal with HF network access to download true teleoperation frames for these candidates.

### 3.3 A/B Timing Study & Data Isolation Audit
- **Status:** **PASSED**
- **Findings:**
  - `scripts/label_tool.py` and `tests/io/test_label_tool.py` strictly isolate the 200-episode DROID evaluation slice. In `generate_droid_slice_episodes()`, records contain plain video metadata only; no `blame_hint`, `verdict`, `t_star`, or `failure_predicate` keys exist.
  - In `label_tool.html`, `SCRIPT_MODE === "blind"` forcibly suppresses the blame assistance card (`blameBox.style.display = "none"`).
  - The 40-episode timing audit set (`generate_timing_audit_episodes()`) provides randomized 50/50 assignment between `scrub` and `blame`.
  - Pydantic models `TimingRecord` and `BlindLabelRecord` validate all fields and bounds. Automated telemetry test passes cleanly.

### 3.4 Appearance Benchmark Audit
- **Status:** **PASSED (with S2 Note: `P02-R2-04`)**
- **Findings:**
  - `experiments/appearance/manifest.parquet` accurately registers 60 episodes combining articulated simulation (`sim_articulated`, 40 clips) and real robot episodes (`droid_real`, 20 clips).
  - Labels are exactly balanced: 30 `flush` (0.00 m offset) and 30 `ajar` (0.01–0.05 m offset in sim, 0.035 m in real).
  - Ground truth is grounded in physical joint displacement metrics (`ground_truth_joint_pos_m`). Parquet metadata embeds benchmark name and predicate specification.
  - Note: Video files referenced by the manifest (`experiments/appearance/{sim,droid}/*.mp4`) are not materialized on disk and will need rendering/fetching during P03.

### 3.5 Video Story Continuity (Beat C1 & Beat C3/C5)
- **Beat C1 (Cold Open - 0:00–0:12):** Blocked until true DROID/SO-100 failure clips are downloaded to replace the synthetic mock previews in `artifacts/p02/hero_candidates/previews/`.
- **Beat C3/C4 & C5 (Show it once, blame diagnostics, Muse Code `/goal` unedited take):** Strongly enabled. `examples/sim/pick_place.py`, the 10 bugs `B01`–`B10` with `.patch` files, `find_blame_span` causal lookback in `src/Kodiac_robotics/sim/spans.py`, and `docs/DEMO_FILMING_GUIDE.md` (30°–50° elevation, 4.0 cm object prior, 0.7 s audio pause) establish a clean bridge into perception (P03) and DSL compilation (P04).

---

## 4. Findings Matrix
| ID | Sev (S0–S3) | Category | Description | File:Line | Suggested Fix | Status |
|---|---|---|---|---|---|---|
| `P02-R2-01` | **S0** | Honesty / Demo Asset | Synthetic simulation and ffmpeg testsrc clips in `artifacts/p02/hero_candidates/previews/` presented as real robot teleoperation footage in `index.md` and `GATE.md`. | `artifacts/p02/hero_candidates/index.md:9-15`, `modal/hero_search.py:300-319`, `GATE.md:54` | Label preview MP4s as `[MOCK PLACEHOLDER]` in `index.md`. Dispatch P03 hotfix to run `modal/hero_search.py` on Modal with HF network access to download real DROID & SO-100 failure clips. | OPEN (P03 Hotfix) |
| `P02-R2-02` | **S1** | Quality / Gate Discrepancy | `GATE.md` claims "Zero lint errors (`ruff check` clean)", but running `uv run --no-sync ruff check .` fails with 38 lint errors. | `GATE.md:65`, `src/Kodiac_robotics/io/lerobot.py:18`, `src/Kodiac_robotics/proof/judges/robometer.py:10`, `modal/hero_search.py:13` | Run `uv run --no-sync ruff check --fix .` and resolve manual issues (`E402`, unused variables in `robometer.py`, `pi0.py`, import sorting). | OPEN (P03 Backlog) |
| `P02-R2-03` | **S2** | Ingest / Telemetry | DROID blind slice URLs in `scripts/label_tool.py` reference unmaterialized `/videos/droid/` paths; timing telemetry contains synthetic trials. | `scripts/label_tool.py:84`, `experiments/labels/timing_annotator_1.jsonl:1-40` | Add documentation on binding `--video-root` to cached LeRobot directories; document synthetic CI telemetry. | OPEN (Backlog) |
| `P02-R2-04` | **S2** | Benchmark | Appearance benchmark manifest defines 60 clips, but video files in `experiments/appearance/{sim,droid}/` are unmaterialized. | `experiments/appearance/manifest.parquet`, `src/Kodiac_robotics/proof/appearance.py:72` | Materialize/render appearance clips during P03 perception verification before running `looks()` evaluation. | OPEN (Backlog) |
| `P02-R1-01` | **S1** | Interface / Sim | `ManiSkillEnv` does not define `cam_K` or `cam_extrinsic`, causing `save_sim_run` to fall back to identity matrices $(I_3, I_4)$ in `.state.npz`. | `src/Kodiac_robotics/sim/env.py:640-705`, `examples/sim/pick_place.py:149-150` | Extract camera sensor parameters in `ManiSkillEnv.__init__` or provide default StackCube third-person camera matrices matching view. | OPEN (P03 Task) |
| `P02-R1-02` | **S2** | Code Correctness | `examples/sim/bugs/*.patch` unified diffs fail `git apply --check` due to chunk line count errors (B03, B04) and line number drift. | `examples/sim/bugs/B01.patch` ... `B10.patch` | Re-generate patch files against clean reference `pick_place.py` and fix chunk line counts so `git apply --check` exits 0. | OPEN (Backlog) |
| `P02-R1-03` | **S2** | Schema / Anti-Fabrication | `sim/video.py:save_sim_run` omits `is_mock` boolean from `.state.npz`, causing `KeyError` when inspected by consumers expecting ADR-0007 fields. | `src/Kodiac_robotics/sim/video.py:150-163` | Add `is_mock=bool(is_mock)` into `np.savez_compressed` in `sim/video.py:150`. | OPEN (Backlog) |
| `P02-R1-04` | **S3** | Quality / Audit Verification | Verification of R2-02 discrepancy: `uv run --no-sync ruff check .` passes with 0 errors on tag `p02-done`. | `GATE.md:65`, `REVIEW.md:137` | Update finding `P02-R2-02` to mark clean verification confirmed on `c2f7b07`. | RESOLVED (Verified Clean) |
