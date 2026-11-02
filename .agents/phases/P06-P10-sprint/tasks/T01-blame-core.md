# T01: Blame core: transition finder, t* refinement, fact table, validated summary
phase: P06 · owner: IMPL-1 (Opus 5.5 @ xhigh) · status: DONE
plan_ref: IMPLEMENTATION_PLAN.md P06.S03–S05 · ARCHITECTURE.md §5.4, §9, §4 (FactTable/Blame)
depends_on: [] · blocks: [ORCH CLI blame wiring, T03 (consumes FactTable)]
owns_paths: [src/Kodiac_robotics/blame/transitions.py, src/Kodiac_robotics/blame/tstar.py, src/Kodiac_robotics/blame/facts.py, src/Kodiac_robotics/blame/summary.py, src/Kodiac_robotics/blame/validate.py, src/Kodiac_robotics/blame/__init__.py, tests/blame/test_transitions.py, tests/blame/test_tstar.py, tests/blame/test_facts.py, tests/blame/test_summary.py, tests/blame/test_validate.py, tests/blame/__init__.py, artifacts/p06/blame_core_report.json]
reads_only: [contracts/**, engine/**, pipeline/**, predicates/**, sim/spans.py, tests/fixtures/**, examples/**]
timebox: 150 min (3-strike rule applies)

## Mission
`blame` is the hero (Invariant: exact onset frame t* + a *measured* physical cause with ± σ). Build the part that turns a FAIL `RunResult`
(+ per-frame `PredFrame`/trace data from the engine) into a `FactTable` and a one-sentence `Blame.summary` that provably contains no fabricated number.

## Interface contract (FROZEN; implement exactly)
```python
# blame/transitions.py
class Transition(BaseModel): cls: Literal["broken_prerequisite","unmet","order_violation"]; step_index: int; step_name: str; literal: str
    t_frame: int; component: str | None; warnings: list[str]
def find_transition(result: RunResult, frames: dict[str, list[PredFrame]] | list[PredFrame], test: GreenTest, fps: float) -> Transition | None
# blame/tstar.py
class TStar(BaseModel): frame: int; t_s: float; sigma_frames: float; method: Literal["detach_onset","piecewise_breakpoint","softscore_argmax"]
def refine_tstar(transition: Transition, pred_frames: list[PredFrame], fps: float, window: tuple[int,int], n_boot: int = 200, seed: int = 0) -> TStar
# blame/facts.py
def build_fact_table(result: RunResult, transition: Transition, tstar: TStar, pred_frames: list[PredFrame], *, code_location: CodeLocation | None = None, dataset_index: int | None = None, action_chunk: int | None = None, fps: float) -> FactTable
# blame/summary.py
def render_template_summary(ft: FactTable) -> str          # ARCHITECTURE §9 template, contains ≥1 `value ± σ` copied from facts
def summarize(ft: FactTable, test: GreenTest, *, llm: Callable[[str], str] | None = None) -> tuple[str, Literal["muse-spark","template"]]
# blame/validate.py
def validate_summary(text: str, ft: FactTable, test: GreenTest) -> list[str]   # [] = valid, else list of violations
def blame_from_run(result: RunResult, test: GreenTest, pred_frames, fps, **kw) -> Blame | None   # orchestrates the above; None if verdict != FAIL
```
`llm` is an injected callable (Muse Spark client is not available offline). With `llm=None` → template, `summary_source="template"`. If an llm
returns text, run `validate_summary`; on violation retry once (call llm again with the violations appended), then fall back to the template.
Never label a template sentence `"muse-spark"`.

## Steps
1. Read ARCHITECTURE §5.4/§9, `engine/steps.py` (how carried literals, step verdicts, achievement times are represented), `pipeline/run.py` and the trace format; find where per-frame PredFrames are available/stored. If the pipeline does not expose them, **add nothing outside owns_paths**: take them as arguments (the contract above) and post a CHANNEL.md note describing exactly what `pipeline/run.py` must expose; ORCH wires it.
2. `transitions.py`: the three classes in §5.4 (broken prerequisite via carried-literal final-False-run onset, argmin t*_L; unmet condition via argmax soft-score of C_{k+1} and the most negative m/σ component; order violation). Transient breaks → `warnings`, not blame. Handle step 1 failing, last step failing, all-U (CAN'T TELL → return None), PASS (None).
3. `tstar.py`: detach-onset rule for `moves_with` T→F; two-segment piecewise-linear breakpoint (least squares) for threshold components; bootstrap σ_t* (seeded). Result must be frame-exact on synthetic ramps; `sigma_frames` honest (not 0 unless noise-free by construction, then ≥ 0.5 frame floor).
4. `facts.py`: facts incl. `xy_offset_cm`, `dt_before_reference_s` (`t_ref − t*`, t_ref = effector's closest xy approach to the target after t*; omit if none), `lift_cm`, `slip_cm`, `aperture_open_event`, `occlusion` as `{value, sigma, unit}` dicts. Every number traces to a Component/PredFrame (`trace_ids`).
5. `summary.py`/`validate.py`: validator = numbers+units regex vs fact values (1-decimal rounding), object names ∈ test objects, licensed verbs ("opened" requires an aperture event or a sim span), exactly one sentence ≤30 words, contains ≥1 `value ± σ` pair from the table. **Test: an injected fabricated number is rejected; a fabricated object is rejected; an unlicensed verb is rejected; a valid LLM sentence is accepted; a bad LLM output twice → template.**
6. Disambiguation rule for `moves_with` T→F (ARCHITECTURE §9): release span precedes `move_to(place)` → blame the release line; elif xy_offset ≤ align_xy ∧ gap_z > gap_cm → blame `move_to(place)`. Expose via facts (`fact["blame_class"]`) for T03's hint/codeloc.
7. Drive it end to end on the real fixtures: `tests/fixtures/clips/b01_early_release.mp4` (+ its recorded tracks) with `examples/stackcube.green` through `pipeline.run.run`. Also b02/b09. Record `artifacts/p06/blame_core_report.json` with the actual t*, σ, facts, summary, and `"evidence_type": "fixture_replay"` (these clips are kinematic-mock sim renders replayed through recorded tracks; say so).

## Definition of Done
- [ ] Tests: `tests/blame/test_{transitions,tstar,facts,summary,validate}.py` pass; includes the fabrication-rejection tests, class 1/2/3 cases, transient-break warning, all-U → None, PASS → None.
- [ ] t* is frame-exact (±0 frames) on ≥3 synthetic ramps with known onset; σ_t* > 0.
- [ ] b01/b02/b09 fixtures produce a `Blame` through `blame_from_run` (or a documented, evidence-backed reason why a clip yields None).
- [ ] No `TODO|NotImplemented` in owned paths; `ruff check` clean on owned paths; full suite still green.
- [ ] Committed `feat(p06/t01): …`.

## Report (filled by owner at DONE)
[2026-11-02T03:55Z · IMPL-1]

**Micro-plan (as executed):** recon fixtures through `pipeline.run` → transitions (3 classes, sustained-recovery rule) → t* (detach-onset, hinge breakpoint, softscore argmax; seeded parametric bootstrap) → facts (measured components only, trace_ids) → template + validator + injected-LLM retry → orchestrator → synthetic kinematic scenarios with known onsets + golden fixture drive → report artifact.

**Built:** `blame/{transitions,tstar,facts,summary,validate}.py` (+ `blame/__init__.py` re-exports `blame_from_run`, `validate_summary`). Commits: b13a8b8, cfbb12e, 77aa8e7, f3d80a3.
`blame_from_run(result, test, pred_frames, fps, **kw)` kwargs: `llm`, `spans`, `code_location`, `code_locator(frame, component)`, `hint_fn(ft)`, `reference_frames`, `dataset_index`, `action_chunk`, `n_boot`, `seed`. `transitions.load_trace_pred_frames(trace.jsonl)` reads PredFrames back from a run trace (the pipeline already writes them, so no pipeline change was needed).

**Evidence:**
- Tests: `tests/blame/test_{transitions,tstar,facts,summary,validate}.py` = 56 passed (13+8+8+12+15). Full suite: 862 passed, 1 xfailed (473 s). Ruff clean on owned paths. No TODO/NotImplemented.
- Frame-exact t*: 4 hinge ramps (3 noise-free + 1 seeded-noise) exact, sigma >= 0.5 floor; detach-onset on the synthetic early release = ground truth frame 46, sigma 0.5.
- Fabrication tests: fabricated number, mixed value/sigma from two facts, fabricated objects (`blue_bowl`, `bowl`, `mugB`), unlicensed `opened`/`hit`/`released`, wrong unit/time/frame, 2 sentences, >30 words, no ± pair: all rejected. Valid LLM sentence accepted as `muse-spark`; bad twice → template (llm called exactly twice); exception → template.
- `artifacts/p06/blame_core_report.json` (regenerate: `KODIAC_WRITE_BLAME_REPORT=1 pytest tests/blame/test_validate.py -k fixture_and_synthetic_report`): `fixture_replay` rows (b01, b02, b09, correct_run) and `synthetic_kinematic` rows, each labelled.

**Deviations:** (1) `Transition` carries a private `_softscore` attr (not a schema field) for the class-2 bootstrap. (2) For a `moves_with` T→F release, context facts are taken on the release pose t*−1 (each fact records its `frame`). (3) `blame_from_run` also returns None when no transition is attributable (all-U / clip ended before the step). (4) `dt_before_reference_s` needs an effector→target series (`facts.reference_pred_frames`, passed as `reference_frames`); the pipeline does not evaluate it, so it is omitted (and logged in evidence) unless the caller supplies it. (5) Order violations are only detected after the first step's achievement, to avoid trivially-true initial states.

**Known limits / honesty:**
1. Golden fixtures are Tier C: every clip, **including correct_run.mp4**, FAILs at `grasp` (moves_with.slip sigma 1.0 cm == threshold → gate G3 keeps it U; posted to CHANNEL as an S0 candidate). Blame says so ("step grasp never confirmed … stayed within noise") with a below-noise-floor warning; b09 gets "lift 0.0 ± 0.7 cm vs ≥ 2.0 cm". These clips are not hero evidence.
2. Synthetic scenarios are hand-built kinematics through an exact fake scale: they validate the blame logic, not perception. Do not quote them as accuracy.
3. Unmet t* on a flat plateau can be arbitrary (b09 fixture: frame 0, sigma 24 frames); the sentence prints t* ± sigma in seconds so this shows. Validator object/verb lists are conservative; a real Muse Spark was never called (no keys).
