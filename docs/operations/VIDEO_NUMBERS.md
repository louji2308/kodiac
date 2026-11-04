# VIDEO_NUMBERS.md: Registered Numbers for Presentation & Video Assets

> **Strict Honesty Rule:** Every number displayed in the 3-minute video, README, or presentation must be registered in this table with its calculating artifact and git commit sha before recording. Unregistered numbers are banned.

| Item | Registered Value | Unit | 95% Confidence Interval | Evidence Type | Source Artifact | Git SHA | Status |
|---|---|---|---|---|---|---|---|
| Target Latency (Fast Path) | < 12.0 | s | - | none (target) | `artifacts/p03/sam_bench.json` (fixture-only; NOT a measurement of SAM) | pending | Target (unmeasured; fixture-only bench exists) |
| StackCube Oracle Tolerance | 3.33 | cm | - | design constant | `IDEA.md §5` | pending | Registered |
| StackCube Placement Gap | 0.50 | cm | - | design constant | `IDEA.md §5` | pending | Registered |
| Hero Test Block Size | 4.0 | cm | - | design constant | `docs/DEMO_FILMING_GUIDE.md` | pending | Registered |
| Hand-Verified Hero Failure Episodes | 5 | episodes | - | cataloged candidates | `artifacts/p02/hero_candidates/index.md` | `ccf1595` | Measured (cataloged candidates) |
| StackCube Blame Early Release Delta Time | 0.4 | s | ± 0.07 s | kinematic simulation | `ARCHITECTURE.md §2` / `artifacts/p06/blame_core_report.json` | `ccf1595` | Measured (simulated kinematic replay) |
| StackCube Blame Early Release Lateral Offset | 2.6 | cm | ± 0.4 cm | kinematic simulation | `ARCHITECTURE.md §2` / `artifacts/p06/blame_core_report.json` | `ccf1595` | Measured (simulated kinematic replay) |
| StackCube Blame Failure Onset Frame | 114 | frame | ± 1 frame | kinematic simulation | `ARCHITECTURE.md §2` / `artifacts/p06/blame_core_report.json` | `ccf1595` | Measured (simulated kinematic replay) |
| Planted Bug Repairs | 10 | bugs | - | kinematic simulation | `artifacts/p06/patch_regen.json` | `ccf1595` | Measured (10 of 10 bugs repaired on mock sim) |
| Clean Evaluation Seeds | 3 | seeds | - | simulation evaluation | `artifacts/p04/discrimination.json` | `ccf1595` | Measured (clean seeds 0, 1, 2) |
| Statistical Confidence Level | 95% | % | - | pre-registered design | `experiments/PREREGISTRATION.md §6` | `prereg-v1` | Measured (pre-registered confidence level) |
| Discrimination Evaluation Runs | 16 | runs | - | synthetic evaluation | `artifacts/p04/discrimination.json` | `ccf1595` | Measured (16/16 exact discrimination) |
| False-PASS Verification Count | 0 | count | - | synthetic evaluation | `artifacts/p04/discrimination.json` | `ccf1595` | Measured (zero false-PASS count) |

> **Not registered (must not appear on screen as measured):**
> - the 5.82 s two-stage p95 in `artifacts/p03/sam_bench.json` (`evidence_type: simulated_timings`, `is_real_sam_latency: false`: random draws, not SAM timings);
> - BA 1.0 / coverage 1.0 / 0 false-PASS in `artifacts/p04/validation.json` (`evidence_type: synthetic_tracks_from_privileged_state`, mock sim, no perception in the loop).
>
> `Evidence Type` values: `live` | `unit_tests` | `fixture_replay` | `simulated_timings` | `synthetic` | `mock_sim` | `design constant` | `none (target)`.
