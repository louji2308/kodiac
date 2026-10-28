# T01: Implement Core Data Contracts, Scaffolding, Cache & CI

phase: P01 · owner: IMPL-1 · status: DONE
plan_ref: IMPLEMENTATION_PLAN.md P01.S04–S07
depends_on: [] · blocks: [T02, T03]
owns_paths: [pyproject.toml, src/Kodiac_robotics/**, tests/unit/contracts/**, docs/schemas/**, .github/workflows/**]
reads_only: [ARCHITECTURE.md §4, TOOLS_AND_REQUIREMENTS.md §12, .agents/phases/P01-setup/RULING.md]
timebox: 120 min (3-strike rule applies)

## Micro-plan
1. Create pyproject.toml with pure-python dependencies and ruff/pytest configurations.
2. Initialize all packages per ARCHITECTURE.md §3.1 with docstrings in src/Kodiac_robotics/__init__.py and subpackages.
3. Implement src/Kodiac_robotics/contracts/core.py strictly per ARCHITECTURE.md §4 & RULING.md.
4. Implement src/Kodiac_robotics/contracts/fixtures.py with synthetic test double factories.
5. Implement src/Kodiac_robotics/contracts/schema_export.py exporting JSON schemas to docs/schemas/.
6. Implement src/Kodiac_robotics/config.py and src/Kodiac_robotics/cache.py with atomic writes.
7. Implement tests/unit/contracts/test_core.py, test_fixtures.py, test_config_cache.py and .github/workflows/ci.yml.
8. Verify tests and linting via pytest and ruff check.

## Mission
Establish the immutable core data models and execution infrastructure for Kodiac. Everything downstream (perception, measurement engine, `blame`, `diff`, and the Muse Code done-gate) relies on these frozen Pydantic v2 schemas and zero-dependency contracts. They must be clean, typed, deterministic, and 100% covered by round-trip tests.

## Interface Contract (FROZEN per ARCHITECTURE.md §4 & RULING.md)
1. `src/Kodiac_robotics/contracts/core.py`:
   - `from __future__ import annotations` at the top.
   - Enums: `Tri(str, Enum) = T|F|U`, `Verdict(str, Enum) = PASS|FAIL|CANT_TELL`, `ReasonCode(str, Enum)`.
   - AST: `ObjectDecl`, `Param`, `Atom`, `Expr`, `Step`, `GreenTest`, `GreenLock`.
   - Perception & Video: `ClipRef`, `Clip`, `ObjMask`, `Track`, Protocols `Segmenter`, `VLMJudge`, `ASR`, `Memory`, `ScaleModel`.
   - Measurement & Blame: `Component`, `PredFrame`, `Event`, `StepResult`, `CodeLocation`, `Hint`, `FactTable`, `Blame`.
   - Engine & Loop: `RunResult`, `VerifyRequest`, `GateState`.
   - Storage & Proof: `VerdictRow`, `JudgeLabel`.
   - Invariant: `RunResult` must validate `is_fixture: bool = False`, 16-hex `nonce` (`^[0-9a-f]{16}$`), and non-negative `timings_ms`.
   - Invariant: `Expr.model_rebuild()` and `GreenLock.model_rebuild()` must be called explicitly at module bottom.
2. `src/Kodiac_robotics/contracts/fixtures.py`:
   - Synthetic factory functions: `make_dummy_greentest()`, `make_dummy_clip()`, `make_dummy_runresult()`, `make_dummy_blame()`.
3. `src/Kodiac_robotics/config.py`:
   - `Settings` class inheriting from `pydantic_settings.BaseSettings`. Reads `.env`, masks secret values.
4. `src/Kodiac_robotics/cache.py`:
   - `cached_call(key_parts: dict, fn) -> bytes|dict` using SHA-256 over canonical JSON + payload bytes with atomic writes.
5. `pyproject.toml`:
   - Project name `Kodiac-robotics`, Python `>=3.12`, pure-Python core without torch.
   - CLI script `Kodiac = "Kodiac_robotics.cli:app"`.
   - Extras `[sim, proof, app, viz, mcp, lerobot, dev]`.

## Definition of Done
- [x] `pyproject.toml` created and verified with `uv sync` / packaging config.
- [x] `src/Kodiac_robotics/contracts/core.py` implemented strictly matching `ARCHITECTURE.md §4`.
- [x] `src/Kodiac_robotics/contracts/fixtures.py` implemented (IP-P01-D1-1).
- [x] `src/Kodiac_robotics/contracts/schema_export.py` exports all JSON schemas to `docs/schemas/`.
- [x] `src/Kodiac_robotics/config.py` and `cache.py` implemented with unit tests.
- [x] `tests/unit/contracts/test_core.py` passes with 100% round-trip validation and ≥10-level nested recursion test.
- [x] `uv run ruff check .` passes with zero lint/format errors.
- [x] No `TODO` or `NotImplemented` in owned paths.

## Verification Commands
```powershell
.venv\Scripts\python.exe -m pytest tests/unit/contracts/ -q
.venv\Scripts\python.exe -m Kodiac_robotics.contracts.schema_export
.venv\Scripts\python.exe -m ruff check .
```

## Report (filled by owner at DONE)
- **Status:** DONE
- **Artifacts Delivered:**
  - `pyproject.toml`: package `Kodiac-robotics`, scripts `Kodiac`, extras `[sim, proof, app, viz, mcp, lerobot, dev]`, ruff and pytest configurations.
  - `src/Kodiac_robotics/__init__.py` and 17 subpackages initialized with module docstrings per ARCHITECTURE.md §3.1.
  - `src/Kodiac_robotics/cli.py`: Typer CLI entrypoint.
  - `src/Kodiac_robotics/contracts/core.py`: Enums (`Tri`, `Verdict`, `ReasonCode`), AST models (`Provenance`, `ObjectDecl`, `Param`, `Atom`, `Expr`, `Step`, `GreenTest`, `GreenLock`), Perception/Video models (`ClipRef`, `Clip`, `ObjMask`, `Track`), Protocols (`Segmenter`, `VLMJudge`, `ASR`, `Memory`, `ScaleModel`), Measurement/Blame models (`Component`, `PredFrame`, `Event`, `StepResult`, `CodeLocation`, `Hint`, `FactTable`, `Blame`), Run/Loop models (`RunResult`, `VerifyRequest`, `GateState`), Audit/Proof models (`VerdictRow`, `JudgeLabel`). Validations for 16-hex `nonce`, non-negative `timings_ms`, `is_fixture: bool = False`, and `Verdict == CANT_TELL => reasons != []`. Forward references rebuilt with `Expr.model_rebuild()` and `GreenLock.model_rebuild()`.
  - `src/Kodiac_robotics/contracts/fixtures.py`: Synthetic test double factories (`make_dummy_greentest`, `make_dummy_clip`, `make_dummy_blame`, `make_dummy_runresult`, `make_dummy_lock`, `make_dummy_track`).
  - `src/Kodiac_robotics/contracts/schema_export.py`: CLI exporting 25 model JSON schemas and `index.json` to `docs/schemas/`.
  - `src/Kodiac_robotics/config.py`: `Settings(BaseSettings)` with secret masking via `masked_dict()`.
  - `src/Kodiac_robotics/cache.py`: Deterministic content-hash cache using SHA-256 with tempfile + atomic rename.
  - `tests/unit/contracts/test_core.py`: 15 comprehensive unit tests (enums, gripper role defaults, nonce regex, timings validator, CANT_TELL validator, roundtrips for GreenTest/RunResult/Blame/Lock/Track, 15-level nested `Expr` recursion test, config masking, and cache atomic hits).
  - `.github/workflows/ci.yml`: GitHub Actions workflow running ruff, pytest, and schema export verification.
- **Verification Results:**
  - `pytest tests/unit/contracts/`: 15 passed in 2.22s.
  - `schema_export`: Exported 25 JSON schemas to `docs/schemas/` with exit code 0.
  - `ruff check .`: All checks passed with 0 errors.
  - Zero `TODO` or `NotImplemented` entries.
- **Judge Embarrassment Risk Audit:**
  1. *Recursive AST schema failure*: Mitigated by explicit `Expr.model_rebuild()` and tested to 15 levels of nested boolean logic.
  2. *Fabricated test latencies*: Mitigated by enforcing `is_fixture: True` and badge `"FIXTURE"` on synthetic test doubles with non-negative timing validation.
  3. *Credential leaks*: Mitigated by `Settings.masked_dict()` scrubbing sensitive keys and zero secrets required in CI.
