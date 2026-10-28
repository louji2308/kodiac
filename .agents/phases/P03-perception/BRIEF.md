# BRIEF: Phase P03 Perception Core (SAM 3.1 Segmentation & Tracking)

- **Phase:** P03
- **Phase Slug:** P03-perception
- **Author:** ORCH
- **Timestamp:** 2026-10-28T14:35:00Z
- **Hours to Deadline:** ~170.5 h (internal submit Nov 4 17:00 UTC)
- **Active Tags:** `contracts-v1`, `p01-done`, `prereg-v0`, `p02-done`

---

## 1. Mission
Deliver reliable 2D instance segmentation masks with persistent, stable object IDs across three interchangeable backends:
1. Hosted Meta SAM 3.1 streaming API (`segment/api.py`),
2. Modal self-hosted SAM 3.1 on L4 GPU (`segment/modal_backend.py`, `modal/sam31.py`),
3. Deterministic fixture replay for 100% offline CI (`segment/fixture.py`).

Implement universal IO core (`io/clip.py`, `io/transcode.py`, `io/windows.py`), frame packing, backward window tracking, re-identification across keyframes and windows, prompt sets with robotic end-effector / gripper aliasing, latency/cost benchmarking (`scripts/bench_sam.py`), and the ORCH walking skeleton prototype (`scripts/skeleton.py`).

## 2. Invariants & Rules (`IDEA.md §0`, `AGENTS.md §4`)
- **Concept Invariant I14:** SAM 3.1 is the measuring instrument (measures pixels, centroids, masks, physical gaps). It measures; it does not compile or judge.
- **Law 1 Compliance (Anti-Fabrication):** Fixture replays must be clearly marked `is_fixture: true` with cached timestamps. Synthetic test tracks must be labeled `is_mock: true`.
- **Latency Budget:** Live locate loop must remain `< 12 s`. SAM window calls and packing must be profiled and optimized.
- **API Prompt Constraint:** **Never send text prompts and object/box prompts in the same API call.** (Meta SAM 3.1 streaming API contract).
- **Offline CI Contract:** All unit/integration tests must pass 100% offline without network or hosted API access (`Kodiac_SAM_BACKEND=fixture`).

## 3. Inputs & Context
- `IMPLEMENTATION_PLAN.md §P03`
- `ARCHITECTURE.md §5.1, §5.2, §5.3, §7, §8`
- `TOOLS_AND_REQUIREMENTS.md §2.1`
- Golden fixtures in `tests/fixtures/clips/` (`manifest.json` with 5 canonical MP4s: `correct_run.mp4`, `b01_early_release.mp4`, `b02_xy_misalignment.mp4`, `b09_lift_failure.mp4`, `occluded_clip.mp4`).
- Candidate hero clips in `artifacts/p02/hero_candidates/`.
- Pre-registration tag `prereg-v0` exists on main.

## 4. Key Questions for Council
1. **Live Locate Strategy (KD-05 decision):** 6-keyframe bisect vs. subsampled full-clip pass (10 fps, <=150 frames) vs. backward tracking window. What is the fastest correct approach within the <12s live budget?
2. **Re-ID & Association Invariants:** How do we guarantee stable object IDs (e.g. distinguishing Cube A red from Cube B green, and gripper fingers) across keyframe probe calls and temporal propagation windows without ID swapping?
3. **Modal vs. Hosted API Fallback:** How do we ensure seamless switching between hosted API and Modal L4 container with identical COCO RLE output format and error handling?
4. **Walking Skeleton Scope (P03.S13):** Minimal end-to-end prototype validating SAM 3.1 masks -> basic `on` + `moves_with` predicate -> blame line -> debug card PNG.
