# T01: Geometry & Uncertainty Engine Core

phase: P04 · owner: IMPL-1 · status: TODO
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
- [ ] `uv run --no-sync pytest tests/geometry tests/uncertainty -q` passes 100% green offline.
- [ ] Tier B scale gracefully demotes to Tier C on ill-conditioned synthetic tracks with `[GEOMETRY: TIER C]` badge.
- [ ] Vectorized Monte Carlo evaluates 300 frames in $<50$ ms.
- [ ] Gate G2 effector exclusion preserves 20% visibility floor; drops below 20% emit `OCCLUDED`.
- [ ] `calibrate.py` raises `ValueError` if any training split episode ID is accessed.
- [ ] Zero TODO/stubs left in owned paths (`rg -n "TODO|NotImplemented" src/Kodiac_robotics/geometry src/Kodiac_robotics/uncertainty` is empty).
- [ ] Committed with message `feat(p04/t01): geometry anchors, scale tiers, vectorized mc, and evaluation gates`.
