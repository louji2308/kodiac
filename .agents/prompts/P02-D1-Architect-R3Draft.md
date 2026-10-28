You are D1 Architect on the Kodiac decision council for Phase P02: Data & Simulation Foundation.

ROUND: R3 Converged Plan (Draft by D1).
All members have written their R2 stress tests in `.agents/phases/P02-data-sim/COUNCIL.md`.

Now, as the SINGLE WRITER of the converged plan draft, synthesize the agreement and resolve the critiques:
- Incorporate D2's watermarking & provenance requirements (`is_mock: true`, `[MOCK SIMULATION]` burned banner, dataset provenance).
- Incorporate D2 & D3's demand for full DAG parallelism (T01 ∥ T02 ∥ T03 decoupled; T02 drafts PREREGISTRATION.md and sets up Modal training concurrently with T01).
- Incorporate D3's causal lag window ($\Delta t \le 1.0$ s) in `find_blame_span` and `sys._getframe(1)` for fast stack resolution.
- Incorporate D3's CFR 30 fps video encoding and D1's settling velocity check ($< 0.01$ m/s) to prevent physics bouncing.
- Ground pre-registration in Git commit SHA + tag `prereg-v0` + content sha256 in Parquet metadata (`ots` non-blocking).
- Resolve IP table with D1, D2, D3 consensus.

Write your draft directly under `## R3: Converged plan (draft by D1)` in `.agents/phases/P02-data-sim/COUNCIL.md` following the template in AGENTS.md §5.5.
Deliverable: Write the section in COUNCIL.md and reply to ORCH with ≤150 words summarizing the converged plan.
