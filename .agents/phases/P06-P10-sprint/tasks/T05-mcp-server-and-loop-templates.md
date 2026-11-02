# T05: MCP server `Kodiac.verify`, loop config templates, `/goal` recipe, fix-rate eval harness
phase: P07 · owner: IMPL-5 (Sonnet 5.5 @ high) · status: DONE
plan_ref: IMPLEMENTATION_PLAN.md P07.S01, S03, S06 · ARCHITECTURE.md §5.5 · IDEA F38, F40, F42
depends_on: [T04 interface only (frozen `sim.runner.run_script` contract in BRIEF.md; in your tests monkeypatch it until T04 lands, then add one real integration test)] · blocks: [ORCH CLI `mcp`/`loop init` wiring]
owns_paths: [src/Kodiac_robotics/loop/mcp_server.py, src/Kodiac_robotics/loop/installer.py, src/Kodiac_robotics/loop/templates/**, src/Kodiac_robotics/proof/loop_eval.py, tests/loop/test_mcp.py, tests/loop/test_installer.py, tests/loop/test_loop_eval.py, artifacts/p07/loop_eval_dryrun.json]
reads_only: [contracts/**, pipeline/run.py, sim/runner.py (from T04), loop/gate.py (from T04), blame/** (when present), examples/**, docs/schemas/VerifyRequest.json]
do_not_touch: [loop/gate.py, loop/pins.py, sim/runner.py, tests/loop/__init__.py, tests/loop/test_gate.py, tests/loop/test_runner.py]
timebox: 120 min

## Mission
Muse Code needs a tool to call (`Kodiac.verify`) and a one-command setup (`Kodiac loop init`), plus a recipe whose text says "Done ONLY when Kodiac run prints PASS".
The fix-rate batch (F42) measures how many of B1–B10 an agent can fix in ≤5 iterations. **We have no Muse Code access or API key**: build the harness so it works the moment keys exist, and run it only in a clearly-labelled *dry-run with a scripted reference patcher* that proves the plumbing, never reported as an agent fix rate.

## Interface contract (FROZEN)
```python
# loop/mcp_server.py   (mcp SDK is installed: `mcp` 1.x; check the installed API: `from mcp.server.fastmcp import FastMCP`)
def verify(req: VerifyRequest) -> dict                      # RunResult JSON + "hint" + "evidence" paths; writes .Kodiac/last_verdict.json (with nonce)
def build_server() -> "FastMCP"                              # registers tool name "verify" on server "Kodiac"
def main() -> None                                           # stdio entry (ORCH wires `Kodiac mcp` to this)
# loop/installer.py
def install_loop(project_dir: Path, *, test: str, sim_script: str, seed: int = 0, max_blocks: int = 8, dry_run: bool = False) -> dict[str,str]  # path -> action
# proof/loop_eval.py
class BugOutcome(BaseModel): bug: str; fixed: bool; iterations: int; gate_pass: bool; oracle_success: bool; hash_unchanged: bool; transcript_path: str; driver: str
def run_loop_eval(bugs: list[str], driver: Callable[[Path, str], ...], *, max_iters: int = 5, out_dir: Path) -> list[BugOutcome]
```
## Steps
1. `verify`: runs `sim.runner.run_script` (T04's contract; import lazily inside the function so your module imports even before T04 lands) then `pipeline.run.run(mode full)` on the produced clip; includes blame/diff/hint if `Kodiac_robotics.blame` provides `blame_from_run` (try-import; absent → omit and say `"blame": null`); writes `.Kodiac/last_verdict.json`. Honest labels pass through (`is_fixture`, badges incl. `[MOCK SIMULATION]`). Input validation errors → structured error, never a stack trace into the model.
2. Templates in `loop/templates/`: `mcp.json` (with `env` passthrough, command `Kodiac mcp`), `hooks.json` (Stop → `Kodiac gate --max-blocks N`; timeouts per ARCH: gate < 60 s, hook timeout 600 s), `goal_recipe.md` / `GOAL.md` (same text for every bug), optional `.claude-plugin/plugin.json`. `install_loop` writes `.mcp.json`, `.muse/hooks.json`, `GOAL.md` into the project, idempotent, never overwrites differing user files without `.bak`, **installs gate templates into `examples/sim/` only**, never writes secrets, `dry_run` lists actions only.
3. `loop_eval.py`: for each bug: fresh workspace copy → apply `examples/sim/bugs/B##.patch` → `gate_init` (T04) → hand the workspace to `driver` for ≤ `max_iters` iterations → check gate PASS ∧ oracle success ∧ test/config hash unchanged → write transcript `artifacts/p07/transcripts/B##.md` + aggregate JSON. Spend guard: refuse to launch the real Muse driver unless env `KODIAC_ALLOW_MUSE_SPEND=1` and print the estimated iterations; there is no real driver to ship (document the `muse exec` command template in the module docstring as unverified).
4. `artifacts/p07/loop_eval_dryrun.json`: run the harness with the built-in **`reference_patcher` driver** (reverse-applies the bug patch: it is NOT an AI agent). Mark the JSON `"driver": "reference_patcher", "evidence_type": "plumbing_dry_run", "agent_fix_rate": null, "note": "NOT a Muse Code fix rate"`. Never write an N/10 fix rate.

## Definition of Done
- [ ] Tests: MCP tool registered with name `verify` and input schema equal to VerifyRequest; verify returns PASS for the correct script / FAIL with hint for B01 (real integration once T04's runner exists; until then monkeypatched, and add `pytest.importorskip`-style guard only for the integration test); installer idempotency + backup + dry-run; `loop_eval` plumbing incl. spend-guard refusal and hash-changed → not fixed.
- [ ] `loop_eval_dryrun.json` generated by a committed command (in the report), clearly labelled.
- [ ] No `TODO|NotImplemented`; ruff clean; full suite green. Committed `feat(p07/t05): …`.

## Report (filled by owner at DONE)

**Micro-plan:** (1) verify = run_script -> state->tracks (gate helper) -> pipeline.run(tier_a) -> try blame -> labels -> last_verdict.json; (2) FastMCP server, flat tool args so the input schema equals VerifyRequest; (3) installer with merge + .bak + dry-run + secret guard; (4) loop_eval with fresh workspaces, pins, hash check, spend guard; (5) reference_patcher dry-run artifact.

**Built (commits fb1802a, 59661ec, 1d81f4a, 5bf899b, fb4e373 on main):**
- `loop/mcp_server.py`: `verify`, `build_server` (server "Kodiac", tool `verify`), `main`. Structured errors only (no stack traces); stdout redirected to stderr during a call; empty `.green` rejected (would pass vacuously); `fresh=false` reuses a labelled cache; blame via `blame_from_run(spans, code_locator, hint_fn)` when present (`blame_status` says why otherwise); sim oracle never in the response; pipeline's "[REPLAY: CACHED SAM 3.1 TRACKS]" badge replaced by `[SIM STATE TRACKS ...]` (+ `[MOCK SIMULATION]`), `evidence_type: sim_state_tracks`.
- `loop/installer.py` + `loop/templates/{mcp.json,hooks.json,GOAL.md,gate.template.json}`: writes `.mcp.json`, `.muse/hooks.json`, `GOAL.md`, `examples/sim/gate.template.json` only; merge, `.bak`/`.bak.N`, idempotent, dry-run, refuses to write secret values. Hook JSON shape is Claude-Code-style and [UNVERIFIED] against Muse Code.
- `proof/loop_eval.py`: `run_loop_eval`, `inject_bug`, `reference_patcher`, `muse_exec_driver` (spend guard `KODIAC_ALLOW_MUSE_SPEND=1`; needs an operator-supplied, verified command template in `KODIAC_MUSE_EXEC_TEMPLATE`; none ships), `build_report`, CLI `python -m Kodiac_robotics.proof.loop_eval`.
- Dry run (generated by): `python -m Kodiac_robotics.proof.loop_eval --driver reference_patcher --out-dir .cache/loop_eval_dryrun --report artifacts/p07/loop_eval_dryrun.json` -> `artifacts/p07/loop_eval_dryrun.json` + `artifacts/p07/transcripts/B01..B10.md`. Labelled `plumbing_dry_run`, `agent_fix_rate: null`, "NOT a Muse Code fix rate", kinematic mock backend. A scripted function restored the pristine script; no AI agent ran; no fix rate exists.

**Tests:** tests/loop/test_mcp.py 25, test_installer.py 14, test_loop_eval.py 29 (incl. 2 real integration tests: correct script -> PASS, B01 -> FAIL with blame+hint on the mock sim). Full suite: 931 passed, 13 skipped, 1 xfailed; ruff clean on owned paths.

**Deviations / findings:** (a) `examples/sim/bugs/B01..B10.patch` do not apply to the current pick_place.py (stale; B03/B04 malformed), so `inject_bug` falls back to pinning `bug_id` in `execute_pick_place` and records `injection: "bug_id_pin"` (all 10 rows in the dry run); the patches should be regenerated by their owner. (b) `BugOutcome` gained optional fields `injection, bug_manifests, sim_backend, is_mock, note`. (c) The earlier `No module named 'pydantic'` failures came from T04's first runner draft: `python -I` drops the user site-packages where pydantic lives on this machine; T04 fixed it (parent sys.path passed to the child); nothing needed in T05 files. (d) The state.npz layout differs from the pool layout (`ee_pos/cubeA_pose/cubeB_pose` vs `obs_state`); verify now uses the gate's `tracks_from_state` (identical perception to the gate) and a local fallback. (e) `artifacts/` is gitignored: files were added with `git add -f`.

**Known limits:** no Muse Code or API key was available, so nothing here is a Muse Code measurement; perception for sim is projected from privileged state (not SAM); the real Muse driver needs an operator-verified launch command; `.muse/hooks.json` format unverified; package-data for `loop/templates/*` is not declared in pyproject (ORCH: add if the wheel is built non-editable).

**3 ways this could embarrass us:** (1) someone reads the dry-run `fixed: true` rows as an agent fix rate -> JSON/transcripts/docstring say scripted patcher, `agent_fix_rate: null`, and no N/10 appears anywhere; (2) a judge asks about "perception" -> every verify/gate output carries `[SIM STATE TRACKS ...]` + `[MOCK SIMULATION]` and `evidence_type`; (3) stale bug patches -> disclosed above, fallback is explicit per row.
