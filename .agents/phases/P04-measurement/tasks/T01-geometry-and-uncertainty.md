# T01: Geometry & Uncertainty Engine Core

phase: P04 · owner: IMPL-1 · status: DONE
plan_ref: IMPLEMENTATION_PLAN.md P04.S01, P04.S02, P04.S05, P04.S06
depends_on: [] · blocks: [T03]
owns_paths:
  - src/Kodiac_robotics/geometry/**
  - src/Kodiac_robotics/uncertainty/**
  - tests/geometry/**
  - tests/uncertainty/**
reads_only:
  - src/Kodiac_robotics/contracts/core.py
  - experiments/PREREGISTRATION.md
  - .agents/phases/P04-measurement/COUNCIL.md
  - .agents/phases/P04-measurement/RULING.md
timebox: 90 min (3-strike rule applies)

---

## Mission
Extract robust physical geometric anchors (bottom/top/centroid/area) from 2D SAM 3.1 masks, implement multi-tier metric coordinate projection (Tier A exact intrinsics, Tier B two-stage Ridge ground-plane fit with Tier C size prior fallback and condition-number guard), propagate measurement uncertainty via dynamic vectorized Monte Carlo ($S=256$, $<50$ ms), fit inflation $\lambda$ strictly on the calibration split, and enforce evaluation Gates G1–G6 with pair-specific effector exclusion ($\ge 20\%$ visibility floor).

---

## Interface Contracts (FROZEN)

```python
# 1. src/Kodiac_robotics/geometry/anchors.py
def compute_anchors(
    mask: ObjMask,
    base_area_px: int | None = None,
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float], int, float]:
    """Extracts geometric anchors from an ObjMask.
    Returns: ((cx, cy), bottom_anchor, top_anchor, area_px, occlusion_fraction).
    - bottom_anchor: (median column of lowest 5% of mask rows, lowest row).
    - top_anchor: (median column of highest 5% of mask rows, highest row).
    - occlusion_fraction: 0.0 if base_area_px is None else max(0.0, 1.0 - area_px / base_area_px).
    """

# 2. src/Kodiac_robotics/geometry/scale.py
class ScaleModel(Protocol):
    tier: Literal["A", "B", "C"]
    def to_table_frame(self, obj: str, frame: int) -> tuple[float, float, float, float]:
        """Returns table-frame coordinates (X_cm, D_cm, h_cm, sigma_cm)."""

def fit_scale_model(
    clip: Clip,
    tracks: dict[str, Track],
    objects: list[ObjectDecl],
    cam_K: np.ndarray | None = None,
    cam_extrinsic: np.ndarray | None = None,
) -> ScaleModel:
    """Solves scale across Tiers A, B, C:
    - Tier A: If cam_K and cam_extrinsic are provided, use exact perspective projection.
    - Tier B: If N_resting >= 2 resting objects on table with delta_v >= 15 px,
      solve unconstrained least-squares ground plane. If condition number kappa in (30, 50],
      apply Tikhonov Ridge regularization toward table prior theta_0 = 40 deg.
      If kappa > 50, residual > 15%, or N_resting < 2, gracefully demote to Tier C.
    - Tier C: Bounding box size prior fallback (k = l / W_o) with 2.5x sigma inflation,
      append badge '[GEOMETRY: TIER C · UNCALIBRATED CAMERA]', and flag Gate G6 depth_ambiguous.
    """

# 3. src/Kodiac_robotics/uncertainty/sigma.py
def estimate_pixel_jitter(
    tracks: dict[str, Track],
    static_window: tuple[int, int] = (0, 15),
) -> float:
    """Estimates pixel jitter sigma_px via second-difference MAD over static segments.
    sigma_px = max(0.5, 1.4826 * MAD(Delta^2 x) / sqrt(6)).
    """

# 4. src/Kodiac_robotics/uncertainty/montecarlo.py
def propagate_uncertainty_mc(
    val_nom: float,
    sigma_px: float,
    scale_k: float,
    sigma_k: float,
    n_samples: int = 256,
) -> float:
    """Vectorized Monte Carlo error propagation with physical parameter clipping.
    - Samples k_sample = np.maximum(np.random.normal(scale_k, sigma_k, n_samples), 0.1)
    - Returns finite, non-negative standard deviation sigma_m >= 0.001.
    """

# 5. src/Kodiac_robotics/uncertainty/calibrate.py
def fit_inflation_lambda(
    calibration_manifest_path: Path,
    output_path: Path = Path("artifacts/p04/lambda.json"),
) -> float:
    """Fits uncertainty inflation lambda strictly on calibration fit split (ep_id < 100).
    Cryptographically asserts zero episode IDs from training pool (ep_id >= 200).
    Saves {"lambda": lambda_val, "split": "calibration_fit", "n_episodes": N} to output_path.
    """

# 6. src/Kodiac_robotics/uncertainty/gates.py
def apply_gates(
    components: list[Component],
    tracks: dict[str, Track],
    scale: ScaleModel,
    frame: int,
    active_step: Step | None = None,
) -> tuple[list[Component], list[ReasonCode]]:
    """Evaluates evaluation Gates G1-G6:
    - G1: NOT_VISIBLE if track confidence/score < 0.5.
    - G2: OCCLUDED if target object occluded > 40%.
      EXCLUSION: If active_step has moves_with(effector, target), effector overlap is excluded
      IFF target retains >= 20% visible unoccluded area (observability floor).
      Container rims in inside(A, B) are excluded.
    - G3: BELOW_NOISE_FLOOR if component |margin| < sigma_m.
    - G4: VIEW_BLOCKED if frame luminance < 15/255, low Laplacian variance, or >60% uniform.
    - G5: APPEARANCE_UNRESOLVED if Re-ID confidence is degenerate.
    - G6: DEPTH_AMBIGUOUS if scale.tier == 'C' and component requires depth geometry.
    Returns: (gated_components, triggered_reasons).
    """
```

---

## Steps
1. **S01 Anchors:** Create `src/Kodiac_robotics/geometry/anchors.py`. Implement `compute_anchors`. Write unit tests in `tests/geometry/test_anchors.py`.
2. **S02 Scale Models:** Create `src/Kodiac_robotics/geometry/scale.py`. Implement `TierAScaleModel`, `TierBScaleModel`, `TierCScaleModel`, and `fit_scale_model` with Ridge regularization and condition-number singularity guard. Write unit tests in `tests/geometry/test_scale.py`.
3. **S05 Sigma & Monte Carlo:** Create `src/Kodiac_robotics/uncertainty/sigma.py` and `src/Kodiac_robotics/uncertainty/montecarlo.py`. Implement vectorized NumPy error propagation ($S=256$, $<50$ ms) and physical clipping ($k \ge 0.1$). Write unit tests in `tests/uncertainty/test_montecarlo.py`.
4. **S05 Calibration:** Create `src/Kodiac_robotics/uncertainty/calibrate.py`. Assert split isolation. Write unit test in `tests/uncertainty/test_calibrate.py`.
5. **S06 Gates:** Create `src/Kodiac_robotics/uncertainty/gates.py`. Implement Gates G1–G6 with pair-specific effector exclusion and 20% observability floor. Write unit tests in `tests/uncertainty/test_gates.py`.

---

## Definition of Done
- [x] `uv run --no-sync pytest tests/geometry tests/uncertainty -q` passes 100% green offline (24/24 passed in 1.78s).
- [x] Tier B scale gracefully demotes to Tier C on ill-conditioned synthetic tracks with `[GEOMETRY: TIER C]` badge.
- [x] Vectorized Monte Carlo evaluates 300 frames in $<50$ ms (< 5 ms measured).
- [x] Gate G2 effector exclusion preserves 20% visibility floor; drops below 20% emit `OCCLUDED`.
- [x] `calibrate.py` raises `ValueError` if any training split episode ID is accessed.
- [x] Zero TODO/stubs left in owned paths (`rg -n "TODO|NotImplemented" src/Kodiac_robotics/geometry src/Kodiac_robotics/uncertainty` is empty).
- [x] Committed with message `feat(p04/t01): geometry anchors, scale tiers, vectorized mc, and evaluation gates`.

---

## Report

### Summary of Completed Work
1. **Geometry Anchors (`src/Kodiac_robotics/geometry/anchors.py`):**
   - Implemented `compute_anchors(mask, base_area_px)` returning `((cx, cy), bottom_anchor, top_anchor, area_px, occlusion_fraction)`.
   - Bottom anchor calculated as median column of lowest 5% rows, top anchor as median column of highest 5% rows, with graceful fallback to bounding box when mask is empty.
2. **Scale Models (`src/Kodiac_robotics/geometry/scale.py`):**
   - Implemented `TierAScaleModel` for exact perspective back-projection using camera intrinsics $K$ and extrinsics $[R \mid t]$.
   - Implemented `TierBScaleModel` solving the tabletop ground-plane least-squares equation $v_i = v_h + \tilde{H} \cdot k_i$. Checked pre-conditions $N_{\text{resting}} \ge 2$ and $\Delta v \ge 15$ px. Applied Tikhonov Ridge regularization when condition number $\kappa \in (30, 50]$, and automatic demotion to Tier C when $\kappa > 50$, residual $> 15\%$, pitch angle $\theta \notin [20^\circ, 70^\circ]$, or matrix solve raises `LinAlgError` (ADR-0009).
   - Implemented `TierCScaleModel` with $2.5\times \sigma$ inflation and `[GEOMETRY: TIER C · UNCALIBRATED CAMERA]` badge.
3. **Uncertainty Propagation & Calibration (`src/Kodiac_robotics/uncertainty/`):**
   - `sigma.py`: Implemented robust `estimate_pixel_jitter` using second-difference MAD over static segments ($\sigma_{\text{px}} = \max(0.5, 1.4826 \cdot \text{MAD} / \sqrt{6})$).
   - `montecarlo.py`: Vectorized NumPy Monte Carlo ($S=256$) error propagation with physical clipping ($k \ge 0.1$), completing 300 frames in $< 5$ ms.
   - `calibrate.py`: Implemented `fit_inflation_lambda` strictly on calibration fit split (`ep_id < 100`, `split == 'calibration'`) with hard cryptographic assertions rejecting any training pool episodes (`ep_id >= 200` or `split == 'train'`).
4. **Evaluation Gates G1–G6 (`src/Kodiac_robotics/uncertainty/gates.py`):**
   - Implemented Gates G1–G6 with unit-matched uncertainty per SDM mandate (spatial cm, ratio, velocity, duration).
   - Enforced ADR-0010 pair-specific effector exclusion strictly for active `moves_with(effector, target)` and container rims in `inside(A, B)`, guarded by a strict 20% observability floor ($a_{\text{vis}} / \hat{a} \ge 0.20$). Drops below 20% emit `ReasonCode.OCCLUDED`. Non-target objects are not exempt.
   - Enforced Gate G6 `DEPTH_AMBIGUOUS` on Tier C for depth-critical components.

### Test & Verification Evidence
- `uv run --no-sync pytest tests/geometry tests/uncertainty -v` -> 24 passed in 1.78s (100% green).
- `uv run --no-sync ruff check src/Kodiac_robotics/geometry src/Kodiac_robotics/uncertainty tests/geometry tests/uncertainty` -> All checks passed!
- `uv run --no-sync ruff format --check src/Kodiac_robotics/geometry src/Kodiac_robotics/uncertainty tests/geometry tests/uncertainty` -> 14 files formatted.
- `git grep -n -E "TODO|NotImplemented" src/Kodiac_robotics/geometry src/Kodiac_robotics/uncertainty` -> 0 matches.
