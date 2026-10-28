# .agents/DECISIONS.md: Architectural Decision Records (ADRs)

All rulings, architectural choices, and deviations are logged here chronologically. Append-only.

---

### ADR-0001 · 2026-10-28 · P01 · Agent Runtime & Execution Stack
- **Context:** Establishing the multi-agent operating environment and subagent invocation model for Kodiac hackathon development.
- **Decision:**
  - **Orchestrator (ORCH):** Antigravity CLI / agent environment on Windows.
  - **Subagents (D1, D2, D3, SDM, IMPL-n, R1, R2):** Invoked via Antigravity native `invoke_subagent` with `Model: 'inherit'` ensuring Gemini 3.8 Flash is used across all spawned subagents without deviation, strictly respecting the user directive.
  - **Workspace Mode:** Direct repository workspace with strict file-ownership partitioning (`owns_paths`) and git staging scoping per task card (`git add <owned_paths>`).
  - **Coordination Protocol:** File-based shared state machine via `.agents/phases/P<NN>-<slug>/` artifacts (`BRIEF.md`, `COUNCIL.md`, `CHANNEL.md`, `RULING.md`, `GATE.md`, `REVIEW.md`).
- **Rationale:** Native subagent execution preserves full context alignment, matches the exact requested model family (Gemini 3.8 Flash), and provides reliable filesystem and terminal tool access.
- **Supersedes:** None.

---

### ADR-0002 · 2026-10-28 · P01 · Senior Decision Maker (SDM) Channel
- **Context:** Establishing the escalation protocol and execution mechanics for the Senior Decision Maker across P01–P10.
- **Decision:**
  - **Option A (Primary CLI):** `opencode run -m deepseek/deepseek-chat` or verified provider flag executing headless with `.agents/prompts/P<NN>-SDM-Ruling.md`.
  - **Option B (Native Antigravity):** Antigravity invocation with Gemini 4 Argon or inherited Gemini 3.8 Flash when headless terminal is active.
  - **Format:** Strict 6-part ruling template (`AGENTS.md §6.3`).
- **Rationale:** Ensures programmatic, auditable, and reproducible technical verdicts without blocking the pipeline.
- **Supersedes:** None.

---

### ADR-0003 · 2026-10-28 · P01 · Smoke Test Dual-Mode Execution & Anti-Fabrication Tagging
- **Context:** Handling day-1 external credential latency (`MODEL_API_KEY`, `MODAL_TOKEN_ID`, etc.) without violating Law 1 ("Never fake anything") or blocking exit gates.
- **Decision:**
  - **Dual-Mode Smoke Execution:** Scripts in `scripts/smoke/st01_models.py` through `st13_sdm.py` support `--live` and auto-mock fallback.
  - **Honesty Invariants:** When sponsor keys are absent, smoke test outputs must strictly write `is_fixture: true`, `live_verified: false`, `latency_ms: null`, and `status: "PENDING_KEY"`.
  - **Zero Fabrication:** Dummy or simulated latencies may never be reported as live benchmark measurements.
  - **SLA Tripwire:** 1.0 hour timeout for live credentials before falling back to mock fixtures to keep task cards unblocked.
- **Rationale:** Strictly upholds Prime Directive Law 1, ensures reproducible local verification, and unblocks Phase P01 exit gate.
- **Supersedes:** None.
