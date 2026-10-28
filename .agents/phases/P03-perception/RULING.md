# RULING: P03 Perception Core · SDM: Gemini 4 Argon @ Antigravity
**Date:** 2026-10-28T16:45:00Z  
**Phase:** P03 Perception Core (SAM 3.1 Segmentation & Tracking)  
**Authority:** Senior Decision Maker (SDM) · Formal Ruling on ADR-0008 & P03 Proposals

---

## 1. Decision Table

| IP ID | Decision | Rationale |
|---|---|---|
| **IP-P03-D1-1** | `APPROVE` | Eliminates fragile `pycocotools` C-extension compilation on Windows/CI; pure-NumPy vectorized RLE codec guarantees 100% offline, cross-platform green CI. |
| **IP-P03-D1-2** | `APPROVE` | Robustly satisfies Meta SAM 3.1 $\ge 50$ frame billing constraint via symmetric padding while preserving exact unpadded query bounds and timestamps. |
| **IP-P03-D1-3** | `APPROVE` | Reconciled design (eroded-core HSV histograms + $L_2$ centroid velocity continuity + coarse Hue gating) prevents cube ID swaps without destructive mask subtraction. |
| **IP-P03-D1-4** | `APPROVE-WITH-CHANGES` | Approved with requirement: `scripts/record_fixtures.py` must support an offline `--synthetic` bootstrap mode to generate fixtures from sim bounds while external keys are pending. |
| **IP-P03-D2-1** | `APPROVE-WITH-CHANGES` | Approved for qualitative tracking verification on `b01` and `HERO-DROID-001`; strictly forbidden from emitting uncalibrated cm metrics; must stamp `[PROTOTYPE · UNCALIBRATED GEOMETRY]`. |
| **IP-P03-D2-2** | `APPROVE` | Correctly scopes `render/overlay.py` to native-resolution mask contours, centroid crosshairs, and bottom anchors in categorical hues, cleanly decoupling P04 step verdicts. |
| **IP-P03-D3-2** | `APPROVE` | Mandates `box_local_to_full_frame_rle` and validates `rle_size == (clip.height, clip.width)`, eliminating catastrophic `(0, 0)` mask canvas placement before P04 predicates. |
| **IP-P03-D3-3** | `APPROVE` | Formally adopts **ADR-0008**: Two-Stage Bisect is primary live path; if S07 benchmark p95 locate $> 8.0$ s, fallback to 10 fps subsampled pass with backward blame refinement. |
| **IP-P03-D3-5** | `APPROVE` | Enforces Law 1 (Anti-Fabrication); mandates `backend="fixture"` and `[FIXTURE REPLAY]` badge; strictly excludes fixture tracks from proof practice pool. |

---

## 2. Final Ordered Phase Plan (<= 15 lines) & Downstream Alignment

1. **T01 (IMPL-1: Video IO & Overlay):** P03.S01 (CFR H.264 normalizer, `WindowCut` padding, keyframe pack) + P03.S09 (native-res categorical overlay renderer).
2. **T02 (IMPL-2: Hosted Backend & Fixtures):** P03.S02 (streaming SAM 3.1 client, prompt isolation) + P03.S04 (fixture backend & dual-mode `--synthetic`/`--live` recorder) + P03.S05 (prompt sets & embodiment aliasing).
3. **T02 Benchmark & ADR-0008:** P03.S07 (`scripts/bench_sam.py` $n \ge 20$ latency/cost benchmark; writes `artifacts/p03/sam_bench.json` and formalizes ADR-0008).
4. **T03 (IMPL-3: Modal Backend & Re-ID):** P03.S03 (self-hosted `facebook/sam3.1` on Modal L4, `use_fa3=False`, 50-frame sliding window cache clearing, batch `track_many`).
5. **T03 (IMPL-3: Track Assembly & Proof Arms):** P03.S06 (hybrid Re-ID, cyclic consistency check) + P03.S08 (quality check vs ManiSkill GT) + P03.S14 (proof arm sets).
6. **ORCH Background Track (BG-A):** P03.S10 (dispatch batch tracking for 1,000 pool episodes on Modal) + P03.S11 (single-pass baseline labelling on calibration split).
7. **ORCH Pre-Registration Check:** P03.S12 (verify git tag `prereg-v1` exists before analyzing any baseline judge labels).
8. **Integration & CI Verification:** Merge T01, T02, T03; assert 100% test pass offline via `pytest` with `Kodiac_SAM_BACKEND=fixture`.
9. **Walking Skeleton S13:** (ORCH) Run `scripts/skeleton.py` on `b01` and `HERO-DROID-001`, burn `[PROTOTYPE · UNCALIBRATED GEOMETRY]`, save PNG cards & terminal take.
10. **P03 Exit Gate & PUSH:** Verify all gate criteria; commit, tag `p03-done`, and trigger parallel Phase P04 Council + Phase P03 Review.
11. **Downstream Phase Alignment:** Zero schedule slip. P04 starts on schedule with frozen perception contracts; BG-A pool tracking unblocks P04.S15 baseline training.

---

## 3. Required Doc Updates

1. **`.agents/DECISIONS.md` §ADR-0008:** Record **ADR-0008 · Live Locate Strategy (KD-05)**: Two-Stage Bisect is the primary live fast path, gated by an empirical 8.0 s p95 threshold in `scripts/bench_sam.py` falling back to 10 fps subsampled locate with backward blame refinement.
2. **`ARCHITECTURE.md` §3.1 & §4.3:** Document perception component tree (`segment/{rle,reid,fixture,prompts,api,modal_backend}.py`) and add the `WindowCut` contract to §4.3.
3. **`IMPLEMENTATION_PLAN.md` §P03:** Update P03.S04 to mandate `--synthetic` fixture bootstrapping, correct P03.S07 to cite ADR-0008, and add the `[PROTOTYPE · UNCALIBRATED GEOMETRY]` banner requirement to P03.S13.
4. **`docs/features.yaml`:** Transition perception feature entries (F14, F15, F16, F28) status from `planned` to `in_progress`.

---

## 4. Tripwires and Kill Criteria

1. **Live Locate Latency Gate (ADR-0008):** In `scripts/bench_sam.py` ($n \ge 20$), if 6-keyframe bisect + 50-frame backward dense window p95 locate time exceeds **8.0 s**, activate the ADR-0008 fallback: live demo fast path switches to 10 fps subsampled single-pass locate (~3.8 s), reserving backward window tracking strictly for final blame refinement. If p95 exceeds **11.5 s**, serve `⚡ CACHED` replays by default on hosted web demo.
2. **Keyframe Packing Tracking Coherence:** In `tests/segment/test_quality.py`, if packed keyframe mask IoU vs. uncompressed native video frame mask is $< 0.70$ on golden clips, abort video-mode frame packing and evaluate keyframes via 1-frame black-divider padding or 10 fps subsampled stream.
3. **Identity Stability & Cyclic Consistency:** If `test_quality.py` detects $> 0$ ID swaps between distinct cubes on StackCube clips, or if backward-vs-forward cyclic IoU $< 0.70$, flag `Track.frames[t].score` as degraded and emit `ReasonCode.OCCLUDED` or `NOT_VISIBLE` in downstream gates.
4. **Modal L4 VRAM & Cost Guard:** If Modal L4 worker VRAM exceeds 18 GB during 150-frame episode tracking, enforce 50-frame chunking with `torch.cuda.empty_cache()`. If container runtime exceeds 180 s per episode or batch spend reaches $25.00 without completion, kill the batch pool job and escalate to human.
5. **Anti-Fabrication & Coordinate Drift:** If `ObjMask.rle_size != (clip.height, clip.width)` on any frame, or if any fixture-generated track lacks `backend="fixture"`, immediate test assertion failure blocks phase exit gate.

---

## 5. The Single Biggest Risk You See that the Council Missed, and What to Do About It

### The Blindspot: The Offline Fixture Deadlock Trap
The council unanimously agreed that `segment/fixture.py` and pre-recorded JSON fixtures (`tests/fixtures/tracks/*.json`) are mandatory to guarantee 100% offline green CI for P03 and all downstream phases. However, the council scheduled `scripts/record_fixtures.py` to record these fixtures exclusively from the live Meta SAM 3.1 API or Modal weights—both of which are currently blocked waiting for external keys (`MODEL_API_KEY` and Modal token are `PENDING_KEY` per `STATE.md`). 

If `record_fixtures.py` only works against the live network API, IMPL-2 cannot record fixtures, `tests/fixtures/tracks/` remains empty, CI fails, and Phase P03 deadlocks before the exit gate.

### What to Do About It (Remedy):
Mandate that `scripts/record_fixtures.py` implement a dual-mode recording architecture:
1. `--live`: Records from live Meta SAM 3.1 API / Modal when credentials are provided.
2. `--synthetic` (Offline Bootstrap Mode): Generates deterministic, geometrically valid `Track` JSON fixtures directly from known simulation ground-truth object bounds or OpenCV color segmentation on the 5 golden clips already present in `tests/fixtures/clips/`.

IMPL-2 must execute `python scripts/record_fixtures.py --synthetic` during Task T02 to commit all 5 track fixtures immediately. This guarantees that `tests/fixtures/tracks/` exists and CI passes 100% offline on clean environments, completely unblocking the Walking Skeleton and exit gate without violating Law 1 (`backend="fixture"` and `is_fixture: true` remain indelible).

---

## 6. What Reviewers Must Scrutinize Hardest

1. **Coordinate Frame Alignment in RLE Translation (`box_local_to_full_frame_rle`):** Verify that box-local masks are correctly translated to the full `(H, W)` frame canvas using exact integer pixel boundaries, and that `assert obj_mask.rle_size == (clip.height, clip.width)` holds across all frames. Verify there is zero `(0, 0)` canvas displacement.
2. **Temporal Window Index Mapping (`WindowCut`):** Verify that symmetric padding to $\ge 50$ frames does not alter the original frame indices in `ObjMask.frame`, and that unpadded timestamps match native clip time $t$ exactly.
3. **Law 1 Compliance in S13 Walking Skeleton:** Verify that any card generated by `scripts/skeleton.py` contains the indelible watermark `[PROTOTYPE · UNCALIBRATED GEOMETRY]` and does not output fabricated metric measurements (cm) on DROID footage before P04 geometry calibration exists.
4. **Offline Isolation & Fixture Watermarking:** Run `pytest tests/` with `Kodiac_SAM_BACKEND=fixture` with network disconnected; verify that zero tests attempt outbound network requests, and all fixture tracks carry `backend="fixture"`.
