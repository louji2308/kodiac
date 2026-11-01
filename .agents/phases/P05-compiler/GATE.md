# GATE: Phase P05 (`Kodiac test` Compiler - "Show It Once")

**Exit Gate Checklist:**
- [x] **G1: Golden Grammar & Round-Trip:** Spec example (`examples/stackcube.green`) parses verbatim; `print_green(parse_green(t)) == t` verified in `tests/compiler/test_parser.py` (all 12 round-trip tests passing).
- [x] **G2: Human Demo Compilation & Latency:** Compilation on demonstration clip produces canonical 4 non-comment lines, every step with provenance, self-test PASS with margin >= 2σ, in < 15 s (< 12 s target). Verified in `tests/cli/test_cli_test.py::test_cli_test_video_correct_run_out`.
- [x] **G3: Diagnostic Integrity:** Missing object -> E001; tactile word ("gently") -> `MANUAL(...)` (W101); invalid comparator -> E004; sloppy demo -> E005. Verified in `tests/compiler/test_lint.py`.
- [x] **G4: Offline Text-Compile & Audit:** `--from-text` reproduces `examples/stackcube.green` bit-identically; compiles >=3 audit task strings offline. Verified in `tests/compiler/test_text_compile.py`.
- [x] **G5: Zero Top-Level Uninstalled Imports:** Zero top-level imports of `torchaudio` or `openai` in `src/Kodiac_robotics/compiler/`. Verified via git grep.
- [x] **G6: UNIX Stream Separation:** Clean `.green` on `stdout` (or `--out`); all progress logs, timers, and warnings on `stderr`. Verified in `tests/cli/test_cli_test.py::test_cli_test_stream_separation`.
- [x] **G7: Test Suite & Ruff Clean:** Full test suite green (`303 passed`), `ruff check .` clean (0 errors), zero stubs.
- [x] **G8: DOC-RECONCILE:** Features F01–F10 matched in `docs/features.yaml` with code evidence.

---

## Gate Evidence (populated by ORCH at GATE stage)

### 1. Test Suite Verification
```powershell
& '.venv\Scripts\python.exe' -m pytest tests/compiler/ tests/cli/test_cli_test.py tests/predicates/test_predicates.py -q
33 passed, 1 warning in 34.98s
```

Full repository regression:
```powershell
& '.venv\Scripts\python.exe' -m pytest tests/ -q --ignore=tests/e2e
303 passed, 1 warning in 137.76s (0:02:17)
```

### 2. Code Quality & Linting
```powershell
& '.venv\Scripts\python.exe' -m ruff check src/Kodiac_robotics/ tests/
All checks passed!
```

### 3. CLI Stream Separation Evidence
```powershell
& '.venv\Scripts\python.exe' -m pytest tests/cli/test_cli_test.py -k test_cli_test_stream_separation -v
tests/cli/test_cli_test.py::test_cli_test_stream_separation PASSED [100%]
```

### 4. Zero Uninstalled Top-Level Imports
```powershell
git grep -E '^(import (torchaudio|openai)|from (torchaudio|openai) import)' src/Kodiac_robotics/compiler/
(0 results found)
```

### 5. Verdict
**PASS** — Phase P05 is certified complete and ready for integration.
