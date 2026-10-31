# .agents/DECISIONS.md: Architectural Decision Records (ADRs)

All rulings, architectural choices, and deviations are logged here chronologically. Append-only.

---

### ADR-0001 · 2026-10-28 · P01 · Agent Runtime & Execution Stack
- **Context:** Establishing the multi-agent operating environment and subagent invocation model for Kodiac hackathon development.
- **Decision:**
  - **Orchestrator (ORCH):** Antigravity CLI / agent environment on Windows.
  - **Subagents (D1, D2, D3, SDM, IMPL-n, R1, R2):** Invoked via Antigravity native `invoke_subagent` with `Model: 'inherit'` ensuring Gemini 3.8 Flash is used across all spawned subagents without deviation, strictly respecting the user directive.
  - **Workspace Mode:** Direct repository workspace with strict file-ownership partitioning (`owns_paths`) and git staging scoping per task card (`git add <owned_paths>`).
  - **Coordination Protocol:** File-based shared state machine via `.agents/phases/P<NN>-<slug>/` artifacts (`BRIEF.md`, `COUNCIL.md`, `CHANNEL.md`, `RULING.md`, `GATE.md`, `REVIEW.md`).
- **Rationale:** Native subagent execution preserves full context alignment, matches the exact requested model family (Gemini 3.8 Flash), and provides reliable filesystem and terminal tool access.
- **Supersedes:** None.

---

### ADR-0002 · 2026-10-28 · P01 · Senior Decision Maker (SDM) Channel
- **Context:** Establishing the escalation protocol and execution mechanics for the Senior Decision Maker across P01–P10.
- **Decision:**
  - **Option A (Primary CLI):** `opencode run -m deepseek/deepseek-chat` or verified provider flag executing headless with `.agents/prompts/P<NN>-SDM-Ruling.md`.
  - **Option B (Native Antigravity):** Antigravity invocation with Gemini 4 Argon or inherited Gemini 3.8 Flash when headless terminal is active.
  - **Format:** Strict 6-part ruling template (`AGENTS.md §6.3`).
- **Rationale:** Ensures programmatic, auditable, and reproducible technical verdicts without blocking the pipeline.
- **Supersedes:** None.

---

### ADR-0003 · 2026-10-28 · P01 · Smoke Test Dual-Mode Execution & Anti-Fabrication Tagging
- **Context:** Handling day-1 external credential latency (`MODEL_API_KEY`, `MODAL_TOKEN_ID`, etc.) without violating Law 1 ("Never fake anything") or blocking exit gates.
- **Decision:**
  - **Dual-Mode Smoke Execution:** Scripts in `scripts/smoke/st01_models.py` through `st13_sdm.py` support `--live` and auto-mock fallback.
  - **Honesty Invariants:** When sponsor keys are absent, smoke test outputs must strictly write `is_fixture: true`, `live_verified: false`, `latency_ms: null`, and `status: "PENDING_KEY"`.
  - **Zero Fabrication:** Dummy or simulated latencies may never be reported as live benchmark measurements.
  - **SLA Tripwire:** 1.0 hour timeout for live credentials before falling back to mock fixtures to keep task cards unblocked.
- **Rationale:** Strictly upholds Prime Directive Law 1, ensures reproducible local verification, and unblocks Phase P01 exit gate.
- **Supersedes:** None.

---

### ADR-0004 · 2026-10-28 · P02 · Dual-Backend Simulation Architecture & Mock Watermarking
- **Context:** Local development environment is Windows 11 with CPU only (no NVIDIA CUDA GPU, missing `mani_skill` and `sapien`). Running headless SAPIEN simulation locally fails or requires fragile software Vulkan drivers. However, full simulation rollouts and downstream policy retraining require true SAPIEN physics.
- **Decision:**
  - Define `SimEnv` Protocol in `src/Kodiac_robotics/sim/env.py` with two interchangeable backends:
    1. `KinematicMockEnv`: Pure-Python/NumPy kinematic simulation of Panda + StackCube for fast, 100% offline local unit testing, CI, and B01–B10 bug validation.
    2. `ManiSkillEnv`: Production SAPIEN physics wrapper executed inside Modal L4 GPU containers for the 1,000-episode practice pool and reference policy training.
  - **Law 1 Anti-Fabrication Watermarking:** `KinematicMockEnv` must burn an indelible visual banner `[MOCK SIMULATION · NOT SAPIEN PHYSICS]` on all rendered MP4 frames and write `is_mock: true` and `env_backend: "kinematic_mock"` in metadata JSON. Mock episodes are strictly rejected from the proof practice pool manifest.
- **Rationale:** Ensures fast local developer iteration and green CI without GPU dependencies, while cleanly partitioning heavy CUDA/Vulkan physics to Modal. Visual and metadata watermarks prevent any mock simulation from being misrepresented as true physics.
- **Supersedes:** None.

---

### ADR-0005 · 2026-10-28 · P02 · Causal Span Blame Window for Physical Actuation Delay
- **Context:** In physical robotics and simulation, physical events (e.g. cube separation, dropping, toppling) lag behind the actuation that caused them due to gravity, inertia, and contact dynamics. For example, `gripper.open()` executes at frame 100 ($t=3.33$ s), but the cube falls and breaks `moves_with` at frame 114 ($t^*=3.80$ s). A naive point-in-time lookup `find_blame_span(t*)` incorrectly blames subsequent statements (such as `arm.move_to` or `wait`).
- **Decision:**
  - Standardize `@span` logger in `src/Kodiac_robotics/sim/spans.py` using `sys._getframe(1)` with repo-relative normalized paths (`os.path.relpath(path, repo_root).replace('\\', '/')`) and AST statement resolution.
  - Implement `find_blame_span(spans, frame_idx, broken_predicate, causal_window_s=1.0, fps=30.0)` which searches backward from $t^*$ within a causal window ($\Delta t \le 1.0$ s) to locate the latest actuation that causally induced the failed predicate transition (e.g. `moves_with` T$\to$F maps to `gripper.open`).
- **Rationale:** Guarantees that `blame` links the physical failure directly to the exact source code line that caused it (Invariant I4), preventing misleading diagnoses and ensuring Muse Code `/goal` receives actionable hints.
- **Supersedes:** None.

---

### ADR-0006 · 2026-10-28 · P02 · Git-Native Pre-Registration Verification & Parquet Metadata Anchoring
- **Context:** Invariant I8 requires pre-registering proof hypotheses H1–H3, arms, oracle tolerances (`align_xy_cm <= 3.33, gap_cm <= 0.5`), and stopping rules before generating the practice pool or evaluating judge labels. OpenTimestamps (`ots`) is missing on the local host and cannot make external network calls from the sandbox.
- **Decision:**
  - Author and commit `experiments/PREREGISTRATION.md` and `experiments/pool_config.yaml` to git and create git tag `prereg-v0`.
  - In `src/Kodiac_robotics/proof/pool.py`, compute the SHA-256 of `experiments/PREREGISTRATION.md` and `experiments/pool_config.yaml` at runtime and embed them directly into `experiments/pool/manifest.parquet` table metadata along with `prereg_tag: "prereg-v0"`.
  - Tripwire: `proof/pool.py` asserts that git tag `prereg-v0` exists before launching episode generation; execution aborts if the tag is missing or file checksums mismatch.
  - `ots stamp` is classified as an optional, non-blocking post-push human step outside the sandbox.
- **Rationale:** Establishes cryptographic, tamper-evident proof hygiene anchored directly in Git history and Parquet metadata, satisfying skeptical robotics judges that retraining results were not p-hacked.
- **Supersedes:** None.

---

### ADR-0007 · 2026-10-28 · P02 · Unified Action Space & State Trajectory Schema for Practice Pool
- **Context:** The Senior Decision Maker identified the "Headless Rollout Trap": treating the 1,000-episode pool solely as an evaluation dataset (videos and cube poses) omits the robot control actions and observation vectors required for downstream policy imitation learning (Invariant I8).
- **Decision:**
  - Expand the `.state.npz` data contract generated by `sim/env.py` and `proof/pool.py` to include:
    1. `actions`: `np.ndarray` of shape `(T, 7)` in `pd_ee_delta_pos` space ($[dx, dy, dz, dr, dp, dy, gripper]$), float32.
    2. `obs_state`: `np.ndarray` of shape `(T, d)` containing robot proprioception (joint positions, joint velocities, EE pose, gripper width) and object poses matching the observation space of the state Diffusion Policy / ACT.
    3. `cam_K`: $(3, 3)$ float32 intrinsics and `cam_extrinsic`: $(4, 4)$ float32 matrix for camera calibration.
  - Require converting all motion-planner trajectories (expert and perturbed) to `pd_ee_delta_pos` control mode before saving.
  - Require a 2-episode end-to-end smoke test in T02 before launching the full 1,000-episode background generator.
- **Rationale:** Guarantees that the practice pool is immediately usable for downstream policy retraining in P05/P08 without requiring expensive data re-generation.
- **Supersedes:** None.

---

### ADR-0008 · 2026-10-28 · P03 · Live Failure Locate Strategy & Empirical Latency Gating (KD-05)
- **Context:** To satisfy the <12s live demo latency budget (KD-05), Kodiac must locate the physical failure onset frame $t^*$ and track object instances with persistent IDs across video clips. Two candidate approaches exist: (1) Two-Stage Bisect (6-keyframe pack for coarse localization + 50-frame backward dense window for causal attribution), and (2) 10 fps Subsampled Single-Pass Forward Locate (~100 frames in 1 API call).
- **Decision:**
  - Formally designate **Two-Stage Bisect** as the primary live fast path. It incurs 100 billed frames ($0.02 cost) and directly leverages Meta SAM 3.1 backward tracking as our hero "time machine" story (video Beat C3).
  - Implement an empirical latency gate in `scripts/bench_sam.py` ($n \ge 20$ trials). If 6-keyframe bisect + 50-frame backward window p95 locate latency exceeds **8.0 s**, activate the automatic fallback:
    - **Fallback Live Path:** 10 fps subsampled single-pass locate (~3.8 s), reserving backward tracking strictly for final blame refinement.
    - **Hosted Demo Safety:** Default to `⚡ CACHED` replays on the public hosted web demo if network round-trip exceeds 11.5 s.
  - Require pure-Python/NumPy vectorized COCO RLE codec (`segment/rle.py`) with `box_local_to_full_frame_rle` translation to eliminate `pycocotools` C-extension compilation and avoid `(0, 0)` mask canvas displacement.
  - Require dual-mode fixture recording (`scripts/record_fixtures.py --synthetic` / `--live`) to ensure 100% offline green CI without waiting for external API keys.
- **Rationale:** Aligns hackathon narrative impact with rigorous engineering tripwires, preserving backward tracking as the core demo differentiator while ensuring a fail-safe fallback against network queueing and rate limits.
- **Supersedes:** None.

---

### ADR-0009 · 2026-10-28 · P04 · Two-Stage Tabletop Ground-Plane Fit & Tier C Fallback
- **Context:** On single-camera tabletop robot setups (DROID, SO-100, Franka Desk), camera tilt $\theta \in [20^\circ, 65^\circ]$ relative to the ground plane must be estimated from resting objects to convert 2D pixel coordinates to 3D metric coordinates ($X, D, h$ in cm). If resting objects have near-identical vertical coordinates ($\Delta v < 15$ px) or $N_{\text{resting}} < 2$, the unconstrained least-squares ground-plane equation is mathematically singular or ill-conditioned ($\kappa > 50$). However, artificially forcing shrinkage toward an arbitrary hardcoded prior (e.g. $\theta_0 = 40^\circ$) on high-angle ($65^\circ$) or low-angle ($20^\circ$) cameras distorts true physical metric scale, leading to false passes or false failures.
- **Decision:**
  1. *Pre-Condition Check:* Require $N_{\text{resting}} \ge 2$ and vertical baseline $\Delta v_{\text{resting}} \ge 15$ px before invoking matrix algebra. If $N_{\text{resting}} < 2$ or $\Delta v < 15$ px, immediately demote to Tier C without attempting matrix inversion. Wrap all matrix solves in `try ... except np.linalg.LinAlgError:`.
  2. *Two-Stage Fit Pipeline:*
     - Stage 1 (Unconstrained): Solve unconstrained least-squares first. If condition number $\kappa \le 30$ and estimated pitch $\theta \in [20^\circ, 70^\circ]$, accept the unregularized fit without bias.
     - Stage 2 (Tikhonov Regularization): If $\kappa \in (30, 50]$, apply Tikhonov Ridge regularization pulling toward the table support aspect prior: $\mathbf{w} = (\mathbf{A}^T\mathbf{A} + \alpha \mathbf{I})^{-1}\mathbf{A}^T\mathbf{y}$ with $\alpha = 0.05 \cdot \text{trace}(\mathbf{A}^T\mathbf{A})$.
  3. *Tier C Demotion & Honesty Gating:* If condition number $\kappa > 50$, residual variance exceeds $15\%$ of image height, estimated pitch $\theta \notin [20^\circ, 70^\circ]$, or matrix solve raises `np.linalg.LinAlgError`, immediately demote to Tier C ($k = \ell / W_o$ with $2.5\times \sigma$ inflation), append badge `[GEOMETRY: TIER C · UNCALIBRATED CAMERA]`, and trigger Gate G6 `depth_ambiguous` on depth-critical components (`on.gap`, `inside.depth`).
- **Rationale:** Protects against mathematical singular matrix inversion crashes while preserving true camera tilt on well-conditioned views. Auto-demoting with an indelible badge and honest Gate G6 abstention upholds Invariants I3 ("Never guess when blind") and I15 ("Honesty affordances").
- **Supersedes:** None.

---

### ADR-0010 · 2026-10-28 · P04 · Pair-Specific Effector Exclusion in Gate G2 with 20% Observability Floor
- **Context:** During robotic manipulation (e.g. grasping a 4 cm block), robot gripper fingers close around the object, causing bounding box and mask overlap exceeding 40%. Under a naive Gate G2 (`OCCLUDED` when overlap $> 40\%$), every valid grasp would spuriously flip to `CAN'T TELL`, breaking the entire demo. However, a blanket exclusion of the effector would blindfold Gate G2: if the gripper completely covers the block from camera view (100% occlusion) or drops the block behind closed jaws, Kodiac would evaluate zero visible pixels and falsely declare `PASS`, violating Invariant I3 ("Never guess when blind"). Furthermore, a global effector exclusion would ignore situations where the gripper occludes other objects (e.g. the target pedestal or a secondary block).
- **Decision:**
  1. *Pair-Specific & Target-Specific Scoping:* Effector mask overlap exclusion from Gate G2 is strictly restricted to the declared target object in an active `moves_with(effector, target)` relation or grasp transition step. Container rims in `inside(A, B)` are similarly excluded. All non-target scene objects occluded $> 40\%$ by the gripper are NOT exempt and MUST trigger Gate G2 (`OCCLUDED`).
  2. *Mandatory 20% Observability Floor:* The effector exclusion applies *if and only if* the target object retains at least 20% visible unoccluded area relative to its expected area ($a_{\text{vis}} / \hat{a} \ge 0.20$).
  3. *Blindness Gating:* If $a_{\text{vis}} / \hat{a} < 0.20$, Gate G2 MUST fire with `CAN'T TELL` and reason code `OCCLUDED` (sub-reason: `target obscured by effector < 20% visible`). Kodiac never guesses physical metric state when optically blind.
- **Rationale:** Resolves false-occlusion rejections during normal robot grasping while establishing a strict physical observability boundary. Upholds Prime Directive Law 1 and Invariant I3.
- **Supersedes:** None.

---

### ADR-0011 · 2026-10-31 · P05 · Two-Stage Multi-Modal Compilation Architecture
- **Context:** To satisfy Invariant I2 ("Show It Once") and Concept C3 in the 3-minute video (Beat 0:24–0:50), Kodiac must compile a single demonstration video and spoken instruction into an unassailable `.green` test. If an LLM (Muse Spark) is asked to generate numerical thresholds (`align_xy_cm <= 1.5`, `min_cm = 2.0`), it hallucinates arbitrary numbers from pre-training priors rather than observing what the demonstrator actually achieved. This violates Invariant I6 ("Measured, not guessed") and Invariant I17 ("Every claim backed by a test").
- **Decision:**
  1. *Stage 1 (Symbolic Structure Extraction):* Muse Spark 1.3 is prompted with a strict Pydantic JSON schema restricted to object roles, step sequencing, and predicate names (`on`, `inside`, `near`, `lifted`, `moves_with`, `dwell`, `looks`, `MANUAL`). Spark is strictly forbidden from generating numerical threshold floats; all parameter values are emitted as symbolic placeholders (`value = -1.0`).
  2. *Stage 2 (Empirical Metric Calibration):* The measurement engine (`pipeline/run.py`) executes an unconstrained metric logging run over the demonstration video (Pass 1) to measure empirical physical extrema ($h_{\text{max}}$, $\Delta_{xy}$, $z_{\text{gap}}$, $v_{\text{settle}}$). `compiler/slack.py` populates the AST thresholds from these empirical measurements using certified safety margins ($\text{margin} \ge 2\sigma$).
  3. *Read-Only Verification:* `compiler/selftest.py` executes a read-only verification run on the calibrated test against the demonstration clip, asserting `Verdict == PASS` and `margin >= 2σ`.
- **Rationale:** Strictly separates structural natural language reasoning from empirical computer vision measurement, guaranteeing that physical thresholds are anchored 100% in physical reality.
- **Supersedes:** None.

---

### ADR-0012 · 2026-10-31 · P05 · Deterministic Fallback Compiler with Anti-Fabrication Badging and Verb Gating
- **Context:** Live demo environments, evaluators without `MODEL_API_KEY`, and automated test suites in offline sandboxes must be able to compile tests without network access or LLM timeouts. However, silently replacing an LLM compilation with a hardcoded template violates Prime Directive Law 1 ("Never fake anything"). Furthermore, blindly emitting a standard pick-and-place AST for completely unrelated user inputs produces a bogus test.
- **Decision:**
  1. *Verb Gating & Domain Validation:* `compiler/template_fallback.py` and `compiler/text_compile.py` are strictly gated on recognized robotics manipulation verbs (`pick`, `lift`, `place`, `stack`, `insert`, `let go`, `release`, `dwell`). If input text contains unrecognized or unsupported actions, compilation MUST fail with diagnostic `E003: unsupported manipulation action` or `E001: object not found`, rather than silently defaulting to a pick-and-place AST.
  2. *Mandatory Anti-Fabrication Badging:* Whenever template compilation is engaged:
     - The `.green` header comment MUST contain: `[COMPILER: DETERMINISTIC TEMPLATE FALLBACK · LLM OFFLINE]`.
     - `Step.provenance.source` MUST be set to `"compiler-default"`.
     - `GreenLock.model_ids["compiler"]` MUST be recorded as `"template-fallback"`.
     - The CLI MUST print an amber notice to `stderr`: `⚠ [COMPILER: DETERMINISTIC TEMPLATE FALLBACK · LLM OFFLINE]`.
- **Rationale:** Ensures 100% offline developer quickstart and CI reliability while guaranteeing complete transparency, preventing any misrepresentation of heuristic templates as live model outputs.
- **Supersedes:** None.

---

### ADR-0013 · 2026-10-31 · P05 · Empirical Auto-Slack Derivation with Physical Sanity Caps
- **Context:** Human webcam demonstrations inevitably contain hand jitter, minor wobbles, or slightly off-center placements. If fixed rigid thresholds are applied, valid demonstrations fail their own self-test (`E005`). Conversely, if auto-slack derivation is unbounded, an extremely sloppy human demonstration (e.g. dropping a block from 15 cm or placing it 8 cm off-center) will yield ridiculously loose thresholds (`align_xy_cm <= 9.5`, `gap_cm <= 16.0`). Downstream robot policies evaluated against such a loose test will pass even when dropping objects on the floor, destroying the headline proof ("+Y points of success", Invariant I8).
- **Decision:**
  1. *Statistical Tolerance Fitting:* `compiler/slack.py` derives thresholds using certified safety bounds over the settled demonstration state:
     - `align_xy_cm` = $\max(1.5, \text{round}(\Delta_{xy} + 2.5\sigma, 1))$
     - `gap_cm` = $\max(0.5, \text{round}(z_{\text{gap}} + 2.5\sigma, 1))$
     - `min_cm` = $\max(1.0, \lfloor 0.6 \cdot h_{\text{max}} \rfloor)$
  2. *Hard Physical Sanity Caps (Anti-Poisoning Filter):* Hard upper bounds are enforced on all calibrated thresholds:
     - `align_xy_cm <= 4.0` cm
     - `gap_cm <= 2.0` cm
     - `min_cm <= 8.0` cm
     - `max_speed_cm_s <= 2.5` cm/s
  3. *Rejection of Sloppy Demonstrations:* If empirical demonstration measurements exceed any physical sanity cap, compilation MUST halt immediately with diagnostic `E005: demonstration exceeds physical sanity cap; re-record a valid demonstration`. No test specification or lockfile shall be generated.
- **Rationale:** Guarantees that valid human demonstrations achieve `Verdict == PASS` with $\text{margin} \ge 2\sigma$ by mathematical construction, while strictly preventing sloppy demonstrations from generating degenerate test oracles that poison policy training.
- **Supersedes:** None.
