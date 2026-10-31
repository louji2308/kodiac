You are the Senior Decision Maker for team Kodiac (Meta Global AI Developer Hackathon 2026). Three decision makers (Architect,
Judge Advocate, Red Team) have deliberated on Phase P05 and send you their converged plan, improvement proposals, and disagreements.
You are the final technical authority for this phase. Think deeply and independently. Do not rubber-stamp. Your job is to find
the move that maximizes the probability of winning while keeping every claim true and the demo robust.

NON-NEGOTIABLE: You may not alter the Concept Invariants listed below. You may not approve anything that costs money or acts publicly.

PACKET:
# SDM Escalation Packet: Phase P05 (`Kodiac test` Compiler - "Show It Once")

**Date:** 2026-10-31 · **Deadline Countdown:** 104.5h to submit · 92.5h to freeze · **Council Confidence:** 96.3/100 (D1: 95, D2: 98, D3: 96) · **Disagreements:** 0

---

## 1. Phase Mission & Goal
Deliver "Show It Once" (Invariant I2, Video Beat 0:24–0:50): compile a single human demonstration video and spoken instructions into an unassailable 4-line `.green` test specification and cryptographic `.green.lock` file in < 12 seconds. Multi-model orchestration:
- **Muse Voice:** Segments spoken instructions into temporal action windows (`VoiceTurn`).
- **Muse Spark:** Compiles high-level task topology, object roles, and step sequences into a symbolic `.green` skeleton.
- **SAM 3.1:** Grounds declared objects on keyframes to visual tracks and verifies affordances.
- **P04 Measurement Engine & Slack Engine:** Empirically measures physical margins on the demo video and calculates calibrated physical tolerances (margin >= 2σ).
- **Zero-Network Fallback:** Guarantees 100% offline text-compile mode (`--from-text`) and offline demo fixture playback.

---

## 2. Converged Architecture & Consensus Commitments
The Council (D1 Architect, D2 Judge Advocate, D3 Red Team) unanimously resolved all failure modes into 7 architectural commitments:
1. **Lark Grammar Disambiguation:** Define `predicate: PRED "(" pred_arg ("," pred_arg)* ")"` with `pred_arg: param | IDENT` to prevent LALR shift/reduce conflicts on 1-arg predicates (`lifted(cubeA, min_cm=2.0)`). Arity and role validation execute in post-parse semantic visitor (`E003`).
2. **Zero Uninstalled Dependencies:** Neither `torchaudio` nor `openai` is installed. Mandate zero top-level imports. Use stdlib `wave` for audio duration, system `ffmpeg` for extraction, and `httpx` (0.27.2) for API calls. Guard MMS-FA alignment behind optional dynamic imports.
3. **Decoupled Two-Pass Calibration:** Muse Spark outputs symbolic placeholders only (`value=-1.0`). LLMs are strictly forbidden from guessing numbers (Invariant I6). Calibration executes in 2 passes:
   - *Pass 1 (Metric Extraction):* `pipeline/run.py` runs in unconstrained metric logging mode over the demonstration clip to capture empirical extrema (h_max, Δ_xy, z_gap, v_settle).
   - *Pass 2 (Slack Derivation & Verification):* `compiler/slack.py` calculates calibrated tolerances with certified safety margins (margin >= 2σ). `compiler/selftest.py` executes read-only verification asserting `Verdict == PASS`.
4. **Physical Sanity Caps (Anti-Poisoning):** To prevent sloppy demos from generating loose tests that poison downstream policy training (Invariant I8), `compiler/slack.py` enforces hard upper caps: `align_xy <= 4.0cm`, `gap <= 2.0cm`, `min_cm <= 8.0cm`, `v_settle <= 2.5cm/s`. Sloppy demos exceeding these caps fail compilation with `E005`.
5. **Mandatory Honesty Badging (Law 1):** If Spark fails, times out (>8s), or `MODEL_API_KEY` is missing, `compiler/template_fallback.py` provides deterministic offline recovery. The output is visibly badged:
   - Header comment: `[COMPILER: DETERMINISTIC TEMPLATE FALLBACK · LLM OFFLINE]`
   - Provenance tag: `source="compiler-default"`
   - Lockfile record: `model_ids["compiler"] = "template-fallback"`
   - Terminal alert: Amber notice to `stderr`.
6. **Clean Stream Separation (Invariant I1):** Interactive spinners, sub-step timers (`✓ [1.2s] transcript`), and warnings (W101–W105) stream strictly to `stderr`. `stdout` is reserved exclusively for clean `.green` syntax when `--out` is omitted.
7. **Frozen Contract Preservation:** Inter-module communication uses the frozen `VoiceTurn` Pydantic model. Top-level `GreenLock` schema is strictly preserved; slack metrics are embedded in `object_baselines["_slack_summary"]`.

---

## 3. Improvement Proposals (IP) Requiring SDM Ruling

| IP ID | Title / Proposal | D1 | D2 | D3 | Reason for Escalation |
|---|---|:---:|:---:|:---:|---|
| **IP-P05-D1-1** | Two-Stage Compiler: Structure by Spark, Calibration by Measurement | APPROVE | APPROVE | APPROVE | Touches `ARCHITECTURE.md` and Invariants I2, I6. Enforces that LLMs output structure only, while physical thresholds derive exclusively from empirical measurement. |
| **IP-P05-D3-1** | Deterministic Template Fallback Compiler with Honesty Badging | APPROVE | APPROVE | APPROVE | Touches Invariant I15 and demo reliability. Guarantees 100% offline recovery without external network, protected by Law 1 badging. |
| **IP-P05-D3-2** | Mathematical Auto-Slack Fitting with Physical Sanity Caps | APPROVE | APPROVE | APPROVE | Touches Invariant I8 (Proof Integrity). Ensures demo self-test succeeds by mathematical construction while bounding upper limits to reject sloppy demos. |

*Council-Local IPs Approved (No Escalation Needed):*
- `IP-P05-D1-2`: Robust Lark grammar with `pred_arg: param | IDENT` and AST semantic visitor.
- `IP-P05-D1-3`: Offline fixture support via `--backend fixture` and stdlib `wave`.
- `IP-P05-D2-1`: Warning highlights (W101–W105) routed to `stderr`.
- `IP-P05-D2-2`: Unified `--backend fixture` auto-detecting clips in `tests/fixtures/clips/`.
- `IP-P05-D2-3`: Lightweight sequential `time.perf_counter()` progress timers on `stderr`.
- `IP-P05-D2-4`: Preserve frozen `GreenLock` schema by nesting slack in `object_baselines["_slack_summary"]`.
- `IP-P05-D3-3`: Strict decoupling of `torchaudio` and `openai` via `httpx` and stdlib `wave`.

---

## 4. Task DAG & Disjoint Ownership

Three implementers running in parallel waves with strictly disjoint file boundaries:
- **T01 (IMPL-1): Core Grammar, Parser, Canonical Printer, Linter, & Lockfile**
  - Scope: S01, S02, S07, S10
  - `owns_paths`: `src/Kodiac_robotics/compiler/{grammar.lark,parser.py,printer.py,lint.py,lock.py}`, `tests/compiler/{test_parser.py,test_printer.py,test_lint.py,test_lock.py}`
- **T02 (IMPL-2): Voice ASR, Spark Compiler, Template Fallback, & Text Compiler**
  - Scope: S03, S04, S08
  - `owns_paths`: `src/Kodiac_robotics/compiler/{asr.py,spark_compile.py,template_fallback.py,text_compile.py,prompts/**}`, `tests/compiler/{test_asr.py,test_spark_compile.py,test_text_compile.py}`, `tests/fixtures/audio/**`
- **T03 (IMPL-3): Keyframe Grounding, Slack Derivation, Demo Self-Test, & CLI Integration**
  - Scope: S05, S06, S09, S11, S12
  - `owns_paths`: `src/Kodiac_robotics/compiler/{typecheck.py,slack.py,selftest.py}`, `src/Kodiac_robotics/cli.py` (`test` subcommand), `tests/compiler/{test_typecheck.py,test_slack.py,test_selftest.py}`, `tests/cli/test_cli_test.py`, `video/tapes/test.tape`

*Execution Flow:* Stage 1 `(T01 || T02)` parallel -> Stage 2 `T03` integrates.

---

## 5. Quantitative Kill Criteria
1. **Round-Trip Idempotency:** `print_green(parse_green("examples/stackcube.green"))` and `examples/stack_blocks.green` must round-trip bit-identically.
2. **Offline Text-Compile:** `Kodiac test --from-text "stack cubeA on cubeB" --first-frame <clip> -o test.green` must execute in < 1.0 s with zero network calls.
3. **Demo Self-Test Determinism:** All golden clips in `tests/fixtures/clips/` must pass self-test with margin >= 2σ.
4. **Physical Sanity Cap Enforcement:** Sloppy demos exceeding upper bounds (`align_xy > 4.0cm` or `gap > 2.0cm`) must be rejected with diagnostic `E005`.
5. **Latency Budget:** Compilation on <= 15 s demo clip must complete in < 12.0 s wall-clock (hard ceiling 15.0 s).
6. **Zero Top-Level Uninstalled Imports:** Test suite must assert zero top-level imports of `torchaudio` or `openai`.
7. **Clean CLI Stream Separation:** Valid `.green` syntax to `stdout` (or `--out`); all progress logs, timers, and warnings to `stderr`.

---

## 6. Deadline Math & Resource Constraints
- **Hours Remaining:** 104.5h to internal submit (92.5h to freeze).
- **Phase P05 Budget:** 16.0h.
- **Estimated Implementer Effort:** T01 (4.5h), T02 (5.0h), T03 (5.5h). Parallel wall-clock: ~5.5h.
- **Post-Integration & Video Take:** 2.0h. Total projected: ~7.5h wall-clock.
- **Safety Margin:** Leaves ~97.0h for Phases P06–P10.
- **Financial Cost:** $0.00 required. $1.60 estimated across free-tier credits for multi-modal evaluation.

---

## 7. Concept Invariant Scan
- **I1 (UNIX composability):** Preserved (`stdout` reserved for `.green`, progress to `stderr`).
- **I2 (Show It Once):** Core deliverable of P05.
- **I6 (Measured, not guessed):** Protected by IP-P05-D1-1 and IP-P05-D3-2 (LLMs never guess numbers).
- **I8 (Proof Validity):** Protected by physical sanity caps preventing loose test poisoning.
- **I10 (Zero-cost offline execution):** Fully delivered via `--from-text` and `--backend fixture`.
- **I15 (Transparent execution mode):** Enforced via mandatory badging for template fallback.
- **Prime Directive Law 1:** Upheld with zero mocked outputs and full honest disclosure.

ANSWER IN EXACTLY THIS FORMAT (it is pasted verbatim into RULING.md):
1. Decision table: | IP | APPROVE / APPROVE-WITH-CHANGES / REJECT / DEFER | rationale ≤2 lines |
2. Final ordered phase plan (≤15 lines) and any reordering of later phases.
3. Required doc updates (file -> what changes).
4. Tripwires and kill criteria (measurable).
5. The single biggest risk you see that the council missed, and what to do about it.
6. What reviewers must scrutinize hardest.
