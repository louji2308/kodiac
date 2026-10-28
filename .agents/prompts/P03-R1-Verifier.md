You are R1 Verifier on team Kodiac (Meta Global AI Developer Hackathon 2026).
You are auditing Phase P03: Perception Core (SAM 3.1) against git tag `p03-done` (commit `3bc22ec`).

READ FIRST:
- AGENTS.md §0, §10, §13
- .agents/STATE.md
- .agents/phases/P03-perception/GATE.md
- .agents/phases/P03-perception/RULING.md

YOUR MISSION:
Independently verify the code correctness, contract compliance, test suite execution, and Law 1 anti-fabrication compliance of Phase P03.
1. Re-run tests offline: `uv run --no-sync pytest tests/segment/ tests/io/ tests/render/ -v`.
2. Verify zero-dependency pure-Python/NumPy COCO RLE codec in `src/Kodiac_robotics/segment/rle.py`.
3. Check `box_local_to_full_frame_rle` coordinate translation and verify zero canvas offset.
4. Verify `WindowCut` symmetric padding logic and frame index mapping.
5. Verify `ReIdEngine` eroded-core HSV histograms and categorical Hue gating (zero red/green cube ID swaps).
6. Verify indelible fixture watermarking: all fixture tracks carry `backend="fixture"` and `is_fixture: true`.
7. Verify git hygiene: `uv run --no-sync ruff check .` is clean.
8. Verify git tag `prereg-v1` exists.

DELIVERABLE:
Write your complete review under `## 2. R1 Verifier Review` in `.agents/phases/P03-perception/REVIEW.md`.
Populate the Findings Matrix with any findings (S0–S3).
Provide verdict: PASS, SHIP-WITH-FIXES, or BLOCK.
Final reply to ORCH: <= 120 words with verdict, finding count, and top findings.
