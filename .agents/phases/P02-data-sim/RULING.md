# RULING: P02  ·  SDM: Gemini 4 Argon @ Antigravity

## 1. Decision Table

| IP | Decision | Rationale |
|---|---|---|
| **IP-P02-D1-1** | **APPROVE** | Enables 100% offline Windows CPU CI via `KinematicMockEnv` while isolating `ManiSkillEnv` on Modal L4; mandatory visual watermarking and `is_mock: true` protect Law 1. |
| **IP-P02-D1-2** | **APPROVE** | Adopts zero-overhead `sys._getframe(1)` for span capture and introduces a $\Delta t \le 1.0\text{ s}$ causal lookback window in `find_blame_span` to bridge physical actuation lag to root cause. |
| **IP-P02-D1-3** | **APPROVE** | Employs 100-episode Parquet sharding for fault-tolerant, resumable pool generation on Modal and cryptographically embeds pre-registration SHA-256 hashes into dataset metadata. |
| **IP-P02-D2-1** | **APPROVE-WITH-CHANGES** | Hero-clip remote scanning and clipping must execute on Modal (`modal/hero_search.py`) downloading single episodes; Beat C1 hero clip must be real robot footage (DROID/LeRobot), never simulation. |
| **IP-P02-D2-2** | **APPROVE-WITH-CHANGES** | Pre-registration integrity is anchored in git tag `prereg-v0` and sha256 checksums embedded in Parquet metadata; external `ots stamp` is classified as non-blocking human follow-up. |
| **IP-P02-D2-3** | **APPROVE-WITH-CHANGES** | Strictly isolates the blind evaluation slice from the time-saved study set ($\ge 40$ episodes) to prevent label contamination; timeboxes label tool build to $\le 1.0\text{ h}$ using single-file HTML/vanilla JS. |
| **IP-P02-D3-1** | **APPROVE** | Approved as consolidated into IP-P02-D1-1; standardizes structural `SimEnv` Protocol and cross-backend kinematic parity. |
| **IP-P02-D3-2** | **APPROVE-WITH-CHANGES** | Mandates 10/10 seeds oracle FAIL in CI via a settling velocity check ($v_{\text{linear}} < 0.01\text{ m/s}$ over 0.5 s dwell) without inflating physical perturbations into cartoon failures. |
| **IP-P02-D3-3** | **APPROVE-WITH-CHANGES** | Caps proof training at $\le 12$ GPU-h total and $\le 20\text{ min/run}$ on Modal L4, but mandates logging checkpoints at 5k/10k/15k/20k steps to ensure policy competence (target 30%–60% success). |

---

## 2. Final Ordered Phase Plan & Pipeline Sequencing

```
Stage 1 (Parallel Dispatch · Width = 3):
- IMPL-1 (T01): Implement `sim/env.py` (`SimEnv` Protocol with lazy `ManiSkillEnv` + watermarked `KinematicMockEnv`), `sim/video.py` (CFR 30fps), `sim/robot.py`, `sim/spans.py` (`@span` via `sys._getframe(1)` + `find_blame_span` causal window), `examples/sim/pick_place.py` (10/10 seeds PASS), B01–B10 bugs with settling velocity checks, and `tests/sim/`.
- IMPL-2 (T02): Draft `experiments/PREREGISTRATION.md` (H1–H3, oracle thresholds) & `experiments/pool_config.yaml` → commit and tag `prereg-v0`; write `.green` specs; scaffold `modal/proof_train.py` & `proof/appearance.py` (60 clips); build `proof/pool.py` (sharded Parquet, embedded prereg sha256); launch background pool generation (BG-A) on Modal L4.
- IMPL-3 (T03): Implement `src/Kodiac_robotics/io/lerobot.py` (single-episode download, AV1→H.264 CFR transcode); build `modal/hero_search.py` & `scripts/find_hero_clips.py` (real robot teleop footage only); build minimal HTML/JS `scripts/label_tool.py` (strict blind vs timing partition); assemble offline fixtures in `tests/fixtures/clips/` with checksums; verify `docs/DEMO_FILMING_GUIDE.md`.
Stage 2 (ORCH Integration & Gate):
- Verify git tag `prereg-v0` exists before pool generation starts; merge task branches; verify 100% offline tests green (`tests/sim/`, `tests/io/`, `tests/proof/`); verify background job `proof/pool.py` running on Modal volume; populate `GATE.md` with evidence; commit and tag `p02-done`.
Pipeline Sequencing:
- P03–P10 sequence confirmed. P03 dispatches immediately in parallel with P02 Review. Background pool generation (BG-A) runs asynchronously into P03, targeting pool completion prior to P03.S14 (Proof arms).
```

---

## 3. Required Doc Updates

- **`ARCHITECTURE.md §4, §5.7, §7.2, §10`**: Document `SimEnv` Protocol, `SimState`, `SimRun`, mandatory `actions: np.ndarray (T, 7)` storage in `.state.npz`, `SimSpan` schema with causal lookback window ($\Delta t \le 1.0\text{ s}$), and camera calibration parameter storage ($K$, $[R \mid t]$) for Tier A scale modeling.
- **`IMPLEMENTATION_PLAN.md §P02`**: Formalize the full 3-task parallel DAG (T01 ∥ T02 ∥ T03), update `find_blame_span` with causal lookback window, specify settling velocity check ($v_{\text{linear}} < 0.01\text{ m/s}$ over 0.5 s dwell) for B01–B10 determinism, and specify git-native pre-registration hash in Parquet metadata with non-blocking `ots`.
- **`TOOLS_AND_REQUIREMENTS.md §2`**: Clarify that `KinematicMockEnv` is pure-Python CPU-only for host CI, `ManiSkillEnv` is isolated to Modal L4 GPU containers, and `ots` is non-blocking.
- **`.agents/DECISIONS.md`**: Append `ADR-0004` (Dual-backend simulation architecture and mock watermarking), `ADR-0005` (Causal span blame window for physical actuation delay), `ADR-0006` (Git-native pre-registration verification & Parquet metadata anchoring), and `ADR-0007` (Unified action space and state trajectory schema for practice pool retraining).

---

## 4. Tripwires and Kill Criteria (Measurable)

1. **Local Sim Import & Physics Trap Tripwire:** If importing `Kodiac_robotics.sim.env` or running `tests/sim/` on local host triggers `ModuleNotFoundError: mani_skill`, `VK_ERROR`, or takes $>30\text{ s}$, immediately fail the test. Local runs must transparently default to `KinematicMockEnv` with zero torch/GPU dependencies.
2. **Policy Action & State Logging Tripwire:** In `proof/pool.py` and `sim/env.py`, every saved `{episode}.state.npz` must contain key `actions` with shape `(T, 7)` in `pd_ee_delta_pos` space and non-empty values. If `actions` is missing or shape is inconsistent, abort pool generation after 5 episodes.
3. **Bug Determinism & False-Pass Kill Criterion:** If any bug B01–B10 records `oracle_success == True` on even 1 seed out of 10 during `tests/sim/test_bugs.py` after the 0.5 s settling dwell, CI fails immediately. Fix the patch parameter (e.g. increase offset or advance release) before proceeding to GATE.
4. **Pre-Registration Tag Order Tripwire:** If `proof/pool.py` starts generating episodes on Modal before git tag `prereg-v0` exists on the commit matching `prereg_sha256` and `config_sha256`, the script must raise `RuntimeError("Pre-registration invariant I8 violated: prereg-v0 tag missing")` and terminate.
5. **Modal Compute & Wall-Clock Budget Kill Criterion:** If single $\pi_0$ policy training on Modal L4 exceeds 20 minutes wall-clock, or cumulative Modal GPU spend across all P02 jobs exceeds $12.00 ($\approx 15$ L4 GPU-hours), immediately kill the job and switch policy architecture to 10-step Flow Matching or 3-layer MLP.
6. **Hero-Clip Sourcing Tripwire:** If the hero-clip search (`modal/hero_search.py`) fails to produce at least 3 candidate real-robot manipulation failure clips from DROID or LeRobot with resolution $\ge 480\text{p}$ and duration $\le 20\text{ s}$ within 45 minutes, immediately alert human and fall back to curated HF LeRobot SO-100 pick/place episodes.

---

## 5. The Single Biggest Risk Missed by Council & Remediation

**The Risk:** The Headless Rollout Trap (Missing Control Actions & Action Space Mismatch for Downstream Policy Retraining).
While the council exhaustively addressed mock watermarking, pre-registration hashes, causal span lookback, and bug bounce damping, they treated the 1,000-episode practice pool generator (`proof/pool.py`) primarily as a *video and judge label dataset* (storing MP4s, metadata, and privileged cube poses for evaluation).
They completely overlooked the **training data contract required for downstream imitation learning (Invariant I8: "+Y points of success")**.
To retrain a policy on `{clean demos ∪ accepted set}` in P05.S12 and P08.S07, the training script (`modal/proof_train.py`) cannot learn from video frames and object coordinates alone; it requires step-by-step **robot control actions $a_t \in \mathbb{R}^7$** perfectly aligned with the robot's observation space in the exact policy control mode (`pd_ee_delta_pos`).
If `SimRun` and `{episode}.state.npz` dump only evaluation poses (`cubeA_pose`, `cubeB_pose`, `in_contact`) and omit the control actions $a_t$, or if the motion-planning expert outputs joint actions (`pd_joint_pos`) while the policy outputs delta EE poses (`pd_ee_delta_pos`), the 1,000-episode pool will be completely un-trainable!

**Remediation:**
1. **Formalize the Action-State Trajectory Schema in `SimState` / `.state.npz`:**
   Mandate that every episode's `.state.npz` must contain:
   - `actions`: `np.ndarray` of shape `(T, 7)` (`pd_ee_delta_pos`: $[dx, dy, dz, dr, dp, dy, gripper]$), float32.
   - `obs_state`: `np.ndarray` of shape `(T, d)` containing robot proprioception (joint positions, joint velocities, EE pose, gripper width) and object states matching the exact feature vector expected by the state Diffusion Policy / ACT.
   - `cam_K`: $(3, 3)$ and `cam_extrinsic`: $(4, 4)$ float32 matrices for camera calibration (enabling Tier A scale model back-projection in P04).
2. **Mandate Unified Action-Space Replay in S01/S04/S06:**
   Enforce that all motion-planner trajectories (expert and perturbed) must be converted into the policy's action space (`pd_ee_delta_pos`) via ManiSkill's trajectory converter before saving to the pool.
3. **Add an End-to-End Pool Ingestion & Training Smoke Test in T02:**
   Before launching the full 1,000-episode background generator, IMPL-2 must run a mandatory 2-episode smoke test: generate 2 episodes, save them to disk/volume, load them directly into `modal/proof_train.py`, run 10 gradient steps of the diffusion policy, and assert that loss decreases with zero shape or key errors.

---

## 6. What Reviewers Must Scrutinize Hardest

1. **Law 1 Compliance & Mock Isolation:**
   Inspect `src/Kodiac_robotics/sim/env.py` and `examples/sim/pick_place.py`. Confirm that `KinematicMockEnv` has zero imports of `mani_skill` or `torch`, burns `[MOCK SIMULATION · NOT SAPIEN PHYSICS]` on all rendered frames, sets `is_mock: true` in metadata, and that mock files cannot be accepted into the pool manifest.
2. **Invariant I8 Pre-Registration Integrity:**
   Verify that `experiments/PREREGISTRATION.md` and `experiments/pool_config.yaml` are committed and tagged `prereg-v0` in git, that the SHA-256 of both files is embedded in the Parquet metadata of `manifest.parquet`, and that the pool generator asserts this tag exists before generating any episodes.
3. **Causal Blame Window & Invariant I4:**
   Verify that `find_blame_span` in `sim/spans.py` correctly maps a physical failure timestamp $t^*$ back to the preceding actuation within $\Delta t \le 1.0\text{ s}$ (e.g. `moves_with` breaking at $t=3.8\text{ s}$ correctly resolves to `gripper.open` at $t=3.33\text{ s}$, not the subsequent `arm.move_to` or `wait`).
4. **Bug Determinism & Settling Velocity Check:**
   Verify that in `tests/sim/test_bugs.py`, all 10 bug patches B01–B10 assert `oracle_success == False` across 10/10 random seeds, and that oracle evaluation occurs only after the 0.5 s dwell window with $v_{\text{linear}} < 0.01\text{ m/s}$ to prevent physics bouncing false-passes.
5. **Data Partitioning in Labeling Tool:**
   Verify that `scripts/label_tool.py` strictly prevents blame overlays or failure hints from appearing during evaluation of the blind benchmark slice (`droid_slice_<annotator>.jsonl`), reserving blame overlays exclusively for the separate timing study set.
6. **Action Space & Retraining Artifact Completeness:**
   Verify that sample `.state.npz` files produced by `proof/pool.py` contain `actions` arrays matching the `pd_ee_delta_pos` shape and that camera extrinsics/intrinsics are recorded for downstream Tier A scale modeling.
