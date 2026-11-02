# T01: Blame core: transition finder, t* refinement, fact table, validated summary
phase: P06 · owner: IMPL-1 (Opus 5.5 @ xhigh) · status: TODO
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
