# BRIEF: P06–P10 Compressed Sprint

updated: 2026-11-02 by ORCH · governed by ADR-0014

## Why
P01–P05 are built. P06–P10 (blame/diff, done-gate, proof, hosted app, video/ship) are 0% built.
Feature freeze Nov 4 04:59 UTC. The `Never cut` list (IDEA §11): test, run, **blame + diff**, the **/goal done-gate**,
the headline experiment (≥4 arms), audit opener, hosted page, video.

## Hard constraints (every agent)
- **Law 1: never fake anything.** No API keys exist (Meta, Modal, HF). Everything runs on fixtures / the kinematic mock sim.
  Every fixture-derived or mock-sim-derived output must be labelled in code, JSON (`is_fixture` / `is_mock` / `evidence_type`), and docs.
  Never write a metric into a registry/README/VIDEO_NUMBERS as if it were measured on real SAM/real physics.
- Concept Invariants (IDEA §0) are untouchable. Verdicts: PASS / FAIL / CAN'T TELL. Blame = exact t* + measured numbers with ± σ.
- Frozen contracts: `src/Kodiac_robotics/contracts/**` is owned by ORCH. Do not edit it. If a contract is insufficient post an
  `INTERFACE-REQUEST` in your phase CHANNEL.md and work around it meanwhile.
- Write ONLY inside your card's `owns_paths`. `cli.py` is ORCH-owned this sprint unless your card says otherwise
  (ORCH wires CLI commands after you deliver clean, importable functions).
- No stubs, `TODO`, `NotImplemented` in owned paths. No secrets in files. No new paid tools. No new dependencies unless in `pyproject.toml` extras.
- Seed everything; cache by content hash where relevant.

## Environment (Windows, PowerShell, the sandbox is quirky)
Run Python tools through the venv. **Always** do this first in every shell command that runs pytest:
```powershell
$env:TEMP='C:\Users\LOUJAN B\Kodiac\.cache\tmpx'; $env:TMP=$env:TEMP; $env:PYTHONIOENCODING='utf-8'
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
& ".\.venv\Scripts\python.exe" -m pytest <your test paths> -q -p no:cacheprovider --basetemp=".cache\pt_<yourtask>"
& ".\.venv\Scripts\python.exe" -m ruff check <your owned paths>
```
- Do NOT pass `--timeout` (pytest-timeout is not installed in the venv). Python is 3.11.9.
- Without the TEMP override pytest crashes with "No usable temporary directory".
- Full-suite baseline at sprint start: **303 passed**, `ruff check .` clean. You must not break any other test.
  Run the full suite once before reporting DONE: `& ".\.venv\Scripts\python.exe" -m pytest tests -q -p no:cacheprovider --basetemp=".cache\pt_full_<yourtask>"` (≈70 s).

## Git
Shared working tree, concurrent agents. Stage ONLY your owned paths: `git add <paths>` then `git commit -m "<type>(p<NN>/t<NN>): ..." -- <paths>`.
If you hit `index.lock`, wait 3 s and retry (max 10 tries). Never `git add -A`, never reset/checkout/stash other people's files, never force-push, never push (ORCH pushes).
Commit after every green increment.

## Existing building blocks you will use (read the code, do not re-implement)
- `contracts.core`: `GreenTest, Step, Expr, Atom, Event, FactTable, Blame, Hint, CodeLocation, RunResult, StepResult, Component, PredFrame, Track, ObjMask, Clip, ClipRef, GreenLock, VerifyRequest, GateState, VerdictRow, JudgeLabel, Tri, Verdict, ReasonCode`.
- `pipeline.run.run(test, clip, tracks=..., cam_K=..., cam_extrinsic=..., camera=...) -> RunResult` (full path) and `pipeline.loader`.
- `engine.{steps,logic,smoothing,trace}`, `predicates.*`, `geometry.*`, `uncertainty.*`, `segment.*` (api/modal/fixture, rle, tracks, reid), `render.{card,overlay}`.
- `sim.{env (KinematicMockEnv, ManiSkillEnv), robot, spans (SimSpan, span, find_blame_span), bugs, video}`, `examples/sim/pick_place.py`, `examples/sim/bugs/B01..B10.patch`.
- `compiler.*` (lock.py has GreenLock IO). `examples/stackcube.green`, `examples/stack_blocks.green`. Golden clips in `tests/fixtures/clips/` with recorded tracks in `tests/fixtures/tracks/`.
- Read ARCHITECTURE.md sections named in your card, IMPLEMENTATION_PLAN.md step IDs named in your card, and `.agents/DECISIONS.md` (ADR-0004..0013) so you do not re-litigate settled decisions.

## Frozen helper contract owned by ORCH (T04 implements, T05 consumes)
`src/Kodiac_robotics/sim/runner.py`:
```python
class SimRunResult(BaseModel):
    video_path: str; state_path: str; spans_path: str
    oracle_success: bool; backend: Literal["maniskill","kinematic_mock"]; is_mock: bool
    script_sha256: str; seed: int; n_frames: int; fps: float
def run_script(script: Path, seed: int, out_dir: Path, backend: Literal["auto","kinematic_mock","maniskill"] = "auto") -> SimRunResult: ...
```
`auto` = ManiSkill if importable else kinematic mock (labelled `is_mock=True`). The script exposes `run(robot)` like `examples/sim/pick_place.py`.

## Reply format (final reply to ORCH, ≤150 words)
DONE | BLOCKED · commit shas · test counts (yours + full suite) · deviations · known limits · the 3 ways your output could embarrass us in front of a skeptical Meta judge and what you did about each.
Fill the `## Report` block of your task card before replying.
