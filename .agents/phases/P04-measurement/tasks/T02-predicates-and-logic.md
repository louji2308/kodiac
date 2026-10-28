# T02: Predicates, Smoothing & Step-Chain Logic Engine

phase: P04 · owner: IMPL-2 · status: TODO
plan_ref: IMPLEMENTATION_PLAN.md P04.S03, P04.S04, P04.S07
depends_on: [] · blocks: [T03]
owns_paths:
  - src/Kodiac_robotics/predicates/**
  - src/Kodiac_robotics/engine/smoothing.py
  - src/Kodiac_robotics/engine/logic.py
  - src/Kodiac_robotics/engine/steps.py
  - src/Kodiac_robotics/engine/dispatch.py
  - tests/predicates/**
  - tests/engine/test_smoothing.py
  - tests/engine/test_logic.py
  - tests/engine/test_steps.py
reads_only:
  - src/Kodiac_robotics/contracts/core.py
  - src/Kodiac_robotics/geometry/**
  - src/Kodiac_robotics/uncertainty/**
  - .agents/phases/P04-measurement/COUNCIL.md
  - .agents/phases/P04-measurement/RULING.md
timebox: 90 min (3-strike rule applies)

---

## Mission
Implement the closed 6-predicate physical vocabulary (`on`, `inside`, `near`, `lifted`, `moves_with`, `dwell`) and AST atom dispatcher returning typed `PredFrame` and `Component` measurements with signed margins ($m > 0 \iff \text{satisfied}$); apply 3-stage temporal smoothing (Hampel outlier rejection $\to$ Savitzky-Golay trajectory smoothing $\to$ Schmitt hysteresis trigger); and execute Kleene 3-valued step-chain logic with carried literals, returning decisive verdicts and bubbling up top-level `ReasonCode`s to guarantee Pydantic schema validation.

---

## Interface Contracts (FROZEN)

```python
# 1. src/Kodiac_robotics/predicates/base.py & dispatch.py
def evaluate_atom(
    atom: Atom,
    tracks: dict[str, Track],
    scale: ScaleModel,
    frame: int,
    fps: float,
    context: dict[str, Any] | None = None,
) -> PredFrame:
    """Evaluates an AST Atom on a single frame.
    - If atom.kind == 'pred', dispatches to predicate implementation in predicates/{name}.py.
    - If atom.kind == 'looks', returns PredFrame(tri=UNKNOWN, components=[]) pass-through.
    - If atom.kind == 'manual', skips evaluation.
    """

# 2. src/Kodiac_robotics/predicates/*.py
# Each predicate implements evaluation returning PredFrame with components:
# - on(a, b): lateral alignment margin m_xy (cm), vertical gap margin m_z (cm), scale consistency m_rho.
# - inside(a, b): in-rim margin m_rim (cm), depth consistency m_depth (cm), front-occluder check (MVP-lite).
# - near(a, b): 3D Euclidean boundary distance margin m (cm).
# - lifted(a, min_cm=5.0): vertical displacement (h_A,t - h_A,0) - min_cm (cm).
# - moves_with(a, b, window_s=0.3): relative displacement rho_rel = ||Delta_A - Delta_B|| over window_s.
# - dwell(condition, for_s=0.5): run-length of stillness and condition satisfaction.

# 3. src/Kodiac_robotics/engine/smoothing.py
class TemporalSmoother:
    def __init__(self, fps: float, hampel_k: int = 7, savgol_window_s: float = 0.2, schmitt_n_on: int = 3): ...
    def smooth_trajectory(self, raw_values: np.ndarray) -> np.ndarray:
        """Hampel filter (k=7) -> Savitzky-Golay (polyorder=2)."""
    def apply_schmitt_trigger(self, tri_states: list[Tri]) -> list[Tri]:
        """Applies tri-state hysteresis: requires n_on consecutive TRUE to flip to TRUE.
        UNKNOWN (U) acts neutrally without confirming or resetting state.
        """

# 4. src/Kodiac_robotics/engine/logic.py
def kleene_not(val: Tri) -> Tri: ...
def kleene_and(a: Tri, b: Tri) -> Tri: ...
def kleene_or(a: Tri, b: Tri) -> Tri: ...
def evaluate_conjunction(literals: list[tuple[bool, Tri]]) -> Tri:
    """Evaluates a conjunction of possibly negated Tri-state literals."""

# 5. src/Kodiac_robotics/engine/steps.py (FIXED CONTRACT)
def evaluate_step_chain(
    steps: list[Step],
    pred_frames_by_atom: dict[str, list[PredFrame]],
    fps: float,
) -> tuple[Verdict, list[StepResult], list[ReasonCode], list[Event]]:
    """Evaluates sequential step chain over clip.
    - Step achievement: a_k = min { t > a_{k-1} : C_k == TRUE for n_on frames }.
    - Carried literals persistence: positive literals in C_k persist into subsequent steps.
    - Resolves overall Verdict: PASS if all steps achieve; FAIL if a terminal violation occurs;
      CANT_TELL if decisive step is UNKNOWN.
    - Returns: (overall_verdict, step_results, top_level_reasons, events).
    - INVARIANT: If overall_verdict == CANT_TELL, len(top_level_reasons) >= 1.
    """
```

---

## Steps
1. **S03 Predicates:** Implement individual predicate evaluations in `src/Kodiac_robotics/predicates/{on,inside,near,lifted,moves_with,dwell,dispatch}.py`. Write unit tests in `tests/predicates/test_predicates.py`.
2. **S04 Smoothing:** Implement `TemporalSmoother` in `src/Kodiac_robotics/engine/smoothing.py` (Hampel $\to$ SavGol $\to$ Schmitt). Write unit tests in `tests/engine/test_smoothing.py`.
3. **S07 Kleene Logic:** Implement 3-valued Kleene boolean operations in `src/Kodiac_robotics/engine/logic.py`. Write unit tests in `tests/engine/test_logic.py`.
4. **S07 Step Chain:** Implement `evaluate_step_chain` in `src/Kodiac_robotics/engine/steps.py` with carried literal persistence, event logging, and top-level reason aggregation. Write unit tests in `tests/engine/test_steps.py`.

---

## Definition of Done
- [ ] `uv run --no-sync pytest tests/predicates tests/engine/test_smoothing.py tests/engine/test_logic.py tests/engine/test_steps.py -q` passes 100% green offline.
- [ ] All 6 physical predicates return typed `PredFrame` and `Component` objects with correct signs ($m > 0 \iff \text{pass}$).
- [ ] Schmitt trigger neutral handling of Unknown ($U$) verified: $U$ neither confirms nor breaks hysteresis run length.
- [ ] Carried literal persistence verified: Step 1 grasp state (`moves_with`) persists during Step 2 place unless explicitly negated.
- [ ] `evaluate_step_chain` returns top-level `list[ReasonCode]` such that `RunResult(verdict=CANT_TELL, reasons=...)` passes Pydantic model validation.
- [ ] Zero TODO/stubs in owned paths (`rg -n "TODO|NotImplemented" src/Kodiac_robotics/predicates src/Kodiac_robotics/engine` is empty).
- [ ] Committed with message `feat(p04/t02): physical predicates, temporal smoothing, and kleene step chain logic`.
