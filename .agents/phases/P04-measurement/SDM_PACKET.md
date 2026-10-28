# SDM Escalation Packet: Phase P04 Measurement Engine (`Kodiac run`, full path)

- **Date:** 2026-10-28T17:40:00Z
- **Phase:** P04 (`P04-measurement`)
- **Sender:** Orchestrator (ORCH)
- **Recipient:** Senior Decision Maker (SDM)
- **Trigger:** High-Leverage Phase Mandate (P04 per `AGENTS.md §6.1`) + Escalated Architectural IPs (`IP-P04-D1-1`, `IP-P04-D3-3`).
- **Council Consensus:** **100% UNANIMOUS APPROVE** (D1 Architect: 94/100, D2 Judge Advocate: 98/100, D3 Red Team: 96/100; Average: 96/100).
- **Open Disagreements:** **NONE** (0 open disagreements).

---

## 1. Phase Goal & Strategic Mission
Transform raw 2D spatio-temporal SAM 3.1 perception mask tracks into verified 3D metric facts ($\text{cm}, \text{s}$) with calibrated uncertainty ($\pm\sigma$) and evaluate Kleene 3-valued step logic to deliver honest `PASS`, `FAIL`, and `CAN'T TELL` verdicts (exit codes 0/1/2/3). Validate physical predicates and uncertainty calibration against ManiSkill3 simulation privileged ground truth ($\text{BA} \ge 0.90, \text{Coverage} \ge 0.85$), producing `runs/<id>/{result.json,trace.jsonl}` and Verdict Card v1 while establishing the live engine for the hackathon video and interactive judge testing.

---

## 2. Key Evidence & Prior Phase Clearance
- **Phase P03 Review:** Dual-reviewer verdict **`PASS (SHIP-AS-IS)`** from R1 Verifier and R2 Judge's Eye (0 S0, 0 S1, 2 S2, 2 S3; weighted judge score 9.39/10). Full test suite 156/156 passing green in 63.2s offline.
- **ADR-0008 Two-Stage Bisect:** Benchmarked at p95 locate time of 5.82 s (< 8.0 s gate, $0.02 cost), reserving 6.18 s headroom for P04 spatial calibration and predicate evaluation against the 12.0 s live ceiling.
- **Pre-Registration Tag:** Git tag `prereg-v1` locked on commit `499d21a`.
- **Contracts Frozen:** `src/Kodiac_robotics/contracts/core.py` provides tested schemas: `Tri`, `Verdict`, `ReasonCode`, `Component`, `PredFrame`, `Event`, `StepResult`, `RunResult`, `ScaleModel`.

---

## 3. High-Leverage Escalated Proposals for SDM Ratification

| IP ID | Title & Summary | Council Recommendation | SDM Action Requested |
|---|---|:---:|---|
| **IP-P04-D1-1** / **IP-P04-D3-1** | **Two-Stage Tabletop Ground-Plane Fit & Tier C Fallback:** When solving camera tilt and horizon on tabletop setups with resting objects, require $N_{\text{resting}} \ge 2$ and vertical baseline $\Delta v \ge 15$ px. Solve unconstrained least-squares first. If condition number $\kappa \in (30, 50]$, apply Tikhonov Ridge regularization toward table aspect prior ($\theta_0 = 40^\circ$). If $\kappa > 50$, residual $> 15\%$, or $N_{\text{resting}} < 2$, automatically demote to Tier C ($k = \ell / W_o$ with $2.5\times \sigma$ inflation), append badge `[GEOMETRY: TIER C · UNCALIBRATED CAMERA]`, and trigger Gate G6 `depth_ambiguous` on depth-critical components. | **APPROVE** (Unanimous) | **RATIFY as ADR-0009**. Eliminates numerical singularity while preserving true tilt on non-standard camera angles. |
| **IP-P04-D3-3** | **Pair-Specific Effector G2 Exclusion with 20% Observability Floor:** Exclude robot effector overlap from Gate G2 (`OCCLUDED`) *strictly* for the declared object in an active `moves_with(effector, target)` relation, and *only* if the target retains $\ge 20\%$ visible area ($a_{\text{vis}} / \hat{a} \ge 0.20$). If $a_{\text{vis}} / \hat{a} < 0.20$, Gate G2 MUST fire with `CAN'T TELL (occluded)`. Container rims in `inside(A, B)` are excluded. Non-target objects occluded by the gripper are NOT exempt. | **APPROVE** (Unanimous) | **RATIFY as ADR-0010**. Solves false occlusion during valid grasps without violating Invariant I3 ("Never guess when blind"). |

---

## 4. Council-Local Consensus Improvements (Ratified by Council)
1. **IP-P04-D1-2 / IP-P04-D3-2 (Vectorized MC Uncertainty):** Dynamic 1D scale vectorization in NumPy ($<8$ ms) with physical clipping ($k \ge 0.1, W \ge 0.2 W_{\text{nom}}$), decoupled from 1D predicate logic, eliminating 3D tensor interface collisions between IMPL-1 and IMPL-2.
2. **IP-P04-D1-3 (Stored-Track Replay API):** Add `tracks` parameter to `pipeline.run()`. When present, enforce `is_fixture=True` and indelible badge `[REPLAY: CACHED SAM 3.1 TRACKS]`, satisfying Law 1.
3. **IP-P04-D2-1 (Verdict Card v1):** 1280×720 (16:9) default layout with decisive frame, supervision masks, step timeline strip, and metadata badges. Card rendering is lazy/opt-in (`render_card=False` in batch labeling). Displacement arrows deferred to P06.
4. **IP-P04-D2-2 (TTY-Aware Rich CLI):** Terminal Rich Table/Panel on interactive TTY; clean plain text when piped; strictly valid pure JSON on `--json`, preserving UNIX composability (Invariant I1).
5. **IP-P04-D2-3 (In-Memory Obstruction Tests):** Programmatic synthetic frame decorators (`apply_synthetic_box`, `apply_black_out`, `apply_gaussian_blur`) in `tests/engine/test_cant_tell.py` without binary MP4 repo bloat.
6. **IP-P04-D2-4 (Automated Validation Report):** Standalone `artifacts/p04/validation_summary.md` and `sigma_calibration.png` generated via headless matplotlib (`matplotlib.use('Agg')`), without modifying `README.md` prematurely.
7. **Contract Alignment:** Return signature of `evaluate_step_chain` standardized to:  
   `tuple[Verdict, list[StepResult], list[ReasonCode], list[Event]]`, guaranteeing Pydantic validator compliance on `CANT_TELL`.

---

## 5. Frozen Task DAG & Disjoint Ownership
```
[Wave 1: Core Engines (Parallel)]
  T01 (IMPL-1): Geometry & Uncertainty Core (S01, S02, S05, S06)
    owns_paths:
      - src/Kodiac_robotics/geometry/**
      - src/Kodiac_robotics/uncertainty/**
      - tests/geometry/**
      - tests/uncertainty/**

  T02 (IMPL-2): Predicates, Smoothing & Step Logic (S03, S04, S07)
    owns_paths:
      - src/Kodiac_robotics/predicates/**
      - src/Kodiac_robotics/engine/{smoothing,logic,steps,dispatch}.py
      - tests/predicates/**
      - tests/engine/test_{smoothing,logic,steps}.py

[Wave 2: Integration, Orchestration & Presentation (Depends on T01 + T02)]
  T03 (IMPL-3): Pipeline Orchestration, Trace, Card v1, CLI & Tests (S08, S09, S10, S11, S13)
    owns_paths:
      - src/Kodiac_robotics/pipeline/**
      - src/Kodiac_robotics/engine/trace.py
      - src/Kodiac_robotics/render/**
      - src/Kodiac_robotics/cli.py
      - tests/pipeline/**
      - tests/render/**
      - tests/engine/test_cant_tell.py
      - tests/cli/test_run_cli.py

[Wave 3: Post-Integration Validation & Background Compute]
  ORCH + IMPL-3: S12 Sim Validation & Background Jobs (S14 Pool Labeling, S15 Modal Training Launch)
    owns_paths:
      - scripts/validate_engine.py
      - artifacts/p04/**
      - experiments/labels/**
```

---

## 6. Measurable Kill Criteria & Tri-Tiered Action Protocol
1. **Sim Balanced Accuracy:** $\text{BA} \ge 0.90$ on calibration validation split.
   - *Tier 1 ($0.80 \le \text{BA} < 0.90$):* 45-min tuning timebox for IMPL-2 on Schmitt trigger and Hampel windows.
   - *Tier 2 ($\text{BA} < 0.80$):* Formal BLOCK, invoke mini-council.
2. **Clean Sim Episode Coverage:** $\text{Coverage} \ge 0.85$ ($\le 15\%$ false CAN'T TELL). Halt if violated.
3. **Proof Integrity (Calibration Leakage):** **Zero** training-split episode IDs in `artifacts/p04/lambda.json`. Instant hard BLOCK if violated.
4. **Vectorized MC Latency:** $< 50$ ms for 300-frame clip evaluation.
5. **Exit Codes:** Strictly $\{0: \text{PASS}, 1: \text{FAIL}, 2: \text{CANT\_TELL}, 3: \text{ERROR}\}$.

---

## 7. Concept Invariant Scan
- **Invariant I1 (UNIX Composable CLI):** Preserved via TTY detection and pure `--json` mode.
- **Invariant I3 (Never Guess When Blind):** Preserved via Gates G1–G6 and the 20% visibility floor on effector exclusions.
- **Invariant I8 (Pre-Registration Integrity):** Preserved via cryptographic split isolation in `calibrate.py`.
- **Invariant I14 (SAM 3.1 Measuring Instrument):** Preserved via direct mask anchor and scale propagation.
- **Prime Directive Law 1 (Never Fake Anything):** Preserved via `[REPLAY: CACHED SAM 3.1 TRACKS]` and `[GEOMETRY: TIER C]` badges.

---

## 8. Schedule Math & Budget
- **Time Remaining to Submit:** 167.3 h (Internal submit Nov 4 17:00 UTC).
- **Phase P04 Window:** 24.0 h budget.
- **Wall-Clock Projection:** Parallel Wave 1 (T01 ∥ T02) = 4.5 h; Wave 2 (T03) = 4.5 h; S12 Validation = 1.5 h. Total = ~10.5 h wall-clock.
- **Cost:** ~$3.62 against Modal free tier ($100 credits). Zero paid external APIs.

---

## 9. Request to SDM
Please review this packet and issue a formal ruling in `.agents/phases/P04-measurement/RULING.md`:
1. Ratify `IP-P04-D1-1` / `IP-P04-D3-1` as **`ADR-0009`** (Two-Stage Tabletop Ground-Plane Fit & Tier C Fallback).
2. Ratify `IP-P04-D3-3` as **`ADR-0010`** (Pair-Specific Effector G2 Exclusion with 20% Observability Floor).
3. Authorize immediate dispatch of task cards T01, T02, and T03 across IMPL-1, IMPL-2, and IMPL-3.
