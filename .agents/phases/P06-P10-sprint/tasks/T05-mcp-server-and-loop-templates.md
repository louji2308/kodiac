# T05: MCP server `Kodiac.verify`, loop config templates, `/goal` recipe, fix-rate eval harness
phase: P07 · owner: IMPL-5 (Sonnet 5.5 @ high) · status: TODO
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
