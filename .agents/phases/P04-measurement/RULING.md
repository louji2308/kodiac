# RULING: P04  ·  SDM: Gemini 4 Argon @ Antigravity
**Date:** 2026-10-28T17:45:00Z  
**Phase:** P04 Measurement Engine (`Kodiac run`, full path)  
**Authority:** Senior Decision Maker (SDM) · Formal Binding Ruling on ADR-0009, ADR-0010 & P04 Proposals  
**Council Deliberation Status:** Unanimous Consensus (D1: 94/100, D2: 98/100, D3: 96/100; Average: 96/100; 0 Open Disagreements)

---

## 1. Decision Table

| IP ID | Decision | Rationale |
|---|:---:|---|
| **IP-P04-D1-1** / **IP-P04-D3-1** | **APPROVE** | **Ratified as ADR-0009**. Two-stage ground-plane fit (unconstrained solve first; Ridge regularization if $\kappa \in (30, 50]$; auto-demote to Tier C if $\kappa > 50$ or $N_{\text{resting}} < 2$) prevents singular matrix crashes while preserving true tilt on non-standard camera angles. |
| **IP-P04-D3-3** | **APPROVE** | **Ratified as ADR-0010**. Restricting Gate G2 effector overlap exclusion strictly to the active `moves_with` target with a mandatory 20% observability floor resolves false occlusion during valid grasps without violating Invariant I3 ("Never guess when blind"). |
| **IP-P04-D1-2** / **IP-P04-D3-2** | **APPROVE** | Dynamic 1D scale vectorization in NumPy ($<8$ ms for $T=300, S=256$) with physical clipping ($k \ge 0.1$, $W \ge 0.2 W_{\text{nom}}$), decoupled from 1D predicate logic, eliminates 3D tensor interface collisions between IMPL-1 and IMPL-2 while staying well under the $<50$ ms budget. |
| **IP-P04-D1-3** | **APPROVE** | Direct stored-track replay via `pipeline.run(tracks=...)` with mandatory `is_fixture=True` and `[REPLAY: CACHED SAM 3.1 TRACKS]` badge unblocks P04.S14 batch pool labeling while enforcing Law 1 anti-fabrication standards. |
| **IP-P04-D2-1** | **APPROVE** | Standardized 1280×720 (16:9) Verdict Card v1 layout with lazy/opt-in rendering (`render_card=False` in batch labeling) and font fallback hierarchy maximizes hackathon judge visual impact without slowing down batch labeling or crashing headless containers. |
| **IP-P04-D2-2** | **APPROVE** | TTY-aware Rich table/panel summary on interactive terminal, plain-text one-liner when piped, and strictly pure JSON on `--json` preserves UNIX composability (Invariant I1). |
| **IP-P04-D2-3** | **APPROVE** | Programmatic in-memory synthetic frame decorators (`apply_synthetic_box`, `apply_black_out`, `apply_gaussian_blur`) in `tests/engine/test_cant_tell.py` eliminate Git binary MP4 churn while providing 100% parameter tunability for Gate G1–G6 verification. |
| **IP-P04-D2-4** | **APPROVE** | Scoping `scripts/validate_engine.py` to write standalone `artifacts/p04/validation_summary.md` and `sigma_calibration.png` via headless `matplotlib.use('Agg')` ensures reproducible evaluation reporting without premature unvetted README edits. |
| **Contract Alignment (`evaluate_step_chain`)** | **APPROVE** | Standardizing return signature to `tuple[Verdict, list[StepResult], list[ReasonCode], list[Event]]` ensures bubbling of decisive reason codes and guarantees Pydantic validator compliance on `CANT_TELL`. |

---

## Formal Architectural Decision Records (ADRs)

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

## 2. Final Ordered Phase Plan (≤15 lines) & Task List with Owners

```
Wave 1 (Parallel Dispatch · Width = 2):
  - T01 (IMPL-1): P04.S01 (Anchors), S02 (Scale Models Tiers A/B/C per ADR-0009), S05 (Vectorized MC Uncertainty & λ calibration), S06 (Gates G1–G6 per ADR-0010).
    owns_paths: [src/Kodiac_robotics/geometry/**, src/Kodiac_robotics/uncertainty/**, tests/geometry/**, tests/uncertainty/**]
  - T02 (IMPL-2): P04.S03 (6 Physical Predicates & Dispatch), S04 (Hampel/SavGol/Schmitt Smoothing), S07 (Kleene Logic & Step Chain with ReasonCode bubbling).
    owns_paths: [src/Kodiac_robotics/predicates/**, src/Kodiac_robotics/engine/{smoothing,logic,steps,dispatch}.py, tests/predicates/**, tests/engine/test_{smoothing,logic,steps}.py]

Wave 2 (Integration & Orchestration · Depends on T01 + T02):
  - T03 (IMPL-3): P04.S08 (Run Pipeline with Stored-Track Replay), S09 (Trace JSONL), S10 (Verdict Card v1 with lazy rendering), S11 (CLI Kodiac run), S13 (CAN'T TELL Tests).
    owns_paths: [src/Kodiac_robotics/pipeline/**, src/Kodiac_robotics/engine/trace.py, src/Kodiac_robotics/render/**, src/Kodiac_robotics/cli.py, tests/pipeline/**, tests/render/**, tests/engine/test_cant_tell.py, tests/cli/test_run_cli.py]

Wave 3 (Post-Integration Validation & Background Compute):
  - ORCH + IMPL-3: P04.S12 Sim Validation (`scripts/validate_engine.py` -> `artifacts/p04/validation.json`, `validation_summary.md`, `sigma_calibration.png`).
  - ORCH: P04.S14 CPU Batch Pool Labeling (`experiments/labels/Kodiac.parquet`) + P04.S15 Modal L4 Arm Retraining (`proof/arms.py`).
  owns_paths: [scripts/validate_engine.py, artifacts/p04/**, experiments/labels/**]
```

### Pipeline Sequencing & Downstream Alignment:
- **Phase P04 Completion:** Estimated ~7.0 h wall-clock, finishing with >15 h margin before P05 window.
- **Phase P05 Overlap (⚡ track):** P05 Grammar & Linter (`compiler/grammar.lark`, `compiler/lint.py`) may proceed in parallel once P04 frozen contracts are verified.
- **Background Jobs (BG-A):** Full-path pool labeling (S14) and baseline arm retraining (S15) run as non-blocking background jobs, targeting evaluation in P08.

---

## 3. Required Doc Updates

1. **`ARCHITECTURE.md` §7.2, §7.4, §7.5:**
   - Document Two-Stage Tabletop Ground-Plane Fit and Tier C Fallback with condition-number thresholding ($\kappa \in (30, 50]$ for Ridge, $\kappa > 50$ for Tier C) and `[GEOMETRY: TIER C · UNCALIBRATED CAMERA]` badge (`ADR-0009`).
   - Document Pair-Specific Effector Exclusion in Gate G2 with the 20% visibility floor ($a_{\text{vis}} / \hat{a} \ge 0.20$) (`ADR-0010`).
   - Update `evaluate_step_chain` return contract to `tuple[Verdict, list[StepResult], list[ReasonCode], list[Event]]`.
2. **`IDEA.md` §4.2 (F15, F23, F24):**
   - Clarify Tier B ground-plane calibration stability rules and Tier C automatic honesty fallback.
   - Clarify Gate G2 grasp exclusion boundaries (active target only, $\ge 20\%$ visible area floor).
3. **`IMPLEMENTATION_PLAN.md` §P04:**
   - Update P04.S02 to cite ADR-0009; update P04.S06 to cite ADR-0010.
   - Standardize P04.S10 to 1280×720 Verdict Card v1 with lazy rendering.
   - Update P04.S13 to mandate programmatic synthetic frame decorators instead of binary MP4 files.
4. **`.agents/DECISIONS.md`:**
   - Append **ADR-0009** (Two-Stage Tabletop Ground-Plane Fit & Tier C Fallback).
   - Append **ADR-0010** (Pair-Specific Effector Exclusion in Gate G2 with 20% Observability Floor).
5. **`docs/features.yaml`:**
   - Transition measurement features (F15, F16, F17, F18, F19, F20, F21, F22, F23, F24, F28) to `in_progress`.

---

## 4. Tripwires and Kill Criteria (Measurable)

1. **Sim Balanced Accuracy Tri-Tiered Action Protocol:**
   - **Tier 1 (Tuning Zone: $0.80 \le \text{BA} < 0.90$):** Do NOT halt or invoke a mini-council. Grant IMPL-2 a strict 45-minute tuning timebox to adjust Schmitt trigger confirmation window ($n_{\text{on}} \in [2, 5]$) and Hampel filter window ($k \in [5, 9]$).
   - **Tier 2 (True Blocker: $\text{BA} < 0.80$):** Formal BLOCK. Trigger ORCH + D3 mini-council (≤15 min) to diagnose root causes before proceeding.
   - **Tier 3 (Proof Integrity Blocker):** If any episode ID from the 800-episode training split appears in `artifacts/p04/lambda.json`, **instant hard BLOCK**. Wipe the artifact, reset RNG seed, and enforce split assertions in `uncertainty/calibrate.py`.
2. **Clean Sim Episode Coverage:**
   - Clean episode coverage on ManiSkill validation split MUST be $\ge 0.85$ (false `CAN'T TELL` rate $\le 15\%$). If violated, halt integration and inspect Gate G2 effector exclusions and Gate G3 noise floor.
3. **Vectorized Monte Carlo Latency Gate:**
   - 300-frame clip vectorized Monte Carlo evaluation in `tests/uncertainty/test_montecarlo.py` MUST complete in $< 50$ ms (target $< 10$ ms). Pure Python loops over sample dimension $S$ are strictly prohibited.
4. **Stored-Track Replay Badging Integrity:**
   - Any execution using pre-computed tracks (`pipeline.run(tracks=...)`) MUST enforce `is_fixture=True` and append `[REPLAY: CACHED SAM 3.1 TRACKS]` to badges. Runs lacking this badge fail tests automatically.
5. **Exit Code & Schema Conformance:**
   - Return codes MUST strictly adhere to $\{0: \text{PASS}, 1: \text{FAIL}, 2: \text{CANT\_TELL}, 3: \text{ERROR}\}$.
   - Every `CANT_TELL` verdict MUST carry $\ge 1$ canonical `ReasonCode` in `RunResult.reasons`, satisfying Pydantic model validation.

---

## 5. The Single Biggest Risk You See that the Council Missed, and What to Do About It

### The Blindspot: The Dimension-Mismatched Gate G3 & Heterogeneous Component Uncertainty Trap
The council meticulously vectorized Monte Carlo for spatial coordinate scaling ($\text{cm} = \text{px} / k$) and formulated Gate G3 as $|m| < \sigma_m$. However, the council overlooked that the 6 physical predicates evaluate **heterogeneous physical quantities** with incompatible dimensions:
1. `on.scale_ratio`: margin $m_\rho = \tau_\rho - |\sqrt{\rho} - 1|$ is a **dimensionless ratio** (nominal value $\sim 0.05$).
2. `inside.depth_consistency`: margin $m_3$ is a **dimensionless depth ratio**.
3. `dwell.speed`: margin is in **$\text{cm/s}$**, while `dwell.duration` margin is in **seconds ($s$)**.
4. `moves_with.slip`: margin is in $\text{cm}$, but detachment is a discrete temporal onset state machine.

If Gate G3 blindly compares $|m| < \sigma_m$ where $\sigma_m$ is always assigned the spatial position variance (typically $\sigma_m \approx 0.35$ cm), Gate G3 will catastrophically misfire:
- For dimensionless ratio margins ($m_\rho \approx 0.05$), comparing against spatial $\sigma_m \approx 0.35$ means $|m| < \sigma_m$ is **TRUE on 100% of frames**! The engine will collapse into an inescapable false `CAN'T TELL (below_noise_floor)` storm on every valid placement step.
- For temporal dwell duration, comparing a margin of $0.2$ s against spatial $\sigma_m$ in cm is dimensional nonsense that corrupts the audit trace.

Furthermore, regarding frame rates: hardcoding integer frame counts (e.g. `n_on = 3`, `window = 10`) calibrated for 30 fps sim will double the effective physical time delay on 15 fps DROID clips (0.1 s vs 0.2 s for Schmitt trigger; 0.33 s vs 0.67 s for `moves_with`), causing spurious temporal mismatches.

### What to Do About It (Remedies for IMPL-1 and IMPL-2):
1. **Mandate Unit-Matched Uncertainty per Component:**
   In `src/Kodiac_robotics/uncertainty/gates.py`, Gate G3 MUST check dimensional compatibility before applying noise floor thresholding:
   - **Spatial (`unit == "cm"`):** $|m| < \sigma_{\text{spatial}}$ where $\sigma_{\text{spatial}}$ is propagated via spatial MC.
   - **Dimensionless Ratio (`unit == "ratio"`):** Derive analytical ratio uncertainty $\sigma_\rho \approx 2 \cdot (\sigma_{\text{px}} / \ell_0)$ from contour pixel jitter, completely independent of spatial cm scale.
   - **Velocity (`unit == "cm/s"`):** Compute $\sigma_v = \sqrt{2}\sigma_{\text{spatial}} / \Delta t$.
   - **Temporal Duration (`unit == "s"`):** $\sigma_t = 1.0 / \text{fps}$ (single-frame discretization uncertainty).
2. **Strict Gate G3 Unit Guard:**
   `Gate G3` must verify `assert component.unit in ("cm", "s", "ratio", "cm/s")`. If $\sigma$ is zero or uncalibrated for a non-spatial component, Gate G3 must pass through neutrally rather than falsely flipping to `CAN'T TELL`.
3. **Dynamic FPS Time-Base Conversion:**
   In `engine/smoothing.py` and `predicates/`, all temporal windows MUST be computed dynamically from clip fps:  
   `window_frames = max(min_frames, int(round(window_s * fps)))`  
   `n_on = max(2, int(round(0.10 * fps)))`  
   This guarantees identical physical duration thresholds across 30 fps sim and 15 fps DROID.

---

## 6. What Reviewers Must Scrutinize Hardest

1. **Dimensional Consistency in Gate G3 (`Component.unit` vs `Component.sigma`):**
   Verify that `uncertainty/gates.py` never compares a dimensionless ratio margin ($m_\rho$) against a spatial metric $\sigma$ (cm). Review the unit tests in `tests/uncertainty/test_gates.py` to confirm that ratio and temporal components carry unit-matched uncertainty.
2. **Ground-Plane Condition Number Guard (`geometry/scale.py`):**
   Verify that Tier B least-squares solve checks $N_{\text{resting}} \ge 2$ and vertical separation $\Delta v \ge 15$ px before invoking matrix algebra. Verify that ill-conditioned cases ($\kappa > 50$ or residual $> 15\%$) cleanly demote to Tier C, append `[GEOMETRY: TIER C · UNCALIBRATED CAMERA]`, and trigger Gate G6 `depth_ambiguous` without throwing unhandled `LinAlgError` exceptions.
3. **Grasp Boundary Behavior with 20% Observability Floor (`uncertainty/gates.py`):**
   Verify that Gate G2 correctly excludes effector overlap during active `moves_with(gripper, target)`, BUT immediately emits `CAN'T TELL (occluded)` when target visible pixels fall below 20% ($a_{\text{vis}} / \hat{a} < 0.20$). Verify that secondary objects occluded by the gripper are NOT exempted.
4. **Cryptographic Calibration Split Isolation (`uncertainty/calibrate.py`):**
   Audit `uncertainty/calibrate.py` and `artifacts/p04/lambda.json`. Verify that `calibrate.py` strictly accesses the calibration split (`split == "calibration"`, `subsplit == "fit"`), and assert that zero episode IDs from the 800-episode training split appear in the calibration output.
5. **Pydantic Model Validation on CANT_TELL (`pipeline/run.py` & `engine/steps.py`):**
   Verify that `evaluate_step_chain` bubbles up decisive `ReasonCode`s to the top-level `RunResult.reasons`, and confirm that running `Kodiac run` on `occluded_clip.mp4` produces `Verdict.CANT_TELL`, exit code 2, and cleanly passes Pydantic model validation without raising `ValidationError`.
