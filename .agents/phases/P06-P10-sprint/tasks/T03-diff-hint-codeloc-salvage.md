# T03: Event diff, corrective hint, code location, prefix salvage
phase: P06 · owner: IMPL-3 (Sonnet 5.5 @ high) · status: DONE
plan_ref: IMPLEMENTATION_PLAN.md P06.S06–S08 · ARCHITECTURE.md §9, §5.4, §10 · IDEA F34, F35b, F36, F37
depends_on: [] (consumes the frozen FactTable/Event/Hint/CodeLocation contracts; T01 produces FactTables in parallel) · blocks: [ORCH CLI diff wiring]
owns_paths: [src/Kodiac_robotics/blame/diff.py, src/Kodiac_robotics/blame/hint.py, src/Kodiac_robotics/blame/codeloc.py, src/Kodiac_robotics/blame/salvage.py, tests/blame/test_diff.py, tests/blame/test_hint.py, tests/blame/test_codeloc.py, tests/blame/test_salvage.py, tests/blame/golden/**, artifacts/p06/codeloc_B01_B10.json]
reads_only: [contracts/**, sim/**, examples/sim/**, compiler/lock.py, tests/fixtures/**]
note: do NOT touch blame/__init__.py, blame/{transitions,tstar,facts,summary,validate}.py or tests/blame/__init__.py (T01 owns them; T01 creates tests/blame/__init__.py; if it is missing when you start, create nothing: pytest rootdir conftest handles it, or wait 5 min and re-check).
timebox: 120 min (3-strike rule applies)

## Mission
`diff` shows the robot's attempt next to the demo as events with measurements; `hint` states the single variable change that fixes it;
`codeloc` maps a blamed frame to `pick_place.py:LINE -> code` (the sim `/goal` loop's key input); `salvage` cuts the good prefix of a failed trajectory for retraining.

## Interface contract (FROZEN)
```python
# diff.py
def myers_lcs(a: Sequence[T], b: Sequence[T]) -> list[tuple[int|None,int|None]]   # aligned index pairs (None = gap)
def diff_events(demo: list[Event], attempt: list[Event], *, camera_tier: Literal["A","B","C"]="C", sigma_k: float = 2.0) -> str   # unified-diff text with measurements
# hint.py
def make_hint(ft: FactTable, demo_events: list[Event] | None = None) -> Hint | None   # single-variable change that flips the blamed margin to ≥ +σ
# codeloc.py
def locate_code(spans: list[SimSpan], ft_frame: int, component: str, *, slack_frames: int = 3) -> CodeLocation | None
# salvage.py
def salvage_cut(t_star_s: float, fps: float, *, margin_s: float = 0.5, min_keep_s: float = 1.0) -> int | None   # last kept frame or None if prefix < min_keep_s
def export_prefix(episode_state_npz: Path, cut_frame: int, out_dir: Path, fmt: Literal["maniskill_h5","lerobot"]="lerobot", chunk_h: int | None = None) -> dict   # manifest incl. chunk-safe start mask
```
`Event` / `SimSpan` shapes: read `contracts/core.py` and `sim/spans.py` (`find_blame_span` exists; reuse/wrap it, do not duplicate logic: but the actuation-class → component table in ARCHITECTURE §9 / `docs/research/01_project_analysis.md §3.11` if present is binding).

## Steps
1. Diff: events from the demo (`.green.lock`'s `demo_events`) vs attempt; Myers LCS on `(step, kind, predicate)`; matched and within `sigma_k`·σ → context line (two spaces), else `-` (demo-only/diverging) and `+` (attempt). Render measurements as `value ± σ unit`. Direction words: `camera-left/right/up/down` unless tier A (then world axes). Golden snapshots in `tests/blame/golden/` (created from real outputs on constructed event lists; review them for honesty).
2. Hint: for `moves_with` T→F release-before-approach → hint variable = order/`dt` (move release after `move_to(place)`); xy-offset breach → `delta` in cm toward the target with `unit="cm"`; z gap → lift/place z delta. `basis` must cite the measured number from the FactTable. Never invent a number: delta = (needed − measured) from facts only. Return None when facts are insufficient.
3. Codeloc: blamed span = latest span with `step_start ≤ frame + slack` whose actuation class matches the broken component; returns file/line/code/span_id. **Validate on B01–B10**: for each, apply the patch to a copy of `examples/sim/pick_place.py` (see `sim/bugs.py` registry; it records expected blame class + span), run it on `KinematicMockEnv` through the spans machinery (look at `tests/sim/test_bugs.py` for how), and assert the located line is the buggy line. Write `artifacts/p06/codeloc_B01_B10.json` with expected vs located per bug, `"backend": "kinematic_mock"`, `"is_mock": true`. If fewer than 10/10, report honestly with root causes.
4. Salvage: `cut = t* − 0.5 s` kept only if ≥ 1.0 s; chunk-safe mask `s + H_a ≤ cut`; export prefix of a pool `.state.npz` episode to a LeRobot-style dir (parquet + meta json) and a ManiSkill-style `.h5` manifest (h5py only if installed; otherwise write the npz-based manifest and say so in the return dict). Roundtrip test.

## Definition of Done
- [ ] Tests pass: LCS properties (empty, identical, disjoint, reorder), diff snapshots, hint per blame class, codeloc B01–B10, salvage boundaries (prefix < 1 s → None; exact cut frame).
- [ ] `artifacts/p06/codeloc_B01_B10.json` produced by a committed test or script (command in the report).
- [ ] No `TODO|NotImplemented`; ruff clean on owned paths; full suite green.
- [ ] Committed `feat(p06/t03): …`.

## Report (filled by owner at DONE)

**Status: DONE** (IMPL-3, 2026-11-02). Commits: 33e5b76 (codeloc), 285a003 (salvage), be7d609 (hint), 7bccd9e (diff + goldens), 485af17 (align with blame/facts.py), df0c66e (newlines).

**Micro-plan:** (1) codeloc table + validation on mock B01-B10; (2) salvage cut/mask/export; (3) hint from FactTable only; (4) Myers diff + goldens; (5) align with T01's fact schema; (6) full suite.

**Built**
- `blame/codeloc.py`: `locate_code` (latest span with `step_start <= frame+slack` in the component's admissible actuation classes; falls back to wrapped `sim.spans.find_blame_span`), `component_for_facts`, `locate_from_fact_table`.
- `blame/salvage.py`: `salvage_cut`, `chunk_safe_start_mask` (`s + H_a <= cut`), `export_prefix` (LeRobot-v2.0-style parquet+meta; ManiSkill h5 when h5py exists, else labelled `npz_fallback`; h5py is NOT installed here, so the h5 path is untested).
- `blame/hint.py`: order / xy / z-gap / lift / dwell hints; None when threshold, margin and demo reference are all absent or the margin is already >= +sigma.
- `blame/diff.py`: `myers_lcs` (checked against a DP LCS on 300 random pairs) and `diff_events` (context/-/+ lines, `value ± sigma unit`, camera-relative direction words unless Tier A).

**Evidence:** tests (mine) 61 passed: `pytest tests/blame/test_{diff,hint,codeloc,salvage}.py`; ruff clean on owned paths; no TODO/NotImplemented. Artifact `artifacts/p06/codeloc_B01_B10.json` (force-added; `artifacts/` is gitignored) is rewritten by `tests/blame/test_codeloc.py`; labelled `backend=kinematic_mock, is_mock=true, evidence_type=mock_sim_privileged_state`.

**B01-B10 code-location accuracy: 10/10 located line == expected buggy line, on the kinematic MOCK sim, seed 0.** Caveats (honest):
- Onset frame/component come from a test-side step machine over privileged mock state, NOT the Kodiac blame engine and not real SAM tracks. The first run of that oracle gave 9/10 (B06): its soft-score clip at +-5 saturated and picked frame 0. I widened the clip to +-100 (a bug in the validation oracle, not in codeloc) and got 10/10. The change was made after seeing the failure, so this is not blind validation.
- Expected lines are anchored by source text in `examples/sim/pick_place.py`. The `.patch` files do not apply to the current script (line numbers and content differ), so the `bug_id` branches are the ground truth. B02/B10/B06/B08 point to the actuation call that consumes the bad variable. B09 is an omission bug, so the expected line is the retract (manifestation).
- Disagrees with the bug registry's `expected_blame_span` on B07 (registry arm.move_to, located arm.lift) and B10 (registry gripper.open, located move_to(place), per ARCHITECTURE section 9's z-gap rule). Flagged per bug in the JSON (`match_registry_span_class`).
- `stable_frame_window` per bug is in the JSON; B01 is tightest (frames 112-126), B07 widest.
- The `01_project_analysis.md` section 3.11 table cited by the card does not exist in the repo; the component->class table is derived from ARCHITECTURE section 9 and `find_blame_span`.

**Deviations / known limits:** codeloc/hint read the T01 fact schema as of 2026-11-02 (`gap_z_cm`, `op`, `objects`, `blame_class`); not run end-to-end on T01's `blame_from_run` (T01 reports fixture clips at Tier C all FAIL at step 0). Diff goldens use hand-constructed (synthetic) event lists. `.agents/.../CHANNEL.md` note posted for ORCH wiring (`diff_events(lock.demo_events, result.events, camera_tier=lock.geometry_tier)`).