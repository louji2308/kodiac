# BRIEF: Phase P04 Measurement Engine (`Kodiac run`, full path)

- **Phase:** P04 Measurement Engine
- **Deadline Countdown:** ~167.5 h remaining
- **Mission:** Turn 2D spatio-temporal perception tracks into measured 3D physical facts and honest 3-valued verdicts (`PASS / FAIL / CAN'T TELL` with exit codes 0/1/2/3).
- **Core Tenet:** "Measured, not guessed" (Invariant I6) and "Never guess when blind" (Invariant I3).

---

## 1. Context & Inputs
- **Perception Core (P03):** 100% complete and verified under tag `p03-done`. Universal video IO (`open_clip`), `WindowCut` padding, zero-dependency COCO RLE codec, three backends (`hosted`, `modal`, `fixture`), Re-ID engine, 5 golden clip track fixtures in `tests/fixtures/tracks/`, and `ADR-0008` (Two-Stage Bisect live locate).
- **Pre-Registration:** `prereg-v1` tagged. Hypotheses H1–H3, oracle tolerances (`align_xy_cm <= 3.33, gap_cm <= 0.5`), CAN'T TELL rejection rule, and 10 benchmark arms locked in `experiments/PREREGISTRATION.md`.
- **Full Test Suite:** 156/156 tests passing green offline.

---

## 2. Scope & Target Steps (P04.S01–S15)
1. **S01 Anchors & Measurements (`geometry/anchors.py`):** Bottom/top anchors, centroids, bounding boxes, pixel areas, occlusion fractions.
2. **S02 Scale Model (`geometry/scale.py`):** Object size priors, Tier A (intrinsics from ManiSkill camera params), Tier B (ground-plane least squares fit), Tier C (bounding box prior fallback).
3. **S03 Physical Predicates (`predicates/{on,inside,near,lifted,moves_with,dwell}.py`):** Per-frame `PredFrame` with numeric components (value, threshold, margin, $\sigma$, unit, tri) per `ARCHITECTURE.md` §7.3.
4. **S04 Smoothing & Hysteresis (`engine/smoothing.py`):** Hampel filter ($k=7$) $\to$ Savitzky-Golay ($\approx 0.2$ s) $\to$ Schmitt trigger ($n_{\text{on}}$); U frames neutral.
5. **S05 Uncertainty Propagation (`uncertainty/{sigma,montecarlo,calibrate}.py`):** $\sigma_{\text{px}}$ estimator, vectorized Monte-Carlo ($S=256$), $\lambda$ parameter fitted on **calibration split only** (target 68% at $1\sigma$).
6. **S06 Gates (`uncertainty/gates.py`):** Gates G1–G6 with reason codes and carried-object / container-contents exclusions (`ARCHITECTURE.md` §7.4).
7. **S07 Logic & Step Chain (`engine/{logic,steps}.py`):** Kleene 3-valued boolean operations, temporal expression evaluation, carried literals, step verdict rule.
8. **S08 Run Orchestration (`pipeline/run.py`):** `run(test, clip, mode="full", tracks=None) -> RunResult` with nonce, timings, badges, exit codes (0: PASS, 1: FAIL, 2: CAN'T TELL, 3: ERROR). Stored track replay support.
9. **S09 Trace (`engine/trace.py`):** orjson JSONL writer outputting `runs/<id>/trace.jsonl`.
10. **S10 Evidence Frames & Verdict Card v1 (`render/{evidence,card}.py`):** Decisive frame with mask outlines, centroid crosshairs, and measured numbers burned in; Verdict Card v1 layout.
11. **S11 CLI `Kodiac run` (`cli.py`):** User command `Kodiac run <test.green> <clip-ref>` producing human-readable terminal output, exit codes, and card/trace.
12. **S12 Sim Validation (`scripts/validate_engine.py`):** Validation on $\ge 100$ calibration-split episodes reporting balanced accuracy $\ge 0.90$, coverage $\ge 0.85$, and confusion matrix.
13. **S13 Occlusion & View-Blocked Tests (`tests/engine/test_cant_tell.py`):** Synthetic occlusion tests verifying honest CAN'T TELL verdicts and reason codes.
14. **S14 BG-A Pool Labeling:** CPU batch evaluation of `examples/stackcube.green` over stored pool tracks $\to$ `experiments/labels/Kodiac.parquet`.
15. **S15 BG-A Train Baseline/Oracle Arms:** Launch training $\times 3$ seeds on Modal for complete judge arms.

---

## 3. Council Focus Questions
1. **Scale Tier B Stability:** In real DROID and SO-100 tabletop setups, how stable is ground-plane estimation when camera pitch varies between 30° and 50°? What is the mathematical fallback to prevent false scaling?
2. **$\lambda$ Calibration Isolation:** How do we guarantee zero data leakage between the calibration split and the 1,000-episode training/proof split during $\lambda$ fitting?
3. **Occlusion Gate Exclusions:** How do we ensure that gripper fingers physically enclosing a block during grasp do NOT trigger false Gate G2 occlusions while still catching true external obstructions?
4. **Target Agreement:** What are the exact acceptance gates for balanced accuracy and coverage against sim privileged state?
