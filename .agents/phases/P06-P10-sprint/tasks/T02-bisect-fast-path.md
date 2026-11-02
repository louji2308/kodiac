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
- [ ] `tests/pipeline/test_bisect.py`: plan determinism; window ≥ 50 frames and inside clip bounds incl. failure at frame 0 and at the last frame; guard G-budget/G-miss/G-pass each triggered by a crafted case; PASS never from keyframes alone; fast vs full verdict agrees on all golden fixtures (or the disagreement is documented in the report with the root cause).
- [ ] `artifacts/p06/agreement.json` produced by `scripts/agreement.py` (command in the report), honestly labelled.
- [ ] No `TODO|NotImplemented`; ruff clean on owned paths; full suite green.
- [ ] Committed `feat(p06/t02): …`.

## Report (filled by owner at DONE)
