# RULING: P01  ·  SDM: Gemini 4 Argon @ Antigravity

## 1. Decision Table

| IP | Decision | Rationale |
|---|---|---|
| **IP-P01-D1-1** | **APPROVE** | Standardizes test doubles in `contracts/fixtures.py`, preventing mock drift and ensuring all downstream phases test against valid canonical instances offline. |
| **IP-P01-D1-2** | **APPROVE** | Enforces Invariant I15 and Law 1 at model boundary via 16-hex nonce and non-negative `timings_ms` validation on `RunResult`. |
| **IP-P01-D2-1** | **APPROVE** | Purges redundant `Project Spec/` files from git tracking, guaranteeing clean repository hygiene and professional presentation for hackathon judges. |
| **IP-P01-D2-2** | **APPROVE** | Separates offline core health (exit 0) from online sponsor credentials in `Kodiac doctor`, ensuring frictionless first impressions for judges. |
| **IP-P01-D3-1** | **APPROVE** | Neutralizes credential deadlock while strictly upholding Law 1: unverified smoke runs flag `is_fixture: true` and null latencies with zero fabrication. |
| **IP-P01-D3-2** | **APPROVE** | Isolates host from Windows CUDA compilation failures by enforcing a pure-Python core locally and offloading heavy GPU/sim workloads to Modal. |

---

## 2. Final Ordered Phase Plan & Pipeline Sequencing

```
Stage 0 (ORCH): S00 (scrub `Project Spec/`), S01 (repo init, LICENSE, BUILD_LOG, ATTRIBUTIONS, README), S02 (agent scaffolding), S03 (ADR-0001).
Stage 1 (IMPL-1 · T01):
  - S04: Scaffold `Kodiac-robotics` with Python >=3.12 via `uv`; enforce pure-Python torch-free core.
  - S05: Implement canonical `contracts/core.py` (ARCHITECTURE.md §4), `contracts/fixtures.py`, schema export, serialization tests; tag `contracts-v1`.
  - S06: Implement `config.py` (masked .env settings) and `cache.py` (atomic SHA-256 disk cache).
  - S07: Configure `ruff`, `pytest` (markers: slow, live, gpu), and zero-secret GitHub Actions CI.
Stage 2 (Parallel · IMPL-2 ∥ IMPL-3 once Stage 1 `uv sync` is green):
  - IMPL-2 (T02): S08 (`Kodiac doctor` two-table Rich UX, exits 0 offline), S09–S10 (smoke tests ST1–ST13 dual-mode, ≤50 frames/clip).
  - IMPL-3 (T03): S11 (SDM CLI harness, ADR-0002), S12 (`modal/hello_*.py` with `scaledown_window=0`), S14 (seed features.yaml, VIDEO_NUMBERS.md, fixtures/experiments READMEs).
Stage 3 (ORCH): S13 (`HUMAN_TODO.md` checklist), S15 (Integration merge, local CI green, doctor check, GATE.md, tag `p01-done`).
```
*Pipeline Sequencing:* P02–P10 sequence remains intact. If ST2/ST3 hosted SAM latency exceeds 5.0 s, P03 must branch to Modal-hosted open weights for the fast path.

---

## 3. Required Doc Updates

- **`ARCHITECTURE.md §4`**: Document `is_fixture: bool = False` flag and `nonce: str` (16-hex regex `^[0-9a-f]{16}$`) constraint on `RunResult`.
- **`IMPLEMENTATION_PLAN.md §P01`**: Formalize the two-stage gated DAG (Stage 1 prerequisite for Stage 2) and the 1.0-hour credential SLA fallback.
- **`TOOLS_AND_REQUIREMENTS.md §2`**: Explicitly specify that the local workspace core is pure-Python and torch-free, with all CUDA/sim tasks routed to Modal.
- **`.agents/DECISIONS.md`**: Append `ADR-0001` (Host runtime & agent roles), `ADR-0002` (SDM OpenCode/Antigravity dual channel), and `ADR-0003` (Smoke test dual-mode execution & honesty tagging).

---

## 4. Tripwires and Kill Criteria (Measurable)

1. **Credential SLA Tripwire:** If sponsor keys (`MODEL_API_KEY`, `MODAL_TOKEN_ID`) are absent >1.0 h post-dispatch, switch ST1–ST13 smoke execution to `--mock` fixture mode (`status: "PENDING_KEY"`, `latency_ms: null`, `is_fixture: true`), record `PENDING_HUMAN_CREDENTIALS` in `ADR-0003`, and proceed without idling implementers.
2. **Hosted Perception Latency Tripwire:** If hosted SAM 3.1 50-frame inference latency exceeds 5.0 s during ST2/ST3, P03 must immediately benchmark Modal self-hosted SAM 3.1 container for fast-path perception.
3. **Schema Recursion Timebox:** Recursive `Expr` schema export in S05 is timeboxed to 30 minutes; fall back immediately to flat `CompileDraft` AST schema if recursion issues arise.
4. **Modal Budget Kill Criterion:** All Modal apps must hardcode `scaledown_window=0`; delete hello containers immediately after ST8; abort test runs if un-cached spend exceeds $2.00.
5. **Local Build Timebox:** Any local task attempting native C++/CUDA wheel builds exceeding 15 minutes is terminated immediately and redirected to Modal.

---

## 5. The Single Biggest Risk Missed by Council & Remediation

**The Risk:** Pydantic v2 Recursive Deserialization and JSON Schema Export Failure on Python 3.12.
While the council noted schema export recursion, they overlooked runtime serialization traps in Pydantic v2: self-referential models (`Expr` containing `list[Expr]` referencing `Atom`) frequently encounter forward-reference resolution issues or infinite depth loops during `.model_dump()` / `.model_dump_json()` unless explicitly resolved with `Expr.model_rebuild()` and guarded against cyclic references. If disk caching or smoke test fixture dumping encounters this, the entire test suite crashes.

**Remediation:**
1. Mandate `from __future__ import annotations` at the top of `src/Kodiac_robotics/contracts/core.py`.
2. Explicitly call `Expr.model_rebuild()` immediately after class declarations.
3. Add a mandatory unit test in `tests/unit/contracts/test_core.py` verifying deep serialization/deserialization (≥10 nested levels) and JSON export of `Expr` and `GreenTest` with zero recursion errors.

---

## 6. Notes for Reviewers: What to Scrutinize Hardest

1. **Contract Purity:** Verify that `src/Kodiac_robotics/contracts/core.py` contains zero imports of `torch`, `cv2`, `numpy`, or GPU packages. It must be 100% lightweight, standard library + Pydantic v2.
2. **Anti-Fabrication Enforcement:** Inspect `artifacts/p01/smoke/st*.json`. If credentials were missing, strictly verify that `is_fixture: true`, `live_verified: false`, and `latency_ms: null`. Any hardcoded synthetic benchmark latencies are an immediate S0 gate rejection under Law 1.
3. **Doctor Exit Code & UX:** Run `Kodiac doctor` without any `.env` configured. Confirm it exits cleanly with returncode `0`, rendering healthy local prerequisites and warning-only status for missing cloud keys.
4. **Git Hygiene:** Verify that `git status` shows no remnants of `Project Spec/` duplicates and that `.gitignore` prevents un-curated spec files from entering git history.
