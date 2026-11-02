# T07: P04 review backlog fixes (small, mechanical)
phase: P06 · owner: IMPL-7 (Haiku 5.5 @ high) · status: TODO
plan_ref: .agents/BACKLOG.md F-P04-R1-01, F-P04-R2-01..03
depends_on: [] · blocks: []
owns_paths: [src/Kodiac_robotics/engine/smoothing.py, src/Kodiac_robotics/pipeline/run.py (only the badge-appending lines near `[FIXTURE REPLAY]`), src/Kodiac_robotics/io/clip.py (only `_infer_source_kind`), src/Kodiac_robotics/cli.py (ONLY the warnings filter at the top of the module; do not touch commands), tests/io/test_clip.py, tests/pipeline/test_run.py, tests/cli/test_run_cli.py, .agents/BACKLOG.md]
reads_only: [.agents/phases/P04-measurement/REVIEW.md, tests/fixtures/clips/manifest.json]
timebox: 45 min

## Tasks
1. **F-P04-R1-01 / F-P04-R2-03:** SciPy emits `UserWarning: A NumPy version >=1.22.4 and <2.3.0 is required for this version of SciPy` on `from scipy.signal import savgol_filter` (installed: numpy 2.4.6, scipy 1.13.1). Register a targeted `warnings.filterwarnings("ignore", message=r"A NumPy version .* is required for this version of SciPy", category=UserWarning)` **before** the scipy import in `engine/smoothing.py`, and at the very top of `cli.py` before other third-party/project imports so CLI stderr is clean. Test: invoking the `Kodiac run … --json` path in a subprocess (or CliRunner with captured stderr) emits no SciPy warning.
2. **F-P04-R2-01:** when `backend == "fixture"`, append both `[FIXTURE REPLAY]` and `[REPLAY: CACHED SAM 3.1 TRACKS]` to the badges (no duplicates). Update/extend a test in `tests/pipeline/test_run.py`.
3. **F-P04-R2-02:** `_infer_source_kind` in `io/clip.py` defaults `tests/fixtures/clips/b01_early_release.mp4` to `"upload"`. Make clips under `tests/fixtures/clips/` (or listed in that dir's `manifest.json` as sim renders) resolve to `"sim"` so the card badges `[SIM]` not `[UPLOAD]`. Keep all other inference behaviour and its tests unchanged. Add tests.
4. Mark the four rows `DONE (2026-11-02, T07)` in `.agents/BACKLOG.md` (edit only the Status column, with the commit sha after you commit).
5. Verify and report: `pytest-timeout` is declared in pyproject but not installed in `.venv`. Try `& ".\.venv\Scripts\python.exe" -m pip install "pytest-timeout>=2.2"` (this is a declared dev dependency, no money/credential involved). If the network is unavailable, report that and do not retry more than once.

## Definition of Done
- [ ] Targeted tests pass; full suite green (303 baseline + your new tests); `ruff check` clean on owned paths.
- [ ] Committed `fix(p06/t07): …` touching only owned paths.

## Report (filled by owner at DONE)
