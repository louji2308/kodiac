# Kodiac: Tests, `git bisect`, and `git blame` for Robots

### *"Robots can finally fail a test."*

> **Meta Global AI Developer Hackathon 2026** | Indie Developer Track | Theme: *"Push the Frontier"*
> Status: Work in progress. Build window opened 2026-10-26.

Show Kodiac a task once, and Meta's models turn it into a readable, executable test. Kodiac then grades every robot video against that test frame by frame, and points to the **exact moment** and the **measured physical cause** of every failure.

Same robot, same practice data, only the judge changed: **+Y points of success.**

> **`Y` is a placeholder. It is not yet measured.** No model arm has been trained and no headline experiment has been run.
> No Meta/Modal/HF API keys have been used so far; everything below ran on recorded fixtures or a kinematic mock simulator.

## Status (hand-written from `docs/features.yaml`; a generator comes in P09)

| State | Features | Evidence caveat |
|---|---|---|
| **Built, unit-tested** | Test capture CLI, `.green` language + lock file, provenance, linter, type-check, demo self-test, text-compile, effector aliasing, ingest/windowing, scale model, predicates `on/near/lifted/moves_with/dwell`, smoothing, verdict + reason codes, evidence frames, trace.jsonl | Deterministic tests; not run against real Meta models |
| **Partial / fixture-only** | Speech to step windows, spec compiler (fixture + mocked API only), object tracking (recorded fixture tracks, real SAM never run), `inside`, sigma + margin gate (validated only on synthetic tracks in the mock sim), occlusion/view gates (G5 untested), sim harness and B01-B10 bug registry (mock sim only, no fix-rate eval) | See `evidence_type` in `docs/features.yaml` |
| **Not built** | Two-stage bisect / exact t* blame, reality diff, prefix salvage, corrective hint, MCP `Kodiac.verify`, done-gate, `/goal` recipe, headline experiment and proof chart, dataset audit, hosted app, latency timer, video | Planned |

**Latency:** the `<12 s` figure is a target. The only benchmark in the repo (`artifacts/p03/sam_bench.json`) is a fixture replay and is not a SAM measurement.
**Practice pool:** 250 mock-physics episodes; not valid for the headline proof (see `experiments/README.md`).
