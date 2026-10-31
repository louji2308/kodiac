# T01: Grammar, Parser, Canonical Printer, Linter, & Lockfile
phase: P05 · owner: IMPL-1 · status: TODO
plan_ref: IMPLEMENTATION_PLAN.md P05.S01, P05.S02, P05.S07, P05.S10 · ADR-0011, ADR-0012, ADR-0013
depends_on: [] · blocks: [T03]
owns_paths:
  - src/Kodiac_robotics/compiler/grammar.lark
  - src/Kodiac_robotics/compiler/parser.py
  - src/Kodiac_robotics/compiler/printer.py
  - src/Kodiac_robotics/compiler/lint.py
  - src/Kodiac_robotics/compiler/lock.py
  - tests/compiler/test_parser.py
  - tests/compiler/test_printer.py
  - tests/compiler/test_lint.py
  - tests/compiler/test_lock.py
reads_only:
  - src/Kodiac_robotics/contracts/core.py
  - ARCHITECTURE.md §6.1–§6.3
  - .agents/phases/P05-compiler/RULING.md
timebox: 180 min (3-strike rule applies)

## Mission
Author the normative `.green` language parser, canonical printer, compile-time linter, and cryptographic lockfile generator. Delivers bit-identical round-trip identity for `examples/stackcube.green` and `examples/stack_blocks.green` with unambiguous Lark EBNF parsing and honest diagnostic enforcement (E001–E005, W101–W105).

## Interface Contract (FROZEN per ARCHITECTURE.md §6.1–§6.3 & RULING.md)
```python
from pathlib import Path
from typing import Any, Literal
from Kodiac_robotics.contracts.core import GreenTest, GreenLock, Diagnostic, RunResult
from Kodiac_robotics.segment.video import Clip

# compiler/parser.py
def parse_green(text_or_path: str | Path) -> GreenTest:
    """Parses .green text or path into GreenTest AST using Lark grammar.
    Normalizes Unicode en-dashes (–) and hyphens (-) in timestamps.
    Raises LarkError on syntax failure with line/col diagnostics."""
    ...

# compiler/printer.py
def print_green(test: GreenTest) -> str:
    """Serializes GreenTest AST back into canonical 4-line .green text.
    Must satisfy round-trip idempotency: parse_green(print_green(t)) == t."""
    ...

# compiler/lint.py
def lint_green(
    test: GreenTest,
    context: dict[str, Any] | None = None,
) -> list[Diagnostic]:
    """Validates AST against diagnostic rules:
    - Errors: E001 (object not found), E002 (ambiguous object), E003 (type mismatch/invalid role),
              E004 (comparator against parameter direction), E005 (demo fails own test).
    - Warnings: W101 (non-visual keyword -> MANUAL(...)), W102 (step without provenance),
                W103 (demo margin < 2σ), W104 (depth-critical on Tier C), W105 (or used)."""
    ...

# compiler/lock.py
def generate_lockfile(
    test: GreenTest,
    test_path: Path,
    clip: Clip,
    demo_run: RunResult,
    model_ids: dict[str, str],
    slack_summary: dict[str, Any] | None = None,
) -> GreenLock:
    """Generates GreenLock sidecar JSON with test sha256, transcript turns, object baselines,
    demo events, geometry tier, model versions, and timestamp.
    Stores slack_summary under object_baselines['_slack_summary'] to preserve frozen GreenLock schema."""
    ...
```

## Steps
1. **P05.S01 `src/Kodiac_robotics/compiler/grammar.lark`:** Author EBNF grammar per `ARCHITECTURE.md §6.1`. Use `predicate: PRED "(" pred_arg ("," pred_arg)* ")"` with `pred_arg: param | IDENT` to prevent LALR shift/reduce collisions on 1-arg predicates (`lifted(cubeA, min_cm=2.0)`). Support both flat and indented step syntax.
2. **`src/Kodiac_robotics/compiler/parser.py`:** Pre-process timestamps (normalize `–` to `-`), build Lark parser (LALR with Earley fallback), transform tree to `GreenTest` AST. Implement post-parse semantic visitor to validate arity (`lifted` has 1 object, `on` has 2) and parameter directions, producing `Diagnostic(code="E003"|"E004", ...)`.
3. **`src/Kodiac_robotics/compiler/printer.py`:** Canonical serializer emitting clean 4-line `.green` files: header comment, objects declaration, and sequential numbered steps with comments and provenance quotes.
4. **P05.S02 `src/Kodiac_robotics/compiler/lint.py`:** Implement linter for E001–E005 and W101–W105. Implement non-visual tactile keyword ontology: `"gently"`, `"firmly"`, `"force"`, `"torque"`, `"weight"`, `"slam"`, `"temperature"`, `"sound"`, `"current"` -> flag W101 and recommend `MANUAL(...)`.
5. **P05.S07 `src/Kodiac_robotics/compiler/lock.py`:** Generate `<name>.green.lock`. Calculate SHA-256 hash of canonical test text. Store `slack_summary` in `object_baselines["_slack_summary"]`.
6. **Tests:** Author thorough tests in `tests/compiler/test_parser.py`, `tests/compiler/test_printer.py`, `tests/compiler/test_lint.py`, and `tests/compiler/test_lock.py`. Assert golden identity: `print_green(parse_green(open("examples/stackcube.green").read())) == open("examples/stackcube.green").read()`. Assert zero top-level imports of `torchaudio` or `openai`.

## Definition of Done
- [ ] Golden round-trip identity on `examples/stackcube.green` and `examples/stack_blocks.green`.
- [ ] Linter correctly detects E001–E005 and W101–W105 with structured `Diagnostic` instances.
- [ ] `generate_lockfile` produces valid `GreenLock` matching frozen Pydantic schema in `contracts/core.py`.
- [ ] `uv run --no-sync pytest tests/compiler/test_parser.py tests/compiler/test_printer.py tests/compiler/test_lint.py tests/compiler/test_lock.py -q` passes 100%.
- [ ] Zero uninstalled package imports (`torchaudio`, `openai`).
- [ ] Committed with message `feat(p05/t01): grammar, parser, canonical printer, linter and lockfile`.

## Verification Commands
```bash
uv run --no-sync pytest tests/compiler/test_parser.py tests/compiler/test_printer.py tests/compiler/test_lint.py tests/compiler/test_lock.py -v
uv run --no-sync ruff check src/Kodiac_robotics/compiler/ tests/compiler/
python -c "import src.Kodiac_robotics.compiler.parser as p, src.Kodiac_robotics.compiler.printer as pr; t = p.parse_green('examples/stackcube.green'); assert pr.print_green(t).strip() == open('examples/stackcube.green').read().strip()"
```

## Report
*(to be filled by IMPL-1 at DONE)*
