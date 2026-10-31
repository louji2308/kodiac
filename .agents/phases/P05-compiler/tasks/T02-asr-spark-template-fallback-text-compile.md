# T02: Multi-Modal Voice ASR, Spark Compiler, Template Fallback, & Text Compiler
phase: P05 · owner: IMPL-2 · status: TODO
plan_ref: IMPLEMENTATION_PLAN.md P05.S03, P05.S04, P05.S08 · ADR-0011, ADR-0012
depends_on: [] · blocks: [T03]
owns_paths:
  - src/Kodiac_robotics/compiler/asr.py
  - src/Kodiac_robotics/compiler/spark_compile.py
  - src/Kodiac_robotics/compiler/template_fallback.py
  - src/Kodiac_robotics/compiler/text_compile.py
  - src/Kodiac_robotics/compiler/prompts/**
  - tests/compiler/test_asr.py
  - tests/compiler/test_spark_compile.py
  - tests/compiler/test_text_compile.py
  - tests/fixtures/audio/**
reads_only:
  - src/Kodiac_robotics/contracts/core.py
  - ARCHITECTURE.md §6.1–§6.3
  - .agents/phases/P05-compiler/RULING.md
timebox: 180 min (3-strike rule applies)

## Mission
Implement the multi-modal linguistic ingestion layer: transcribe human demo speech via Muse Voice Transcribe 1.0 into typed `VoiceTurn` windows; compile task topology and step sequences via Muse Spark 1.3 (strictly emitting symbolic placeholders `value = -1.0` without hallucinating physical thresholds per ADR-0011); deliver instant offline recovery via deterministic template fallback with mandatory Law 1 anti-fabrication badging (ADR-0012); and deliver 100% offline text-compile mode reproducing `examples/stackcube.green` bit-identically.

## Interface Contract (FROZEN per ARCHITECTURE.md §6.1–§6.3 & RULING.md)
```python
from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, Field
from Kodiac_robotics.contracts.core import GreenTest

class VoiceTurn(BaseModel):
    transcript: str
    t_start: float = Field(..., ge=0.0, description="Start timestamp in seconds")
    t_end: float = Field(..., ge=0.0, description="End timestamp in seconds")
    source: Literal["voice", "text", "fixture", "compiler-default"] = "voice"

# compiler/asr.py
def transcribe_demo_audio(
    audio_path: Path,
    backend: Literal["api", "fixture"] = "fixture",
) -> list[VoiceTurn]:
    """Transcribes audio using Muse Voice API (via httpx) or offline fixtures.
    Uses stdlib wave for duration and metadata. Zero top-level torchaudio imports."""
    ...

# compiler/spark_compile.py
def compile_speech_to_skeleton(
    turns: list[VoiceTurn],
    object_hints: list[str] | None = None,
    backend: Literal["api", "fixture"] = "fixture",
) -> GreenTest:
    """Prompts Muse Spark to compile VoiceTurns into symbolic GreenTest AST.
    STRICT INVARIANT: Physical parameter floats are emitted as placeholder value = -1.0.
    Prompt template stored in compiler/prompts/compile_v1.md."""
    ...

# compiler/template_fallback.py
def template_compile(
    text: str,
    objects: list[str] | None = None,
) -> GreenTest:
    """Deterministic rule-based fallback compiler for robotic primitives
    (pick, lift, place, stack, insert, let go, release, dwell).
    Gated on recognized verbs; unrecognized verbs raise ValueError or E003.
    Applies mandatory Law 1 badging: [COMPILER: DETERMINISTIC TEMPLATE FALLBACK]."""
    ...

# compiler/text_compile.py
def text_compile(
    task: str,
    first_frame_path: Path | None = None,
    profile: str | None = None,
    backend: Literal["api", "fixture", "template"] = "template",
) -> GreenTest:
    """Compiles task description text and keyframe into GreenTest AST.
    Guarantees bit-identical reproduction of examples/stackcube.green when profile='stackcube'."""
    ...
```

## Steps
1. **P05.S03 `src/Kodiac_robotics/compiler/asr.py`:** Implement `transcribe_demo_audio`. Support `backend="api"` via `httpx` POST to Muse Voice endpoint and `backend="fixture"` replaying from `tests/fixtures/audio/`. Extract audio from MP4 using `ffmpeg` subprocess. Parse WAV duration using stdlib `wave`. If turn count != step count, implement proportional word interpolation. Provide synthetic test audio fixture `tests/fixtures/audio/voice_demo.wav`.
2. **P05.S04 `src/Kodiac_robotics/compiler/spark_compile.py`:** Implement `compile_speech_to_skeleton`. Prompt Muse Spark 1.3 with structured JSON schema (`response_format={"type": "json_schema", ...}`). Store master prompt in `src/Kodiac_robotics/compiler/prompts/compile_v1.md`. **Enforce ADR-0011 Invariant:** All metric parameters (`min_cm`, `align_xy_cm`, `gap_cm`, `for_s`) must have `value = -1.0` (symbolic placeholder).
3. **P05.S08 `src/Kodiac_robotics/compiler/template_fallback.py`:** Implement deterministic keyword regex parsing for manipulation primitives (`pick`, `lift`, `place`, `stack`, `insert`, `let go`, `release`, `dwell`). If text contains unrecognized actions, fail cleanly with `E003`. Apply ADR-0012 anti-fabrication badging:
   - Header comment: `[COMPILER: DETERMINISTIC TEMPLATE FALLBACK · LLM OFFLINE]`
   - `provenance.source = "compiler-default"`
   - `model_ids["compiler"] = "template-fallback"`
4. **`src/Kodiac_robotics/compiler/text_compile.py`:** Implement `text_compile(task, first_frame_path, profile)`. When `profile="stackcube"`, generate AST that matches `examples/stackcube.green` bit-identically.
5. **Tests:** Author thorough tests in `tests/compiler/test_asr.py`, `tests/compiler/test_spark_compile.py`, and `tests/compiler/test_text_compile.py`. Assert that Spark AST output has zero hardcoded floats (`value == -1.0`). Assert zero top-level imports of `torchaudio` or `openai`.

## Definition of Done
- [ ] `VoiceTurn` schema strictly validated across all audio functions.
- [ ] Muse Spark compiler emits symbolic AST skeleton with `value == -1.0` for all physical parameters.
- [ ] Template fallback enforces verb gating and applies mandatory Law 1 badging.
- [ ] `text_compile(..., profile="stackcube")` bit-identically reproduces `examples/stackcube.green`.
- [ ] `uv run --no-sync pytest tests/compiler/test_asr.py tests/compiler/test_spark_compile.py tests/compiler/test_text_compile.py -q` passes 100%.
- [ ] Zero uninstalled package imports (`torchaudio`, `openai`).
- [ ] Committed with message `feat(p05/t02): asr client, spark compiler, template fallback, and text compile`.

## Verification Commands
```bash
uv run --no-sync pytest tests/compiler/test_asr.py tests/compiler/test_spark_compile.py tests/compiler/test_text_compile.py -v
uv run --no-sync ruff check src/Kodiac_robotics/compiler/ tests/compiler/
python -c "import src.Kodiac_robotics.compiler.text_compile as tc, src.Kodiac_robotics.compiler.printer as pr; t = tc.text_compile('stack cubeA on cubeB', profile='stackcube'); assert pr.print_green(t).strip() == open('examples/stackcube.green').read().strip()"
```

## Report
*(to be filled by IMPL-2 at DONE)*
