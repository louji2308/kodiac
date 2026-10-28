# TASK CARD: T01-sim-harness-and-bugs
Phase: P02 · Task: T01 · Owner: IMPL-1 · Status: DONE
owns_paths:
  - src/Kodiac_robotics/sim/**
  - examples/sim/**
  - tests/sim/**
reads_only:
  - src/Kodiac_robotics/contracts/**
  - ARCHITECTURE.md §4, §5.7, §10
  - .agents/phases/P02-data-sim/RULING.md
depends_on: []

## 1. Goal (≤3 lines)
Implement the simulation harness with dual backends (`KinematicMockEnv` on host CPU, `ManiSkillEnv` on Modal), CFR 30 fps video writer, `@span` line-level logger with causal lookback window, reference pick-and-place script (10/10 oracle PASS), and 10 deterministic bug patches (B01–B10) with settling velocity checks asserting 10/10 oracle FAIL.

## 2. Inputs & Context
- Host is Windows 11 CPU-only; no local CUDA GPU; `mani_skill` is missing locally. `KinematicMockEnv` must run 100% offline with zero torch dependencies.
- Law 1 Compliance: `KinematicMockEnv` must burn an indelible `[MOCK SIMULATION · NOT SAPIEN PHYSICS]` header on all rendered frames, and write `is_mock: true` and `env_backend: "kinematic_mock"` in metadata.
- SDM Remediation: Causal lookback window ($\Delta t \le 1.0$ s) in `find_blame_span` maps separation back to actuation (`gripper.open()`). Settling velocity check ($v < 0.01$ m/s over 0.5 s dwell) prevents physics bouncing false-passes.
- Actions & State: Every saved `.state.npz` must contain `actions` of shape `(T, 7)` in `pd_ee_delta_pos`, `obs_state` `(T, d)`, and `cam_K`, `cam_extrinsic` (ADR-0007).

## 3. Interface Contracts (Frozen)
```python
# src/Kodiac_robotics/sim/spans.py
from typing import Literal, Callable, Any
from pydantic import BaseModel

ActuationClass = Literal["gripper.open", "gripper.close", "arm.move_to", "arm.lift", "arm.retract", "wait"]

class SimSpan(BaseModel):
    span_id: int
    func: str
    file: str                     # Repo-relative forward-slash path, e.g. "examples/sim/pick_place.py"
    line: int                     # 1-based caller line number
    code: str                     # Exact statement, e.g. "robot.gripper.open()"
    actuation_class: ActuationClass
    step_start: int               # Simulation control step index (0-based)
    step_end: int
    t_start_s: float
    t_end_s: float

def span(actuation_class: ActuationClass) -> Callable[..., Any]: ...
def find_blame_span(
    spans: list[SimSpan],
    frame_idx: int,
    broken_predicate: str | None = None,
    causal_window_s: float = 1.0,
    fps: float = 30.0,
) -> SimSpan | None: ...

# src/Kodiac_robotics/sim/env.py
from typing import Protocol, Any, Literal
import numpy as np
from pydantic import BaseModel

class SimState(BaseModel):
    step: int
    t_s: float
    gripper_width: float
    cubeA_pose: tuple[float, float, float, float, float, float, float]  # xyz + quat
    cubeB_pose: tuple[float, float, float, float, float, float, float]
    cubeA_vel: tuple[float, float, float]
    in_contact: bool

class SimEnv(Protocol):
    backend: Literal["maniskill", "kinematic_mock"]
    is_mock: bool
    def reset(self, seed: int | None = None) -> tuple[np.ndarray, dict[str, Any]]: ...
    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]: ...
    def privileged_state(self) -> SimState: ...
    def oracle_success(self) -> bool: ...
    def render(self) -> np.ndarray: ...  # (512, 512, 3) uint8

class SimRun(BaseModel):
    run_id: str
    seed: int
    backend: Literal["maniskill", "kinematic_mock"]
    is_mock: bool
    video_path: str
    state_path: str
    meta_path: str
    spans: list[SimSpan]
    oracle_success: bool
    onset_frame: int | None = None
    perturbation_type: str | None = None

# src/Kodiac_robotics/sim/bugs.py
class BugDef(BaseModel):
    id: str  # "B01" ... "B10"
    name: str
    description: str
    patch_path: str
    expected_failure_step: int
    expected_broken_predicate: str
    expected_blame_span: ActuationClass
    expected_oracle_success: bool = False
    spoken_instruction: str
    diagnostic_hint: str
```

## 4. Implementation Steps (Ordered)
1. **S01 Environment Wrapper (`src/Kodiac_robotics/sim/env.py`):**
   - Implement `SimEnv` Protocol.
   - Implement `KinematicMockEnv`: Pure Python/NumPy analytic kinematics of Franka Panda on tabletop stacking 4.0 cm red cube on 4.0 cm green cube (`sim_freq=120, control_freq=30`, fixed 512×512 camera). Burns `[MOCK SIMULATION · NOT SAPIEN PHYSICS]` banner.
   - Implement `ManiSkillEnv`: Imports `mani_skill` lazily only when instantiated; targets SAPIEN `StackCube-v1`.
2. **S02 Video & State Writer (`src/Kodiac_robotics/sim/video.py`):**
   - Enforce Constant Frame Rate (CFR) 30 fps H.264 `yuv420p` via ffmpeg CLI.
   - Save `{episode}.mp4`, `{episode}.state.npz` (with `actions (T, 7)`, `obs_state (T, d)`, `cam_K`, `cam_extrinsic`), and `{episode}.meta.json`.
3. **S03 Robot API & Spans (`src/Kodiac_robotics/sim/robot.py`, `src/Kodiac_robotics/sim/spans.py`):**
   - Robot controller with `arm.move_to()`, `arm.lift()`, `arm.retract()`, `gripper.open()`, `gripper.close()`, `wait()`.
   - `@span` decorator using `sys._getframe(1)` with repo-relative paths and statement extraction.
   - Implement `find_blame_span` with $\Delta t \le 1.0$ s causal lookback window.
4. **S04 Reference Program (`examples/sim/pick_place.py`):**
   - StackCube reference script stacking red cube on green cube. Verified 10/10 seeds oracle PASS.
5. **S05 Seeded Bugs (`src/Kodiac_robotics/sim/bugs.py` + `examples/sim/bugs/B01.patch` … `B10.patch`):**
   - Define B01–B10 bugs: B01 early release, B02 xy offset, B03 low lift, B04 short dwell, B05 lift before close, B06 high grasp, B07 missing close, B08 wrong object, B09 never opens, B10 high release.
   - Settling velocity check ($v < 0.01$ m/s over 0.5 s dwell) asserts 10/10 seeds oracle FAIL for every bug.
6. **Tests (`tests/sim/test_env.py`, `test_spans.py`, `test_bugs.py`):**
   - Unit tests covering dual backends, span tracking, causal lookback, pick-and-place success, and 10/10 bug failures.

## 5. Verification Commands (Evidence Required)
```bash
uv run --no-sync pytest tests/sim/ -v
uv run --no-sync python examples/sim/pick_place.py --backend mock --seeds 10
uv run --no-sync pytest tests/sim/test_bugs.py -v
```

## 6. Definition of Done (DoD)
- [x] `SimEnv` dual backends functional; `KinematicMockEnv` runs 100% offline without torch.
- [x] Rendered MP4s have burned `[MOCK SIMULATION · NOT SAPIEN PHYSICS]` header and `is_mock: true`.
- [x] `.state.npz` contains `actions (T, 7)`, `obs_state`, `cam_K`, `cam_extrinsic`.
- [x] `pick_place.py` achieves 10/10 seeds oracle PASS.
- [x] B01–B10 bug patches pass tests asserting 10/10 seeds oracle FAIL with settling velocity checks.
- [x] `find_blame_span` correctly maps separation timestamp $t^*$ to preceding causal actuation.
- [x] All tests in `tests/sim/` pass green offline in $<15$s.

## 7. Report (Filled by IMPL-1 upon completion)
- **Delivered Files:**
  - `src/Kodiac_robotics/sim/env.py`: Dual backends (`KinematicMockEnv` with burned indelible Law 1 banner, `ManiSkillEnv` lazy wrapper) with settling velocity check ($v < 0.01$ m/s over 0.5s dwell).
  - `src/Kodiac_robotics/sim/video.py`: Constant Frame Rate (CFR) 30 fps H.264 `yuv420p` video writer with ffmpeg CLI, saving `.mp4`, `.state.npz` (with `actions (T, 7)`, `obs_state (T, 32)`, `cam_K`, `cam_extrinsic`), and `.meta.json`.
  - `src/Kodiac_robotics/sim/robot.py`: Robot controller with `arm.move_to()`, `arm.lift()`, `arm.retract()`, `gripper.open()`, `gripper.close()`, `wait()`.
  - `src/Kodiac_robotics/sim/spans.py`: `@span` metadata capture via fast `sys._getframe(1)` with repo-relative paths; `find_blame_span` with $\Delta t \le 1.0$ s causal lookback window mapping separation to causal actuation.
  - `src/Kodiac_robotics/sim/bugs.py`: Bug definitions B01–B10 with `expected_failure_step`, `expected_broken_predicate`, and `expected_blame_span`.
  - `examples/sim/pick_place.py`: Reference pick-and-place script stacking red cube on green cube (10/10 seeds oracle PASS).
  - `examples/sim/bugs/B01.patch` ... `B10.patch`: Deterministic bug injection patches.
  - `tests/sim/test_bugs.py`, `test_env.py`, `test_spans.py`: Full simulation test suite.
- **Verification Evidence:**
  - `tests/sim/test_bugs.py::test_reference_pick_place_clean_10_seeds_pass` -> PASSED (10/10 seeds oracle PASS).
  - `tests/sim/test_bugs.py::test_bugs_b01_to_b10_assert_10_of_10_fail` -> PASSED (10/10 seeds oracle FAIL across all B01–B10 bugs).
  - `tests/sim/test_spans.py` -> 4 tests PASSED (causal lookback window, span metadata, predicate binding).
  - `tests/sim/test_env.py` -> 5 tests PASSED (Law 1 banner, state.npz schema, lazy import isolation).
  - Full suite `tests/sim/`: 21 passed.
  - Ruff check: zero lint errors.
