# IMPLEMENTATION_PLAN.md: Ten Phases, Setup → Verification

> **Audience: the AI agents in this codebase.** Every step is written as an instruction to an agent. Humans appear only where a
> step needs a human (marked **👤 HUMAN**); the agent prepares everything and asks via `HUMAN-DECISION-NEEDED`.
> Read with: `AGENTS.md` (protocol: council → ruling → dispatch → build → gate → push → review ∥ next council), `IDEA.md` (features
> F##, invariants I##), `ARCHITECTURE.md` (contracts §4, workflows §5, key decisions KD-##), `TOOLS_AND_REQUIREMENTS.md` (approved stack).
>
> **Step IDs:** `P<phase>.S<step>` (e.g. `P04.S06`). Task cards cite step ranges. Steps marked ⚡ **may start early** in the previous
> phase if implementers are idle and the step does not depend on that phase's unfinished outputs. Steps marked 🔁 launch or poll a
> **background job** (`AGENTS.md` §2.1). Steps marked 🎬 produce a **video/demo asset** (log the asset in `docs/VIDEO_NUMBERS.md`).

---

## 0. Master Schedule (UTC; today = Tue 2026-10-27, ~19:00 UTC)

| Phase | Name | Window (UTC, target) | SDM escalation | Key output for judges |
|---|---|---|---|---|
| **P01** | Setup & Environment Verification | Oct 27 19:00 → Oct 28 08:00 | **Always** | Verified stack, frozen contracts, CI |
| **P02** | Data & Simulation Foundation | Oct 28 08:00 → Oct 28 22:00 | If IPs | Sim harness, seeded bugs, proof pool started 🔁, pre-registration |
| **P03** | Perception Core (SAM 3.1) | Oct 28 22:00 → Oct 29 14:00 | If IPs | Masks + backward tracking + measured latency |
| **P04** | Measurement Engine (`Kodiac run`) | Oct 29 14:00 → Oct 30 14:00 | **Always** | 6 predicates, σ gate, verdicts, card v1 |
| **P05** | `Kodiac test` Compiler | Oct 30 06:00 → Oct 30 22:00 (overlaps via ⚡) | If IPs | Voice → 4-line test 🎬 |
| **P06** | Fast Path, Judge Layer, `blame` + `diff` | Oct 30 22:00 → Oct 31 22:00 | If IPs | t* + cause + diff 🎬 |
| **P07** | Muse Code Loop & Done-Gate | Oct 31 22:00 → Nov 1 16:00 | If IPs | One unedited `/goal` take 🎬 + backup video |
| **P08** | Proof & Dataset Audit | Nov 1 16:00 → Nov 2 22:00 (**go/no-go Nov 2 12:00**) | **Always** | Headline chart 🎬, benchmark, audit card 🎬 |
| **P09** | Hosted Live App & Packaging | Nov 2 12:00 → Nov 3 14:00 | If IPs | Public URL, <12 s timer 🎬, `pip install` |
| **P10** | Video, Write-up, Final Verification & Submission | Nov 3 06:00 → **Nov 4 17:00** | **Always** | Submitted project; ops runbook to Nov 16 |

**Hard dates:** feature freeze **Nov 4 04:59 UTC** (Nov 3 23:59 EST) · **internal submit Nov 4 17:00 UTC** · official deadline Nov 5 02:00
UTC · finals Nov 9 17:00 UTC · keep the demo alive through Nov 16.
**Overlap rule:** where windows overlap (P04/P05, P08/P09, P09/P10), the next phase runs as a **parallel track**: its council R0–R2 may start during the previous BUILD (frozen contracts only), R3 + ruling wait for the previous PUSH, and ⚡ steps start immediately with disjoint `owns_paths`. Arithmetic: sequential P09 (26 h) + P10 (35 h) after P08 ends Nov 2 22:00 would finish ≈ Nov 5 11:00 UTC (too late); with the P09/P10 ⚡ tracks starting Nov 2 12:00 / Nov 3 06:00, P10 finishes by the Nov 4 17:00 internal submit with ≈ 9 h margin before the official deadline.
**Schedule rule:** if any phase ends > 4 h late, ORCH escalates a cut list from `IDEA.md` §11 (`AGENTS.md` §12.6).

### 0.1 Background tracks (run across phases; never block the pipeline)

| Track | Start | Steps (phase where each happens) | Finish |
|---|---|---|---|
| **BG-A Proof compute** | P02 | pool generation (P02) → full-path SAM tracking of the pool (P03) → baseline judge labels (P03–P04) → baseline/oracle/control arm training (P04–P05) → Kodiac labels (P04–P05) → Kodiac arm training (P05–P06) → evals (P06–P07) | stats + chart in P08 |
| **BG-B Dataset audit** | P05 | text-compile tests per task (P05) → batch runs (P05–P06) → candidate flags (P06) → 👤 human verification (P07–P08) | digest + card in P08 |
| **BG-C Real-footage labels** | P02 | DROID slice manifest + labelling tool (P02) → 👤 human labels (P03–P07) | benchmark in P08 |
| **BG-D Video assets** | P04 | every phase's 🎬 steps → backup cut (P07, Nov 1) | final cut in P10 |
| **BG-E External validation** | **P02** | 👤 contacts 1–2 robotics researchers now (try it on their own clips Nov 1–3, permission to quote) → first consolidated maintainer note once ≥5 flags are 👤-verified (P06.S16) → remaining reports P08 | quotes in P10 |

### 0.2 How each phase runs (`AGENTS.md` §2, condensed)
`BRIEF → COUNCIL (D1, D2, D3 on the whole phase; blind R1) → RULING (SDM if required) → DOC-SYNC → DISPATCH (one task card per implementer, frozen contracts) → BUILD → INTEGRATE → GATE → PUSH + tag p<NN>-done → REVIEW(N) ∥ COUNCIL(N+1)`.
Each phase below provides **council focus questions**, **numbered steps**, a **suggested task split** (3 implementers by default, with
`owns_paths`), an **exit gate**, **tripwires**, and **human items**.

---

## P01: Setup & Environment Verification

**Goal.** A clean, compliant repository; a verified Meta + partner stack (every P1 product smoke-tested, with measured latency); frozen
contracts; CI; and an established SDM channel. **No feature code yet.** We are buying certainty.
**Why it matters for winning.** Every later phase depends on facts we don't have yet: hosted SAM latency, Muse Code hook behavior,
credit coverage, and ManiSkill rendering. Discovering them on day 5 kills the demo.

**Council focus questions (D1–D3).**
1. Is the schedule in §0 realistic given the smoke-test results? What is the cut line if the hosted SAM latency is > 5 s per window?
2. Which unverified items (`TOOLS_AND_REQUIREMENTS.md` tag **U**) could force an architecture change, and what is each one's tripwire?
3. Are the contracts in `ARCHITECTURE.md` §4 complete enough to freeze? What's missing for P02–P04 parallel work?
4. Which runtime and SDM channel are actually available (OpenCode/DeepSeek, Antigravity/Gemini, human relay)?

**Steps.**
- **P01.S00 Public-surface scrub (before the first commit).** Verify `grep -niE -f <(grep -v '^#' docs/private/lineage_terms.txt)` returns 0 hits in IDEA, ARCHITECTURE, TOOLS_AND_REQUIREMENTS, IMPLEMENTATION_PLAN, AGENTS. Fix any hit before committing.
- **P01.S01 Repo init & compliance.** `git init -b main` in the repo root. This is the **private working repo**; the public submission repo is a filtered mirror built in P10.S07b. Verify `.gitignore` covers `docs/private/`, `.env`, `.cache/`,
  `runs/`, large media. Add `LICENSE` (Apache-2.0), `BUILD_LOG.md` (first dated entry: "build window opened 2026-10-26; all code written in-window"),
  `ATTRIBUTIONS.md` (skeleton table: component, licence, use), and a `README.md` placeholder (title, tagline, "work in progress"). First
  commit: `chore(p01): initialize repository with design docs`. **Check `git log --format=%cI` ≥ 2026-10-26.**
- **P01.S02 Agent scaffolding.** Create `.agents/{STATE.md,DECISIONS.md,BACKLOG.md,LESSONS.md}`, `.agents/prompts/`, and
  `.agents/phases/P01-setup/{BRIEF.md,COUNCIL.md,CHANNEL.md,GATE.md}` from the `AGENTS.md` templates. `STATE.md` holds the phase,
  stage, active agents, background jobs (none yet), blockers, next action, and the deadline countdown.
- **P01.S03 Runtime ADR.** Record `ADR-0001 · runtime`: which agent runtime is ORCH (Claude Code / OpenCode / Antigravity / Muse Code),
  how subagents are spawned, whether worktrees are available, and the model IDs in use (`AGENTS.md` §16).
- **P01.S04 Python project scaffold.** `uv init --package --name Kodiac-robotics`; `src/Kodiac_robotics/` with the package
  directories from `ARCHITECTURE.md` §3.1, each with an `__init__.py` docstring stating its responsibility. `pyproject.toml` from
  `TOOLS_AND_REQUIREMENTS.md` §12 (Python 3.12, extras). The console script `Kodiac` ships with only `--version` and `doctor` (P01.S08).
  **Do not register commands that don't work yet.**
- **P01.S05 Contracts (frozen).** Implement `src/Kodiac_robotics/contracts/core.py` exactly as in `ARCHITECTURE.md` §4 (field names
  binding). Add `contracts/schema_export.py` (writes JSON Schemas to `docs/schemas/`). Tests: model round-trip (`model_dump_json` →
  `model_validate_json`), enum values, `Verdict.CANT_TELL` serialization, `ReasonCode` coverage. Tag `contracts-v1` after the gate.
- **P01.S06 Config & cache.** `config.py` (`Settings` from env + optional `Kodiac.toml`: backends, model IDs, thresholds, cache dir).
  `cache.py`: `cached_call(key_parts: dict, fn) -> bytes|dict` with a sha256 key over canonical JSON + input-bytes hashes, an atomic
  write, and hit/miss logging. Tests: same key → hit; different params → miss; corrupted file → recompute.
- **P01.S07 Tooling & CI.** `ruff` (lint + format), `pytest` config (markers `slow`, `live`, `gpu`; `--timeout=300`), `pre-commit`
  (ruff, end-of-file, `detect-secrets` baseline). `.github/workflows/ci.yml`: `uv sync --extra dev`, `ruff check`,
  `pytest -m "not slow and not live and not gpu"`. CI must run with **no network secrets**.
- **P01.S08 `Kodiac doctor`.** A real command that checks the Python version, ffmpeg, env-var **presence** (`MODEL_API_KEY`, `HF_TOKEN`, Modal
  token), reachability of `api.meta.ai`, GPU availability, and optional extras. It prints a Rich table, exits 0 only if the core is usable, and
  never prints secret values.
- **P01.S09 Smoke-test suite.** `scripts/smoke/st01_models.py … st13_sdm.py` implementing ST1–ST13 from `TOOLS_AND_REQUIREMENTS.md` §11.
  Each writes `artifacts/p01/smoke/stNN.json` with `{ok, latency_ms, notes, evidence_path}` and uses tiny test media
  (generate a 50-frame H.264 clip from one ManiSkill episode, or a synthetic red/green block clip with OpenCV, if ManiSkill isn't ready yet).
- **P01.S10 Run the smoke tests** (with keys provided by 👤). Record every result in `.agents/DECISIONS.md` as `ADR-0003 · stack facts`:
  SAM model ID string, **hosted latency for the 6-frame pack and the 50-frame backward window**, Spark/Wonder crop latency, Voice turn
  behavior, Muse Code Stop-hook block semantics, Modal cold start, ManiSkill render path, gated-weights status, partner credits, and
  whether Muse Code is billed.
- **P01.S11 SDM channel.** Verify Option A (`opencode run --help`, then a 1-question ruling with DeepSeek V4.1 Flash) and/or Option B
  (Antigravity + Gemini 4 Argon; headless if available). Fall back to C/D per `AGENTS.md` §6.2. Record `ADR-0002 · SDM channel`, with the
  exact command template.
- **P01.S12 Modal foundation.** 👤 provides the tokens. Create Secrets `meta-model-api` and `huggingface`, and Volumes `hf-cache`, `gl-cache`,
  `gl-replays`, `gl-pool`, `gl-uploads`. Deploy `modal/hello_cpu.py` (asgi) and `modal/hello_l4.py`, then delete the hello apps after ST8.
- **P01.S13 Human checklist.** Write `HUMAN_TODO.md` (top-level, gitignored if it contains personal details; otherwise committed without
  secrets): claim the Meta $150 credit + spend limit; Modal/Baseten/Fireworks forms; request `facebook/sam3.1` access; reserve
  `Kodiac-robotics` on PyPI; create the private GitHub repo; Discord channels; attend Agents 102 (Oct 28 16:00 UTC) and the Fireworks session
  (Oct 30 16:00 UTC); post the `#office-hours` questions from `HACKATHON.md` §12; confirm the I16 closing-line change.
- **P01.S14 Docs skeletons.** `docs/VIDEO_NUMBERS.md` (table: number, value, source artifact, commit), `experiments/README.md`,
  `tests/fixtures/README.md` (recording format for SAM/Spark responses), `docs/DEMO_FILMING_GUIDE.md` (stub sections filled in P02), and **`docs/features.yaml`** seeded with F01–F60 `{id, name, tier, status: planned, evidence: null}` (source of truth for DOC-RECONCILE and the shipped table).
- **P01.S15 Gate & push.** Fill `GATE.md` with evidence. Commit and push (if 👤 has created the remote; otherwise record "push pending remote" as
  a blocker). Tag `p01-done` and `contracts-v1`.

**Suggested task split (Two-stage gated DAG ⟲ changed in P01 ruling).**
- Stage 1 (Sequential prerequisite): IMPL-1: S04–S07 (`pyproject.toml`, `src/Kodiac_robotics/{contracts,config.py,cache.py}`, `tests/unit/`, CI).
- Stage 2 (Parallel execution once Stage 1 `uv sync` succeeds):
  - IMPL-2: S08–S10 (`src/Kodiac_robotics/cli.py` doctor, `scripts/smoke/`, `artifacts/p01/`)
  - IMPL-3: S11–S12, S14 (`modal/`, `docs/*` skeletons, SDM channel scripts in `scripts/sdm/`).
- Stage 3: ORCH: S00–S03, S13, S15.
*(Credential SLA: 1.0 h wait max before ST1–ST13 switch to `--mock` fixture mode with `status: PENDING_KEY`, `latency_ms: null`, `is_fixture: true`).*

**Exit gate.**
- [ ] CI green on GitHub (or locally if the remote is pending) · `ruff` clean · contract tests pass · `contracts-v1` tag.
- [ ] `Kodiac doctor` exits 0 on the dev machine.
- [ ] ST1–ST13 each recorded as ok / failed / pending, with evidence. **Measured hosted SAM latency** is recorded.
- [ ] ADR-0001 (runtime), ADR-0002 (SDM channel), ADR-0003 (stack facts) exist.
- [ ] `HUMAN_TODO.md` delivered; human-blocked items are listed in `STATE.md`.

**Tripwires.**
- Hosted SAM 50-frame window > 6 s → the P03 council must evaluate Modal-hosted SAM for the live path (cost escalation).
- Muse Code Stop hook doesn't block → the KD-11 fallback (wrapper gate) becomes the plan.
- No ManiSkill rendering anywhere → MuJoCo cookbook harness (KD-12 fallback).

**👤 Human items.** Credits, keys, accounts, gated access, PyPI reservation, GitHub repo, attending Agents 102, confirming I16.

---

## P02: Data & Simulation Foundation

**Goal.** A working ManiSkill3 StackCube harness with a span-logged robot API; the 10 seeded bugs; the **proof practice pool generation
running in the background**; a pre-registration draft; dataset loaders; hero-clip candidates; the real-footage labelling setup.
**Why it matters.** The headline proof (I8) needs compute time. It must start now. The `/goal` loop and `blame`'s code line both depend on this harness.

**Council focus questions.**
1. Pool design: what mix of weak-policy rollouts vs. perturbed-expert near-misses gives oracle success of 40–60% **and** enough near-misses a 2 fps judge misses?
2. Which policy (state DP vs. ACT vs. BC-MLP) trains fast enough for 10+ arms × 3 seeds on our Modal budget? Measure one run.
3. Is `control_freq=30` stable for the motion planner? If not, what's the honest frame-rate story?
4. Which public datasets most likely contain hero failure clips with a clear view?

**Steps.**
- **P02.S01 ManiSkill env wrapper** (`src/Kodiac_robotics/sim/env.py`): `StackCube-v1`, Panda, **`sim_freq=120, control_freq=30`**, **`max_episode_steps` = 2× measured expert length (ADR)**, fixed 512×512
  render camera, `render_mode="rgb_array"`, deterministic seeds. Expose `privileged_state(t)` (cube poses, gripper width, contacts) **for
  eval only**, and `oracle_success()`.
- **P02.S02 Video writer.** Render each control step to frames → H.264 `yuv420p` MP4 at 30 fps (PyAV). Save `{episode}.mp4`,
  `{episode}.state.npz`, and `{episode}.meta.json` (seed, oracle success per step, perturbation onset frame if any).
- **P02.S03 Robot API + span logger** (`sim/robot.py`, `sim/spans.py`): `arm.move_to(kind, target)`, `arm.lift(z)`,
  `arm.retract()`, `gripper.open()/close()`, `wait(s)`, implemented over ManiSkill's motion-planning solution utilities. Each call is wrapped
  by `@span(cls=…)`, recording `{span, file, line, func, code, class, step_start, step_end}` (caller file/line via `inspect`).
  Write `runs/<id>/spans.jsonl`.
- **P02.S04 `examples/sim/pick_place.py`** (correct program; `ARCHITECTURE.md` §10). Verify that the oracle reports success on **10/10 seeds**.
- **P02.S05 Seeded bug registry** (`sim/bugs.py` + `examples/sim/bugs/B01.patch … B10.patch`): B1 early release (`open()` moved before `arm.move_to("above","green_block")`) · B2 xy offset +3 cm ·
  B3 lift 0.10 → 0.01 m · B4 no wait · B5 lift before close · B6 grasp z +3 cm · B7 missing close · B8 wrong object · B9 never opens · B10
  place z +6 cm. Each entry records the expected blame class and expected span. Test: each patched script runs, oracle fails (or the
  expected outcome is recorded), and the span log contains the expected span. **Assert an oracle FAIL for every bug.**
- **P02.S06 π0 weak policy** (`proof/pi0.py`, Modal L4 function in `modal/proof_train.py`). Generate 20–50 expert demos with the motion
  planner (**do not** use `--only-count-success` for practice data). Convert all expert/perturbed episodes to the policy control mode with `replay_trajectory` (pd_joint_pos → pd_ee_delta_pos); the pool stores one control mode. Train ManiSkill's **state-based Diffusion Policy** (or ACT; council
  decides) for a short budget. Target oracle success 30–60% on 100 eval episodes. Record the training time per run (drives the P08 budget).
- **P02.S07 🔁 Practice pool generator** (**precondition:** `prereg-v0` tagged and pushed: pool_config.yaml, thresholds, arms, metrics, seeds, stopping rule) (`proof/pool.py`): ~70% π0 rollouts + ~30% perturbed-expert episodes (early open, xy offset
  U(1,6) cm, low lift, short dwell, regrasp). Pre-registered distribution parameters live in `experiments/pool_config.yaml`. Target total
  ≈ 600–1,000 episodes. Write the manifest `experiments/pool/manifest.parquet` (episode_id, split ∈ {calibration, train}, video URI,
  state URI, oracle_success, perturbation_type, onset_frame). Launch on Modal → `STATE.md` background_jobs.
- **P02.S08 Pre-registration draft** (`experiments/PREREGISTRATION.md`): hypotheses H1 (Kodiac's false-PASS < each baseline's),
  H2 (downstream success Kodiac > single-pass Spark), H3 (salvage ≥ Kodiac); task; pool config; arms (`IDEA.md` F44 list);
  `stackcube.green` oracle-matched thresholds (`align_xy_cm<=3.33, gap_cm<=0.5`); CAN'T TELL = not accepted; fixed gradient steps; 3
  seeds; ≥200 eval episodes per seed; metrics + statistics (`ARCHITECTURE.md` §5.7); stopping rule; the minimal fallback version. The council
  finalizes it. Also pre-register: the engine-agreement target (BA, coverage); the RoboRewardBench rule (5 = success); truth = oracle `success` at the final step; policy trained from scratch on {clean demos ∪ accepted set} for N fixed gradient steps; size-matched control = random oracle-successes with |set| = |Kodiac accepted|; k% = false-PASS rate; all judge metrics on the **training split**; the calibration split divided into fit (≈100) / validate (≈100). **Tag `prereg-v0` before P02.S07 launches and `prereg-v1` before any judge label is inspected; push each tag at once and run `ots stamp experiments/PREREGISTRATION.md`.**
- **P02.S09 `examples/stackcube.green`** written from the pre-registration (handwritten now; in P05 it must be reproduced by `--from-text` and
  diffed). Also `examples/stack_blocks.green` (the source spec's example, verbatim) for golden parsing tests later.
- **P02.S10 Dataset loaders** (`io/lerobot.py`): `lerobot://repo/episode[/camera]` → `Clip` (H.264 transcode, native fps, metadata:
  task string, global index). Test on `lerobot/droid_100` episode 0 and one SO-100/101 community dataset.
- **P02.S11 🎬 Hero-clip search** (`scripts/find_hero_clips.py`): scan candidate datasets (DROID, popular LeRobot pick/place sets) by
  task keywords; export thumbnails + short MP4s of candidates to `artifacts/p02/hero_candidates/` with `index.md`. Rank candidates by expected |m|/σ from a quick full-path run (keep |m| ≥ 3σ; prefer gross failures: never placed, dropped, wrong object); record resolution/fps; target ≥1 source at ≥480p/30 fps (LeRobot SO-100/101). If `droid_100` episode 42 is used, label it "also reported by the community (HF discussion #2)". **👤 reviews the shortlist.**
- **P02.S12 🔁 Real-footage benchmark prep** (BG-C): (a) a DROID slice manifest (≈200): the success stratum from keyword-filtered `droid_1.0.1` task strings; the failure stratum from the ~58 instructed failures + ≤40 with 👤-written task strings (≈1 h), or FailBench/RoboArena rollouts; stratify by **our** blind labels; DROID's own flag is reported as an extra judge; (b) a local labelling tool (`scripts/label_tool.py`: a static HTML page with a video player + PASS/FAIL/UNSURE buttons →
  `experiments/labels/droid_slice_<annotator>.jsonl`), blind to judge outputs; (c) fetch RoboRewardBench test-split metadata; (d) check whether
  FailBench data is released (record in DECISIONS); (e) **time-saved instrumentation:** the label tool logs seconds-to-decision per episode in two randomized modes, *scrub* (plain video) and *blame* (jump to t* with overlay + diff), on a **separate** set of ≥40 audit candidates (never the blind benchmark slice) → `experiments/labels/timing_<annotator>.jsonl`.
- **P02.S13 Baseline-judge spike** (`proof/judges/robometer.py`, `proof/judges/topreward.py`, Modal L4): run Robometer-4B and TOPReward
  (LeRobot v0.6 `lerobot.rewards`) on 5 pool clips; record VRAM, latency, and output format. If OK → 🔁 launch baseline labelling as soon as the pool's
  calibration split is ready.
- **P02.S13b Single-pass baseline judge** (`proof/judges/single_pass.py`): `muse-spark-1.3` on the whole clip at 2 fps (≤50 frames as images or `input_video`), yes/no schema, cached (ARCHITECTURE §8.5).
- **P02.S14 Golden fixture set** (`tests/fixtures/clips/`): ≤2 MB each: correct run, B1, B2, B9, one occluded variant (painted), plus
  manifests with sha256. Large media live on the Modal volume / HF with manifest references.
- **P02.S15 Filming guide** (`docs/DEMO_FILMING_GUIDE.md`): 30–50° camera elevation; ≥2 resting objects at different depths; known block
  sizes (4 cm); pause ≥0.7 s between instructions; plain background; 720p; ≤15 s.

- **P02.S16 Appearance benchmark** (`proof/appearance.py`, `experiments/appearance/manifest.parquet`): ≥60 labelled `looks()` clips: (a) a ManiSkill3 articulated cabinet/drawer scene (verify the asset in ST9) scripted to end flush vs. 1–5 cm ajar, ground truth from the joint position; (b) ≥20 real DROID "close/open the drawer" episodes, 👤 blind-labelled (BG-C). Feeds F25–F27, ablation rungs R2–R4 (P08.S07), the open-weights row (P06.S10) and one curated live appearance example (P09.S03). Owner: IMPL-2.
**Suggested task split.** IMPL-1: S01–S05 (`src/Kodiac_robotics/sim/**`, `examples/sim/**`, `tests/sim/**`) · IMPL-2: S06–S09, S13
(`src/Kodiac_robotics/proof/**`, `modal/proof_*.py`, `experiments/**`) · IMPL-3: S10–S12, S14–S15 (`src/Kodiac_robotics/io/lerobot.py`,
`scripts/`, `tests/fixtures/`, `docs/DEMO_FILMING_GUIDE.md`).

**Exit gate.**
- [ ] Correct `pick_place.py` → oracle success 10/10 seeds; MP4 at 30 fps plays; span log present.
- [ ] B1–B10 each reproduce their expected outcome deterministically (test passes).
- [ ] π0 oracle success measured (target 30–60%) and the training time per run recorded.
- [ ] Pool generation running with ≥25% complete, or done; manifest schema validated.
- [ ] `PREREGISTRATION.md` draft approved by the council (tag `prereg-v1` may follow in P03, but **before** any label is revealed).
- [ ] LeRobot loader exports playable H.264; hero candidates index exists; the labelling tool works; baseline spike result recorded.

**Tripwires.** π0 success outside 20–70% → adjust demos/steps before the pool. The baselines OOM on L4 → A10G/A100 for those jobs (cost
estimate first). ManiSkill at 30 Hz unstable → render at 20 Hz and report native fps honestly (update IDEA/ARCH via doc-sync).

**👤 Human items.** Review hero candidates; start DROID-slice labelling (BG-C; ≈ 1–2 h total); record the webcam demo (P05 needs it; follow
the filming guide).

---

## P03: Perception Core (SAM 3.1 segmentation & tracking)

**Goal.** Reliable masks with stable IDs from three interchangeable backends (hosted API, Modal weights, fixture replay), native backward
tracking over exact windows, keyframe packing, and **measured latency and cost**, including the KD-05 alternative.
**Why it matters.** SAM 3.1 is the measuring instrument (I14). Its speed decides whether the <12 s live claim is possible.

**Council focus questions.**
1. From the P01 latency numbers: what is the fastest *correct* live locate strategy: 6-keyframe bisect vs. a subsampled full-clip pass? (KD-05 test design.)
2. Re-ID across keyframe calls and window calls: concept label + colour histogram + continuity. Is that enough for two same-shape cubes?
3. How do we keep CI free of network while still covering the API backend? (Fixture design.)

**Steps.**
- **P03.S01 IO core** (`io/clip.py`, `io/transcode.py`, `io/windows.py`): `open_clip(ref)` for file / lerobot / sim / upload; ffprobe
  metadata; normalize to H.264 `yuv420p` (even dimensions); `cut_window(clip, f0, f1)` (frame-accurate; pads to ≥50 frames when needed
  and records the true range); `pack_frames(clip, indices)` → a small MP4 plus an index map; a frame accessor with an LRU cache; the native-fps time base.
- **P03.S02 Hosted SAM backend** (`segment/api.py`): adapt the cookbook `sam_api.py` streaming adapter + `meta-sam-parser`; text prompts
  and box prompts (`build_object_prompt`); `propagation_direction`; `include_confidence`; sort records by frame; convert box-local masks
  → full-frame COCO RLE; retries with backoff; `cached_call` keyed by (model, prompt, direction, clip sha). **Never send text and object
  prompts together.**
- **P03.S03 Modal SAM backend** (`segment/modal_backend.py`, `modal/sam31.py`): the image recipe from `docs/research/03_tools_research.md`
  §7.2 (`use_fa3=False` on L4); `handle_request` / `handle_stream_request` with `start_frame_index` + `max_frame_num_to_track`;
  scale-to-zero; returns RLE masks; the HF cache volume. Batch entrypoint `track_many(manifest)`.
- **P03.S04 Fixture backend** (`segment/fixture.py`): replays recorded `output_text` (or decoded RLE JSON) by request key; the
  `scripts/record_fixtures.py` recorder (supporting dual-mode `--synthetic` offline bootstrap and `--live`); CI uses `Kodiac_SAM_BACKEND=fixture`.
- **P03.S05 Prompt sets & effector aliasing** (`segment/prompts.py`): per-role prompt sets (robot gripper / end effector / gripper fingers vs.
  hand); clip-type detection by the higher score on the first keyframes.
- **P03.S06 Re-ID & track assembly** (`segment/reid.py`, `segment/tracks.py`): match objects across keyframe calls and window calls
  (prompt label, eroded-core HSV histogram, centroid velocity continuity, coarse categorical Hue gating, IoU); merge `both`-direction outputs; enforce ≤16 objects; IoU(fwd, bwd)
  consistency → a confidence flag.
- **P03.S07 Latency & cost benchmark** (`scripts/bench_sam.py` → `artifacts/p03/sam_bench.json`): n ≥ 20 runs each of: 6-frame pack
  (text), single-frame probe (image mode), 50-frame backward window (box seeds), subsampled full-clip pass (10 fps, ≤150 frames). Report p50/p95,
  billed frames, $. Formalize **ADR-0008 · live locate strategy** (KD-05 decision; Two-Stage Bisect primary, 8.0s p95 gate to subsampled fallback).
- **P03.S08 Quality check on golden clips** (`tests/segment/test_quality.py`, `slow`): mask IoU vs. sim ground-truth segmentation
  (ManiSkill can render segmentation; use it as GT); ID swap count; backward vs forward IoU. Record in `artifacts/p03/quality.json`.
- **P03.S09 Debug overlay renderer** (`render/overlay.py`): mask outlines, centroid crosshairs, and bottom anchors in categorical hues at native resolution; decoupled from P04 verdicts.
- **P03.S10 🔁 Pool tracking** (BG-A): Modal batch full-path tracking for every pool episode (needed for Kodiac labels in P04). Store
  RLE tracks on the `gl-pool` volume. Poll status at each stage transition.
- **P03.S11 🔁 Baseline labels** (BG-A): run single-pass Spark (2 fps), Robometer-4B, and TOPReward over the **calibration split first**, then
  the train split; write `experiments/labels/<judge>.parquet` (`JudgeLabel`). Labels are written but **not analysed** until `prereg-v1` exists.
- **P03.S12 Tag prereg.** If not done in P02: commit `PREREGISTRATION.md` final + tag `prereg-v1` **before** any label analysis.

- **P03.S13 ⚡ Walking skeleton (ORCH-owned, throwaway)** (`scripts/skeleton.py`): hosted SAM 3.1 masks on `tests/fixtures/clips/b01_early_release.mp4` and real `HERO-DROID-001` → minimal `on` + `moves_with` → verdict → template blame line → card PNG with badge `[PROTOTYPE · UNCALIBRATED GEOMETRY]`. Record terminal take into `video/backup/`. **Exit-gate item.**
- **P03.S14 Proof arms** (`proof/arms.py`): accepted sets for every arm from `JudgeLabel` + oracle + prereg seeds (size-matched control, k% doses), so P04.S15 can train. Owner: IMPL-3.
**Suggested task split.** IMPL-1: S01, S09 (`io/**`, `render/overlay.py`) · IMPL-2: S02, S04, S05, S07 (`segment/api.py`,
`segment/fixture.py`, `segment/prompts.py`, `scripts/bench_sam.py`, `scripts/record_fixtures.py`) · IMPL-3: S03, S06, S08, S10
(`segment/modal_backend.py`, `segment/reid.py`, `segment/tracks.py`, `modal/sam31.py`). ORCH: S11–S12 (background jobs).

**Exit gate.**
- [ ] All three backends return `Track`s for golden clips; CI (fixtures) green.
- [ ] Backward propagation verified on the hosted and Modal backends.
- [ ] Modal vs hosted mask IoU ≥ 0.8 on the same clips (or the discrepancy documented).
- [ ] `sam_bench.json` + ADR-0008 written (live locate strategy decided with numbers).
- [ ] Pool tracking ≥50% complete; baseline labelling running; `prereg-v1` tagged.
- [ ] **Walking skeleton runs end to end** on sim B1 + one real clip (P03.S13).

**Tripwires.** Mask IoU vs GT < 0.7 on cubes → tune prompts / box seeding before P04. Hosted p95 window > 6 s → escalate the KD-03 cost option.

---

## P04: Measurement Engine (`Kodiac run`, full path)

**Goal.** Turn masks into measured facts and honest verdicts: the scale model, the 6 predicates, smoothing, σ + gates, the 3-valued step
chain with carried literals, the verdict + reason codes + exit codes, evidence frames, the verdict card v1, and `trace.jsonl`, all validated
against sim ground truth.
**Why it matters.** This is the core of "measured, not guessed" (I6) and of `CAN'T TELL` (I3). Tech-depth judges will read this code.

**Council focus questions.**
1. Scale Tier B on the 512×512 sim camera and on DROID: is the ground-plane fit stable? What's the fallback?
2. Is λ (σ inflation) calibrated on the *calibration split only* (no leakage into the proof)?
3. Do the occlusion-gate exclusions (carried object, container contents) prevent constant false CAN'T TELL during grasps?
4. What oracle-agreement target is credible and pre-registered (e.g., balanced accuracy ≥ 0.90 with coverage ≥ 0.85 on sim)?

**Steps.**
- **P04.S01 Anchors & measurements** (`geometry/anchors.py`): bottom/top anchors, centroid, bbox, area, expected area `â`, occlusion fraction.
- **P04.S02 Scale model** (`geometry/scale.py`): size priors (from `.green` attributes / priors table), per-object k, Tier A (sim intrinsics from
  ManiSkill camera params), Tier B ground-plane least squares, Tier C fallback; `ScaleModel.fit()` reports its tier. Tests vs sim GT (Tier A
  exact within 0.3 cm; Tier B within the documented σ).
- **P04.S03 Predicates** (`predicates/{on,inside,near,lifted,moves_with,dwell}.py`), each returning per-frame `PredFrame` with components
  (value, threshold, margin, σ, unit, tri) per `ARCHITECTURE.md` §7.3. `inside` = MVP-lite (in-rim + depth consistency + front-occluder);
  full rim memory is Strong (P06 ⚡ if time allows).
- **P04.S04 Smoothing & hysteresis** (`engine/smoothing.py`): Hampel(7) → Savitzky–Golay(≈0.2 s) → Schmitt trigger (n_on); U frames neutral.
- **P04.S05 Uncertainty** (`uncertainty/sigma.py`, `uncertainty/montecarlo.py`, `uncertainty/calibrate.py`): σ_px estimator, Monte-Carlo S=256
  (vectorized numpy), λ fitted on the **calibration split** sim GT (target coverage ≈ 68% at 1σ). Write `artifacts/p04/lambda.json`.
- **P04.S06 Gates** (`uncertainty/gates.py`): G1–G6 with reason codes and exclusions (`ARCHITECTURE.md` §7.4).
- **P04.S07 Logic & step chain** (`engine/logic.py`, `engine/steps.py`): Kleene ops; expression evaluation over frames; achievement times;
  carried literals; the step verdict rule; overall verdict = first non-PASS step; MANUAL listing.
- **P04.S08 Run orchestration (full path)** (`pipeline/run.py`): `run(test, clip, mode="full") -> RunResult`; nonce; timings; backends; badges;
  writes `runs/<id>/{result.json,trace.jsonl}`, plus `.Kodiac/last_verdict.json`. Exit codes 0/1/2/3. Supports `run(..., tracks=<stored>)` to replay stored tracks with no SAM calls (needed by P04.S14).
- **P04.S09 Trace** (`engine/trace.py`): orjson JSONL writer; every Component/PredFrame/gate carries a `trace_id`; optional Rerun logging (`render/rerun_log.py`, `[viz]` extra).
- **P04.S10 Evidence & card v1** (`render/evidence.py`, `render/card.py`): the decisive frame with outlines and the measured number burned in; the
  verdict card layout from `ARCHITECTURE.md` §1.1 (blame strip added in P06). Snapshot tests on the golden clips.
- **P04.S11 CLI `Kodiac run`** (`cli.py`): `Kodiac run <test.green> <clip-ref> [--camera] [--mode full] [--json] [--card]`, using the
  terminal formats in `ARCHITECTURE.md` §1.2. Temporary test loading: a minimal JSON/`.green` loader for `examples/stackcube.green` until P05's
  grammar lands (owned by `compiler/`; if P05.S01 ⚡ is done, use it).
- **P04.S12 Sim validation** (`scripts/validate_engine.py` → `artifacts/p04/validation.json`): on ≥100 **calibration-split** episodes —
  predicate accuracy vs privileged state; verdict vs oracle (confusion matrix, BA, coverage, false-PASS); per-gate firing rates.
  **Use only the calibration split** (λ fitted on the fit half, validated on the validate half). The train split is for the proof. Also export `artifacts/p04/sigma_calibration.png` (predicted vs. true margin; 1σ coverage) for the README.
- **P04.S13 Occlusion & view-blocked tests** (`tests/engine/test_cant_tell.py`): painted occluders (30%, 50%, 80%), a black frame, blur →
  CAN'T TELL with the correct reason codes; partial occlusion < 40% stays decided.
- **P04.S14 🔁 Kodiac labels on the pool** (BG-A): run the full path with `examples/stackcube.green` on all pool episodes (Modal CPU
  workers reading the stored tracks) → `experiments/labels/Kodiac.parquet`.
- **P04.S15 🔁 Train baseline/oracle/control arms** (BG-A): for the judges whose labels are complete (oracle, accept-all, size-matched random,
  injected-noise doses, baselines), launch training × 3 seeds (fixed gradient steps from the prereg) on Modal in parallel.

**Suggested task split.** IMPL-1: S01–S02, S05–S06 (`geometry/**`, `uncertainty/**`) · IMPL-2: S03–S04, S07 (`predicates/**`,
`engine/smoothing.py`, `engine/logic.py`, `engine/steps.py`) · IMPL-3: S08–S11, S13 (`pipeline/run.py`, `engine/trace.py`, `render/**`, `cli.py`
run command). ORCH + D-team: S12 (validation script owned by IMPL-3 after integration), S14–S15 background.

**Exit gate.**
- [ ] Unit + property tests for every predicate, gate, and logic op; ruff clean.
- [ ] `validation.json`: oracle agreement meets the pre-registered target (BA and coverage reported with Wilson CIs); λ calibrated.
- [ ] CAN'T TELL tests pass with correct reason codes.
- [ ] `Kodiac run examples/stackcube.green tests/fixtures/clips/b01.mp4` → FAIL, exit 1, a card and trace produced (fixture backend, no network).
- [ ] Kodiac pool labelling running; baseline arm training launched.

**Tripwires.** BA < 0.8 on sim → the mini-council (D3 + ORCH) diagnoses which predicate is wrong before P05 dispatch. False CAN'T TELL > 25% on
clean sim clips → revisit the gate exclusions.

---

## P05: `Kodiac test` Compiler (Show It Once)

**Goal.** Voice + demo → canonical 4-line `.green` + `.green.lock`, with provenance, linter, SAM type-check, effector aliasing, demo self-test,
and text-compile mode.
**Why it matters.** "Show it once" is the new capability (I2). It is beat 0:24–0:50 of the video.

**Council focus questions.**
1. Prompt + schema design for Spark: how do we guarantee structure from 3 instructions without letting the LLM invent thresholds?
2. Turn-level timestamps only: is `ENDPOINTING` + pauses enough, or do we need MMS_FA?
3. The threshold slack table: which formulas generalize from a human demo to robot attempts (different cameras)?

**Steps.**
- **P05.S01 ⚡ Grammar, parser, printer** (`compiler/grammar.lark`, `compiler/parser.py`, `compiler/printer.py`): `ARCHITECTURE.md` §6.1;
  provenance binding; canonical 4-line printer; round-trip tests; **golden test: the source spec example parses verbatim**
  (`examples/stack_blocks.green`).
- **P05.S02 ⚡ Linter** (`compiler/lint.py`): E001–E005, W101–W105; the non-visual keyword ontology (force, torque, weight, temperature,
  sound, gently, firmly, slam, current); comparator directions per parameter.
- **P05.S03 ⚡ ASR client** (`compiler/asr.py`): Muse Voice one-shot HTTP (cookbook `transcribe_recording` pattern), `ENDPOINTING`;
  WAV extraction via ffmpeg; turns → clause windows; cached. Optional `compiler/align.py` with torchaudio `MMS_FA` (behind the `[proof]`/`[viz]` extra).
- **P05.S04 Spark compiler** (`compiler/spark_compile.py`): structured output into a `GreenTest` skeleton (objects + steps + expressions,
  **numeric params as placeholders**); a few-shot prompt with the three IDEA examples; role inference (container/articulated); one retry on schema
  failure. Store the prompt in `compiler/prompts/compile_v1.md`.
- **P05.S05 Object type-check & baselines** (`compiler/typecheck.py`): SAM 3.1 segment on 2–3 demo keyframes per object prompt; E001/E002; record
  A0, k0, scores, and the rim ellipse for containers (OpenCV `fitEllipse` on the upper boundary); effector alias resolution.
- **P05.S06 Self-test & thresholds** (`compiler/selftest.py`, `compiler/slack.py`): run the engine (full path) on the demo with default
  params → demo events → thresholds from the slack table (`min_cm = max(1.0, ⌊0.5·demo_lift⌋)`, `align_xy = max(1.5, 3σ)`, `for_s = 0.5`,
  …) → re-run → require PASS with margin ≥ 2σ (E005/W103).
- **P05.S07 Lock file** (`compiler/lock.py`): `GreenLock` with test sha256, transcript, baselines, demo events (for `diff`), geometry tier, model IDs.
- **P05.S08 Text-compile** (`compiler/text_compile.py`): `--from-text "<task>" --first-frame <clip>`; existence check only; the
  defaults table or the oracle-matched table (`--profile stackcube`). **Verify it reproduces `examples/stackcube.green` exactly** (diff = empty).
- **P05.S09 CLI `Kodiac test`** (`cli.py` test command): `--webcam` (OpenCV capture ≤20 s), `--video`, `--from-text`, `--out`; the terminal format in `ARCHITECTURE.md` §1.2.
- **P05.S10 🎬 Human demo compile.** 👤 records `demos/stack_blocks_demo.mp4` (filming guide). The agent compiles it → a 4-line test → self-test PASS.
  Record the terminal take with VHS (`video/tapes/test.tape`) → `artifacts/p05/test_take.mp4`. Log in `VIDEO_NUMBERS.md`.
- **P05.S11 🔁 Audit compile** (BG-B): text-compile tests for the task strings of the audit datasets chosen in P02 (cache per dataset+task);
  launch batch full-path runs on the selected episodes (Modal) → `experiments/audit/<dataset>/verdicts.parquet`.
- **P05.S12 🔁 Kodiac arm training** (BG-A): once `Kodiac.parquet` is complete, launch Kodiac-arm training × 3 seeds.

**Suggested task split.** IMPL-1: S01–S02, S07 (`compiler/{grammar.lark,parser.py,printer.py,lint.py,lock.py}`, `tests/compiler/**`) ·
IMPL-2: S03–S04, S08 (`compiler/{asr.py,align.py,spark_compile.py,text_compile.py,prompts/**}`) · IMPL-3: S05–S06, S09 (`compiler/{typecheck.py,selftest.py,slack.py}`, `cli.py` test command).

**Exit gate.**
- [ ] The spec example parses verbatim; print∘parse round-trip is the identity on all examples.
- [ ] The human demo → 4 non-comment lines, every step with provenance, self-test PASS with margin ≥ 2σ, in < 15 s (measured).
- [ ] A missing object → E001; "gently" → `MANUAL` (W101); a wrong comparator → E004.
- [ ] Text-compile reproduces `stackcube.green` exactly and compiles ≥3 audit task strings.
- [ ] Audit batch running; Kodiac arm training launched.

**Tripwires.** The Voice turn count ≠ the instruction count in ≥2/5 trials → Spark clause-splitting on the transcript + MMS_FA. Self-test fails on
the human demo → a filming-guide issue (re-record) or a scale-tier issue (escalate).

---

## P06: Fast Path, Judge Layer, `blame` + `diff`

**Goal.** The live two-stage bisect fast path (validated against the full path); the frame-exact `t*` with a measured cause; the fact-bound
sentence; the event diff; the corrective hint; the code line for sim; prefix salvage; the two-way crop judge with Wonder escalation; and the
open-weights switch.
**Why it matters.** This is **the hero** (I4, I5): beat 0:50–1:20 and the core of the wedge against success detectors.

**Council focus questions.**
1. ADR-0004 chose the locate strategy. Does the bisect still satisfy "git bisect" literally, and is the dense window always backward-seeded?
2. Blame accuracy target vs. the perturbation onset (MVP: ±0.5 s on ≥70%; winning: ±0.3 s on ≥85%). What's achievable at 30 fps?
3. Which appearance task (lid/drawer/DROID) exercises `looks()` for the ablation ladder, and where do we get its clips?
4. The open-weights row: Muse Spark Open on Baseten vs. Glimmer on Modal. Which one is real by P08?

**Steps.**
- **P06.S01 Bisect scheduler** (`pipeline/bisect.py`): Stage 1 (K keyframes, packed; static proxies; prefix-max progress), Stage 1.5 (halving
  on the monotone target `F_L`), Stage 2 (window ≥50 frames, seeds = boxes on the last frame, backward), guards G-alias / G-miss / G-budget /
  G-pass, sparse verification windows for PASS steps. `engine.run(mode="fast")`.
- **P06.S02 Fast-vs-full agreement** (`scripts/agreement.py` → `artifacts/p06/agreement.json`): ≥100 clips (sim calibration split + real
  golden clips): verdict agreement ≥95%; t* within ±2 frames on ≥90%; latency p50/p95 per stage.
- **P06.S03 Transition finder** (`blame/transitions.py`): carried literals; classes (broken prerequisite / unmet / order violation / transient →
  warning).
- **P06.S04 t* refinement & fact table** (`blame/tstar.py`, `blame/facts.py`): detach-onset rule; piecewise-linear breakpoint;
  bootstrap σ_t*; facts incl. `dt_before_reference_s` (defined in `ARCHITECTURE.md` §9); dataset index / action chunk.
- **P06.S05 Summary + validator** (`blame/summary.py`, `blame/validate.py`): Spark gets the FactTable JSON + the `.green` text only; the validator
  (numbers, objects, licensed verbs, ≤30 words); retry once → template. **Test: an injected fabricated number is rejected.**
- **P06.S06 Diff** (`blame/diff.py`): event extraction for demo (lock) and attempt; Myers LCS on `(step, kind, predicate)`; unified-diff
  rendering with measurements; `camera-left` wording; golden snapshots.
- **P06.S07 Hint & code location** (`blame/hint.py`, `blame/codeloc.py`): the single-variable correction; span → `file:line -> code` mapping
  table (`ARCHITECTURE.md` §9).
- **P06.S08 Prefix salvage** (`blame/salvage.py`): `cut = t* − 0.5 s` (≥1.0 s); export for ManiSkill `.h5` and LeRobot; chunk-safe sampling mask.
- **P06.S09 Judge layer** (`judge/crops.py`, `judge/two_way.py`, `judge/client.py`, `judge/backends.py`): crops with outlines; the antonym
  question pair; the decision table; Wonder escalation (3 s live cap); backends `meta`, `baseten-spark-open`, `modal-glimmer`, `llamacpp-glimmer`;
  caching. Wire `looks()` atoms in the engine.
- **P06.S10 Open-weights deployment** (`modal/glimmer.py` and/or Baseten config): bring up **one** working open-weights backend (prefer Muse
  Spark Open on Baseten if credits arrived; else Glimmer GGUF via llama.cpp on L4; else vLLM image on H100 with scale-to-zero). Measure
  cost/latency per 1,000 crops.
- **P06.S11 CLI `blame` / `diff` + card v2** (`cli.py`, `render/card.py`): the blame strip timeline; terminal formats; `--json`.
- **P06.S12 Blame accuracy eval** (`scripts/eval_blame.py` → `artifacts/p06/blame_eval.json`): on calibration-split failures with known
  perturbation onset: |t̂* − t*| distribution, % within ±5 frames / ±0.5 s, cause-class accuracy; B1–B10 code-line accuracy (10/10 expected).
- **P06.S13 🎬 Hero beat assets.** Run `Kodiac run` / `blame` / `diff` on the 👤-approved real hero clip + a contrasting PASS + sim B1 → cards,
  terminal takes (VHS `video/tapes/blame.tape`), frames for the bisect animation. Log every number in `VIDEO_NUMBERS.md`.
- **P06.S14 🔁 BG polls.** Audit batch → candidate flags list for human review (`experiments/audit/<dataset>/candidates.html`); Kodiac
  salvage labels for the salvage arm → launch its training; eval jobs for finished arms.

- **P06.S15 CLI flags & Strong features** (`cli/run.py`, `blame/salvage.py`, `judge/backends.py`): `--sim <script> --seed N` (F41), `--salvage` (F36), `--local-glimmer` private mode that forces the self-hosted SAM backend + an open-weights judge for every pixel-bearing call (F27). ⚡ if time allows: full 2.5D `inside` with rim-crossing memory (F17).
- **P06.S16 🔁 First maintainer note (BG-E):** as soon as ≥5 audit flags are 👤-verified, draft one consolidated, polite report → 👤 approval → publish (KD-19).
**Suggested task split.** IMPL-1: S01–S02 (`pipeline/bisect.py`, `scripts/agreement.py`) · IMPL-2: S03–S08, S11–S12 (`blame/**`,
`cli.py` blame/diff, `render/card.py` strip, `scripts/eval_blame.py`) · IMPL-3: S09–S10 (`judge/**`, `modal/glimmer.py`, backend
configs). Scale to 4 implementers if needed: split IMPL-2 into blame-core (S03–S05, S12) and diff/hint/codeloc/salvage (S06–S08, S11).

**Exit gate.**
- [ ] `agreement.json` meets the targets; fast-path latency p50/p95 recorded on curated clips (the claim decision deferred to P09).
- [ ] `blame_eval.json`: MVP target met (±0.5 s on ≥70%); B1–B10 code-line 10/10.
- [ ] Validator test passes; diff snapshots pass; `Kodiac blame` and `diff` work end to end on fixtures.
- [ ] `looks()` works on at least one appearance clip, or is marked "not shipped" in the feature registry; ≥1 open-weights backend measured.
- [ ] Hero-beat assets produced and logged.
- [ ] **I16:** `Kodiac run` with the human-demo test on the human demo **and** on ≥1 robot clip → both verdicts logged.

**Tripwires.** Agreement < 90% → the fast path ships only for curated clips and the full path is used elsewhere (disclosed). Blame ±0.5 s < 50%
→ the mini-council; the video uses sim B1 (labelled) for the hero beat.

---

## P07: Muse Code Loop & Done-Gate

**Goal.** MCP `Kodiac.verify`, the `Kodiac gate` Stop-hook done-gate (pin + nonce + freshness + attempt cap), project config
templates, the `/goal` recipe, the B1–B10 fix-rate batch with transcripts, and **one unedited take**, plus the **backup video cut** (Nov 1).
**Why it matters.** I7 and the Best Agentic bonus: "a coding agent that cannot declare victory until a physical test passes."

**Council focus questions.**
1. ADR-0003 recorded the Stop-hook semantics. Does the gate need the PreToolUse `update_goal` deny too, or the wrapper fallback?
2. Anti-cheat: what are all the ways Muse Code could make the gate pass without fixing the program? (Edit the test, edit the thresholds, cache a PASS, edit the gate config, stub the sim.)
3. Is the fix-rate eval fair (≤5 iterations, no human hints, the same recipe text for every bug)?

**Steps.**
- **P07.S01 MCP server** (`loop/mcp_server.py`): `mcp` 2.x `MCPServer("Kodiac")`, tool `verify(VerifyRequest) -> RunResult+hint+evidence`
  (runs the sim script via `sim.run_script`, then `engine.run(mode="full")`, writes `.Kodiac/last_verdict.json`). Entry `Kodiac mcp`. Test with
  the MCP inspector or a client script.
- **P07.S02 Gate** (`loop/gate.py`, CLI `Kodiac gate`): `--init` pins the test/config hashes into `.Kodiac/gate_state.json`; on Stop: read the
  hook payload (stdin) + last verdict; checks (PASS ∧ hashes pinned ∧ nonce fresh vs. the newest mtime of watched sources ∧ blocks < max) → exit 0,
  else exit 2 with blame + diff + hint on stderr; increment blocks; never auto-pass on `stop_hook_active`. **Per ARCHITECTURE KD-11:** pins live outside the workspace (`~/.config/Kodiac/gates/<sha256(workspace)>.json`); the gate **re-runs** the pinned sim + test itself; it **never exits 3** (any error → exit 2, fail closed); with no `--init` state it exits 0. Loads keys from
  `Kodiac_ENV_FILE` (hooks get a cleared env).
- **P07.S03 Config templates & installer** (`loop/templates/{mcp.json,hooks.json,goal_recipe.md}`, CLI `Kodiac loop init`): writes the
  project `.mcp.json` (with `env` passthrough), `.muse/hooks.json` (Stop → `Kodiac gate`), and `GOAL.md` (the recipe text: "Done ONLY when
  Kodiac run prints PASS"). Optional `.claude-plugin/plugin.json` packaging (Muse Code imports it), documented in the README.
- **P07.S04 Anti-cheat tests** (`tests/loop/test_gate.py`): modified `.green` → refuse ("test modified"); modified thresholds → refuse; stale verdict
  after a code edit → refuse; a fabricated `last_verdict.json` → ignored (the gate re-runs); a PASS on another clip → refused; a missing/corrupt state or env file → exit 2; max-blocks → "GATE EXHAUSTED: goal NOT verified".
- **P07.S05 Rehearsal on B1** (interactive, ORCH or 👤): apply B1 → `/goal …` in Muse Code → observe verify → blame → patch → gate refusal → PASS.
  Fix the recipe wording until it works reliably (≤3 rehearsals; log lessons).
- **P07.S06 Fix-rate batch** (`proof/loop_eval.py`): for B1–B10: fresh workspace copy → apply the patch → `Kodiac gate --init` →
  drive each bug through `/goal` (via `@muse-code/sdk goal/set` if `/goal` is unavailable under `muse exec --trust-workspace`) headless → capture the transcript → check gate PASS ∧ oracle success ∧ hash unchanged within ≤5
  iterations. Write `artifacts/p07/loop_eval.json` + `artifacts/p07/transcripts/B##.md`. **Spend guard:** estimate Muse Code cost first (ADR-0003).
- **P07.S07 🎬 One unedited take.** Record the B1 fix in one take (asciinema for a TUI, or OBS for a GUI; 👤 if a GUI login is needed). Overlay labels
  "Simulation · unedited take". Save the raw recording + the transcript hash in `artifacts/p07/`.
- **P07.S08 🎬 Backup video cut** (`video/backup/`): stitch the available assets (audit placeholder card clearly marked DRAFT, test take, blame take,
  loop take, a chart template with *watermarked placeholder data*) into a ≤3:00 rough cut with the scripted VO text as captions. **It is a safety
  net, never submitted with placeholder numbers.** 👤 shows it to one non-roboticist **now**; their restatement goes to `LESSONS.md` and drives the script lock.
- **P07.S09 🔁 BG polls.** Evals for completed arms; audit candidates → ping 👤 for human verification (target ≥20 flags reviewed by the end of P08).

**Suggested task split.** IMPL-1: S01, S03 (`loop/mcp_server.py`, `loop/templates/**`, the `cli.py` loop/mcp commands) · IMPL-2: S02, S04
(`loop/gate.py`, `tests/loop/**`) · IMPL-3: S06, S08 (`proof/loop_eval.py`, `video/backup/**`). ORCH/👤: S05, S07.

**Exit gate.**
- [ ] Anti-cheat tests pass; a recorded gate refusal exists.
- [ ] `loop_eval.json` with N/10 + transcripts (MVP ≥5/10; winning ≥8/10), the same recipe for all bugs.
- [ ] One unedited take saved; the backup cut exists (`video/backup/backup_cut.mp4`).

**Tripwires.** The Stop hook isn't invoked in headless `muse exec` → use the interactive recording for the take + the wrapper gate for the batch
(disclosed). Fix rate < 3/10 → simplify the bugs' recipe hints? **No:** report the real rate; improve the blame hint quality instead.

---

## P08: Proof & Dataset Audit (go/no-go Nov 2 12:00 UTC)

**Goal.** The measured headline ("only the judge changed: +Y"), the judge benchmark (sim + real footage) with n and CIs, the ablation ladder,
the hand-verified audit with the Failure-Norm Digest and verdict export, and (human-approved) external validation.
**Why it matters.** Impact (30%) and Tech Depth (20%) hinge on these numbers. One unreproducible number is a kill-shot.

**Council focus questions.**
1. At go/no-go: which arms have complete training+eval with ≥3 seeds? Apply the pre-registered minimal fallback if not. **Never re-define the metrics after seeing results.**
2. Do all the numbers trace to `artifacts/` with commit SHAs? Is every metric computed exactly as pre-registered?
3. Audit wording: "published as successful demonstrations", "at least X%", "hand-verified". Is every shown flag human-verified?
4. Is the external-validation outreach polite, consolidated, and human-approved?

**Steps.**
- **P08.S01 Prereg check.** Verify the `prereg-v1` tag predates every label-analysis commit (`git log`). Record it in `GATE.md`.
- **P08.S02 Label consolidation** (`proof/labels.py`): merge all `JudgeLabel` parquets; apply calibration-split thresholds to score judges (max
  BA, the baselines' best case); CAN'T TELL = not accepted.
- **P08.S03 Judge metrics** (`proof/stats.py` → `experiments/results/judge_metrics.json`): false-PASS, contamination, false-REJECT, coverage, BA,
  AUROC with Wilson CIs; Holm-corrected McNemar pairwise vs Kodiac; all on the training split. **Time saved:** median seconds per episode, scrub vs. blame mode, bootstrap 95% CI, scaled to hours per 1,000 episodes → `experiments/results/time_saved.json`.
- **P08.S04 🔁 Training/eval completion** (BG-A): ensure all arms × 3 seeds are trained with fixed gradient steps and evaluated on ≥200 oracle
  episodes per seed (fixed eval seeds). **Go/no-go at Nov 2 12:00 UTC:** missing arms → minimal fallback (single-pass Spark, one reward model,
  Kodiac, Oracle, Accept-all × ≥2 seeds), disclosed.
- **P08.S05 Downstream stats + chart** (`proof/chart.py` → `experiments/results/headline.json`, `artifacts/p08/proof_chart.{png,svg}`):
  success mean ± 95% hierarchical-bootstrap CI; Δ(Kodiac − single-pass) with CI; the dose-response curve; the chart per `ARCHITECTURE.md` §1.4.
  🎬 Also export an animated build (Plotly/Manim) for the 1:50 beat.
- **P08.S06 Real-footage benchmark** (`proof/real_bench.py` → `experiments/results/real_bench.json`): RoboRewardBench test (binarized per the
  prereg rule), the DROID slice (👤 labels; κ if 2 raters), FailBench subsets if released. All judges where feasible; report n.
- **P08.S07 Ablation ladder** (`proof/ablation.py` → `experiments/results/ablation.json`): R1 SAM + predicates (looks → CAN'T TELL) → R2 + Spark
  single question → R3 + two-way → R4 + Wonder → R5 + calibrated σ, on a benchmark including appearance tasks. Phrase it as "each stage adds".
- **P08.S08 Audit finalization** (`audit/`): 👤 completes verification of the candidates (`Kodiac audit review` UI); compute N, X (lower
  bound), and the sampling description; `Kodiac audit digest` (deterministic histogram + Wilson CI → Muse Wonder narration + memory file);
  `Kodiac audit export` → `Kodiac_verdicts.parquet` + evidence; 🎬 audit card PNG + 3 hero verdict cards.
- **P08.S09 External validation (BG-E).** Draft one consolidated, polite report per dataset (`experiments/audit/<dataset>/report.md`) with the
  parquet + evidence links → **👤 approves** → `Kodiac audit publish --i-have-human-approval <ticket>` (KD-19). 👤 also contacts 1–2
  robotics researchers to try it (permission to quote).
- **P08.S10 Numbers registry.** Update `docs/VIDEO_NUMBERS.md` and the feature registry (`docs/features.yaml`: F##, tier, shipped status, evidence
  path). Doc-sync IDEA §8 phrasing with the measured values (concept version bump if wording changed).

**Suggested task split.** IMPL-1: S02–S05 (`proof/{labels,stats,chart}.py`, `experiments/results/**`) · IMPL-2: S06–S07
(`proof/{real_bench,ablation}.py`) · IMPL-3: S08 + S10 tooling (`audit/**`, `docs/features.yaml`, `docs/VIDEO_NUMBERS.md`). ORCH: S01, S04 go/no-go, S09 with 👤.

**Exit gate.**
- [ ] `headline.json` + chart with the measured Y and CI (whatever it is); prereg compliance verified.
- [ ] `judge_metrics.json`, `real_bench.json`, `ablation.json` exist with n and CIs.
- [ ] Audit: ≥20 (MVP) / ≥40 (winning) human-verified flags; digest; parquet; audit card.
- [ ] Every number in `VIDEO_NUMBERS.md` maps to an artifact + commit.

**Tripwires.** Y's CI includes 0 → keep the invariant sentence with the measured value; lead the chart with false-PASS/contamination (still the
story). Fewer than 10 verified flags → the opener uses the verified ones only; X wording adjusted.

---

## P09: Hosted Live App & Packaging

**Goal.** A public zero-login page (curated datasets, upload, webcam, occlusion brush, timer, labelled cached replay) on Modal CPU with rate
limits, upload hygiene, spend guard, and uptime monitoring; a clean installable package; a README first screen.
**Why it matters.** Demo (25%): "holds up live." A dead link during Nov 5–9 is a severe hit.

**Council focus questions.**
1. Measured p95 on curated clips: is "<12 s" claimable (n ≥ 30)? If not, what honest number do we show?
2. Failure modes under 50 concurrent judges: rate limits, the API 429, cold start. Is the cached replay always available?
3. Privacy of webcam uploads: retention, notice, no contributor-tier use.

**Steps.**
- **P09.S01 ⚡ UI** (`app/ui.py`): Gradio Blocks per the `ARCHITECTURE.md` §1.3 wireframe; tabs Dataset / Upload / Webcam; episode + camera pickers;
  the test selector (curated precompiled, example tests, or text-compile from a typed instruction); the Grade button; a client-side timer; the
  verdict card; diff; a frame scrubber around t*; badges; the "How it works" model table; honest limits; a privacy notice; a **Teach it live** tab (webcam + 3 spoken instructions → `Kodiac test` → the 4-line test on screen → record an attempt → verdict; timer on both; compile failure → friendly message + typed-instruction fallback); a friendly E001 message ("We couldn't find 'red block'. Try Teach it or an example test.").
- **⚡ P09.S02 API & guards** (`app/server.py`): FastAPI routes (`/grade`, `/health`, `/replay/<id>`); per-IP token bucket; 20 s / 50 MB caps;
  transcode; a typed error page; structured logs without PII.
- **⚡ P09.S03 Replay store** (`app/replay.py`, `scripts/precompute_replays.py`): precompute curated episodes (hero clips, B1 sim, a contrasting
  PASS, an occluded example) → the Modal Volume; **⚡ CACHED** badge; a "Re-run live" button.
- **⚡ P09.S04 Occlusion brush + webcam** (`app/occlusion.py`): `gr.ImageEditor` on frame 0 → rectangles applied to all frames before grading;
  webcam via `gr.Video(sources=["webcam"])` ≤15 s.
- **⚡ P09.S05 Modal deploy** (`app/modal_app.py`): CPU image (ffmpeg + package), `@modal.concurrent(max_inputs=20)`, `min_containers=1` scheduled for
  Nov 4–16 only, Secrets, volumes; `upload_reaper` scheduled function (24 h deletion); `spend_check` scheduled function (Meta API usage + Modal
  usage vs. caps → alert file / Discord webhook if 👤 provides one).
- **P09.S06 Uptime & latency** (`scripts/live_bench.py`, `.github/workflows/uptime.yml`): a GitHub Actions cron ping (free) hitting `/health` + one cached
  replay; `live_bench.py` runs n ≥ 30 live grades on curated clips → p50/p95 → `artifacts/p09/live_latency.json` → **claim decision ADR**.
- **P09.S07 E2E browser tests** (`tests/e2e/test_app.py`, Playwright): load the page, play a cached replay, run a live grade, occlusion → CAN'T TELL, an
  oversized upload → friendly error.
- **⚡ P09.S08 Packaging** (`pyproject.toml`, `scripts/release_check.sh`): build the sdist/wheel; install in a clean venv; `Kodiac --version`,
  `Kodiac run examples/... --backend fixture` works offline; `uvx --from dist/*.whl Kodiac`; a TestPyPI dry run. **Publishing to PyPI = 👤 approval.**
- **P09.S09 README v1** (`README.md`, `scripts/gen_readme_tables.py`): the first screen per `ARCHITECTURE.md` §1.6; generated tables (results from
  `experiments/results/*.json`; shipped status from `docs/features.yaml`); the model-role table; limits; build log + attributions links.
- **P09.S08b PyPI release (👤).** By Nov 3 12:00 UTC: 👤 approves publishing `Kodiac-robotics==0.9.x` (trusted publishing). Verify `pip install Kodiac-robotics && Kodiac --version && <quickstart>` in a clean venv **from PyPI**. If not approved, the video and README use `pip install git+https://github.com/<org>/Kodiac`.
- **⚡ P09.S10 Static mirror** (`site/`, GitHub Pages workflow): a landing page + cached replay cards + the video embed (used if Modal is down).

**Suggested task split.** IMPL-1: S01, S03–S04 (`app/{ui,replay,occlusion}.py`, `scripts/precompute_replays.py`) · IMPL-2: S02, S05–S07
(`app/{server,modal_app}.py`, `scripts/live_bench.py`, `.github/workflows/uptime.yml`, `tests/e2e/**`) · IMPL-3: S08–S10
(`pyproject.toml` packaging bits, `scripts/release_check.sh`, `scripts/gen_readme_tables.py`, `README.md`, `site/**`).

**Exit gate.**
- [ ] The public URL works zero-login from a fresh browser; cached replays instant; a live grade works.
- [ ] `live_latency.json` (n ≥ 30) + the claim ADR; the timer shows real wall-clock.
- [ ] Playwright E2E green; the uptime cron active; the spend check active.
- [ ] Clean-venv install works offline with fixtures; README first screen complete.

**Tripwires.** p95 > 12 s → the page shows the measured number; the video doesn't claim "<12 s" (doc-sync IDEA F54 wording).

---

## P10: Video, Write-up, Final Verification & Submission

**Goal.** A ≤3:00 video that passes the concept and banned-word lint; a final README/write-up; full reproducibility from a fresh clone;
compliance checks; a final judge-simulation review; feature freeze; the submission (👤); and the post-submission ops runbook.
**Why it matters.** The video is the primary judged artifact. Verification protects against kill-shots.

**Council focus questions.**
1. Judge simulation (HACKATHON §9): score the actual artifacts. Which single fix moves the weighted score most in the time left?
2. Does every on-screen number trace to `VIDEO_NUMBERS.md`? Is sim/cached labelled everywhere?
3. Is anything in the public repo a new-work-rule risk (lineage language, pre-event code, `docs/private/` leaked)?

**Steps.**
- **⚡ P10.S01 Script lock** (`video/SCRIPT.md`): the `IDEA.md` §10 script filled with the measured values; the concept ledger (≤8); `scripts/lint_script.py`
  (the banned-word list from IDEA §10.3 + the concept count) passes. 👤 confirms the I16 line.
- **⚡ P10.S02 🎬 Capture beats** (`video/tapes/*.tape`, `video/capture/`): VHS terminal tapes (test, run, blame, diff); OBS captures of the hosted page
  (timer, occlusion → CAN'T TELL, cached badge); the Muse Code take (P07); the proof chart animation; audit card frames; the human demo.
- **P10.S03 Voiceover & edit** (`video/edit/`): 👤 records the VO (or Kokoro-82M TTS if 👤 approves); Kdenlive edit; captions; the first 5 s hook check;
  ≤3:00 hard; export 1080p; upload (👤) as public/unlisted; test the link in an incognito window.
- **P10.S04 Test viewer** (👤): one non-roboticist watches it and restates the problem and solution. If they can't, fix the VO.
- **P10.S05 Final judge-simulation review** (R2 + council): score every criterion against `HACKATHON.md` §9.3 with the actual artifacts; produce
  `artifacts/p10/judge_sim.md` with a ranked fix list; apply the top fixes before the freeze.
- **P10.S06 Reproducibility drill** (R1): a fresh clone at the release candidate → `uv sync` → `Kodiac doctor` → quickstart (offline fixtures) →
  `pytest` (incl. `slow` on a GPU box if available) → regenerate the README tables from `experiments/results/*.json` (byte-identical) → spot-recompute
  3 headline numbers from the raw labels.
- **P10.S07 Compliance sweep** (`scripts/compliance_check.py`): first commit ≥ 2026-10-26; `BUILD_LOG.md` dated entries; `ATTRIBUTIONS.md` complete
  (SAM License, DROID CC-BY, LeRobot Apache, ManiSkill Apache, Robometer/TOPReward licences, cookbook MIT); LICENSE; **no secrets in history**
  (`detect-secrets scan --all-files` + a `git log -p` grep); `docs/private/` not tracked; `scripts/compliance_check.py` scans every tracked file **and `git log -p`**
  against the private lineage list `docs/private/lineage_terms.txt` and the voiceover list (IDEA §10.3); it must return 0 hits before any repo is made public.
- **P10.S07b Public mirror** (👤 approves publication): `scripts/make_public_mirror.sh`: fresh clone of the private working repo → `git filter-repo --invert-paths --path HACKATHON.md --path docs/research/ --path docs/private/ --path .agents/ --path HUMAN_TODO.md` → `scripts/lint_public.py --history` over the mirror's files, full history and commit messages → push to the public repo. The working repo is never rewritten.
- **P10.S08 Feature freeze & release** (Nov 4 04:59 UTC): tag `v1.0.0`; deploy the app from the tag; `min_containers=1` active; the replay store
  refreshed; README links verified.
- **⚡ P10.S09 Submission package** (`docs/SUBMISSION.md`): the form text (title, one-liner, track = Indie, theme = Push the Frontier, description,
  Meta tools used, links: repo, video, live URL), an X post draft with the verdict card + a 20 s clip, gallery text. 👤 posts on X early Nov 4 and
  **submits by Nov 4 17:00 UTC** (repo public ☐, video link ☐, contributors ☐, X link ☐).
- **⚡ P10.S10 Ops runbook** (`docs/OPS_RUNBOOK.md`): Nov 5–16 daily checklist (uptime, spend, replay health, Discord watch), the incident playbook
  (API down → cached mode banner; credits low → cache-only), finals prep (Nov 9 17:00 UTC: a 3-minute live pitch outline + a hot demo path).
- **P10.S11 Final push.** Push `main` + tags; archive `.agents/` state; final `STATE.md` = "SUBMITTED"; R1/R2 post-submission review for the finals fixes.

**Suggested task split.** IMPL-1: S02 (`video/tapes/**`, `video/capture/**`) · IMPL-2: S06–S07 (`scripts/compliance_check.py`, reproducibility
report `artifacts/p10/repro.md`) · IMPL-3: S09–S10 (`docs/SUBMISSION.md`, `docs/OPS_RUNBOOK.md`, the README final pass). ORCH/👤: S01, S03–S05, S08, S11.

**Exit gate (= submission readiness).**
- [ ] Video ≤3:00, lint pass, the test viewer passes, the link works in incognito.
- [ ] Reproducibility drill passes; compliance sweep passes; `v1.0.0` tagged and deployed.
- [ ] The judge-simulation fix list applied (or consciously deferred, with a reason).
- [ ] `Kodiac --help` primary verbs = test/run/blame/diff (I1); README H3 = tagline = last VO line (I12).
- [ ] Public mirror built and `lint_public.py --history` = 0 hits (P10.S07b).
- [ ] 👤 has submitted (confirmation captured in `docs/SUBMISSION.md`), and the ops runbook is active.

---

## Appendix A: Global Go/No-Go Checkpoints

| When (UTC) | Check | If NO |
|---|---|---|
| Oct 28 08:00 (P01 gate) | Hosted SAM + Spark + Voice work; Muse Code hook semantics known | Escalate KD-03/KD-11 fallbacks; re-plan P03 |
| Oct 29 14:00 (P03 gate) | Masks + backward tracking + latency measured; pool tracked ≥50%; **walking skeleton runs end to end on sim B1 + one real clip** | Cut live claims to measured; ORCH halts P04 dispatch until the skeleton runs; P04 scope = the skeleton's predicates first |
| Oct 30 14:00 (P04 gate) | Sim oracle agreement at target; CAN'T TELL tests pass | Mini-council; freeze scope at MVP predicates |
| Oct 31 22:00 (P06 gate) | Blame MVP accuracy; fast path agreement | Hero beat uses sim B1 (labelled) |
| **Nov 1 16:00 (P07 gate)** | One-take recorded; **backup video exists** | Record the backup now; everything else waits |
| **Nov 2 12:00** | **Proof go/no-go:** arms complete? | Pre-registered minimal fallback |
| Nov 3 14:00 (P09 gate) | Public URL live; p95 measured | Cached-replay-first page; honest latency |
| **Nov 4 04:59** | **Feature freeze** | Only fixes from the judge-sim list |
| **Nov 4 17:00** | **👤 submits** | Hard cutoff 01:00 UTC Nov 5 (internal); official 02:00 UTC |

## Appendix B: Human (👤) Task Summary
Credits + spend limits (P01) · keys/accounts (P01) · gated SAM weights (P01) · PyPI reservation (P01) · GitHub repo (P01) · Agents 102 (Oct 28) ·
Fireworks session (Oct 30) · I16 confirmation (P01) · hero-clip review (P02) · webcam demo recording (P02–P05) · DROID-slice labels (BG-C) ·
audit flag verification (P07–P08) · approval of public reports/outreach (P08) · Muse Code take if GUI (P07) · VO recording (P10) · test viewer (P10) ·
video upload (P10) · X post + submission (P10) · finals pitch (Nov 9).

**Human-hours ledger (≈ 10–11 h):** hero review 0.5 h · DROID slice ~200 eps ≈ 3 h (+ a second rater ≈ 1 h for κ on ≥20%) · time-saved set ≈ 1 h · audit flags ≥40 ≈ 2–3 h · demo recording 0.5 h · VO 1 h · outreach 1 h · approvals 0.5 h. Name the second rater by Oct 29; if none, report n and agreement with DROID's own flag, never κ. Decide Muse Code billing (smallest plan + cap, or credits) on day 1.

## Appendix C: Feature → Phase Coverage Check
F01–F10 → P05 · F11–F12, F14 → P03 · F13 → P06 · F15–F24, F28–F30 → P04 · F25–F27 → P06 · F31–F37 → P06 · F38–F40 → P07 · F41 → P02 · F42 → P02 (bugs) + P07 (eval) ·
F43–F48 → P02 (pool, prereg) + P08 · F49–F52 → P05/P06 (batch) + P08 · F53–F57 → P09 · F58 → P09 · F59 → P10 · F60 → P09 + P10.
Added in review round 1: F17/F27/F36/F41 → P06.S15 · F44 single-pass → P02.S13b · F43 arms → P03.S14 · F48 appearance benchmark → P02.S16 · walking skeleton → P03.S13 · time saved → P02.S12(e) + P08.S03 · public mirror → P10.S07b · PyPI → P09.S08b.
**Every feature in `IDEA.md` §4 is covered by at least one step.** (Reviewers: re-check this when docs change.)


*Review round 1 (R1/R2) applied 2026-10-28: see `docs/research/07_fix_ruling.md`. Every exit gate also requires DOC-RECONCILE (`AGENTS.md` §7.1).*