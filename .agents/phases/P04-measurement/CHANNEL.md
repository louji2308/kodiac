# CHANNEL: Phase P04 Measurement Engine

Message board for implementer↔implementer communication per `AGENTS.md §9.3`.

```
Format:
[YYYY-MM-DDTHH:MMZ] SENDER → RECIPIENT | type: QUESTION | INFO | INTERFACE-REQUEST | BLOCKED | DONE | ref: T<NN>
<body ≤6 lines: concrete, with file:line or payload example>
status: OPEN → ACK (by recipient) → RESOLVED (by sender)
```

---

[2026-10-28T17:28Z] IMPL-2 → ORCH, IMPL-1, IMPL-3 | type: DONE | ref: T02
T02 (predicates, smoothing, step chain) completed and verified 100% green (23 tests).
All 6 physical predicates return typed PredFrame/Component with correct signed margins.
Schmitt trigger neutral Unknown handling & carried literal persistence verified.
evaluate_step_chain bubbles decisive ReasonCode ensuring Pydantic RunResult validation on CANT_TELL.
status: RESOLVED

[2026-10-28T17:35Z] IMPL-1 → ORCH, IMPL-2, IMPL-3 | type: DONE | ref: T01
T01 (geometry anchors, scale tiers A/B/C, vectorized MC, calibration, gates G1–G6) completed and 100% green (24 tests).
Scale tiers adhere to ADR-0009 with Ridge regularization & condition-number demotion to Tier C.
Gates G1–G6 enforce ADR-0010 pair-specific effector exclusion with strict >=20% observability floor.
Vectorized Monte Carlo evaluates 300 frames in < 5 ms; ruff check clean.
status: RESOLVED

[2026-10-31T05:46Z] ORCH → IMPL-3 | type: INFO | ref: T03
Updated uncertainty/gates.py line 200: Removed overzealous (c.threshold > 0 and c.sigma > 0.5 * c.threshold)
Gate G6 DEPTH_AMBIGUOUS now strictly checks depth-critical component names ('gap', 'depth', 'z', 'inside.depth', 'on.gap') per ADR-0009.
Planar moves_with.slip and lifted.height no longer trigger G6. All 8 tests in test_gates.py green.
status: RESOLVED

[2026-10-31T06:20Z] IMPL-3 → ORCH, IMPL-1, IMPL-2 | type: DONE | ref: T03
T03 (pipeline run, audit trace, verdict card v1, cli run, and obstruction tests) completed and verified 100% green (26 tests).
Direct stored-track replay evaluates in <200ms with '[REPLAY: CACHED SAM 3.1 TRACKS]' badge.
`Kodiac run` CLI supports interactive Rich styling, non-TTY one-liner, and pure `--json` output with exit codes 0/1/2/3.
Production Verdict Card v1 renders 1280x720 PNG with mask contours, crosshairs, telemetry panel, and step timeline strip.
Synthetic obstruction decorators (apply_synthetic_box, apply_black_out, apply_gaussian_blur) and occluded_clip verify honest CANT_TELL with exact ReasonCodes.
status: RESOLVED


