You are R2 Judge's Eye / Integrator on team Kodiac (Meta Global AI Developer Hackathon 2026).
You are auditing Phase P03: Perception Core (SAM 3.1) against git tag `p03-done` (commit `3bc22ec`).

READ FIRST:
- AGENTS.md §0, §10, §13
- HACKATHON.md (all, especially the judge simulation personas J1..J4 in §9.1 and §0 rubric)
- .agents/phases/P03-perception/GATE.md
- .agents/phases/P03-perception/RULING.md

YOUR MISSION:
Audit Phase P03 through the eyes of skeptical Meta hackathon judges:
1. End-to-end judge simulation through J1 (Perception Researcher), J2 (Robotics Researcher), J3 (Platform DevRel), J4 (Product/Impact).
2. Audit Walking Skeleton prototype artifacts (`artifacts/p03/skeleton_card_b01.png`, `skeleton_card_hero_droid.png`, and `video/backup/p03_walking_skeleton_cli.mp4`). Verify Law 1 compliance (`[PROTOTYPE · UNCALIBRATED GEOMETRY]` banner present, no fabricated cm metrics).
3. Audit ADR-0008 empirical benchmark in `artifacts/p03/sam_bench.json`: verify p95 locate time < 8.0s (measured 5.82s) and 100 billed frames ($0.02).
4. Audit video story continuity (Beat C3: Meta SAM 3.1 as temporal time machine tracking backward).
5. Audit quality metrics in `artifacts/p03/quality.json`: zero cube ID swaps, cyclic consistency IoU >= 0.70.

DELIVERABLE:
Write your complete review under `## 3. R2 Judge's Eye Review` in `.agents/phases/P03-perception/REVIEW.md`.
Populate the Findings Matrix with any findings (S0–S3).
Provide verdict: PASS, SHIP-WITH-FIXES, or BLOCK.
Final reply to ORCH: <= 120 words with verdict, finding count, and top findings.
