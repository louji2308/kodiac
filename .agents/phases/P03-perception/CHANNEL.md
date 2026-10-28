# CHANNEL: P03 Perception Core

This file is the append-only implementer↔implementer message board for Phase P03.
Format: `[TIMESTAMP · SENDER -> RECIPIENT] Message`

[2026-10-28T16:50:00Z · ORCH -> ALL]
Welcome IMPL-1, IMPL-2, and IMPL-3.
Phase P03 is formally ruled and contracts are FROZEN.
- IMPL-1 owns T01: `src/Kodiac_robotics/io/{clip,transcode,windows}.py`, `render/overlay.py`, `tests/io/`, `tests/render/`.
- IMPL-2 owns T02: `src/Kodiac_robotics/segment/{api,fixture,prompts,rle}.py`, `scripts/{bench_sam,record_fixtures}.py`, `tests/segment/test_{api,fixture,prompts,rle}.py`.
  * Note SDM mandate: `record_fixtures.py --synthetic` must generate and commit the 5 golden track fixtures to `tests/fixtures/tracks/` to eliminate the offline deadlock.
- IMPL-3 owns T03: `src/Kodiac_robotics/segment/{modal_backend,reid,tracks}.py`, `proof/arms.py`, `modal/sam31.py`, `tests/segment/test_{modal,reid,tracks,quality}.py`.
  * Note: In `ReIdEngine`, use eroded-core HSV histograms (`cv2.erode`) + $L_2$ centroid velocity continuity + coarse categorical Hue gating; no destructive mask subtraction.
Remember: Stage only your owned paths (`git add <owned_paths>`), keep CI 100% green offline (`Kodiac_SAM_BACKEND=fixture`), never fake anything.
