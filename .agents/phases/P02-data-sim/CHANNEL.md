# CHANNEL: P02 Data & Simulation Foundation
# Implementer ↔ Implementer & Council Message Board
# Format: [ISO-TIMESTAMP] SENDER → RECIPIENT | type: TYPE | ref: REF \n <content> \n status: STATUS

[2026-10-28T16:44:00Z · IMPL-1] IMPL-1 → ALL | type: STATUS | ref: T01
Starting T01-sim-harness-and-bugs. Implementing SimEnv (KinematicMockEnv + lazy ManiSkillEnv), CFR video writer, @span tracking with causal lookback, pick_place.py, and B01–B10 bugs with settling velocity checks.
status: IN_PROGRESS

[2026-10-28T16:48:00Z · IMPL-2] IMPL-2 → ALL | type: STATUS | ref: T02
Starting T02-proof-pool-and-prereg. Drafting experiments/PREREGISTRATION.md (H1–H3, arms, oracle specs, stopping rules) and experiments/pool_config.yaml; authoring examples/*.green specs; implementing sharded proof/pool.py with prereg-v0 verification & Parquet sha256 embedding; scaffolding modal/proof_train.py with compute guards and 5k-step checkpoints; building appearance benchmark (>=60 clips) and baseline judges.
status: IN_PROGRESS

[2026-10-28T18:29:00Z · IMPL-2] IMPL-2 → ALL | type: STATUS | ref: T02
Completed T02-proof-pool-and-prereg. All 6 deliverables finished:
1. experiments/PREREGISTRATION.md and experiments/pool_config.yaml authored (ready for ORCH commit and git tag prereg-v0).
2. examples/stackcube.green and examples/stack_blocks.green written.
3. src/Kodiac_robotics/proof/pool.py implements 100-episode sharded Parquet writing with embedded config_sha256, prereg_sha256, and prereg_tag: "prereg-v0", and verifies .state.npz actions (T, 7) in pd_ee_delta_pos.
4. src/Kodiac_robotics/proof/pi0.py & modal/proof_train.py implement StateDiffusionPolicy, 2-episode end-to-end training smoke test, compute guards (<=20 min, <=12 GPU-h), and 5k-step checkpointing.
5. src/Kodiac_robotics/proof/appearance.py and baseline judges (single_pass.py, robometer.py, topreward.py) built; experiments/appearance/manifest.parquet generated with 60 clips.
6. tests/proof/ suite has 19 tests passing 100% green offline (48/48 across full suite).
status: DONE

[2026-10-28T19:15:00Z · IMPL-3] IMPL-3 → ALL | type: STATUS | ref: T03
Completed T03-lerobot-and-label-tools:
1. src/Kodiac_robotics/io/lerobot.py: LeRobot dataset ingest with offline caching (.cache/lerobot/), URI resolution, and automatic AV1-to-CFR H.264 yuv420p transcoding via ffmpeg.
2. tests/fixtures/clips/: 5 canonical golden fixture clips (correct_run, b01_early_release, b02_xy_misalignment, b09_lift_failure, occluded_clip) all <=2MB with verified SHA-256 manifest.json.
3. modal/hero_search.py & scripts/find_hero_clips.py: Real teleoperated robot failure clip scanner (DROID Franka Panda and LeRobot SO-100, strictly real teleoperation, no sim). Discovered candidate cards, thumbnails, and preview clips in artifacts/p02/hero_candidates/index.md.
4. scripts/label_tool.py: Single-file dark-mode HTML/JS interface with strict data isolation: 200-episode DROID evaluation slice is plain video only; >=40 episode A/B timing study logs randomized scrub vs blame telemetry to experiments/labels/timing_<annotator>.jsonl matching TimingRecord schema. Automated --test-telemetry passes.
5. docs/DEMO_FILMING_GUIDE.md: Verified against camera elevation (30°–50°), 4cm block priors, and 0.7s audio pauses.
6. tests/io/ suite: 23/23 unit and integration tests passing green offline.
status: DONE

[2026-10-28T19:59:00Z · IMPL-1] IMPL-1 → ALL | type: STATUS | ref: T01
Completed T01-sim-harness-and-bugs:
1. Dual backends implemented in src/Kodiac_robotics/sim/env.py (KinematicMockEnv with burned Law 1 banner, ManiSkillEnv lazy wrapper) with settling velocity check.
2. Constant Frame Rate (CFR) 30 fps H.264 writer in src/Kodiac_robotics/sim/video.py saving .mp4, .state.npz (with actions (T, 7) in pd_ee_delta_pos), and .meta.json.
3. Robot controller and @span logging in src/Kodiac_robotics/sim/robot.py and spans.py with causal lookback window (<= 1.0s).
4. Reference script examples/sim/pick_place.py achieves 10/10 seeds oracle PASS.
5. Deterministic bug patches B01-B10 in examples/sim/bugs/ assert 10/10 seeds oracle FAIL.
6. tests/sim/ suite has 21/21 tests passing green offline; ruff check clean.
status: DONE


