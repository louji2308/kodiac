# T02: Implement `Kodiac doctor` CLI & Smoke Test Suite (ST1–ST13)

phase: P01 · owner: IMPL-2 · status: DONE
plan_ref: IMPLEMENTATION_PLAN.md P01.S08–S10
depends_on: [T01] · blocks: []
owns_paths: [src/Kodiac_robotics/cli/**, src/Kodiac_robotics/cli.py, scripts/smoke/**, artifacts/p01/**, tests/unit/cli/**]
reads_only: [src/Kodiac_robotics/contracts/**, src/Kodiac_robotics/config.py, src/Kodiac_robotics/cache.py, TOOLS_AND_REQUIREMENTS.md §11, .agents/phases/P01-setup/RULING.md]
timebox: 90 min (3-strike rule applies)

## Mission
Deliver the user-facing `Kodiac doctor` diagnostic command and the ST1–ST13 smoke test suite. Judges running `Kodiac doctor` on a fresh machine without API keys must see a polished, informative two-table Rich summary that exits 0 when the offline core is healthy, and all smoke tests must strictly enforce Law 1 (anti-fabrication) when keys are pending.

## Micro-Plan
1. **Recon & CLI Structure**: Inspect typer app in `cli.py`, add version flag (`--version` / `version` command) and `doctor` command with `--json` option.
2. **Table 1 (Offline Core)**: Check Python >=3.11, ffmpeg binary, cache dir writeability, contracts/fixtures import. Exit 0 if all pass.
3. **Table 2 (Cloud & Sponsors)**: Presence check for `MODEL_API_KEY`, `HF_TOKEN`, `MODAL_TOKEN_ID`, `BASETEN_API_KEY`, `FIREWORKS_API_KEY`, `nvidia-smi` GPU check, `opencode` CLI. Never print secrets!
4. **Doctor Terminal Capture**: Write ANSI text output to `artifacts/p01/doctor_terminal.txt`.
5. **Synthetic Video Generator**: Generate 50-frame H.264 `yuv420p` test clip at `artifacts/p01/smoke/synthetic_50f.mp4` using ffmpeg/cv2.
6. **Smoke Suite ST01–ST13**: Implement modular scripts in `scripts/smoke/` and `scripts/smoke/run_all.py` producing `artifacts/p01/smoke/st01.json` ... `st13.json` following exact schema and Law 1 rules.
7. **CLI Unit Tests**: Implement `tests/unit/cli/test_doctor.py` testing `--version`, `doctor`, `--json`, and secret redaction assertion.
8. **Verify & Report**: Run pytest and ruff, fill report, commit incrementally, update status.

## Interface Contract (FROZEN per RULING.md)
1. CLI Entrypoint (`src/Kodiac_robotics/cli.py` or `src/Kodiac_robotics/cli/__init__.py` exposing `app: typer.Typer`):
   - `Kodiac --version` prints version `0.1.0`.
   - `Kodiac doctor [--json]` prints two Rich tables:
     - **Table 1: Core Engine (Offline)** — Python version, `ffmpeg` binary, cache dir writeability, core schema imports.
     - **Table 2: Cloud Services & Sponsors (Online)** — Presence-only check (NEVER print secret values!) for `MODEL_API_KEY`, `HF_TOKEN`, `MODAL_TOKEN_ID`, `BASETEN_API_KEY`, `FIREWORKS_API_KEY`, `nvidia-smi` GPU check, `opencode` CLI check.
   - Exits `0` if Table 1 checks pass.
   - Captures output to `artifacts/p01/doctor_terminal.txt`.
2. Smoke Test Suite (`scripts/smoke/st01_models.py` … `st13_sdm.py` and `scripts/smoke/run_all.py`):
   - Implements ST01 through ST13 per `TOOLS_AND_REQUIREMENTS.md §11`.
   - Generates a tiny 50-frame H.264 `yuv420p` synthetic red/green block test clip using OpenCV/PyAV/ffmpeg at `artifacts/p01/smoke/synthetic_50f.mp4` (≤50 frames).
   - Each script writes `artifacts/p01/smoke/stNN.json` with exact schema:
     ```json
     {
       "test_id": "ST01",
       "name": "Meta Model API /v1/models",
       "ok": false,
       "status": "PENDING_KEY",
       "is_fixture": true,
       "live_verified": false,
       "latency_ms": null,
       "notes": "MODEL_API_KEY not set in environment; verified request structure in mock mode.",
       "evidence_path": null
     }
     ```
   - For tests verifiable locally without missing cloud keys (e.g. ST13 checking `opencode run --help` SDM readiness, synthetic H.264 clip generation), record real measured `latency_ms`, `ok: true`, `status: "OK"`, `is_fixture: false`, `live_verified: true`.
   - **CRITICAL LAW 1 GUARD:** Never fabricate or hardcode dummy `latency_ms` for unverified cloud API calls; `latency_ms` MUST be `null` whenever `is_fixture` is `true`.

## Definition of Done
- [x] `uv run Kodiac --version` and `uv run Kodiac doctor` exit 0.
- [x] `artifacts/p01/doctor_terminal.txt` generated.
- [x] `scripts/smoke/st01_models.py` … `st13_sdm.py` and `scripts/smoke/run_all.py` implemented and executed.
- [x] `artifacts/p01/smoke/st01.json` … `st13.json` exist and obey Law 1 (`is_fixture: true => latency_ms: null`).
- [x] `tests/unit/cli/test_doctor.py` passes (tests exit code 0, `--json` output, and ensures dummy secret values in env are never printed to stdout).
- [x] `uv run ruff check` clean on owned paths.

## Verification Commands
```powershell
uv run Kodiac --version
uv run Kodiac doctor
uv run python scripts/smoke/run_all.py
uv run pytest tests/unit/cli/ -q
uv run ruff check src/Kodiac_robotics/cli* scripts/smoke/ tests/unit/cli/
```

## Report (filled by owner at DONE)
- **Built:**
  - CLI: `src/Kodiac_robotics/cli.py` with `Kodiac --version` (prints `0.1.0`), `Kodiac doctor` (two Rich ASCII tables: Table 1 Core Engine Offline, Table 2 Cloud Services & Sponsors Online, exiting 0 on Table 1 health, capturing text to `artifacts/p01/doctor_terminal.txt`), and `--json` support.
  - Smoke Suite: `scripts/smoke/common.py` (Law 1 programmatic guard, 50-frame synthetic H.264 test clip generator), `scripts/smoke/st01_models.py` through `st13_sdm.py`, and `scripts/smoke/run_all.py`.
  - Artifacts: `artifacts/p01/doctor_terminal.txt`, `artifacts/p01/smoke/synthetic_50f.mp4` (50 frames, 3.2 KB), `artifacts/p01/smoke/st01.json` through `st13.json`, and `artifacts/p01/smoke/summary.json`.
  - Tests: `tests/unit/cli/test_doctor.py` (7 tests: version flag/command, doctor offline healthy exit 0, `--json` structure, secret non-leakage, table 1 failure exit 1, and Law 1 smoke artifact anti-fabrication assertions).
- **Evidence:**
  - `uv run Kodiac --version` -> `Kodiac 0.1.0` (exit 0)
  - `uv run Kodiac doctor` -> Table 1 all PASS, Table 2 safe status, exit 0
  - `uv run python scripts/smoke/run_all.py` -> 13 tests executed (ST13 live OK with real latency 1302.2 ms; ST01-ST12 fixture with latency null), exit 0
  - `uv run pytest tests/unit/cli/ -q` -> 7 passed in 8.52s
  - `uv run ruff check src/Kodiac_robotics/cli.py scripts/smoke/ tests/unit/cli/` -> All checks passed
- **Commits:**
  - `4b3fdc2`: `feat(p01/t02): implement Kodiac doctor CLI and ST01-ST13 smoke test suite`
- **Deviations:** None.
- **Known limits:** Cloud services are in fixture mode pending sponsor credentials (`MODEL_API_KEY`, `MODAL_TOKEN_ID`, etc.), which is non-blocking for local dev per RULING.md / ADR-0003.
