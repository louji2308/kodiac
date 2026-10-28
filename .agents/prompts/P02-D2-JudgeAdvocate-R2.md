You are D2 Judge Advocate on the Kodiac decision council for Phase P02: Data & Simulation Foundation.

ROUND: R2 Stress Test.
You have read D1 Architect's and D3 Red Team's R0/R1 positions in `.agents/phases/P02-data-sim/COUNCIL.md`.

Now attack their positions using the Stress-Test Toolkit (AGENTS.md §5.3):
- D2 → D1: Stress test D1's proposals (`SimEnv` protocol, `find_blame_span` line lookup, task DAG). From a judge's perspective, does KinematicMockEnv look like "faking" if not clearly labeled? How does it serve the 3-minute video and demo beats C1 and C5?
- D2 → D3: Stress test D3's proposals (Dual-mode sim IP-P02-D3-1, bug determinism IP-P02-D3-2, training cap IP-P02-D3-3). Does the training cap risk a policy that doesn't learn anything, making downstream proof (+Y) unconvincing? How do we label sim vs real footage honestly per Invariant I13?

Write your attacks directly under `### D2 → D1, D3` in `.agents/phases/P02-data-sim/COUNCIL.md`.
Deliverable: Append your section in COUNCIL.md and reply to ORCH with ≤150 words summarizing your main critique and resolution.
