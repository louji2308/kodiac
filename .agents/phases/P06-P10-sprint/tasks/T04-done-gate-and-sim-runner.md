# T04: Done-gate (anti-cheat) + `sim.runner.run_script`
phase: P07 · owner: IMPL-4 (Opus 5.5 @ xhigh) · status: DONE
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

### Micro-plan (IMPL-4, 2026-11-02)
1. `sim/runner.py`: execute the script in an **isolated child interpreter** (`python -I`, whitelisted env, no secrets) that only records the
   commanded Robot-API actions + spans; the parent then **replays those actions in a fresh env it owns** (deterministic) and writes video,
   `state.npz` (frame-aligned, incl. ee_pos), `spans.jsonl`, `meta.json`. Monkeypatching the env/oracle/pipeline inside the script cannot reach
   the grader. Action sanity bounds (finite, ≤3600 steps, ≤5 cm/step, |grip|≤1). `auto` → ManiSkill iff importable.
2. `loop/pins.py`: pins outside the workspace (`KODIAC_GATE_HOME` override), self-digest, workspace marker so a deleted pin fails closed.
3. `loop/gate.py`: `gate_init` / `gate_check` per KD-11: pins → exhausted → env file → test sha → config sha → engine-source digest → fresh
   run_script → synthetic tracks from the gate's own replayed state (labelled) → `pipeline.run.run` → provenance checks → PASS/BLOCK.
   Outer wrapper maps every exception to exit 2. Blame via `blame.validate.blame_from_run` if importable, else decisive components + span.
4. Tests: runner (correct PASS-oracle, B01–B10, isolation, crash, bounds) and gate anti-cheat list; generate `artifacts/p07/gate_refusals.json`.

### What was built (commits 4e5a5f0, d4258d1, 0f9e116)
- `sim/runner.py`: `run_script` (frozen contract) + `run_script_with_digests` (artifact sha256s), `load_spans`, `validate_actions`,
  `SimRunError`. Script runs in `python -I -B` child (parent sys.path passed explicitly; env whitelist, no API keys; cwd in run dir);
  parent replays the commanded actions in its own env → `video.mp4` (ffmpeg H.264, cv2 fallback), frame-aligned `state.npz` (incl.
  `ee_pos`, camera), `spans.jsonl`, `meta.json` (`is_mock`, label, evidence_type, oracle note, child/replay divergence, digests).
  Rejects: crash, no entry point, early exit, timeout (300 s), self-modifying script, NaN, >3600 steps, >5 cm/step (teleport), |grip|>1.
  Entry point `run(robot)`, fallback `execute_pick_place(robot)` (the reference script has no `run`).
- `loop/pins.py`: pins at `<KODIAC_GATE_HOME or ~/.config/Kodiac/gates>/<sha256(ws)>.json` with self-digest, test sha, config sha
  (`<test>.lock` + `Kodiac.toml`, pinned even if absent), engine-source digest (verdict-path files), script path, seed, env-file path,
  authoritative `blocks`, `previous_pins` history; workspace marker so a deleted pin fails closed; `.Kodiac/gate_state.json` mirror only.
- `loop/gate.py`: `gate_init`, `gate_check` (outer wrapper: any exception incl. SystemExit/KeyboardInterrupt → exit 2; codes ∉{0,2} → 2;
  secrets redacted), `tracks_from_state` / `synthetic_tracks_from_state` (Tier A-exact masks, worst error < 4 mm, tested), `grade_sim_run`
  (pipeline.run full/Tier A; badges rewritten to `[SYNTHETIC TRACKS FROM SIM STATE · NOT PERCEPTION]` + `[MOCK SIMULATION]`; config sha set),
  `provenance_problems`, blame via T01 `blame_from_run(spans=, hint_fn=)` + T03 codeloc (try-import; fallback decisive components +
  `find_blame_span`), `main(argv)` CLI adapter for ORCH (`--init --test --sim --seed --max-blocks`; check-time `--max-blocks` ignored).

### Evidence
- `tests/loop/test_runner.py`: 21 passed (11 default + 10 `slow` B01–B10). `tests/loop/test_gate.py`: 55 passed, 11 skipped (artifact-only
  matrix). With `KODIAC_WRITE_GATE_ARTIFACT=1`: 66 passed. `ruff check` clean on owned paths; no TODO/NotImplemented.
- Artifact command: `$env:KODIAC_WRITE_GATE_ARTIFACT='1'; .venv\Scripts\python.exe -m pytest tests/loop/test_gate.py -q -p no:cacheprovider --basetemp=.cache\pt_t04_artifact`
  → `artifacts/p07/gate_refusals.json` (18 attack records, all `backend: kinematic_mock`, `is_mock: true`, paths scrubbed) + B01–B10 matrix.
- Full suite (once): 939 passed, 4 failed, 13 skipped. The 4 failures are in tests/proof/test_judges.py and tests/segment/test_quality.py,
  which another agent was changing while the suite ran (597fbe7, committed mid-run); re-running those two files alone: 21 passed. Not T04 paths.
- Gate latency on mock: ~8–11 s per check (child ~4 s, replay+video ~3 s, tracks ~1 s, pipeline ~1–3 s), well under the 60 s target.

### B01–B10 outcomes (seed 0, mock; run_script works on all 10; oracle FAIL on all 10)
| script | gate | verdict | oracle (cross-check only) | code location shown to the agent (from T01/T03 blame) |
|---|---|---|---|---|
| correct | 0 PASS | PASS | True | — |
| B01 | 2 | FAIL | False | :83 `robot.gripper.open(steps=15)` ✔ |
| B02 | 2 | FAIL | False | :104 `move_to(place_pose)` ✔ |
| B03 | 2 | FAIL | False | :66 `lift(distance=0.005)` ✔ |
| B04 | **0 PASS** | PASS | False | **engine false PASS** |
| B05 | 2 | FAIL | False | :39 `move_to(pre_grasp)` ✘ (bug at :58) |
| B06 | 2 | FAIL | False | :39 ✘ (bug at :51) |
| B07 | 2 | FAIL | False | :39 ✘ (bug at :62) |
| B08 | 2 | FAIL | False | :39 `move_to(pre_grasp)` ✔ |
| B09 | **0 PASS** | PASS | False | **engine false PASS** |
| B10 | 2 | FAIL | False | :91 `move_to(pre_place)` ✘ (bug at :101/104) |

### Deviations
- Card says `run(robot)`; the reference script only has `execute_pick_place` → accepted as fallback entry point.
- `examples/sim/bugs/*.patch` no longer apply (`git apply --check` fails) → bug copies flip the default `bug_id` (same as T05).
- No verdict card rendered by the gate (`render/card.py:242` hard-codes `[sam-3.1]`); `[MOCK SIMULATION]` is carried by the message,
  the result badges, `meta.json`, and the burned-in frame banner. INTERFACE-REQUESTs posted (card badge, pipeline perception label).
- Added an engine-source digest pin and an action sanity bound (anti-cheat), beyond the card's list.

### The 3 ways this could embarrass us (and what was done)
1. **The gate PASSes B04 and B09 on the mock** (engine/test-spec false PASS: step 3 is satisfied while gripper and cube are both still,
   and `dwell` ignores its 2nd arg). The gate never consults the oracle (KD-13), so it cannot catch this. It is disclosed in the artifact
   `bug_matrix` (`DISAGREE (engine false PASS)`) and was sent to ORCH/T01 as an S1. Do not demo B04/B09 until the spec or engine is fixed.
2. **Same-user attacks outside the workspace can defeat any in-process gate.** An agent that can write to `~/.config` (recompute the
   pin digest, or delete both pin and marker; the second case is tested and gives exit 0), edit site-packages beyond the pinned
   verdict-path files, or run `gate --init` itself gets past the checks. Docstrings say so; re-inits are recorded and shown in every
   message. Running the agent sandboxed to its workspace is the real fix.
3. **A gate PASS here does not show perception or physics.** The verdict is graded on tracks projected from privileged
   kinematic-mock state, not SAM masks or SAPIEN physics. Every output says so (`[MOCK SIMULATION]`, `[SYNTHETIC TRACKS…]`,
   `evidence_type`). Also, the T01/T03 code locations are wrong for B05, B06, B07 and B10 (table above), and the agent sees them.
   Reported to IMPL-1/IMPL-3.
- Known limits: ManiSkill branch untested (not installed); gate run dirs accumulate under `.Kodiac/gate_runs/` (bounded by max_blocks per init);
  engine digest changes after a git checkout that rewrites line endings (requires re-init); time spent ≈ 150 min.
