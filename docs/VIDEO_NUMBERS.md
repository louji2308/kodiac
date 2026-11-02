# VIDEO_NUMBERS.md: Registered Numbers for Presentation & Video Assets

> **Strict Honesty Rule:** Every number displayed in the 3-minute video, README, or presentation must be registered in this table with its calculating artifact and git commit sha before recording. Unregistered numbers are banned.

| Item | Registered Value | Unit | 95% Confidence Interval | Evidence Type | Source Artifact | Git SHA | Status |
|---|---|---|---|---|---|---|---|
| Target Latency (Fast Path) | < 12.0 | s | - | none (target) | `artifacts/p03/sam_bench.json` (fixture-only; NOT a measurement of SAM) | pending | Target (unmeasured; fixture-only bench exists) |
| StackCube Oracle Tolerance | 3.33 | cm | - | design constant | `IDEA.md §5` | pending | Registered |
| StackCube Placement Gap | 0.50 | cm | - | design constant | `IDEA.md §5` | pending | Registered |
| Hero Test Block Size | 4.0 | cm | - | design constant | `docs/DEMO_FILMING_GUIDE.md` | pending | Registered |

> **Not registered (must not appear on screen as measured):**
> - the 5.82 s two-stage p95 in `artifacts/p03/sam_bench.json` (`evidence_type: fixture_replay`, `is_real_sam_latency: false`: random draws, not SAM timings);
> - BA 1.0 / coverage 1.0 / 0 false-PASS in `artifacts/p04/validation.json` (`evidence_type: synthetic_tracks_from_privileged_state`, mock sim, no perception in the loop).
>
> `Evidence Type` values: `live` | `unit_tests` | `fixture_replay` | `synthetic` | `mock_sim` | `design constant` | `none (target)`.
