# T02: Two-stage bisect fast path + fast-vs-full agreement
phase: P06 · owner: IMPL-2 (Opus 5.5 @ xhigh) · status: TODO
plan_ref: IMPLEMENTATION_PLAN.md P06.S01–S02 · ARCHITECTURE.md §5.2, KD-05, ADR-0008 · IDEA F13/F14
depends_on: [] · blocks: [ORCH `run --mode fast` wiring]
owns_paths: [src/Kodiac_robotics/pipeline/bisect.py, scripts/agreement.py, tests/pipeline/test_bisect.py, artifacts/p06/agreement.json]
reads_only: [contracts/**, segment/**, io/**, pipeline/run.py, engine/**, tests/fixtures/**, artifacts/p03/sam_bench.json]
timebox: 150 min (3-strike rule applies)

## Mission
"git bisect for robots": find the failing moment in a long clip with a few SAM calls instead of a full pass, then run one dense
backward-seeded window around it. This is the live <12 s path. `features.yaml` currently (wrongly) says F13/F14 are done; this card makes them true or leaves them honest.

## Interface contract (FROZEN)
```python
class BisectPlan(BaseModel): stage1_frames: list[int]; stage15_probes: list[int]; window: tuple[int,int]; n_sam_calls: int; guards_fired: list[str]
class FastRun(BaseModel): result: RunResult; plan: BisectPlan; stage_timings_ms: dict[str,int]; billed_frames: int
def run_fast(test: GreenTest | Path, clip: Clip, segmenter: Segmenter, *, k_keyframes: int = 6, budget_calls: int = 6, seed: int = 0, **run_kwargs) -> FastRun
```
`segmenter` is the existing `Segmenter` Protocol (fixture/api/modal backends in `segment/`). `run_kwargs` pass through to `pipeline.run.run`
(cam_K, cam_extrinsic, camera). Do NOT edit `pipeline/run.py`; call it. ORCH wires `mode="fast"` and the CLI afterwards.

## Steps
1. Read ARCHITECTURE §5.2/KD-05/ADR-0008, `segment/{fixture,tracks,api}.py`, `io/windows.py` (cut_window, pack_frames), `pipeline/run.py`.
2. Stage 1: K keyframes packed in one call; static proxies; prefix-max progress per step → coarse failure segment. Stage 1.5: halving on the monotone target `F_L` (single-frame probes) until the window ≤ N. Stage 2: dense window ≥ 50 frames (use `cut_window` padding rules), seeds = boxes on the **last** frame of the window, `direction="backward"`; then evaluate with `pipeline.run.run(..., tracks=<stitched>)`.
3. Guards: G-alias (effector alias resolved), G-miss (object lost → widen/fallback to full path, record), G-budget (calls > budget → fallback to subsampled pass or full path, recorded in `guards_fired`), G-pass (PASS steps need sparse verification windows; never declare PASS from keyframes alone).
4. Fixture-backend determinism: with the fixture segmenter the plan must be reproducible bit-for-bit given `seed`. A PASS-clip must not be turned into a FAIL or vice versa by the shortcut (that is the whole agreement test).
5. `scripts/agreement.py`: run full vs fast on every available clip: the 5 golden clips in `tests/fixtures/clips/` and the calibration-split pool episodes in `experiments/pool/manifest.parquet` **only if** a renderable video + recorded/synthetic tracks exist (the pool has state `.npz` only and is `is_mock=True`; if you must use tracks projected from state, label it `"evidence_type": "synthetic_tracks_from_privileged_state"` and do NOT present it as perception agreement). Output `artifacts/p06/agreement.json`: n, verdict agreement %, t* within ±2 frames %, per-stage latency p50/p95, SAM calls, billed frames, `evidence_type`, `is_fixture`. Report the real numbers even if they miss the ≥95% / ≥90% targets; add `"target_met": bool`.
6. Latency: stage timings measured with `time.perf_counter`. Fixture latency is NOT real SAM latency; label `"latency_kind": "fixture_replay_not_sam"`. Do not write any latency into `docs/VIDEO_NUMBERS.md`.

## Definition of Done
- [x] `tests/pipeline/test_bisect.py`: plan determinism; window ≥ 50 frames and inside clip bounds incl. failure at frame 0 and at the last frame; guard G-budget/G-miss/G-pass each triggered by a crafted case; PASS never from keyframes alone; fast vs full verdict agrees on all golden fixtures (or the disagreement is documented in the report with the root cause).
- [x] `artifacts/p06/agreement.json` produced by `scripts/agreement.py` (command in the report), honestly labelled.
- [x] No `TODO|NotImplemented`; ruff clean on owned paths; full suite green.
- [x] Committed `feat(p06/t02): …`.

## Report (filled by owner at DONE)
### Micro-plan (IMPL-2, recon findings first)
- Recon: `pipeline.run.run` cannot evaluate sparse stitched tracks: its G2 scene scan (`run.py:246-258`) marks any frame
  missing from a non-effector track as OCCLUDED and flips every non-PASS verdict to CANT_TELL; temporal predicates
  (`moves_with.py:62-99`, `dwell.py:56-85`) read frames outside the window. → INTERFACE-REQUEST to ORCH; meanwhile a
  dense-window evaluator in `bisect.py` reuses run.py's building blocks, and a test pins it to `run.run` on fully observed clips.
- Recon: on the 5 golden clips the full path gives 4× FAIL (grasp unmet, frame 89) + 1× CANT_TELL; `correct_run.mp4` does NOT
  PASS `examples/stackcube.green` (moves_with is U/below-noise-floor during transport). Not mine to fix; disclosed.
- Stage 1 keyframes (one call) → static proxies → prefix-max progress → bracket; Stage 1.5 single-frame halving on the carried
  literal; Stage 2 window (cut_window padding arithmetic, seeds on the last frame, backward); residual test anchored on the last
  proxy-achieved step; G-miss extend-back ×2 then full fallback; G-pass dense verification windows; G-budget call cap + a
  short-clip rule (bisect bills ≥100 frames, so clips ≤100 frames go direct).
- `scripts/agreement.py`: golden clips × a fixed spec family (both specs + every step/atom of stackcube) in default and forced-bisect
  mode, plus pool calibration episodes with tracks projected from privileged state (labelled, not perception).

### Report [2026-11-02 · IMPL-2] status: DONE
**Commits:** 972e270 (fast path + guards + dense evaluator + tests) · 080ab6e (dwell proxy fix, dense carried-literal windows,
agreement script) · 4a22911 (agreement.json + stricter target rule).

**Built:** `pipeline/bisect.py::run_fast` (frozen contract; `BisectPlan`, `FastRun`). Stage 1 = K = max(6, ⌈dur/2.5 s⌉)
keyframes in one `segment_frames` call → static proxies (real predicates for on/inside/near/lifted; bbox contact for moves_with;
keyframe-to-keyframe stillness for dwell) → prefix-max progress. Stage 1.5 = single-frame halving on the carried literal's
contact proxy while the bracket is > 50 frames. Stage 2 = one window with `cut_window` padding arithmetic (`pad_window`, pinned to
`cut_window` by test), seeds = masks on the window's last frame (one image probe if not already observed), `direction="backward"`.
Guards: G-alias (effector resolved via KD-18 alias prompts; carried flicker → earliest bracket), G-miss (object lost at a
keyframe → full; anchor unverified/late → extend back 50 frames ≤ 2× → full; contradiction → full), G-budget (call cap; clips
≤ 100 frames go direct because bisect bills ≥ 100), G-pass (dense verification windows; PASS only from dense frames). Every
fallback runs `pipeline.run.run`. `RunResult.backends` carries `mode`, `latency_kind`, `seed`, SAM calls, billed units.

**Two real bugs found by the agreement run, fixed and regression-tested:** (1) the dwell proxy used `on(A,B)`, but `dwell.py` only
checks that A stays still. Result: 5 forced-golden PASS→FAIL flips. (2) Carried `moves_with` was watched only at keyframes, but
the engine breaks at its first dense F (any pause makes it F). Result: pool t*±2 was 50% (e.g. t* 106 vs 54). Fix: the dense
window now spans from the step that introduces a checked carried literal (guard `carry-window:dense_from_step`).

**Evidence** (`python scripts/agreement.py`, BRIEF TEMP env, 340 s; `artifacts/p06/agreement.json`):
| block | evidence_type | n | verdict | t*±2 | fallback | target_met |
|---|---|---|---|---|---|---|
| pool calibration (headline) | synthetic_tracks_from_privileged_state, is_mock | 200 | 100% [98.1–100] | 100% (200) | 0% | **false** |
| golden, bisect forced | fixture_replay_synthetic_tracks | 45 | 100% | 100% (31) | 56% | false (n<100) |
| golden, default policy | fixture_replay_synthetic_tracks | 45 | 100% (by construction: direct pass) | 100% | 100% | false |
All latencies: `latency_kind: fixture_replay_not_sam` (in-process replay; no SAM timing exists). Nothing goes to VIDEO_NUMBERS.

**Why target_met=false:** the full path FAILs all 200 pool episodes, including 66 oracle successes, so no PASS case exists to
test PASS-preservation (an engine/sim-track issue, not the bisect). The golden blocks have n=45 < 100.
Tests: `tests/pipeline/test_bisect.py` 38 passed; full suite 932 passed, 13 skipped, 1 xfailed (490 s); ruff clean.

**Deviations:** (a) dense windows are evaluated by `_evaluate_dense` (mirror of run.py:170-333 restricted to dense frames),
because `run.run` flips sparse tracks to CANT_TELL. INTERFACE-REQUEST in CHANNEL.md, and the mirror is pinned to `run.run` on all
5 goldens. (b) Short-clip direct rule (G-budget). (c) The window's start is anchored at the introducing step when a carried
literal is checked, so "≤ 50-frame window" holds only without carried literals. (d) Segmenter keys use snake_case labels
(`cubeA`→`cube_a`), because `FixtureBackend.track` cannot resolve `cubeA` (fixture.py:164 passes no prompts).

**Known limits / 3 ways this could embarrass us:**
1. *Quoting fixture timings as SAM speed.* Every RunResult and agreement block is labelled `fixture_replay_not_sam`, and no
   number is written to VIDEO_NUMBERS. Live latency is unmeasured.
2. *"100% agreement" read as perception accuracy.* Both data sources run full and fast on identical synthetic tracks. Pool tracks
   are projected from privileged state; golden tracks are synthetic fixtures. Blocks are never pooled, and `target_met` is false
   with the reasons written into the JSON.
3. *"Bisect saves cost."* Untrue on the available data: pool bills 168.5 vs 150.7 frames for one dense pass
   (`fast_bills_more_than_one_dense_pass: true`), and forced-golden falls back 56% (Tier C noise floor makes moves_with U; IMPL-1
   reports the same). Savings need clips ≥ ~10 s, which we don't have. Also: proxy misses of a short achievement between
   keyframes stay possible, and only 20 of the 200 pool npz files are git-tracked.
