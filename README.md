# Kodiac: Tests, `git bisect`, and `git blame` for Robots

### *"Robots can finally fail a test."*

> **Meta Global AI Developer Hackathon 2026** · Indie Developer Track · Theme: *"Push the Frontier"*

Show Kodiac a task once. Meta's models turn it into a short, readable, executable test. Kodiac then
grades every robot attempt against that test frame by frame and returns **PASS**, **FAIL**, or
**CAN'T TELL** — and on a FAIL it points at the **exact onset frame** and the **measured physical
cause**, down to the line of robot code that actuated it.

Robotics has no `pytest` and no `git blame`. A demonstration labelled "successful" is taken on trust,
a policy that regressed is debugged by scrubbing video, and an agent that says "done" is believed.
Kodiac gives robots the three things every codebase already has: a test, a bisect, and a blame.

---

## Read this before the numbers

**There is no measured headline yet, and this README will not pretend otherwise.**

- No Meta Model API key, no Modal token and no HF gated weights were available during the build.
  Every SAM 3.1 / Muse Spark / Muse Voice / Muse Wonder call site is therefore exercised against
  **recorded fixtures or a deterministic mock**, and says so at runtime with a badge.
- The headline claim (*"same robot, same practice data, only the judge changed: +Y points of
  success"*) is **NOT MEASURED**. `experiments/results/headline.json` carries `Y_points: null` and the
  proof chart refuses to draw bars; it renders a `NOT MEASURED` watermark instead.
- The engine is real and runs end to end. Its *perception* input is not: `--sim` grades tracks
  projected from simulator state, and every badge on that path says
  `[SYNTHETIC TRACKS FROM SIM STATE · NOT PERCEPTION]`.
- `docs/features.yaml` is the ground truth for what shipped and on what evidence. The status section
  at the bottom of this file is generated from it (`scripts/gen_status_table.py --check` fails if the
  two ever disagree).

If a claim is not backed by a committed artifact, it is labelled `[UNVERIFIED]` where it appears.

---

## Try it in 90 seconds

```bash
git clone <this repo> && cd Kodiac
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
Kodiac --version                                   # Kodiac 0.1.0
```

**1. Compile a demonstration into a test.** Text mode works offline (deterministic template, badged):

```bash
Kodiac test --from-text "stack cubeA on cubeB" --out demo.green
```

```text
⚠ [COMPILER: DETERMINISTIC TEMPLATE FALLBACK · LLM OFFLINE]
  ✓ [2.3s] compiled    test_cubeA_cubeB.green
  wrote demo.green (5 lines)
```

```green
# test_cubeA_cubeB.green — [COMPILER: DETERMINISTIC TEMPLATE FALLBACK · LLM OFFLINE]
objects: [gripper, cubeA, cubeB]
1. grasp:   moves_with(gripper, cubeA) and lifted(cubeA, min_cm>=2.0)    # "stack cubeA on cubeB" [0:00.0–0:00.0]
2. place:   on(cubeA, cubeB, align_xy_cm<=1.5)                           # "stack cubeA on cubeB" [0:00.0–0:00.0]
3. release: not moves_with(gripper, cubeA) and dwell(cubeA, cubeB, for_s>=0.5)  # "stack cubeA on cubeB" [0:00.0–0:00.0]
```

The `[0:00.0–0:00.0]` windows are empty on purpose: with no ASR and no live compile, the template
cannot invent when a step happens. `examples/stackcube.green` is the hand-checked version used below.

**2. Grade an attempt.** The mock simulator needs no keys, no GPU and no network:

```bash
Kodiac run examples/stackcube.green --sim examples/sim/pick_place.py
```

```text
PASS  stackcube   (exit 0)
  grasp    PASS   moves_with(gripper, cubeA) and lifted(cubeA, min_cm=2.0)
  place    PASS   on(cubeA, cubeB, align_xy_cm<=3.33, gap_cm<=0.5)
  release  PASS   not moves_with(gripper, cubeA) and dwell(cubeA, cubeB, for_s=0.5)
badges: [SIM] [SYNTHETIC TRACKS FROM SIM STATE · NOT PERCEPTION] [MOCK SIMULATION]
```

**3. Break it, then blame it.** `--bug B01` injects a real seeded bug (a patch from
`examples/sim/bugs/`) into a copy of the script — the copy is what runs, and the badge says how the
bug got in:

```bash
Kodiac run  examples/stackcube.green --sim examples/sim/pick_place.py --bug B01
Kodiac blame examples/stackcube.green --sim examples/sim/pick_place.py --bug B01
```

```text
+------------------------------- Kodiac Blame --------------------------------+
| BLAME step #2 place · moves_with(gripper, cubeA)                            |
| onset t* = 3.833 s (frame 115, ± 10.5 frames @ 30.0 fps) · transition T->F  |
+-----------------------------------------------------------------------------+
template: gripper released cubeA 9.4 ± 0.1 cm from cubeB in xy at 00:03.8, frame 115

| xy_offset_cm |  9.406 ± 0.122 | cm   |     | lift_cm  | 11.984 ± 0.130 | cm |
| slip_cm      |  0.184 ± 0.168 | cm   |     | dwell_s  |   0.033 ± 0.033 | s  |

code: .../pick_place_B01.py:83   robot.gripper.open(steps=15)
warning: blame_class 'xy_offset' (measurement rule) overridden to 'release_before_place' by sim span order
warning: fixture replay: measurements come from recorded tracks, not a live SAM 3.1 call
```

That is the whole product in one screen: *the cube was released 9.4 cm from where it had to go, at
frame 115, by line 83 of the script.*

**4. Diff the attempt against the demonstration.** Same script, one bug apart:

```bash
Kodiac diff examples/stackcube.green --sim examples/sim/pick_place.py --bug B01 \
            --demo-sim examples/sim/pick_place.py --geometry tier_a
```

```diff
@@ 1 matched, 2 demo-only/diverging, 2 attempt-only/diverging (tier A; world axes) @@
  [0] grasp: achieved @ 2.33 s (demo 2.33 s); moves_with.slip 0.2 ± 0.2 cm
- [1] place: settled on(cubeA, cubeB) @ 5.33 s (frame 160); on.align_xy 0.1 ± 0.1 cm
+ [1] place: failed @ 3.93 s (frame 118)
+ [1] place: released moves_with(gripper, cubeA) @ 3.93 s (frame 118)
```

**5. Make an agent's "done" mean something.** The done-gate is a Stop hook that refuses to let a
coding agent stop until the test passes; `Kodiac mcp` exposes the same check as `Kodiac.verify`.

```bash
Kodiac loop init --dir path/to/agent/project --dry-run     # shows what it would install
Kodiac gate --init --workspace . --test examples/stackcube.green --sim examples/sim/pick_place.py
```

---

## The three verbs

| Verb | What it answers | Exit codes |
|---|---|---|
| `Kodiac test` | "What does *done* mean for this task?" | 0 built · 3 error |
| `Kodiac run` | "Did this attempt do it?" | 0 PASS · 1 FAIL · 2 CAN'T TELL · 3 error |
| `Kodiac blame` | "When exactly did it go wrong, and why?" | FAIL only; PASS/abstain pass through |

`blame` is defined **only** for FAIL. On PASS it says there is nothing to attribute; on CAN'T TELL it
refuses to guess. `Kodiac diff` shows attempt vs demonstration as aligned events; `Kodiac bisect`
(`run --mode fast`) finds the same verdict with a fraction of the frames.

### CAN'T TELL is a feature, not a gap

The abstain path is the reason the positive path can be trusted. Every predicate carries a
measurement and a σ; when a measurement sits inside its noise floor, the gate returns `U`, Kleene
logic propagates it, and the verdict is CAN'T TELL with a reason code (`below_noise_floor`,
`occluded`, `out_of_frame`, …). An occluded camera produces an abstain, not a confident FAIL.

---

## How it works

```text
video / sim ──▶ ingest (fps-agnostic) ──▶ tracks (SAM 3.1 or fixture/sim)
             ──▶ per-frame predicates with ±σ ──▶ Kleene step chain
             ──▶ verdict + reason codes ──▶ trace.jsonl + verdict card
                                              └─▶ blame: t*, measured facts, hint, code line
```

| Layer | Where | Note |
|---|---|---|
| `.green` language + lock file | `src/Kodiac_robotics/compiler/` | Readable test spec, demo self-test, provenance per step |
| Predicates | `src/Kodiac_robotics/predicates/` | `on`, `near`, `lifted`, `moves_with`, `dwell`, `inside` — each returns values ± σ |
| Uncertainty | `src/Kodiac_robotics/uncertainty/` | Margin gates G1–G6, hysteresis, noise floor |
| Engine | `src/Kodiac_robotics/engine/` | Kleene chain over steps, reason codes, exit codes |
| Blame | `src/Kodiac_robotics/blame/` | Transition search, bootstrap t*, fact table, hint, diff, code location |
| Sim + gate | `src/Kodiac_robotics/sim/`, `loop/` | Isolated sim runner, 10 seeded bugs, Stop-hook done-gate, MCP `verify` |
| App + audit | `src/Kodiac_robotics/app/`, `audit/` | FastAPI/Gradio app, cached replays, dataset audit + digest |

---

## Meta tools: what ran, and what did not

Nothing below ran live. This table exists so nobody has to guess.

| Tool | Role in Kodiac | Status in this build |
|---|---|---|
| **SAM 3.1** | measures objects; backward frame inspection | Adapter + H.264/≤16-object constraints implemented; graded against **recorded fixture tracks**. Live call never made. |
| **Muse Spark** | compiles the spec; two-way crop judge | Compiler + judge protocol implemented and unit-tested; deterministic template fallback is what produced the tests here. Live call never made. |
| **Muse Voice** | anchors step windows from speech | Endpointing + turn timestamps implemented; **fixture transcripts only**. |
| **Muse Wonder** | adjudicates hard cases; narrates | Escalation with a wall-clock cap, digest-bound narration validator; live model unverified. |
| **Muse Code** | the `/goal` loop with the done-gate | Gate, MCP server, hook templates and install script built and tested; `.muse/hooks.json` format is `[UNVERIFIED]` against the real product. |

Every Meta-shaped call site takes an injectable client, which is why the offline test suite can
exercise the real protocol without a key — and why we refuse to call any of it "measured".

---

## Evidence you can re-run

| Artifact | What it shows | Honest label |
|---|---|---|
| `artifacts/p04/validation.json` | Engine discrimination on synthetic tracks | `synthetic_tracks_from_privileged_state` |
| `artifacts/p06/agreement.json` | Fast path vs full path on 200 mock episodes | `target_met: false` (all episodes FAIL) |
| `artifacts/p06/codeloc_B01_B10.json` | 10/10 seeded bugs located to their actuation line | `mock_sim`, not blind |
| `artifacts/p07/gate_refusals.json` | 18 tamper attempts refused by the done-gate | `mock_sim` |
| `artifacts/p07/loop_eval_dryrun.json` | Fix-rate harness plumbing | `plumbing_dry_run`, `agent_fix_rate: null` |
| `site/replays.json` | 6 cached verdict cards | `is_fixture: true`, `backend: cached_replay` |
| `experiments/results/headline.json` | The headline experiment | **`NOT_MEASURED`** |

Reproduce the test suite:

```bash
python -m pytest -q            # ~1000 tests, no keys, no network, no GPU
python scripts/compliance_check.py
python scripts/gen_status_table.py --check
```

---

## Repository map

```text
src/Kodiac_robotics/   engine, predicates, blame, compiler, sim, loop, app, audit, proof
tests/                 unit + integration, all offline (fixtures, mock sim, injectable clients)
examples/              stackcube.green + a mock pick-and-place sim + 10 seeded bug patches
artifacts/             evidence committed with its provenance label
experiments/           pre-registered proof protocol; headline NOT MEASURED
docs/                  features.yaml (ground truth), SUBMISSION.md, VIDEO_NUMBERS.md, runbook
site/                  static mirror of the hosted app with cached replays
```

---

<!-- BEGIN GENERATED STATUS (scripts/gen_status_table.py) -->

## Status (generated from `docs/features.yaml`)

61 tracked features: **32 done** · **22 partial** · **7 planned**.

> **Nothing is `live`.** No Meta Model API key, Modal token or HF gated-weight access was used, so every row below is backed by deterministic tests, recorded fixtures, synthetic data or the mock simulator. The registry's `evidence_type` column, not this list, is the authority.

### Built and tested (32)

- `F01` **Demo capture** (MVP) - deterministic tests
- `F04` **.green language + lock file** (MVP) - deterministic tests
- `F05` **Per-step provenance** (MVP) - deterministic tests
- `F06` **Compile-time spec linter** (MVP) - deterministic tests
- `F07` **Object type-check** (MVP) - deterministic tests
- `F08` **Demo self-test** (MVP) - deterministic tests
- `F09` **Text-compile mode** (MVP) - deterministic tests
- `F10` **Effector aliasing** (MVP) - deterministic tests
- `F11` **Universal ingest, fps-agnostic time** (MVP) - deterministic tests
- `F14` **Dense backward window** (MVP) - synthetic data only
- `F15` **Scale model (px -> cm)** (MVP) - deterministic tests
- `F16` **on(A,B) + 2.5D depth check** (MVP) - deterministic tests
- `F18` **near(A,B)** (MVP) - deterministic tests
- `F19` **lifted(A)** (MVP) - deterministic tests
- `F20` **moves_with(E,A)** (MVP) - deterministic tests
- `F21` **dwell(A[,B])** (MVP) - deterministic tests
- `F22` **Smoothing & hysteresis** (MVP) - deterministic tests
- `F28` **Verdict + reason codes + exit codes** (MVP) - deterministic tests
- `F29` **Evidence frames** (MVP) - deterministic tests
- `F30` **trace.jsonl + provenance viewer** (MVP) - deterministic tests
- `F31` **Step-chain transition finder** (MVP) - deterministic tests
- `F33` **One-sentence summary bound to measurements** (MVP) - deterministic tests
- `F34` **Event-level reality diff** (MVP) - synthetic data only
- `F35b` **Blame target, sim code** (MVP) - mock simulator only
- `F37` **Corrective hint** (MVP) - deterministic tests
- `F38` **MCP tool Kodiac.verify** (MVP) - mock simulator only
- `F39` **Done-gate** (MVP) - mock simulator only
- `F50` **Failure-Norm Digest** (MVP) - deterministic tests
- `F51` **LeRobot-compatible verdict export** (MVP) - deterministic tests
- `F55` **Camera-cover test + occlusion brush** (MVP) - recorded fixtures only
- `F56` **Instant Cached Replay** (MVP) - recorded fixtures only
- `F57` **Operations guard** (MVP) - deterministic tests

### Built or partly built, with an evidence caveat (22)

- `F02` **Speech -> step windows** (MVP) - recorded fixtures only. Fixture/mocked-API tests only;
  live Muse Voice never run (no key).
- `F03` **Spec compiler** (MVP) - recorded fixtures only. Fixture/mocked-API tests only; live Muse
  Spark compile never run (no key).
- `F12` **Object tracking with stable IDs** (MVP) - recorded fixtures only. Recorded fixture tracks
  on golden clips; real SAM tracking never run (no key).
- `F13` **Two-stage git bisect fast path** (MVP) - recorded fixtures only. Built and tested
  (keyframes -> halving -> dense window, guards G-alias/G-miss/G-budget/G-pass). On the synthetic
  pool (n=200) fast and full agreed 100% on verdict and t* (+-2 frames), but every episode was FAIL
  so PASS-as-PASS is untested; on short clips (<=100 frames) it falls back to the full path and it
  billed more frames than one dense pass (168.5 vs 150.7). artifacts/p06/agreement.json records
  target_met false.
- `F17` **inside(A,B) + 2.5D rim-occlusion** (MVP) - deterministic tests. Lite inside() with rim
  margin only; 2.5D rim-occlusion memory not built.
- `F23` **+-sigma uncertainty + margin gate** (MVP) - synthetic data only. Sigma/margin gate
  implemented; validation.json is on synthetic tracks from privileged state in the mock sim
  (perception not in loop).
- `F24` **Occlusion & view gates** (MVP) - deterministic tests. tests/uncertainty/test_gates.py
  covers G1-G4 and G6; G5 (appearance) not covered; 0 gate firings in validation are on synthetic
  tracks.
- `F25` **Two-way contrastive crop judge** (Strong) - recorded fixtures only. Protocol built and
  tested offline (antonym question pairs, 9-combination decision table, yes-bias defeat, crop >=512
  px with outline). The live Meta API was never called (no key); endpoint and model ids are
  [UNVERIFIED].
- `F26` **Hard-case escalation** (Strong) - recorded fixtures only. Wonder escalation with a
  wall-clock cap tested with an injectable clock; live muse-wonder-1.0 unverified.
- `F32` **Exact t* by backward refinement** (MVP) - synthetic data only. Detach-onset /
  piecewise-breakpoint refinement with seeded bootstrap sigma; frame-exact on synthetic ramps. On
  Tier C fixture tracks sigma is several frames (~7), so "exact" is proven only on synthetic data.
- `F36` **Prefix salvage** (MVP) - deterministic tests. Cut + chunk-safe mask + LeRobot-style export
  tested; the h5 path is untested (h5py absent) and no retraining run exists.
- `F40` **/goal recipe** (MVP) - deterministic tests. Templates + idempotent installer tested; the
  `.muse/hooks.json` format is unverified against Muse Code and no live /goal run exists.
- `F41` **Sim harness** (MVP) - mock simulator only. Kinematic mock env plus an isolated-child sim
  runner (action replay, sanity bounds, digests), all mock. The ManiSkill path is unverified (no
  GPU/Modal) and scripts are graded on tracks projected from sim state.
- `F42` **10 seeded physical bugs + fix-rate eval** (MVP) - mock simulator only. B01-B10 registry
  and real patches (all apply, oracle fails on each). The fix-rate harness ran only its plumbing dry
  run with a scripted reference patcher; there is no agent fix rate (agent_fix_rate null).
- `F44` **Fair baselines** (MVP) - synthetic data only. Arms are fail-closed: a missing judge label
  makes the arm absent with a reason, never oracle-derived. Oracle / accept-all / injected-noise
  controls exist; no baseline judge has been run, so no comparison exists.
- `F47` **Proof chart** (MVP) - synthetic data only. Renderer refuses to draw bars unless the
  headline is MEASURED; it currently renders the "NOT MEASURED: NO TRAINED ARMS YET" watermark,
  which is the honest current state.
- `F48` **Meta ablation ladder** (Strong) - synthetic data only. Ladder logic tested with synthetic
  inputs; no rung has been measured.
- `F49` **Audit of public robot datasets** (MVP) - mock simulator only. Batch runner, review queue,
  digest, export and guarded publish are built and tested on fixture episodes labelled DEMONSTRATION
  DATA. No public dataset has been audited; no flag is human-verified yet.
- `F53` **Hosted web app** (MVP) - recorded fixtures only. FastAPI server (/health, /grade, /replay)
  and a Gradio UI are built and tested offline against fixture clips. Nothing is deployed: no Modal
  token, no public URL. Every grade is fixture replay and says so.
- `F54` **Live wall-clock timer, "<12 s"** (MVP) - recorded fixtures only. The timer measures real
  wall-clock of what actually ran and is shown as measured, never as a "<12 s" claim. No live grade
  exists (no API key), and the fixture benchmark timings are simulated, so the budget is unverified.
- `F58` **pip package + CLI** (MVP) - deterministic tests. Commands
  run/test/blame/diff/gate/mcp/loop/audit are wired and tested locally; the package is not published
  (the PyPI name reservation is still a human action).
- `F60` **README + write-up** (MVP) - deterministic tests. README has a generated-from-registry
  status table; the write-up and submission text still contain [PENDING] links.

### Not built (7)

- `F27` **Open-weights / private mode** (Strong) - no evidence. Backends are wired
  (baseten-spark-open / modal-glimmer-vllm / llamacpp-glimmer) but no model was ever loaded or run.
- `F35a` **Blame target, real footage** (MVP) - no evidence. No real-footage clip exists; blame was
  exercised on fixture replays of mock-sim renders only.
- `F43` **Headline: "Only the judge changed"** (MVP) - no evidence. NOT MEASURED. Statistics
  machinery is built and tested; there are no judge labels and no trained arms, so
  experiments/results/headline.json carries Y_points null and status NOT_MEASURED (no number is
  claimed).
- `F45` **Judge benchmark table** (MVP) - no evidence. No judge has been run against labelled clips;
  the benchmark table cannot be filled without keys/labels.
- `F46` **Real-footage validation** (Strong) - no evidence
- `F52` **Helpful community reports** (Strong) - no evidence. Publish is a guarded stub that refuses
  without a recorded human approval ticket; nothing was ever posted.
- `F59` **3-minute video** (MVP) - no evidence. A draft script and linter exist (video/SCRIPT.md);
  no footage, voiceover or edit exists, and unmeasured numbers are marked pending.

<!-- END GENERATED STATUS -->

---

## License

Apache-2.0. Third-party components and their licences are listed in `ATTRIBUTIONS.md`; where a
licence could not be verified it says so instead of guessing.
