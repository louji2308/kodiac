# T03: Run Pipeline, Audit Trace, Verdict Card v1, CLI & Obstruction Tests

phase: P04 · owner: IMPL-3 · status: DONE
plan_ref: IMPLEMENTATION_PLAN.md P04.S08, P04.S09, P04.S10, P04.S11, P04.S13
depends_on: [T01, T02] · blocks: []
owns_paths:
  - src/Kodiac_robotics/pipeline/**
  - src/Kodiac_robotics/engine/trace.py
  - src/Kodiac_robotics/render/**
  - src/Kodiac_robotics/cli.py
  - tests/pipeline/**
  - tests/render/**
  - tests/engine/test_cant_tell.py
  - tests/cli/test_run_cli.py
reads_only:
  - src/Kodiac_robotics/contracts/core.py
  - src/Kodiac_robotics/geometry/**
  - src/Kodiac_robotics/uncertainty/**
  - src/Kodiac_robotics/predicates/**
  - src/Kodiac_robotics/engine/**
  - .agents/phases/P04-measurement/COUNCIL.md
  - .agents/phases/P04-measurement/RULING.md
timebox: 90 min (3-strike rule applies)

---

## Mission
Integrate geometry, uncertainty, and step logic into `pipeline/run.py` supporting live perception and direct stored-track replay (`[REPLAY: CACHED SAM 3.1 TRACKS]`); stream granular intermediate step records to `runs/<id>/trace.jsonl` via `orjson`; render publication-grade 1280×720 Verdict Card v1 PNGs with lazy opt-in execution; build the user-facing `Kodiac run` CLI command with interactive Rich tables and pure `--json` output; and author programmatic in-memory obstruction tests (`tests/engine/test_cant_tell.py`) validating honest `CAN'T TELL` verdicts and exact reason codes.

---

## Interface Contracts (FROZEN)

```python
# 1. src/Kodiac_robotics/pipeline/run.py
def run(
    test: GreenTest | Path | str,
    clip: ClipRef | Path | str,
    mode: Literal["full", "fast"] = "full",
    tracks: dict[str, Track] | None = None,
    backend: Literal["api", "modal", "fixture"] = "fixture",
    render_card: bool = False,
    output_dir: Path | None = None,
) -> RunResult:
    """Executes a Green test over a video clip.
    - If tracks is provided: sets is_fixture=True, adds badge '[REPLAY: CACHED SAM 3.1 TRACKS]',
      bypasses segmenters, and evaluates directly.
    - Measures per-stage timings (segment_ms, scale_ms, eval_ms, render_ms, total_ms).
    - Generates 16-hex nonce run_id.
    - Writes run artifacts: runs/<id>/result.json, runs/<id>/trace.jsonl, and .Kodiac/last_verdict.json.
    - If render_card is True: renders 16:9 Verdict Card v1 PNG to runs/<id>/card.png.
    - Returns RunResult model instance.
    """

# 2. src/Kodiac_robotics/engine/trace.py
class TraceWriter:
    def __init__(self, trace_path: Path): ...
    def write_event(self, event: Event) -> None: ...
    def write_pred_frame(self, frame_idx: int, atom_name: str, pred_frame: PredFrame) -> None: ...
    def close(self) -> None: ...

# 3. src/Kodiac_robotics/render/card.py
def render_verdict_card_v1(
    run: RunResult,
    clip: Clip,
    decisive_frame: np.ndarray,
    output_path: Path,
    resolution: tuple[int, int] = (1280, 720),
) -> Path:
    """Renders standardized 16:9 Verdict Card v1 PNG.
    - Decisive frame overlay with categorical mask contours and bottom centroid crosshairs.
    - Left/bottom telemetry panel with measured numbers (value +/- sigma, threshold, margin, unit).
    - Step timeline strip: green PASS, red FAIL, amber CAN'T TELL.
    - Badges: [REAL]/[SIM], [sam-3.1], [REPLAY: CACHED SAM 3.1 TRACKS].
    - Safe font fallback hierarchy: bundled -> system sans-serif -> ImageFont.load_default().
    """

# 4. src/Kodiac_robotics/cli.py
# Extends Kodiac CLI with `Kodiac run <test_path> <clip_path>`:
# - Options: --mode [full|fast], --camera [tier_a|tier_b|tier_c], --json, --card, --output <dir>
# - UNIX composability: checks sys.stdout.isatty(). If piped, emits clean plain text summary.
# - If --json is passed: suppresses all decorative Rich boxes and emits pure JSON to stdout.
# - Returns exit codes: 0 (PASS), 1 (FAIL), 2 (CAN'T TELL), 3 (ERROR).
```

---

## Steps
1. **S08 Run Pipeline:** Implement `src/Kodiac_robotics/pipeline/run.py` integrating `fit_scale_model`, `evaluate_atom`, `apply_gates`, and `evaluate_step_chain`. Implement stored-track replay logic and Law 1 badging. Write unit tests in `tests/pipeline/test_run.py`.
2. **S09 Audit Trace:** Implement `TraceWriter` in `src/Kodiac_robotics/engine/trace.py` with fast `orjson` serialization. Write tests in `tests/pipeline/test_trace.py`.
3. **S10 Verdict Card v1:** Implement `render_verdict_card_v1` in `src/Kodiac_robotics/render/card.py`. Support 1280×720 resolution, font fallback, and decisive frame mask contours. Write tests in `tests/render/test_card.py`.
4. **S11 CLI Command:** Add `run` command in `src/Kodiac_robotics/cli.py` with Typer, TTY detection, Rich table formatting, and exit code mapping (0/1/2/3). Write tests in `tests/cli/test_run_cli.py`.
5. **S13 Obstruction Tests:** Author programmatic synthetic frame decorators (`apply_synthetic_box`, `apply_black_out`, `apply_gaussian_blur`) in `tests/engine/test_cant_tell.py` validating Gates G1–G6 and reason codes.

---

## Definition of Done
- [x] `uv run --no-sync pytest tests/pipeline tests/render tests/engine/test_cant_tell.py tests/cli/test_run_cli.py -q` passes 100% green offline.
- [x] Direct stored-track replay evaluated in $< 200$ ms with `[REPLAY: CACHED SAM 3.1 TRACKS]` badge.
- [x] `Kodiac run examples/stackcube.green tests/fixtures/clips/b01_early_release.mp4` returns exit code 1 (FAIL) and writes `runs/<id>/result.json`.
- [x] `Kodiac run examples/stackcube.green tests/fixtures/clips/occluded_clip.mp4` returns exit code 2 (CAN'T TELL) with reasons `[OCCLUDED]`.
- [x] `cli.py --json` emits 100% valid JSON with zero ANSI/terminal formatting.
- [x] Zero TODO/stubs in owned paths (`rg -n "TODO|NotImplemented" src/Kodiac_robotics/pipeline src/Kodiac_robotics/render src/Kodiac_robotics/cli.py` is empty).
- [x] Committed with message `feat(p04/t03): pipeline orchestrator, audit trace, verdict card v1, cli run command, and obstruction tests`.

---

## Report (IMPL-3)
- **Status:** DONE
- **Tests:** 26/26 tests passing 100% green offline across `tests/pipeline`, `tests/render`, `tests/engine/test_cant_tell.py`, and `tests/cli/test_run_cli.py`.
- **Lint:** Spotless clean (`uv run --no-sync ruff check src/Kodiac_robotics/pipeline src/Kodiac_robotics/render src/Kodiac_robotics/engine/trace.py src/Kodiac_robotics/cli.py tests/pipeline tests/render tests/engine/test_cant_tell.py tests/cli` passes with 0 errors).
- **Core Deliverables:**
  1. `src/Kodiac_robotics/pipeline/loader.py`:
     - Robust parser for both `.green` DSL syntax (steps, invariants, tolerance, metadata) and JSON test specifications with SHA-256 integrity hash verification.
  2. `src/Kodiac_robotics/pipeline/run.py`:
     - End-to-end execution pipeline linking perception (FixtureBackend or cached tracks), geometry scaling, Gates G1–G6, and Kleene step chain logic.
     - Direct stored-track replay: bypasses segmentation stage in <200ms, marks `is_fixture=True`, and appends `[REPLAY: CACHED SAM 3.1 TRACKS]` badge per Law 1.
     - Memoized table coordinate scaling avoiding redundant RLE decoding bottlenecks.
     - Granular per-stage timing breakdown (`segment_ms`, `scale_ms`, `eval_ms`, `render_ms`, `total_ms`).
     - Standard artifact writing: `runs/<id>/result.json`, `runs/<id>/trace.jsonl`, `.Kodiac/last_verdict.json`, and lazy opt-in `runs/<id>/card.png`.
     - Strict exit code mapping: 0 (PASS), 1 (FAIL), 2 (CAN'T TELL), 3 (ERROR).
  3. `src/Kodiac_robotics/engine/trace.py`:
     - `TraceWriter` providing fast, line-delimited `orjson` serialization of intermediate `Event` and `PredFrame` records with unique trace nonces.
  4. `src/Kodiac_robotics/render/card.py`:
     - `render_verdict_card_v1` generating publication-grade 1280x720 (16:9) Verdict Card PNGs.
     - Decisive frame overlay with categorical mask contours and bottom-centroid crosshairs.
     - Dark-themed telemetry panel displaying measured values, margins, $\pm \sigma$ uncertainties, and units.
     - Step timeline strip with colored status nodes (green PASS, red FAIL, amber CAN'T TELL).
     - Proof badge row ([REAL]/[SIM], [sam-3.1], [REPLAY: CACHED SAM 3.1 TRACKS], [GEOMETRY: TIER C · UNCALIBRATED CAMERA]).
     - Robust 3-tier font fallback hierarchy (`bundled` -> `system sans-serif` -> `ImageFont.load_default()`).
  5. `src/Kodiac_robotics/cli.py`:
     - Added Typer command `Kodiac run <test.green> <clip-path> [--mode full|fast] [--camera tier_a|tier_b|tier_c] [--json] [--card] [--output <dir>]`.
     - TTY-aware formatting: interactive Rich status table with colored verdict pill banner; scripted/piped plain-text one-liner; and pure valid JSON on `--json` with zero ANSI artifacts.
     - Exit code mapping: 0, 1, 2, 3.
  6. `tests/engine/test_cant_tell.py`:
     - In-memory synthetic frame decorators (`apply_synthetic_box`, `apply_black_out`, `apply_gaussian_blur`) verifying Gates G1–G6 and reason codes (`not_visible`, `occluded`, `below_noise_floor`, `view_blocked`, `depth_ambiguous`).
     - End-to-end verification of `occluded_clip.mp4` returning exit code 2 and `ReasonCode.OCCLUDED`.
