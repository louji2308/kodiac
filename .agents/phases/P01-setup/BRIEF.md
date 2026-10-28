# BRIEF: P01 Setup & Environment Verification

PHASE P01: Setup & Environment Verification · Hours to internal deadline: 175.5 · Budget left: $150 Meta credit (pending claim), $100 Modal credit (pending claim)

## Why This Phase Matters For Winning
Establishes a clean, compliant engineering foundation, freezes core data contracts (`src/Kodiac_robotics/contracts/core.py`), builds `Kodiac doctor`, defines the smoke-test suite against the Meta + partner stack (SAM 3.1, Muse Spark, Muse Wonder, Voice, ManiSkill3, Modal), and ensures our tooling, CI, and test harness are 100% deterministic, audited against hackathon rules, and ready for high-velocity parallel execution.

## Scope
`IMPLEMENTATION_PLAN.md` P01 (steps S00–S15):
- S00: Public-surface scrub
- S01: Repo init & compliance (`.gitignore`, `LICENSE`, `BUILD_LOG.md`, `ATTRIBUTIONS.md`, `README.md`)
- S02: Agent scaffolding (`STATE.md`, `DECISIONS.md`, `BACKLOG.md`, `LESSONS.md`)
- S03: Runtime ADR (`ADR-0001`)
- S04: Python project scaffold (`pyproject.toml`, `src/Kodiac_robotics/`, package structure)
- S05: Frozen data contracts (`src/Kodiac_robotics/contracts/core.py`, Pydantic models, JSON Schema export, unit tests)
- S06: Configuration & caching (`config.py`, `cache.py`, hash-based caching)
- S07: Tooling & CI (`ruff`, `pytest`, `.github/workflows/ci.yml`)
- S08: `Kodiac doctor` CLI command
- S09: Smoke-test suite ST1–ST13 (`scripts/smoke/`)
- S10: Run smoke tests and record stack facts (`ADR-0003`)
- S11: SDM channel setup (`ADR-0002`)
- S12: Modal foundation & secrets setup
- S13: `HUMAN_TODO.md` checklist
- S14: Doc skeletons (`docs/VIDEO_NUMBERS.md`, `docs/features.yaml`, etc.)
- S15: Gate verification & tag

## Exit Gate
- [ ] `uv run ruff check .` clean; contract tests pass `uv run pytest tests/ -q`.
- [ ] `Kodiac doctor` exits 0 (or provides clean diagnostics without printing secrets).
- [ ] ST1–ST13 smoke test suite defined and runnable.
- [ ] ADR-0001 (runtime), ADR-0002 (SDM channel), ADR-0003 (stack facts) committed.
- [ ] `HUMAN_TODO.md` written and presented to human.
- [ ] Contracts frozen and tagged `contracts-v1`.

## Inputs & Status
- Previous phase: None (Initial phase bootstrap)
- Active blockers: API keys & tokens pending from human (handled via fixture backend & graceful environment checks)
- Background jobs: None

## Constraints
- Concept Invariants (`IDEA.md §0`) are strictly binding.
- Tool policy (`TOOLS_AND_REQUIREMENTS.md §0`): P1 Meta/partners first, P2 free/OSS second, no paid third-party tools.
- Subagent model constraint: All spawned subagents must strictly run Gemini 3.8 Flash (`Model: 'inherit'`).
- Latency budget: Live fast path must target < 12 s p95.

## What Great Looks Like
A fully functional repository with `pyproject.toml`, passing ruff/pytest checks, frozen Pydantic v2 core contracts with roundtrip tests, a working `Kodiac doctor` diagnostic tool, comprehensive smoke tests ST1–ST13, and zero stubs in core interfaces.
