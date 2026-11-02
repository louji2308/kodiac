# T04: Done-gate (anti-cheat) + `sim.runner.run_script`
phase: P07 · owner: IMPL-4 (Opus 5.5 @ xhigh) · status: TODO
plan_ref: IMPLEMENTATION_PLAN.md P07.S02, S04 · ARCHITECTURE.md §5.5, KD-11 · IDEA F39 (Invariant: the /goal loop with a done-gate that blocks "done" until `Kodiac run` returns PASS)
depends_on: [] · blocks: [T05 (consumes runner contract), ORCH CLI `gate` wiring]
owns_paths: [src/Kodiac_robotics/loop/gate.py, src/Kodiac_robotics/loop/pins.py, src/Kodiac_robotics/sim/runner.py, tests/loop/test_gate.py, tests/loop/test_runner.py, tests/loop/__init__.py, artifacts/p07/gate_refusals.json]
reads_only: [contracts/**, pipeline/run.py, sim/{env,robot,spans,bugs,video}.py, examples/**, blame/** (when present)]
timebox: 150 min (3-strike rule applies)

## Mission
"A coding agent that cannot declare victory until a physical test passes." The gate is a Stop hook: exit 0 allows stopping, exit 2 blocks and
feeds blame + diff + hint back to the agent. It is attacked by design: Muse Code can edit the test, thresholds, cache a PASS, edit the pin
file, stub the sim. Make each attack fail closed. Also provide `sim.runner.run_script`, the sim execution primitive the gate and MCP need.

## Interface contract (FROZEN; ORCH-owned, you implement)
```python
# sim/runner.py  (as in BRIEF.md)
class SimRunResult(BaseModel):
    video_path: str; state_path: str; spans_path: str
    oracle_success: bool; backend: Literal["maniskill","kinematic_mock"]; is_mock: bool
    script_sha256: str; seed: int; n_frames: int; fps: float
def run_script(script: Path, seed: int, out_dir: Path, backend: Literal["auto","kinematic_mock","maniskill"]="auto") -> SimRunResult
# loop/pins.py
def pin_dir() -> Path                                   # ~/.config/Kodiac/gates/ (override: env KODIAC_GATE_HOME for tests)
def pin_path(workspace: Path) -> Path                   # <pin_dir>/<sha256(resolved workspace)>.json  (OUTSIDE the workspace)
def write_pins(workspace: Path, *, test: Path, sim_script: Path, seed: int, config_files: list[Path], max_blocks: int) -> GateState
def load_pins(workspace: Path) -> tuple[GateState, dict] | None   # None = no --init state
# loop/gate.py
def gate_init(workspace: Path, test: Path, sim_script: Path, seed: int = 0, max_blocks: int = 8) -> GateState
def gate_check(workspace: Path, hook_payload: dict | None = None) -> tuple[int, str]   # (exit_code ∈ {0,2}, stderr_message)
```
Env: gate loads secrets only from `Kodiac_ENV_FILE` (hooks run with a cleared env) and never prints values. **`gate_check` never returns 3.**

## Semantics (ARCHITECTURE §5.5 / KD-11, binding)
- No pin state for the workspace → exit 0 (never blocks unrelated sessions).
- `blocks ≥ max_blocks` → print `GATE EXHAUSTED: goal NOT verified`, write `.Kodiac/gate_exhausted`, exit 0.
- Otherwise the gate **re-runs** the pinned sim script (current file contents) through `sim.runner.run_script` then the pinned test through `pipeline.run.run`; it never trusts `.Kodiac/last_verdict.json`.
- PASS iff verdict == PASS ∧ test sha256 == pin ∧ config sha256 == pin ∧ `ClipRef.source_kind == "sim"` ∧ the clip graded is the one just produced from `sha256(current script)`.
- Not PASS → `blocks += 1`, exit 2, stderr = blame + diff + hint when available (use `blame.*` if importable, otherwise the verdict reasons/decisive components; do not import-fail), never auto-pass on `stop_hook_active`.
- Any internal error (missing/corrupt pin or env file, sim crash, test unparsable) → exit 2 `GATE ERROR: …` (fail closed). Mock backend → still gates, but the message and the verdict card carry `[MOCK SIMULATION]`; PASS on mock is valid for the loop demo and is labelled.

## Steps
1. Read ARCHITECTURE §5.5, KD-11, `sim/env.py` (KinematicMockEnv API, how `pick_place.run(robot)` is driven; see `tests/sim/test_env.py`, `examples/sim/pick_place.py`), `sim/video.py`, `sim/spans.py`, `pipeline/run.py`.
2. `sim/runner.py`: load the script module from path, build env by backend (`auto` → ManiSkill iff importable), construct `Robot`, run `run(robot)`, write video (watermarked for mock per ADR-0004), `state.npz`, `spans.jsonl`, compute `oracle_success` from the env's privileged state (**oracle is for eval/gate-honesty checks only**: the gate verdict comes from `pipeline.run.run`, never from the oracle). Produce tracks for the engine the same way `scripts/skeleton.py` / `scripts/validate_engine.py` do, and label them synthetic-from-state if that is how they are made (`evidence_type`); note this limit prominently in the module docstring (this is the loop demo path, not perception evidence).
3. `loop/pins.py` + `loop/gate.py` per the contract.
4. **Anti-cheat tests (`tests/loop/test_gate.py`, all must pass):** modified `.green` → refuse ("test modified"); modified thresholds (config sha) → refuse; stale verdict after a code edit → refuse; fabricated `.Kodiac/last_verdict.json` PASS → ignored (gate re-runs and refuses on a buggy script); a PASS on a different clip/script → refused; pin file edited **inside** the workspace has no effect; missing/corrupt pin or env file → exit 2; max-blocks → exhausted message + exit 0 + marker; no `--init` → exit 0; `stop_hook_active=true` does not auto-pass; sim crash → exit 2; a script that stubs `Robot`/monkeypatches the oracle or verdict path → refuse (the gate grades the clip, not script claims; test with a script that tries to write a PASS file or set env vars). Use B01 patched script (must be refused with blame) and the correct `pick_place.py` (must pass) as the two ground truths.
5. `artifacts/p07/gate_refusals.json`: the recorded refusals from a scripted run (test-generated) for each attack with exit code, stderr first line, `backend: "kinematic_mock"`, `is_mock: true`. This is the "recorded gate refusal" the P07 exit gate needs.

## Definition of Done
- [ ] All anti-cheat tests above pass; `gate_check` provably never returns 3 (test it with injected exceptions at every stage).
- [ ] `run_script` works on the correct script and each of B01–B10 patched copies on the mock backend (assert gate PASS for correct, refusal for B01 at least; report all 10 outcomes in the report honestly).
- [ ] `artifacts/p07/gate_refusals.json` committed with the generating command in the report.
- [ ] No `TODO|NotImplemented`; ruff clean; full suite green. Committed `feat(p07/t04): …`.

## Report (filled by owner at DONE)
