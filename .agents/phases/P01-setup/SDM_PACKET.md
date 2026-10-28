# SDM PACKET: Phase P01 Setup & Environment Verification

## 1. Phase Mission & Stakes
Phase P01 establishes the foundational engineering infrastructure for Kodiac: a clean Apache-2.0 repository compliant with the Meta Global AI Developer Hackathon (Indie Track), frozen Pydantic v2 core contracts matching `ARCHITECTURE.md §4`, hash-based caching, `Kodiac doctor` diagnostics, non-blocking smoke suite ST1–ST13 with mock fixture support, and verified SDM and Modal integration paths. Total hours to deadline: 175.5 hours.

## 2. Key Evidence Gathered
- **Runtime Environment:** Windows host with Python 3.11.9 (`cpython-3.12.13` available via `uv`), `uv` 0.12.3, `ffmpeg` 8.1 (with libx264/libx265), and `opencode` 1.18.20 operational. First git commit dated 2026-10-28 (compliant with Rule R1 ≥ Oct 26).
- **Hardware Constraint:** No local NVIDIA GPU on host PATH (`nvidia-smi` missing). Architecture deduction: all CUDA/sim workloads (ManiSkill, SAM 3.1 batch tracking) must run remotely on Modal. Local core must remain lightweight, pure-Python, and torch-free for zero-friction judge installation.
- **Credential State:** Sponsor keys (`MODEL_API_KEY`, `MODAL_TOKEN_ID`, `HF_TOKEN`, `BASETEN_API_KEY`) are currently unset.
- **Repository Hygiene:** Duplicate specification files in `Project Spec/` must be untracked during S00 scrub.

## 3. Converged Plan (Two-Stage Gated DAG)
- **Stage 0 (ORCH):** S00 (public scrub of `Project Spec/` and lineage terms check), S01 (repo init, `.gitignore`, Apache-2.0 `LICENSE`, `BUILD_LOG.md`, `ATTRIBUTIONS.md`, `README.md`), S02 (agent scaffolding), S03 (`ADR-0001` runtime).
- **Stage 1 (IMPL-1 · T01):** S04 (scaffold `Kodiac-robotics` with Python 3.12 via `uv`), S05 (freeze `src/Kodiac_robotics/contracts/core.py` verbatim from `ARCHITECTURE.md §4`, add `contracts/fixtures.py`, JSON schema export, unit tests, tag `contracts-v1`), S06 (`config.py` from `.env`, atomic SHA-256 disk `cache.py`), S07 (`ruff`, `pytest`, secret-free CI).
- **Stage 2 (Parallel · IMPL-2 ∥ IMPL-3):** Once Stage 1 `uv sync` succeeds:
  - **IMPL-2 (T02):** S08 (`Kodiac doctor` two-table Rich UX exiting 0 on healthy offline core), S09–S10 (smoke tests ST1–ST13 with honest dual-mode execution: live when keys exist, mock fixture outputting `status: "PENDING_KEY"`, `latency_ms: null`, `is_fixture: true` when absent; ≤50 frames per clip).
  - **IMPL-3 (T03):** S11 (SDM test harness, `ADR-0002`), S12 (Modal app definitions with `scaledown_window=0`), S14 (seed `docs/features.yaml` F01–F60 matrix, `docs/VIDEO_NUMBERS.md`, `tests/fixtures/README.md`, `experiments/README.md`).
- **Stage 3 (ORCH):** S13 (`HUMAN_TODO.md` delivery), S15 (Integration merge, local CI verification, `Kodiac doctor` check, `GATE.md`, tag `p01-done`).

## 4. Improvement Proposals & Votes

| IP | Title | D1 | D2 | D3 | Impact | Cost |
|---|---|:---:|:---:|:---:|---|---|
| **IP-P01-D1-1** | Contract Synthetic Fixtures (`contracts/fixtures.py`) | APPROVE | APPROVE | APPROVE | Standardizes test doubles, avoids mock drift | 0.5 h |
| **IP-P01-D1-2** | Strict Nonce & Timings Validation on `RunResult` | APPROVE | APPROVE | APPROVE | Enforces Invariant I15 auditability | 0.25 h |
| **IP-P01-D2-1** | Public-Surface Scrub (`Project Spec/` purge) | APPROVE | APPROVE | APPROVE | Pristine repo hygiene for judges | 0.25 h |
| **IP-P01-D2-2** | Two-Table Rich `Kodiac doctor` UX | APPROVE | APPROVE | APPROVE | Zero-error fresh onboarding, exits 0 offline | 0.5 h |
| **IP-P01-D3-1** | Honest Dual-Mode Smoke Suite (`is_fixture: true`) | APPROVE | APPROVE | APPROVE | Non-blocking gate, bans fake latencies | 0.5 h |
| **IP-P01-D3-2** | Windows Host Isolation & Modal GPU Partitioning | APPROVE | APPROVE | APPROVE | Prevents Windows CUDA compile failures | 0.25 h |

## 5. Disagreements & Compromises
Zero open disagreements. D1, D2, and D3 reached unanimous consensus:
- Ad-hoc contract models (`BlameReport`, `PredicateResult`) were rejected in favor of strict `ARCHITECTURE.md §4` canonical models (`Verdict`, `FactTable`, `Blame`, `RunResult`).
- Credential wait SLA was slashed from 12 hours to 1.0 hour, falling back to mock fixtures to prevent idling.
- Packaging race conditions were resolved by gating Stage 2 (T02 ∥ T03) on Stage 1 (T01) `uv sync`.

## 6. Tripwires & Kill Criteria
1. Credential SLA: 1.0 hour wait max before generating mock smoke artifacts with `status: "PENDING_KEY"`.
2. Latency Tripwire: Hosted SAM 3.1 50-frame latency > 5.0 s triggers evaluation of Modal self-hosted SAM for fast path.
3. Recursion Timebox: 30 minutes max for AST schema export; fall back to flat `CompileDraft` if recursive export fails.
4. Modal Compute Guard: Hardcode `scaledown_window=0`; delete test containers immediately; abort if un-cached spend > $2.00.
5. Windows CUDA Guard: Any local CUDA build taking >15 minutes is terminated and shifted to Modal.

## 7. Concept Invariants Status
All Concept Invariants (I1–I17) in `IDEA.md §0` remain 100% intact and uncompromised.
