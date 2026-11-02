# T06: Honesty reconciliation (Law 1 fixes from the status audit)
phase: P06 (hotfix, S0-equivalent) · owner: IMPL-6 (Sonnet 5.5 @ medium) · status: TODO
plan_ref: AGENTS.md §0 Law 1, §7.1 DOC-RECONCILE · REVIEW(P04) corrections · ADR-0014
depends_on: [] · blocks: [every later doc/claim]
owns_paths: [docs/features.yaml, docs/VIDEO_NUMBERS.md, artifacts/p03/sam_bench.json, artifacts/p04/validation.json, scripts/validate_engine.py, scripts/bench_sam.py, .agents/phases/P04-measurement/REVIEW.md, .agents/phases/P03-perception/REVIEW.md, README.md, IDEA.md (changelog + Claims table only), experiments/README.md]
reads_only: [everything]
timebox: 75 min

## Mission
A status audit found overstated evidence. One misread number costs the whole project. Fix wording, labels and registries; change **no** measured values and invent none.

## Findings to fix (each has evidence; verify before editing)
1. `artifacts/p03/sam_bench.json` says `"backend": "fixture (deterministic replay)"`, yet ADR-0008 and `features.yaml` F13/F14 treat 5.82 s p95 as a real latency pass. → Add to the JSON: `"evidence_type": "fixture_replay"`, `"is_real_sam_latency": false`, and edit `adr_0008_ruling.status` from `"PASS"` to `"PROVISIONAL_UNVERIFIED (fixture latency; re-measure with live SAM before any <12 s claim)"` (keep all numbers). Make `scripts/bench_sam.py` write these fields when the backend is fixture (minimal change; keep its tests green).
2. `artifacts/p04/validation.json` / `scripts/validate_engine.py`: tracks are synthesised from the simulator's privileged state (`build_synthetic_tracks_from_obs`), so BA = 1.0 / coverage 1.0 / zero gate firings measures engine geometry on perfect tracks, not perception. → Add `"evidence_type": "synthetic_tracks_from_privileged_state"`, `"perception_in_loop": false`, `"is_mock_sim": true` (all 250 pool episodes are `KinematicMockEnv`), and a `"caveat"` string. Make the script emit these fields. Do NOT change counts.
3. `experiments/pool/manifest.parquet` is 250 episodes, all `is_mock=True`, with state `.npz` only (no videos), against ADR-0004 (mock episodes rejected from the pool) and a 600–1000 target. → Do not alter the data. Document the truth in `experiments/README.md` (a "Pool status" section: 250 mock-physics episodes; not valid for the headline proof until regenerated on ManiSkill via Modal; no model arm trained).
4. `docs/features.yaml`: reconcile with reality using these rules: status ∈ {done, partial, planned}; add `evidence_type` (`unit_tests` | `fixture_replay` | `synthetic` | `mock_sim` | `live`) and keep `evidence` pointing at an **existing** path (verify each path exists). Known fixes: F11 evidence file `tests/io/test_transcode.py` does not exist → point to an existing test (`tests/io/test_clip.py`/`test_windows.py`) or mark partial; F13/F14 → `planned` until the bisect lands (this sprint's T02 may flip them; leave a note `pending T02`); F17 → `partial` (lite `inside`, rim memory not built); F23 (`sigma`) → `partial/synthetic` (validation is synthetic); F41 (sim harness) and F42 (B1–B10 bug registry) → `partial` with mock_sim evidence (ManiSkill path unverified; fix-rate eval not run). Re-check every `done` row for evidence that exists on disk and tests that really cover it.
5. `docs/VIDEO_NUMBERS.md`: the "Target Latency" row cites a non-existent `artifacts/p01/sam_bench.json`; fix the path and mark `Status: Target (unmeasured; fixture-only bench exists)`. Add the columns/notes needed for `evidence_type`. Register nothing new as measured.
6. `P04 REVIEW.md` (append-only!): append a `CORRECTION:` block under the R1/R2 sections stating the above (validation is synthetic/circular; the "9.54/10" self-score has no rubric basis (IDEA §12 "Internal self-scores: never publish"); "0.0000 false-PASS" is on synthetic tracks, mock sim). Same for `P03 REVIEW.md` regarding the fixture benchmark. Never delete existing lines.
7. `README.md` is a 6-line placeholder with "+Y points of success". Keep the tagline and keep `Y` explicitly as a placeholder with a visible "not yet measured" note, and add an honest **Status** table (what is built / fixture-only / not built) generated from `docs/features.yaml` by hand now (generator script is P09). No numbers that are not in an artifact.
8. `IDEA.md`: add a changelog line (v3.N bump per AGENTS §7) recording the honesty reconciliation. Do not touch §0.

## Definition of Done
- [ ] Every edited JSON still loads; `scripts/bench_sam.py` and `scripts/validate_engine.py` tests/behaviour unchanged except the new fields; full suite green (`303 passed` baseline).
- [ ] `features.yaml`: every `done` row's evidence path exists (provide the check command + output in the report: a small python one-liner is fine).
- [ ] No fabricated or changed measurements; diff reviewed by you line by line.
- [ ] Committed `docs(p06/t06): honesty reconciliation (Law 1)` (separate commits per concern are fine).

## Report (filled by owner at DONE)
