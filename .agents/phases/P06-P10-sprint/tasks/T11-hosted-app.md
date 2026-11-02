# T11: Hosted app (API server, replay store, occlusion, Gradio UI, Modal deploy file)
phase: P09 · owner: IMPL-11 (Sonnet 5.5 @ high) · status: TODO
plan_ref: IMPLEMENTATION_PLAN.md P09.S01–S05, S07, S10 · ARCHITECTURE.md §1.3, §5.8, §11, §12, §14 · IDEA F53–F57
depends_on: [] · blocks: [ORCH integration of blame/fast path into `/grade`]
owns_paths: [src/Kodiac_robotics/app/**, scripts/precompute_replays.py, site/**, tests/app/**, tests/e2e/**, modal/app_deploy.py, .github/workflows/pages.yml]
reads_only: [contracts/**, pipeline/run.py, io/**, render/card.py, compiler/text_compile.py, examples/**, tests/fixtures/**, modal/__init__.py, modal/volumes.py]
do_not_touch: [src/Kodiac_robotics/cli.py, pyproject.toml (read only; if an extra is missing, tell ORCH in the report)]
timebox: 150 min

## Mission
A judge opens a public page with no login, picks a curated clip or uploads one, hits Grade, and sees a verdict card with a **wall-clock timer**, honest badges, the CAN'T TELL path (occlusion brush / camera-cover), and an **instant, clearly-labelled ⚡ CACHED replay**. It must hold up under concurrent judges and never fake a live result.

## Interface contract (FROZEN)
```python
# app/server.py  (FastAPI)
GET  /health  -> {"ok": true, "version": ..., "backend": "fixture|api|modal", "mode": "live|cache-only"}
POST /grade   multipart(file|clip_id, test_id|typed_instruction, occlusion_rects?) -> {"run": RunResult-json, "card_url": ..., "timer_ms": int, "badges": [...], "cached": false}
GET  /replay/{id} -> same shape, "cached": true, badge "⚡ CACHED"
def create_app(settings: AppSettings | None = None) -> FastAPI
# app/replay.py:   ReplayStore(root: Path).put(id, run_result, card_png) / .get(id) / .list()  (content-addressed; every entry records is_fixture, backend, created_at, source commit)
# app/occlusion.py: apply_rects(frames_bgr: np.ndarray, rects: list[tuple[int,int,int,int]]) -> np.ndarray  (black-out rectangles on ALL frames before grading)
# app/ui.py:       build_ui(api_base: str | None = None) -> "gradio.Blocks"   (import gradio lazily; tabs Dataset / Upload / Webcam / Teach it live; timer; verdict card; "How it works" model table; honest limits; privacy notice)
```
## Rules
- **Honesty first (Law 1):** without API keys the backend is the fixture/replay path. The UI must show the badge `[FIXTURE REPLAY]` / `⚡ CACHED` exactly as the run's badges say, and the timer must measure real wall-clock of what actually ran. Never show "<12 s" as a claim; show the measured time only. A cached replay is never presented as a live grade ("Re-run live" is a separate action).
- Guards (`server.py`): per-IP token bucket (default 6/min, configurable), 20 s video / 50 MB caps → friendly typed errors, transcode via `io.transcode` to H.264, upload retention ≤24 h with a reaper function, structured logs **without PII** (no IPs/filenames in logs; hash them), 429 → friendly page + cached replay link.
- E001 (object not found) → the friendly message: "We couldn't find 'red block'. Try Teach it or an example test."; compile failures → typed-instruction fallback.
- `site/`: static landing page + the cached replay cards generated from `ReplayStore` + a clearly marked video embed placeholder (`<!-- VIDEO_URL -->`; no fake link). `.github/workflows/pages.yml` deploys `site/` (no secrets).
- `modal/app_deploy.py`: CPU image (ffmpeg + package), `@modal.concurrent(max_inputs=20)`, scheduled `upload_reaper`; `min_containers` read from env (default 0 — **never a warm GPU**; the 1-container Nov 4–16 setting is applied by a human/ORCH at release). It must import without `modal` installed guard-wise? No: modal is not installed locally; keep the file importable only under `if TYPE_CHECKING`/lazy imports so `ruff` and tests pass; unit-test its pure helper functions only. Deploying = human action (needs a Modal token). Do not call Modal.
- Gradio/Playwright may not be installed locally: tests for `server.py`, `replay.py`, `occlusion.py` use FastAPI `TestClient` (installed). UI/E2E tests are marked `@pytest.mark.slow` and skip cleanly with a reason if gradio/playwright are missing; write them anyway so they run on a machine that has them. Try installing the declared `app` extra's gradio once (`pip install "gradio>=5"`): report the outcome; never block on it.
- Precompute: `scripts/precompute_replays.py` runs the golden clips (correct, B1, B2, B9, occluded) through `pipeline.run.run` (fixture backend) into a ReplayStore (path configurable; default `site/replays/` for the static mirror, small PNG/JSON only, ≤2 MB total) with honest badges.
## Definition of Done
- [ ] Tests pass: health; grade on a fixture clip (FAIL for B1 with card_url, PASS for correct); occlusion → CAN'T TELL with a reason code; oversize/over-length → friendly error; rate limit → 429 + replay link; replay marked cached; logs contain no raw IP/filename; reaper deletes >24 h uploads.
- [ ] `site/` builds from the script; its HTML contains the FIXTURE/CACHED badge text for every card (test).
- [ ] ruff clean; no `TODO|NotImplemented`; full suite green. Committed `feat(p09/t11): …`.

## Report (filled by ORCH at DONE, 2026-11-02; owner session died at final-reply step)

### What was built
- `src/Kodiac_robotics/app/`: `settings.py`, `server.py` (FastAPI: `/health`, `POST /grade`, `GET /replay/{id}`), `service.py` (grade
  pipeline with per-run dirs, wall-clock `timer_ms`, transcode, retention reaper), `guards.py` (per-IP token bucket, size/length caps,
  typed errors), `occlusion.py` (rectangle brush applied to all frames), `replay.py` (content-addressed `ReplayStore`), `ui.py`
  (Gradio Blocks: Dataset / Upload / Webcam / Teach it), `site.py`, `precompute.py`, `content.py`, `client.py`, `errors.py`, `core.py`.
- `scripts/precompute_replays.py`, `site/` (static mirror + 6 cached replays), `modal/app_deploy.py` (CPU image, `max_inputs=20`,
  `min_containers` from env, scheduled reaper), `.github/workflows/pages.yml`.
- `tests/app/`, `tests/e2e/` (FastAPI `TestClient`; UI/E2E marked slow, skip with reason when gradio is absent).

### Evidence (re-verified by ORCH after the owner died)
- `python -m pytest tests/app tests/e2e -q` → **50 passed, 2 skipped, 1 xfailed** (skips: `gradio is not installed in this environment`).
- `site/replays.json` → 6 cached replays, every one with `is_fixture: true`, `backend: "cached_replay"`, badges
  `[FIXTURE REPLAY]` + `[REPLAY: CACHED SAM 3.1 TRACKS]` + `[GEOMETRY: TIER C · UNCALIBRATED CAMERA]`. The static page states in a banner
  that every card is a precomputed cached replay, never a live grade.
- `correct_run` replay carries an explicit note that the engine's FAIL on the reference clip is a known limitation, "not a PASS".
- Last increment committed by ORCH: `7f873e4` (Windows directory-move retry).

### Known limits / follow-ups
- **Replays predate the engine fix**: generated at `cb44d53`, i.e. before T13. `scripts/precompute_replays.py` must be re-run after T13 lands,
  and `correct_run`'s verdict will change (Tier C should abstain, not FAIL).
- Gradio and Playwright are not installed, so the UI visual tests never ran here; they are written and skip with a reason.
- Nothing was deployed: no Modal token, no hosted URL. `modal/app_deploy.py` is import-guarded and unit-tested on pure helpers only.
- No live grade exists anywhere (no API key); every path is fixture/cached and labelled as such.
