# BRIEF: Phase P02 Data & Simulation Foundation

PHASE P02: Data & Simulation Foundation · Hours to internal deadline: 174.5 · Budget left: $150 Meta credit (pending claim), $100 Modal credit (pending claim)

## Why This Phase Matters For Winning
Phase P02 establishes the physical simulation backbone (ManiSkill3 `StackCube-v1`) and the span-logged robot execution API that drives:
1. **The Headline Retraining Proof (Invariant I8):** "Same robot, same practice data, only the judge changed: +Y points of success." The background pool generation (BG-A) must start now because downstream policy retraining across multiple seeds and judge arms requires substantial compute time before the Nov 2 go/no-go gate.
2. **The 10 Seeded Physical Bugs Benchmark (Feature F42):** The reproducible physical bug patches (B01–B10) that demonstrate failure localization and power the Muse Code `/goal` unedited take in Phase P07.
3. **The Proof Hygiene & Pre-Registration:** Formalizing hypotheses, oracle-matched thresholds (`align_xy_cm <= 3.33, gap_cm <= 0.5`), and metric protocols in `experiments/PREREGISTRATION.md` tagged `prereg-v0` before any judge labels are revealed.
4. **Hero Failure Clips & Real Footage Infrastructure:** Building the LeRobot dataset loaders, hero-clip search tool, and DROID slice labeling tool (BG-C).

## Scope
`IMPLEMENTATION_PLAN.md` P02 (steps S01–S16):
- **S01:** ManiSkill env wrapper (`src/Kodiac_robotics/sim/env.py`) with Panda, `sim_freq=120, control_freq=30`, fixed 512×512 camera, deterministic seeds, privileged state access for eval, and `oracle_success()`.
- **S02:** Video writer (`src/Kodiac_robotics/sim/video.py` or within env) generating H.264 `yuv420p` MP4 at native 30 fps, state `.npz`, and metadata JSON.
- **S03:** Robot API + span logger (`src/Kodiac_robotics/sim/robot.py`, `src/Kodiac_robotics/sim/spans.py`): `@span` logging of calls to `arm.move_to`, `arm.lift`, `arm.retract`, `gripper.open/close`, `wait` with file/line inspection.
- **S04:** Correct pick-and-place reference program (`examples/sim/pick_place.py`), verified 10/10 seeds oracle success.
- **S05:** Seeded physical bug registry (`src/Kodiac_robotics/sim/bugs.py` + `examples/sim/bugs/B01.patch` … `B10.patch`) asserting oracle FAIL for every bug.
- **S06:** $\pi_0$ weak policy pipeline (`src/Kodiac_robotics/proof/pi0.py`, `modal/proof_train.py`), targeting 30–60% oracle success on 100 eval episodes.
- **S07:** 🔁 Practice pool generator (`src/Kodiac_robotics/proof/pool.py`): ~70% $\pi_0$ rollouts + ~30% perturbed-expert near-misses. Generates `experiments/pool/manifest.parquet`.
- **S08:** Pre-registration document (`experiments/PREREGISTRATION.md`) detailing hypotheses H1–H3, arms, thresholds, metrics, and stopping rules; tagged `prereg-v0`.
- **S09:** `examples/stackcube.green` and `examples/stack_blocks.green` test specifications.
- **S10:** LeRobot dataset loader (`src/Kodiac_robotics/io/lerobot.py`) supporting `lerobot://repo/episode[/camera]` to `Clip`.
- **S11:** 🎬 Hero-clip search utility (`scripts/find_hero_clips.py`) exporting candidate clips to `artifacts/p02/hero_candidates/`.
- **S12:** 🔁 Real-footage benchmark preparation (BG-C): DROID slice manifest, labeling tool (`scripts/label_tool.py`), and time-saved instrumentation.
- **S13/S13b:** Baseline judge spikes (`proof/judges/robometer.py`, `topreward.py`, `single_pass.py`).
- **S14:** Golden fixture set (`tests/fixtures/clips/`) with manifest and sha256 checksums.
- **S15:** Filming guide verification ([`docs/DEMO_FILMING_GUIDE.md`](file:///C:/Users/LOUJAN%20B/Kodiac/docs/DEMO_FILMING_GUIDE.md)).
- **S16:** Appearance benchmark dataset (`proof/appearance.py`, `experiments/appearance/manifest.parquet`) with $\ge 60$ labeled `looks()` clips.

## Exit Gate
- [ ] Correct `pick_place.py` produces oracle success on 10/10 seeds; MP4 at 30 fps plays; span log present.
- [ ] B01–B10 each reproduce their expected failure outcome deterministically (tests pass; asserts oracle FAIL).
- [ ] $\pi_0$ weak policy pipeline measured (target 30–60% oracle success) and training time recorded.
- [ ] Pool generation script runnable/launched; manifest schema validated.
- [ ] `PREREGISTRATION.md` draft approved by council and tagged `prereg-v0`.
- [ ] LeRobot loader exports playable H.264; hero candidates index exists; labeling tool functions; baseline spike verified.

## Inputs & Context
- Tag `p01-done` (`c7ed6d0` / `f549080`) verified and active.
- Core contracts frozen in `src/Kodiac_robotics/contracts/core.py`.
- Hardware fact: Local host has no GPU; heavy CUDA rendering/training pipelines must be partitioned to Modal (`modal/proof_train.py`), while local simulation code supports CPU/headless mode or lightweight mock verification.
- Reviewer findings from P01: All clean; zero blockers.

## Constraints
- Concept Invariants (`IDEA.md §0`): Invariant I8 (pre-registration tagged before any judge label analysis), Invariant I4 (exact onset `t*` + cause with numbers), Invariant I13 (100% software, sim clearly labeled).
- Subagent model constraint: All spawned subagents must strictly run Gemini 3.8 Flash (`Model: 'flash'`).
- Parallelism: All spawned council members and implementers must be executed in parallel waves.
