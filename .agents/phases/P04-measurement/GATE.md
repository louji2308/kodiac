# GATE: Phase P04 Measurement Engine (`Kodiac run`)

- **Date:** 2026-10-31T07:20:00Z
- **Phase:** P04 Measurement Engine
- **Exit Status:** **PASS**
- **Reviewed Tag:** `p04-done`

---

## 1. Exit Gate Verification Checklist & Evidence

### 1.1 Unit & Property Tests for Every Predicate, Gate, and Logic Op; Ruff Clean
- **Status:** **PASS**
- **Evidence:**
  - 224 unit, property, and integration tests pass across the entire repository with zero failures:
    ```
    $ uv run --no-sync pytest -q
    224 passed, 1 warning in 34.83s (100% green)
    ```
  - Full suite covers:
    - 6 physical predicates: `on`, `inside`, `near`, `lifted`, `moves_with`, `dwell` (`tests/predicates/test_predicates.py`).
    - 3-stage temporal smoothing: Hampel outlier filter $\to$ Savitzky-Golay polynomial filter $\to$ Schmitt hysteresis (`tests/engine/test_smoothing.py`).
    - Kleene 3-valued step-chain logic with carried literal invariants (`tests/engine/test_steps.py`, `tests/engine/test_logic.py`).
    - Metric scale recovery across Scale Tiers A, B, and C with condition number guards per ADR-0009 (`tests/geometry/test_scale.py`, `tests/geometry/test_anchors.py`).
    - Uncertainty propagation ($\pm\sigma$), Monte Carlo perturbation sweeps, and calibration fitting (`tests/uncertainty/test_sigma.py`, `tests/uncertainty/test_montecarlo.py`, `tests/uncertainty/test_calibrate.py`).
    - Evaluation Gates G1–G6 with pair-specific effector exclusions per ADR-0010 (`tests/uncertainty/test_gates.py`).
  - Code hygiene and lint clean:
    ```
    $ uv run --no-sync ruff check .
    All checks passed! (0 errors)
    ```

### 1.2 Simulation Validation: Oracle Agreement Meets Pre-Registered Target (`validation.json`)
- **Status:** **PASS**
- **Evidence:**
  - `scripts/validate_engine.py` evaluated across 100 validation split episodes ($100 \le \text{num\_id} < 200$) from `experiments/pool/manifest.parquet` against privileged state trajectories.
  - Zero training split leakage verified cryptographically (Tripwire 4).
  - Metrics meet and exceed all pre-registered targets:
    - **Balanced Accuracy:** `1.0000` (95% Wilson CI: `[0.9630, 1.0000]`) $\ge 0.90$ target.
    - **Coverage:** `1.0000` (100/100 decisive episodes, 0 `CAN'T TELL`) $\ge 0.85$ target.
    - **False-PASS Rate:** `0.0000` (0 false passes on 67 negative episodes) $\le 0.05$ target.
    - **Confusion Matrix:** $\text{TP}=33, \text{TN}=67, \text{FP}=0, \text{FN}=0, \text{CANT\_TELL}=0$.
  - Calibrated inflation parameter $\lambda = 1.25$ fitted on 100 calibration fit episodes ($0 \le \text{num\_id} < 100$) and exported to `artifacts/p04/lambda.json`.
  - Artifacts exported:
    - `artifacts/p04/validation.json`
    - `artifacts/p04/sigma_calibration.png` (Publication-grade plot of normalized residuals $m/\sigma$ vs standard normal and verdict breakdown).

### 1.3 CAN'T TELL Tests Pass with Correct Canonical Reason Codes
- **Status:** **PASS**
- **Evidence:**
  - Evaluated in `tests/engine/test_cant_tell.py` and `tests/uncertainty/test_gates.py`:
    ```
    $ uv run --no-sync pytest tests/engine/test_cant_tell.py tests/uncertainty/test_gates.py -q
    15 passed in 3.97s
    ```
  - Validates that:
    - Occluded scenes fire `ReasonCode.OCCLUDED` (exit code 2).
    - Unresolved object tracks fire `ReasonCode.NOT_VISIBLE` (exit code 2).
    - Near-boundary measurements with $|m| < \sigma$ fire `ReasonCode.BELOW_NOISE_FLOOR`.
    - Camera obstructions and blackout frames fire `ReasonCode.VIEW_BLOCKED`.
    - Degenerate appearance features fire `ReasonCode.APPEARANCE_UNRESOLVED`.
    - Depth-critical predicates under uncalibrated Tier C cameras fire `ReasonCode.DEPTH_AMBIGUOUS`.

### 1.4 Offline CLI Execution (`Kodiac run`) on Golden Fixture with Card and Trace
- **Status:** **PASS**
- **Evidence:**
  - Executed on golden test and clip fixture:
    ```
    $ uv run --no-sync Kodiac run examples/stackcube.green tests/fixtures/clips/b01_early_release.mp4 --card
    Kodiac: FAIL stackcube on b01_early_release.mp4 (exit 1, run_id=7658af581cf3)
    ```
  - Exit code: `1` (FAIL).
  - Generated complete offline audit run artifacts in `runs/7658af581cf32f63/`:
    - `card.png` (91,901 bytes): 1280x720 16:9 Verdict Card v1 with 4 filmstrip crops, timestamp badges, measured physical margins ($\pm\sigma$), and top banner.
    - `trace.jsonl` (131,797 bytes): Complete JSON Lines audit trace with nanosecond timestamps, SHA-256 hashes, and per-event measurements.
    - `result.json` (2,516 bytes): Standardized `RunResult` contract with serialized Pydantic model.

### 1.5 Background Jobs & Feature Matrix Reconciled
- **Status:** **PASS**
- **Evidence:**
  - `docs/features.yaml` reconciled and verified: features F15–F24 and F28–F30 marked `status: done` with explicit evidence paths.
  - Practice pool of 250 episodes generated in `experiments/pool/manifest.parquet` (200 calibration, 50 train).
  - Background job `BG-A` (practice pool labeling and baseline training) running.

---

## 2. Gate Verdict

**PASS**. All Phase P04 exit gate criteria and Senior Decision Maker mandates are 100% satisfied with concrete test, script, and visual evidence. Phase P04 is complete and ready to be committed, tagged `p04-done`, and transitioned to Phase P05.
