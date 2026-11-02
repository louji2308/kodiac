# T14: S0 honesty fix: proof arms and baseline-judge stand-ins must never fabricate
phase: P08 (hotfix) · owner: IMPL-14 (Sonnet 5.5 @ high) · status: TODO
plan_ref: AGENTS §0 Law 1 · CHANNEL.md 2026-11-02T10:45Z IMPL-9 finding · experiments/PREREGISTRATION.md · contracts `JudgeLabel` (now has `is_mock: bool = True`, `evidence_type`)
depends_on: [] · blocks: [any baseline/arm labelling, headline proof]
owns_paths: [src/Kodiac_robotics/proof/arms.py, src/Kodiac_robotics/proof/judges/**, tests/proof/test_judges.py, tests/proof/test_arms.py, tests/proof/test_pool.py (only if it asserts the removed behaviour), modal/proof_train.py (only labelling-honesty edits), experiments/README.md (append-only "Judge baselines status" section)]
reads_only: [contracts/**, proof/labels.py, proof/stats.py (from T09), experiments/PREREGISTRATION.md]
timebox: 90 min

## The bug (verify first, then fix)
1. `proof/arms.py:~147-224`: when no label file exists, `assemble_proof_arms` silently **invents** Kodiac / open-weights / single-pass / Robometer / TOPReward accept sets *from the oracle with hard-coded error rates* ("High-fidelity double: 92% balanced accuracy"). Anything trained on these arms would be a fake headline.
2. `proof/judges/single_pass.py:~47-81`: offline path sets `accept = oracle_success_hint` (it reads ground truth); the "real inference path" returns a constant PASS / 0.90 **without calling a model**. `robometer.py:~38-44` and `topreward.py` derive scores from `oracle_success_hint`.
3. None of these `JudgeLabel`s sets provenance.

## Required behaviour (fail closed)
- `assemble_proof_arms(...)`: if a judge's label file is missing → that arm is **absent/None with an explicit reason string** (`"no labels: judge not run"`); it must **never** be synthesised from the oracle. Arms that need only the oracle (oracle arm, accept-all, size-matched random control, injected-noise dose arms with their pre-registered rates **labelled as injected noise, not a judge**) remain legitimate; keep them, clearly named, `evidence_type="synthetic"`, `is_mock=True` where derived from mock-sim oracle data. Check the preregistration to keep exactly the arms it defines.
- Judge stand-ins: offline "doubles" may remain **only** as test utilities, renamed/located so they cannot be mistaken for judges (e.g. `proof/judges/_test_doubles.py`, class names `OracleCopyDouble`), never reachable from a production code path or CLI default, and every `JudgeLabel` they produce carries `is_mock=True, evidence_type="synthetic"`, and `judge` name suffixed `"(oracle-copy test double)"`.
- Real inference paths (`single_pass`, `robometer`, `topreward`): if no API key/model/GPU is available they must **raise a clear `JudgeUnavailable` error**, not return a constant. When a real call is made they set `is_mock=False, evidence_type="live"`; recorded-fixture replays set `evidence_type="fixture"`, `is_mock=True`. Do not invent request/response shapes: reuse what `compiler/spark_compile.py` already does for Muse Spark and mark anything unverified with `[UNVERIFIED]` in docstrings.
- A single audit test `tests/proof/test_no_oracle_leak.py`: statically (AST/grep) assert that no module under `proof/judges/` (except `_test_doubles.py`) references `oracle_success_hint` or `oracle_success`, and that `assemble_proof_arms` with an empty labels dir returns no judge arms.
- Update all callers/tests (grep the repo). Do not touch `proof/{labels,stats,chart,ablation}.py` (T09, done, reads only).
- Append a "Judge baselines status" section to `experiments/README.md`: no baseline judge has been run; Robometer/TOPReward/single-pass labels do not exist; the headline arms cannot be built until they (and Modal/Meta credentials) exist.

## Definition of Done
- [ ] New/updated tests pass; the oracle-leak audit test passes; ruff clean; no `TODO|NotImplemented`; full suite green. Commit `fix(p08/t14): …`.

## Report (filled by owner at DONE)
