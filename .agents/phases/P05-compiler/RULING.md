# RULING: P05  ·  SDM: Gemini 4 Argon @ Antigravity
**Date:** 2026-10-31T08:30:00Z  
**Phase:** P05 Compiler (`Kodiac test` - "Show It Once")  
**Authority:** Senior Decision Maker (SDM) · Formal Binding Ruling on ADR-0011, ADR-0012, ADR-0013 & P05 Proposals  
**Council Deliberation Status:** Unanimous Consensus (D1: 95/100, D2: 98/100, D3: 96/100; Average: 96.3/100; 0 Open Disagreements)

---

## 1. Decision Table

| IP ID | Decision | Rationale |
|---|:---:|---|
| **IP-P05-D1-1** | **APPROVE** | **Ratified as ADR-0011**. Decouples symbolic topology from metric tolerance fitting. Eliminates LLM threshold hallucination (Invariants I2, I6); physical thresholds derive exclusively from empirical demonstration video measurement in Pass 1. |
| **IP-P05-D3-1** | **APPROVE-WITH-CHANGES** | **Ratified as ADR-0012**. Approved with mandatory Law 1 anti-fabrication badging across AST headers, provenance, lockfiles, and CLI stderr. Must strictly reject unrecognized verbs with `E003`/`E001` rather than emitting bogus pick-and-place ASTs. |
| **IP-P05-D3-2** | **APPROVE** | **Ratified as ADR-0013**. Auto-slack derivation ($\text{margin} \ge 2\sigma$) guarantees valid demonstrations self-test PASS, while hard physical sanity caps (`align_xy <= 4.0cm`, `gap <= 2.0cm`) prevent sloppy demonstrations from poisoning policy training (Invariant I8). |
| **IP-P05-D1-2** | **APPROVE** | Lark grammar disambiguation `pred_arg: param \| IDENT` with post-parse semantic visitor (`compiler/parser.py`) resolves LALR shift/reduce collisions on 1-arg predicates (`lifted(cubeA, min_cm=2.0)`) into clean `E003` diagnostics. |
| **IP-P05-D1-3** | **APPROVE** | Zero-network offline testability supported via `--backend fixture` and stdlib `wave`/`ffmpeg`. |
| **IP-P05-D2-1** | **APPROVE** | Formatting Rule W101 tactile adverbs (`gently`, `firmly`) into `MANUAL("contact force")` routed strictly to `stderr` highlights visual-only sensor honesty while preserving clean UNIX file piping on `stdout`. |
| **IP-P05-D2-2** | **APPROVE** | Auto-detecting committed fixtures under standard `--backend fixture` avoids creating a bespoke `--demo-fixture` flag, eliminating the appearance of a hardcoded demo branch (Prime Directive Law 1). |
| **IP-P05-D2-3** | **APPROVE** | Sequential single-line `time.perf_counter()` checkmark logs (`✓ [1.2s] transcript...`) to `stderr` prove $<12$ s performance without multi-line cursor manipulation bugs on Windows PowerShell. |
| **IP-P05-D2-4** | **APPROVE** | Storing physical slack derivation metrics inside `object_baselines["_slack_summary"]` preserves the frozen `GreenLock` schema without breaking downstream contracts. |
| **IP-P05-D3-3** | **APPROVE** | Strict decoupling of missing dependencies (`torchaudio`, `openai`) via stdlib `wave` duration inspection and `httpx` (0.27.2) for API transport eliminates fatal import crashes in the active environment. |

---

## Formal Architectural Decision Records (ADRs)

### ADR-0011 · 2026-10-31 · P05 · Two-Stage Multi-Modal Compilation Architecture
- **Context:** To satisfy Invariant I2 ("Show It Once") and Concept C3 in the 3-minute video (Beat 0:24–0:50), Kodiac must compile a single demonstration video and spoken instruction into an unassailable `.green` test. If an LLM (Muse Spark) is asked to generate numerical thresholds (`align_xy_cm <= 1.5`, `min_cm = 2.0`), it hallucinates arbitrary numbers from pre-training priors rather than observing what the demonstrator actually achieved. This violates Invariant I6 ("Measured, not guessed") and Invariant I17 ("Every claim backed by a test").
- **Decision:**
  1. *Stage 1 (Symbolic Structure Extraction):* Muse Spark 1.3 is prompted with a strict Pydantic JSON schema restricted to object roles, step sequencing, and predicate names (`on`, `inside`, `near`, `lifted`, `moves_with`, `dwell`, `looks`, `MANUAL`). Spark is strictly forbidden from generating numerical threshold floats; all parameter values are emitted as symbolic placeholders (`value = -1.0`).
  2. *Stage 2 (Empirical Metric Calibration):* The measurement engine (`pipeline/run.py`) executes an unconstrained metric logging run over the demonstration video (Pass 1) to measure empirical physical extrema ($h_{\text{max}}$, $\Delta_{xy}$, $z_{\text{gap}}$, $v_{\text{settle}}$). `compiler/slack.py` populates the AST thresholds from these empirical measurements using certified safety margins ($\text{margin} \ge 2\sigma$).
  3. *Read-Only Verification:* `compiler/selftest.py` executes a read-only verification run on the calibrated test against the demonstration clip, asserting `Verdict == PASS` and `margin >= 2σ`.
- **Rationale:** Strictly separates structural natural language reasoning from empirical computer vision measurement, guaranteeing that physical thresholds are anchored 100% in physical reality.
- **Supersedes:** None.

---

### ADR-0012 · 2026-10-31 · P05 · Deterministic Fallback Compiler with Anti-Fabrication Badging and Verb Gating
- **Context:** Live demo environments, evaluators without `MODEL_API_KEY`, and automated test suites in offline sandboxes must be able to compile tests without network access or LLM timeouts. However, silently replacing an LLM compilation with a hardcoded template violates Prime Directive Law 1 ("Never fake anything"). Furthermore, blindly emitting a standard pick-and-place AST for completely unrelated user inputs produces a bogus test.
- **Decision:**
  1. *Verb Gating & Domain Validation:* `compiler/template_fallback.py` and `compiler/text_compile.py` are strictly gated on recognized robotics manipulation verbs (`pick`, `lift`, `place`, `stack`, `insert`, `let go`, `release`, `dwell`). If input text contains unrecognized or unsupported actions, compilation MUST fail with diagnostic `E003: unsupported manipulation action` or `E001: object not found`, rather than silently defaulting to a pick-and-place AST.
  2. *Mandatory Anti-Fabrication Badging:* Whenever template compilation is engaged:
     - The `.green` header comment MUST contain: `[COMPILER: DETERMINISTIC TEMPLATE FALLBACK · LLM OFFLINE]`.
     - `Step.provenance.source` MUST be set to `"compiler-default"`.
     - `GreenLock.model_ids["compiler"]` MUST be recorded as `"template-fallback"`.
     - The CLI MUST print an amber notice to `stderr`: `⚠ [COMPILER: DETERMINISTIC TEMPLATE FALLBACK · LLM OFFLINE]`.
- **Rationale:** Ensures 100% offline developer quickstart and CI reliability while guaranteeing complete transparency, preventing any misrepresentation of heuristic templates as live model outputs.
- **Supersedes:** None.

---

### ADR-0013 · 2026-10-31 · P05 · Empirical Auto-Slack Derivation with Physical Sanity Caps
- **Context:** Human webcam demonstrations inevitably contain hand jitter, minor wobbles, or slightly off-center placements. If fixed rigid thresholds are applied, valid demonstrations fail their own self-test (`E005`). Conversely, if auto-slack derivation is unbounded, an extremely sloppy human demonstration (e.g. dropping a block from 15 cm or placing it 8 cm off-center) will yield ridiculously loose thresholds (`align_xy_cm <= 9.5`, `gap_cm <= 16.0`). Downstream robot policies evaluated against such a loose test will pass even when dropping objects on the floor, destroying the headline proof ("+Y points of success", Invariant I8).
- **Decision:**
  1. *Statistical Tolerance Fitting:* `compiler/slack.py` derives thresholds using certified safety bounds over the settled demonstration state:
     - `align_xy_cm` = $\max(1.5, \text{round}(\Delta_{xy} + 2.5\sigma, 1))$
     - `gap_cm` = $\max(0.5, \text{round}(z_{\text{gap}} + 2.5\sigma, 1))$
     - `min_cm` = $\max(1.0, \lfloor 0.6 \cdot h_{\text{max}} \rfloor)$
  2. *Hard Physical Sanity Caps (Anti-Poisoning Filter):* Hard upper bounds are enforced on all calibrated thresholds:
     - `align_xy_cm <= 4.0` cm
     - `gap_cm <= 2.0` cm
     - `min_cm <= 8.0` cm
     - `max_speed_cm_s <= 2.5` cm/s
  3. *Rejection of Sloppy Demonstrations:* If empirical demonstration measurements exceed any physical sanity cap, compilation MUST halt immediately with diagnostic `E005: demonstration exceeds physical sanity cap; re-record a valid demonstration`. No test specification or lockfile shall be generated.
- **Rationale:** Guarantees that valid human demonstrations achieve `Verdict == PASS` with $\text{margin} \ge 2\sigma$ by mathematical construction, while strictly preventing sloppy demonstrations from generating degenerate test oracles that poison policy training.
- **Supersedes:** None.

---

## 2. Final Ordered Phase Plan (≤15 lines) & Task List with Owners

```
Wave 1 (Parallel Foundations · Width = 2):
  - T01 (IMPL-1): P05.S01 (Lark grammar & parser per ADR-0011), S02 (Linter E001-E005, W101-W105), S07 (Lockfile generator), S10 (Canonical printer & round-trip tests).
    owns_paths: [src/Kodiac_robotics/compiler/{grammar.lark,parser.py,printer.py,lint.py,lock.py}, tests/compiler/{test_parser.py,test_printer.py,test_lint.py,test_lock.py}]
  - T02 (IMPL-2): P05.S03 (Voice ASR via httpx + stdlib wave), S04 (Muse Spark 1.3 compiler per ADR-0011), S08 (Deterministic template fallback per ADR-0012 & text compile).
    owns_paths: [src/Kodiac_robotics/compiler/{asr.py,spark_compile.py,template_fallback.py,text_compile.py,prompts/**}, tests/compiler/{test_asr.py,test_spark_compile.py,test_text_compile.py}, tests/fixtures/audio/**]
Wave 2 (Integration & CLI · Depends on T01 + T02):
  - T03 (IMPL-3): P05.S05 (SAM 3.1 grounding & embodiment aliasing), S06 (Kinematic metric extraction & slack calibration per ADR-0013), S09 (Demo self-test verifier), S11 (CLI `Kodiac test` subcommand with stderr timers), S12 (Golden fixture verification & VHS tape).
    owns_paths: [src/Kodiac_robotics/compiler/{typecheck.py,slack.py,selftest.py}, src/Kodiac_robotics/cli.py (test subcommand), tests/compiler/{test_typecheck.py,test_slack.py,test_selftest.py}, tests/cli/test_cli_test.py, video/tapes/test.tape]
Later Phase Reordering: None. P05 feeds directly into P06 (`Kodiac blame` + `diff`). Schedule is intact (104.5h to submit, P05 budget 16h / ~7.5h projected).
```

---

## 3. Required Doc Updates

1. **`ARCHITECTURE.md` §6.1, §6.2, §6.3:**
   - Document Lark grammar predicate argument disambiguation (`pred_arg: param | IDENT`) and post-parse semantic visitor arity validation.
   - Document Two-Stage Compiler architecture (`ADR-0011`): Spark compiles symbolic structure only; empirical measurement computes tolerances.
   - Document Template Fallback badging specifications and verb gating (`ADR-0012`).
   - Document Empirical Auto-Slack Fitting and Physical Sanity Caps (`ADR-0013`).
   - Standardize `VoiceTurn` schema and `object_baselines["_slack_summary"]` lockfile format.
2. **`IDEA.md` §0, §4.1:**
   - Reaffirm Invariants I2 ("Show It Once") and I6 ("Measured, not guessed") with the two-stage compiler and mathematical auto-slack formulation.
   - Reaffirm Invariant I16 ("The same test grades human and robot") through canonical `gripper` role normalization.
3. **`IMPLEMENTATION_PLAN.md` §P05:**
   - Update P05.S01–S12 task descriptions, dependencies, and owners matching T01, T02, T03 allocation.
   - Record ADR-0011, ADR-0012, and ADR-0013 citations.
4. **`.agents/DECISIONS.md`:**
   - Append **ADR-0011** (Two-Stage Multi-Modal Compilation Architecture).
   - Append **ADR-0012** (Deterministic Fallback Compiler with Anti-Fabrication Badging).
   - Append **ADR-0013** (Empirical Auto-Slack Derivation with Physical Sanity Caps).
5. **`docs/features.yaml`:**
   - Transition compiler features (F01, F02, F03, F04, F05, F06, F07, F08, F09, F10) to `in_progress`.

---

## 4. Tripwires and Kill Criteria (Measurable)

1. **Golden AST Round-Trip Invariant:** `print_green(parse_green("examples/stackcube.green"))` and `examples/stack_blocks.green` must round-trip bit-identically with 0 AST node divergence and 100% comment/provenance retention. (Tested by T01).
2. **Zero Top-Level Uninstalled Dependencies:** AST import audit in `test_compiler_imports.py` must assert zero top-level imports of `torchaudio` or `openai` across all files in `src/Kodiac_robotics/compiler/`. (Tested by T01/T02).
3. **Pure Structural Output Guarantee:** Unit tests in `test_spark_compile.py` must assert that raw Muse Spark AST output contains `value == -1.0` (symbolic placeholder) for all physical thresholds prior to Pass 2 slack calibration. Any hardcoded float from the LLM fails the build. (Tested by T02).
4. **Deterministic Offline Fallback Execution:** `Kodiac test --from-text "stack cubeA on cubeB" --first-frame <clip> -o test.green` must execute in $< 1.0$ s with zero network calls and produce a valid `.green` test matching the golden AST. (Tested by T02/T03).
5. **Physical Sanity Cap Enforcement (Anti-Poisoning):** If demo measurements exceed physical sanity bounds (`align_xy > 4.0cm` or `gap > 2.0cm`), the compiler MUST raise `E005` and abort without emitting a test file. (Tested by T03).
6. **Demo Self-Test Determinism:** All golden clips in `tests/fixtures/clips/` must pass self-test with $\text{margin} \ge 2\sigma$ and `Verdict == PASS`. (Tested by T03).
7. **Compilation Latency Budget:** End-to-end compilation on $\le 15$ s demonstration video must execute in $< 12.0$ s wall-clock (hard ceiling $15.0$ s). (Tested by T03).
8. **UNIX Composability & Stream Separation:** Automated tests must verify that `stdout` emits valid `.green` syntax when `--out` is omitted, while all progress checkmarks, timers, and warnings route strictly to `stderr`. (Tested by T03).

---

## 5. The Single Biggest Risk You See That the Council Missed, and What to Do About It

### The Risk: Kinematic Phase Collapse in Pass 1 Metric Extraction (Measuring Extrema Across the Wrong Demonstration Window)
- **The Blind Spot:** The Council assumed that Pass 1 metric extraction can run "unconstrained metric logging over the demonstration video measuring extrema: $h_{\text{max}}, \Delta_{xy}, z_{\text{gap}}, v_{\text{settle}}$". However, a demonstration video is not temporally stationary:
  1. At $t=0$, objects rest separately on the table ($\Delta_{xy} \approx 15$ cm).
  2. In mid-clip, the target object is in transit; measuring alignment during transport yields unphysical errors or triggers false sanity cap rejections (`E005`).
  3. Measuring $v_{\text{settle}}$ before release yields hand motion velocity ($\approx 25$ cm/s) rather than resting dwell ($\le 1.0$ cm/s).
  4. Most critically, **human speech-action asynchrony** means spoken instruction timestamps almost never coincide with physical kinematics: demonstrator speech often ends seconds before the physical placement is completed, or describes an action that begins 2 seconds later. If `compiler/slack.py` slices video frames strictly by voice turn timestamps, it samples the wrong physical state.
- **What To Do About It (Mandatory Engineering Directive for IMPL-3 in `compiler/slack.py` & `compiler/typecheck.py`):**
  1. **Kinematic Phase Segmentation (Decoupled from Audio Timestamps):**
     - *Apex Detection (`lifted`):* Detect the trajectory inflection point where target elevation $h(t)$ reaches its global maximum ($h_{\text{max}}$). Measure `lifted.min_cm` relative to initial rest $h(0)$ at this apex.
     - *Settled Terminal Window (`on`, `dwell`):* Detect the terminal placement phase by scanning backward from clip end for the stable kinematic plateau where inter-object lateral distance $\| \Delta XY(t) \|$ stabilizes and target velocity drops below $2.5$ cm/s for $\ge 0.5$ s. Measure settled alignment $\Delta_{xy}$, vertical gap $z_{\text{gap}}$, and stillness velocity $v_{\text{settle}}$ exclusively within this settled terminal window.
  2. **Effector Aliasing Grounding via Embodiment Detection:** In `compiler/typecheck.py`, when grounding the canonical AST role `gripper` on demo frames, invoke `detect_embodiment(clip)` from `segment/prompts.py`. If human embodiment is detected, query `HUMAN_PROMPT_LIBRARY` ("human hand") while maintaining `gripper` as the canonical AST identifier (Invariant I16). This prevents false `E001` "gripper not found" errors on webcam recordings.

---

## 6. What Reviewers Must Scrutinize Hardest

1. **Lark Grammar LALR Shift/Reduce Table:** Verify that `compiler/grammar.lark` uses `pred_arg: param | IDENT` and compiles with zero shift/reduce or reduce/reduce conflicts on both 1-argument (`lifted(cubeA, min_cm=2.0)`) and 2-argument (`on(cubeA, cubeB, align_xy_cm<=1.5)`) predicates.
2. **Two-Pass Decoupling & LLM Number Ban:** Review `compiler/spark_compile.py` to verify that prompt schemas and output parsers strictly forbid numerical parameter values (`value = -1.0`), ensuring all physical numbers derive exclusively from `compiler/slack.py` video measurements.
3. **Law 1 Badging on Template Fallback:** Review `compiler/template_fallback.py` and `compiler/lock.py` to ensure that fallback ASTs visibly declare `[COMPILER: DETERMINISTIC TEMPLATE FALLBACK · LLM OFFLINE]`, set `provenance.source = "compiler-default"`, and record `model_ids["compiler"] = "template-fallback"`.
4. **Physical Sanity Cap Enforcement:** Confirm that unit tests explicitly test out-of-bounds demonstrations (e.g., block dropped from 10 cm, lateral error 5 cm) and verify that compilation halts with diagnostic `E005`.
5. **Stream Separation & Clean UNIX Output:** Inspect `cli.py` to confirm that all progress spinners, elapsed timers, and diagnostics stream to `stderr`, and that `stdout` emits only parseable `.green` text when `--out` is omitted.
6. **Zero Top-Level Uninstalled Imports:** Scrutinize all imports across `src/Kodiac_robotics/compiler/` to verify zero top-level imports of `torchaudio` or `openai`.
