You are the Senior Decision Maker for team Kodiac (Meta Global AI Developer Hackathon 2026). Three decision makers (Architect, Judge Advocate, Red Team) have deliberated on Phase P02: Data & Simulation Foundation and send you their converged plan, improvement proposals, and disagreements.
You are the final technical authority for this phase. Think deeply and independently. Do not rubber-stamp. Your job is to find the move that maximizes the probability of winning while keeping every claim true and the demo robust.

NON-NEGOTIABLE: You may not alter the Concept Invariants in IDEA.md §0. You may not approve anything that costs money or acts publicly.

PACKET:
# SDM PACKET: Phase P02 Data & Simulation Foundation

- **Phase:** P02 Data & Simulation Foundation
- **Hours to internal deadline:** ~174.0 h (Nov 4 17:00 UTC)
- **Budget remaining:** $150 Meta credit (pending claim), $100 Modal credit (pending claim)
- **Council alignment:** Unanimous (D1 Architect, D2 Judge Advocate, D3 Red Team) · Zero open disagreements.

## 1. Phase Goal
Establish the physical simulation and real-robot data backbone:
1. Panda `StackCube-v1` harness with `@span` line-level logging and 10 deterministic bug patches (B01–B10).
2. Pre-registration document `experiments/PREREGISTRATION.md` tagged `prereg-v0` before pool generation starts (Invariant I8).
3. 600–1,000 episode practice pool background generator (`proof/pool.py`) launched on Modal L4.
4. LeRobot dataset loader (`io/lerobot.py`), hero-clip discovery tool (`scripts/find_hero_clips.py`), and real-footage labeling tool (`scripts/label_tool.py`).

## 2. Converged Council Plan (Summary)
- **Dual-Backend Sim Protocol:** `KinematicMockEnv` for 100% offline local Windows CPU unit tests and CI (burns `[MOCK SIMULATION · NOT SAPIEN PHYSICS]` header, `is_mock: true`); `ManiSkillEnv` on Modal L4 GPU for real pool rollouts.
- **Fast, Causal Code Spans:** `@span` uses `sys._getframe(1)` with repo-relative normalized paths. `find_blame_span` uses a causal lookback window ($\Delta t \le 1.0$ s) to map physical failure back to the actuation that caused it.
- **Deterministic Bug Benchmarks:** Bug patches B01–B10 assert 10/10 seeds oracle FAIL in CI, protected by a settling velocity check ($v < 0.01$ m/s over 0.5 s dwell) against physics bouncing false-passes.
- **Git-Native Pre-Registration:** Pre-registration tagged `prereg-v0` on git; content hashes (`config_sha256`, `prereg_sha256`) embedded directly in Parquet table metadata. OpenTimestamps is non-blocking human follow-up.
- **Decoupled 3-Task Parallel DAG:**
  - `T01` (IMPL-1): Sim Environment, `@span` Logger, `pick_place.py`, B01–B10 Bugs (S01–S05).
  - `T02` (IMPL-2): Pre-Registration, $\pi_0$ Policy, Proof Pool Generator, Baselines & Appearance Benchmark (S06–S09, S13, S13b, S16).
  - `T03` (IMPL-3): LeRobot Loaders, Hero-Clip Search, Labeling Tool & Fixtures (S10–S12, S14, S15).
  - All three tasks are fully independent, have disjoint `owns_paths`, and dispatch concurrently in Wave 1.

## 3. Improvement Proposals (IPs) Table
| IP | Title | D1 | D2 | D3 | Consensus & Action |
|---|---|---|---|---|---|
| **IP-P02-D1-1** | Dual-Backend Sim Architecture (`ManiSkillEnv` + `KinematicMockEnv`) | APPROVE | APPROVE | APPROVE | **APPROVE:** Full consensus. `KinematicMockEnv` for host CPU with watermarked frames; `ManiSkillEnv` on Modal L4. |
| **IP-P02-D1-2** | Standardized `@span` Schema & Causal-Window Lookup (`find_blame_span`) | APPROVE | APPROVE | APPROVE | **APPROVE:** Full consensus. `sys._getframe(1)`, repo-relative paths, $\Delta t \le 1.0$s causal window. |
| **IP-P02-D1-3** | Sharded Parquet Pool Manifest with Resumable Checkpointing | APPROVE | APPROVE | APPROVE | **APPROVE:** Full consensus. 100-episode shards with embedded prereg content hashes. |
| **IP-P02-D2-1** | Hero-Clip Curation Protocol (Metadata-filtered real robot footage) | APPROVE-WITH-CHANGE | APPROVE | APPROVE-WITH-CHANGE | **APPROVE-WITH-CHANGE:** Metadata filtering on Modal; real teleoperated robot footage only (no sim cold open). |
| **IP-P02-D2-2** | Pre-Registration Git-Native Hash in Parquet Metadata (`ots` non-blocking) | APPROVE-WITH-CHANGE | APPROVE | APPROVE-WITH-CHANGE | **APPROVE-WITH-CHANGE:** Tag `prereg-v0` + content sha256 embedded in Parquet. `ots` non-blocking. |
| **IP-P02-D2-3** | Time-Saved Study Telemetry with Strict Data Partition | APPROVE-WITH-CHANGE | APPROVE | APPROVE-WITH-CHANGE | **APPROVE-WITH-CHANGE:** Blind benchmark slice is plain video only; timing study uses separate audit set. |
| **IP-P02-D3-1** | Dual-Mode Sim Architecture | APPROVE | APPROVE | APPROVE | **APPROVE:** Merged into IP-P02-D1-1. |
| **IP-P02-D3-2** | Mandatory Bug B01–B10 Seeded Determinism Assertion | APPROVE | APPROVE | APPROVE | **APPROVE:** 10/10 seeds oracle FAIL asserted in CI with settling velocity threshold. |
| **IP-P02-D3-3** | Enforce Policy Training Budget Cap on Modal L4 | APPROVE-WITH-CHANGE | APPROVE-WITH-CHANGE | APPROVE | **APPROVE-WITH-CHANGE:** Cap at $\le 12$ GPU-h total ($\le 20$ min/run) with convergence monitoring. |

## 4. Key Evidence & Stack Facts
- Host is Windows 11 AMD64, Python 3.11.9, CPU only. `ffmpeg 8.1` with `libx264` present.
- 29/29 P01 tests pass offline (`uv run --no-sync pytest tests/ -q` in 21.5s).
- Core package stays torch-free (`[sim]` and `[proof]` extras isolated).
- Zero open disagreements.

ANSWER IN EXACTLY THIS FORMAT (it is pasted verbatim into RULING.md):
# RULING: P02  ·  SDM: <Senior Decision Maker>
1. Decision table: | IP | APPROVE / APPROVE-WITH-CHANGES / REJECT / DEFER | rationale ≤2 lines |
2. Final ordered phase plan (≤15 lines) and any reordering of later phases.
3. Required doc updates (file § → what changes).
4. Tripwires and kill criteria (measurable).
5. The single biggest risk you see that the council missed, and what to do about it.
6. What reviewers must scrutinize hardest.
