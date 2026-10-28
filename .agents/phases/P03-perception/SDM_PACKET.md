# SDM PACKET: Phase P03 Perception Core (SAM 3.1)

- **Date:** 2026-10-28T16:20:00Z
- **Phase:** P03 Perception Core
- **Target Deadline:** Feature freeze Nov 4 04:59 UTC (~169.2 h remaining)
- **Council Status:** Unanimous APPROVE across D1 Architect, D2 Judge Advocate, D3 Red Team (Confidence: 95/100)
- **Escalation Reason:** Formal ruling on **ADR-0008** (KD-05 Live Locate Strategy: Two-Stage Bisect vs. Subsampled Full-Clip Pass) per `AGENTS.md §6.1`.

---

## 1. Phase Mission & Context

Deliver a deterministic, zero-dependency spatio-temporal perception core providing 2D object instance masks and tracks with persistent IDs across three interchangeable backends:
1. **Hosted SAM 3.1 Backend:** Streaming client for Meta SAM 3.1 (`POST /v1/responses`).
2. **Modal SAM Backend:** Self-hosted `facebook/sam3.1` on Modal L4 (`nvidia-l4`, `use_fa3=False`, `torch.bfloat16`).
3. **Deterministic Fixture Backend:** Pre-recorded track JSONs for 5 golden clips in `tests/fixtures/tracks/` guaranteeing 100% offline green CI.

---

## 2. Core Question for SDM: ADR-0008 (KD-05 Live Locate Decision)

How should Kodiac locate the failure onset frame $t^*$ and track objects within the <12s live demo budget?

- **Council Converged Recommendation (ADR-0008):**
  - **Primary Live Fast Path:** **Two-Stage Bisect** (6-keyframe pack for coarse localization + 50-frame backward dense window for causal attribution).
    - *Economic & Narrative Profile:* 100 billed frames ($0.02 cost); preserves Meta SAM 3.1 backward tracking as our hero "time machine" story (video Beat C3).
  - **Empirical Latency Gate:** P03.S07 (`scripts/bench_sam.py`) benchmarks n $\ge 20$ trials. If 6-keyframe bisect + backward window p95 locate latency exceeds **8.0 s**, `ADR-0008` triggers the automatic fallback:
  - **Fallback / Batch Path:** **10 fps Subsampled Single-Pass Forward Locate** (~100 frames in 1 API call, ~3.8 s), reserving backward tracking strictly for final blame refinement. Default to `⚡ CACHED` replays on hosted web demo if network conditions degrade.
- **Council Vote:** Unanimous `APPROVE` (D1, D2, D3).

---

## 3. Improvement Proposals (IPs) & Council Votes

| IP ID | Title & Summary | D1 | D2 | D3 | Verdict |
|---|---|---|---|---|---|
| **IP-P03-D1-1** | *Pure-Python / NumPy Vectorized COCO RLE Codec (`segment/rle.py`).* Eliminates `pycocotools` C-extension compilation failure on Windows/CI. | `APPROVE` | `APPROVE` | `APPROVE` | **ADOPTED** |
| **IP-P03-D1-2** | *Padded Window Range Abstraction (`WindowCut` in `io/windows.py`).* Enforces SAM 3.1 $\ge 50$ frame minimum via symmetric padding. | `APPROVE` | `APPROVE` | `APPROVE` | **ADOPTED** |
| **IP-P03-D1-3** | *HSV-Centroid Hybrid Re-ID Engine (`segment/reid.py`).* Reconciled: eroded-core HSV histograms + $L_2$ centroid continuity + coarse Hue gating; rejects destructive mask subtraction. | `APPROVE` | `APPROVE` | `APPROVE` | **ADOPTED** |
| **IP-P03-D1-4** | *Deterministic Golden Clip JSON Fixtures (`segment/fixture.py`).* Pre-records track annotations for 5 golden clips for 100% offline green CI. | `APPROVE` | `APPROVE` | `APPROVE` | **ADOPTED** |
| **IP-P03-D2-1** | *Walking Skeleton Hero Asset Integration on Real DROID Clip.* Reconciled: runs on `b01` and `HERO-DROID-001`, watermarking `[PROTOTYPE · UNCALIBRATED GEOMETRY]`. | `APPROVE` | `APPROVE` | `APPROVE` | **ADOPTED** |
| **IP-P03-D2-2** | *High-Contrast Visual Styling for `render/overlay.py`.* Reconciled: scoped strictly to perception debug on native resolution; step verdicts deferred to P04. | `APPROVE` | `APPROVE` | `APPROVE` | **ADOPTED** |
| **IP-P03-D3-2** | *Strict Coordinate-Frame Anchor & Box-Local Translation Contract.* Validates `rle_size == (clip.height, clip.width)` via `box_local_to_full_frame_rle`. | `APPROVE` | `APPROVE` | `APPROVE` | **ADOPTED** |
| **IP-P03-D3-3** | *Empirical KD-05 Latency Gate & Subsampled Locate Fallback (`ADR-0008`).* Formalizes ADR-0008 with empirical 8.0s p95 threshold in `bench_sam.py`. | `APPROVE` | `APPROVE` | `APPROVE` | **ESCALATE TO SDM** |
| **IP-P03-D3-5** | *Indelible Fixture Watermarking (`is_fixture: true`).* Mandates `is_fixture: true` metadata and `[FIXTURE REPLAY]` badge per Law 1. | `APPROVE` | `APPROVE` | `APPROVE` | **ADOPTED** |

---

## 4. Converged Task DAG & Disjoint File Ownership

```
Task T01 (IMPL-1: Video IO Core, Windowing & Debug Overlay)
  owns: src/Kodiac_robotics/io/{clip,transcode,windows}.py, render/overlay.py, tests/io/, tests/render/
Task T02 (IMPL-2: Hosted SAM Backend, Fixtures, Prompts, RLE Codec & Benchmark)
  owns: src/Kodiac_robotics/segment/{api,fixture,prompts,rle}.py, scripts/{bench_sam,record_fixtures}.py, tests/segment/test_{api,fixture,prompts,rle}.py
Task T03 (IMPL-3: Modal SAM Backend, Re-ID Engine, Track Assembly & Proof Arms)
  owns: src/Kodiac_robotics/segment/{modal_backend,reid,tracks}.py, proof/arms.py, modal/sam31.py, tests/segment/test_{modal,reid,tracks,quality}.py
ORCH Background Track:
  Modal batch pool tracking (S10), baseline labeling (S11), prereg-v1 check (S12), walking skeleton (S13: scripts/skeleton.py)
```

---

## 5. Invariant & Law 1 Checks
- **Law 1 (Never fake anything):** All synthetic fixtures declare `is_fixture: true` and burn `[FIXTURE REPLAY]`. S13 walking skeleton prototype burns `[PROTOTYPE · UNCALIBRATED GEOMETRY]`. P02 candidate preview mock status disclosed in `artifacts/p02/hero_candidates/index.md`.
- **Invariant I4 (Exact onset $t^*$, measured physical cause):** Preserved via SAM backward dense tracking.
- **Invariant I8 (Pre-registration boundary):** `prereg-v1` tag verified before S11 baseline labels are analyzed.
- **Invariant I14 (SAM 3.1 load-bearing):** SAM 3.1 serves as the primary measuring instrument.

---

## 6. Request to SDM
1. **Rule on ADR-0008:** Confirm Two-Stage Bisect as the primary live fast path with empirical 8.0s p95 gating against 10 fps subsampled pass.
2. **Authorize Phase P03 Plan & Task Dispatch:** Ratify task cards T01, T02, and T03 for parallel implementation.
