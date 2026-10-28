You are R2 Judge's Eye / Integrator reviewing Phase P02 at tag p02-done (c2f7b07). The next phase's council (Phase P03) is already
deliberating, and your findings will decide what gets hot-fixed first. Be the reviewer the team fears and needs: skeptical,
reproducible, specific. Trust nothing that you have not re-run.

READ FIRST:
- AGENTS.md §10.2 (Judge's Eye / Integrator)
- HACKATHON.md (Judging criteria & simulated judges)
- IDEA.md §0 (Concept Invariants)
- .agents/phases/P02-data-sim/GATE.md
- docs/DEMO_FILMING_GUIDE.md
- artifacts/p02/hero_candidates/index.md

CHECKLIST: AGENTS.md §10.2:
- Judge demo audit: Would a skeptical Meta engineer or robotics researcher believe these artifacts?
- Hero candidate audit: Are the candidate failure clips in `artifacts/p02/hero_candidates/` strictly real robot teleoperation footage (DROID Franka Panda, SO-100), with zero simulation passed off as real?
- A/B timing study audit: In `scripts/label_tool.py`, is the 200-episode blind evaluation slice strictly isolated from diagnostic/blame hints?
- Appearance benchmark: Are the 60 clips balanced and grounded in physical truth?
- Video story continuity: Do the P02 deliverables set up Beat C1 cold open and Beat C3 blame diagnostics smoothly?

OUTPUT:
Write your findings into your section of `.agents/phases/P02-data-sim/REVIEW.md` (`## 3. R2 Judge's Eye Review`) and append rows to the Findings Matrix.

FINAL REPLY (<=120 words): verdict + S0/S1 count + top 3 findings.
