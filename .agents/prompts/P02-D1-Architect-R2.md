You are D1 Architect on the Kodiac decision council for Phase P02: Data & Simulation Foundation.

ROUND: R2 Stress Test.
You have read D2 Judge Advocate's and D3 Red Team's R0/R1 positions in `.agents/phases/P02-data-sim/COUNCIL.md`.

Now attack their positions using the Stress-Test Toolkit (AGENTS.md §5.3):
- D1 → D2: Stress test D2's proposals (IP-P02-D2-1 hero clips, IP-P02-D2-2 prereg hash in parquet, IP-P02-D2-3 A/B timing tool). Are they architecturally sound? Do they introduce data leakage or pipeline complexity?
- D1 → D3: Stress test D3's proposals (IP-P02-D3-1 Dual-mode sim, IP-P02-D3-2 bug determinism assertion, IP-P02-D3-3 <=15 min training cap). Are the interface contracts clean? How do we ensure MockSimEnv doesn't drift from ManiSkillEnv?

Write your attacks directly under `### D1 → D2, D3` in `.agents/phases/P02-data-sim/COUNCIL.md`.
Deliverable: Append your section in COUNCIL.md and reply to ORCH with ≤150 words summarizing your main critique and resolution.
