# GATE: Phase P05 (`Kodiac test` Compiler - "Show It Once")

**Exit Gate Checklist:**
- [ ] **G1: Golden Grammar & Round-Trip:** The spec example (`examples/stack_blocks.green`) parses verbatim; `print_green(parse_green(t)) == t` on all examples (`stackcube.green`, `stack_blocks.green`).
- [ ] **G2: Human Demo Compilation & Latency:** Compilation on demonstration clip produces canonical 4 non-comment lines, every step with provenance, self-test PASS with margin >= 2σ, in < 15 s (< 12 s target).
- [ ] **G3: Diagnostic Integrity:** Missing object -> E001; tactile word ("gently") -> `MANUAL(...)` (W101); invalid comparator -> E004; sloppy demo -> E005.
- [ ] **G4: Offline Text-Compile & Audit:** `--from-text` reproduces `examples/stackcube.green` bit-identically; compiles >=3 audit task strings offline.
- [ ] **G5: Zero Top-Level Uninstalled Imports:** Zero top-level imports of `torchaudio` or `openai` in `src/Kodiac_robotics/compiler/`.
- [ ] **G6: UNIX Stream Separation:** Clean `.green` on `stdout` (or `--out`); all progress logs, timers, and warnings on `stderr`.
- [ ] **G7: Test Suite & Ruff Clean:** Full test suite green (`uv run --no-sync pytest -q`), `uv run --no-sync ruff check .` clean (0 errors), zero stubs.
- [ ] **G8: DOC-RECONCILE:** All features F01–F10 matched in `docs/features.yaml` with code evidence.

---

## Gate Evidence (populated by ORCH at GATE stage)
