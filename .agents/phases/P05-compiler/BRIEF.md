# BRIEF: Phase P05 `Kodiac test` Compiler (Show It Once)

```yaml
phase: P05
phase_slug: P05-compiler
hours_to_freeze: 93.0
hours_to_submit: 105.0
budget_left:
  meta_credits: $0
  modal_credits: $30
  gpu_hours: free tier
```

---

## 1. Why This Phase Matters for Winning
- **The Core Capability:** "Show it once" (Invariant I2). Beat 0:24–0:50 of the 3-minute video: A human records a demonstration video and speaks intent ("stack the red cube onto the green cube"), and Kodiac compiles it into a permanent, verifiable test specification (`.green` + `.green.lock`).
- **Judging Alignment:** Drives criteria **Pushing the Frontier** (novel formulation of robot validation from multimodality) and **Ecosystem Impact** (robots can finally have deterministic unit tests generated in seconds).
- **Meta Technology Integration:** Load-bearing Muse Voice (transcription & clause anchoring) + Muse Spark (Llama-based compilation & structure extraction) + SAM 3.1 (demo keyframe grounding & baseline measurement).

---

## 2. Scope & Target Steps
- **P05.S01 ⚡ Grammar, Parser, & Canonical Printer:**
  - `src/Kodiac_robotics/compiler/grammar.lark`
  - `src/Kodiac_robotics/compiler/parser.py`
  - `src/Kodiac_robotics/compiler/printer.py`
  - Canonical 4-line printer, round-trip AST serialization, golden test (`examples/stackcube.green` parses verbatim).
- **P05.S02 ⚡ Linter (Rules E001–E005, W101–W105):**
  - `src/Kodiac_robotics/compiler/lint.py`
  - Detects non-visual keywords (force, torque, gently, current), unmatched comparators, missing baselines, duplicate step identifiers.
- **P05.S03 ⚡ Voice ASR Client (Muse Voice & Offline Fixture):**
  - `src/Kodiac_robotics/compiler/asr.py`
  - One-shot transcription, turn timestamping, WAV extraction via ffmpeg, cached fixtures for offline execution.
- **P05.S04 Spark Compiler (Muse Spark Structured Output):**
  - `src/Kodiac_robotics/compiler/spark_compile.py`
  - Pydantic structured output compiling natural language into `GreenTest` AST skeleton with typed object roles and step sequencing.
- **P05.S05 Object Typecheck & Grounding Baselines:**
  - `src/Kodiac_robotics/compiler/typecheck.py`
  - 2D SAM 3.1 keyframe verification on demo video, effector aliasing, initial area $A_0$, scale $k_0$, container rim fit.
- **P05.S06 Self-Test & Threshold Derivation:**
  - `src/Kodiac_robotics/compiler/slack.py`
  - `src/Kodiac_robotics/compiler/selftest.py`
  - Full measurement engine run on demo clip $\to$ extracts empirical physical margins $\to$ derives thresholds with certified slack ($\text{margin} \ge 2\sigma$) $\to$ asserts self-test `PASS`.
- **P05.S07 CLI Integration & Lockfile Generation:**
  - `src/Kodiac_robotics/compiler/lock.py`
  - `src/Kodiac_robotics/cli.py` (`Kodiac test` subcommand)
  - Emits cryptographic lockfile `.green.lock` with clip SHA-256, model IDs, bounding boxes, and timestamp bounds.

---

## 3. Exit Gate (P05)
1. **Golden Grammar Test:** Golden spec parses and prints bit-identically (`examples/stackcube.green`).
2. **Linter Test Suite:** E001–E005 and W101–W105 all fire on broken examples; clean specs emit 0 warnings.
3. **Voice Compile Pipeline:** Voice demo (`examples/voice_demo.wav` or text) + `tests/fixtures/clips/correct_run.mp4` produces `stackcube.green` matching golden AST structure.
4. **Offline CLI Test:** `Kodiac test --text "stack the red cube on the green cube" tests/fixtures/clips/correct_run.mp4 -o test.green` executes 100% offline with zero network tokens, generating `test.green` and `test.green.lock`.
5. **Self-Test Validation:** Compiled spec runs on the demonstration clip itself and returns `Verdict.PASS` with margin $\ge 2\sigma$.

---

## 4. Inputs & Status
- **Review(P04):** Reviewers R1 & R2 dispatched in parallel. P04 exit gate is PASS (224/224 green tests, 0 lint errors, BA=1.0, Cov=1.0, 0 False-PASS).
- **Background Jobs:** BG-A (pool tracking & baseline training) running.
- **Frozen Contracts:** `contracts/core.py` (GreenTest, Step, Atom, Expr, Lockfile, Provenance).

---

## 5. Constraints
- **Invariants (IDEA §0):**
  - I1: UNIX composable CLI (`Kodiac test` generates `.green` + `.green.lock`).
  - I2: Show It Once. No hand-tuning thresholds or YAML authoring.
  - I10: Zero-cost offline execution mode (`--text` or fixture backend).
  - I12: 100% software, no physical robot required to compile or verify.
- **Latency Budget:** Full compile pipeline on demo clip $< 12$ seconds.
