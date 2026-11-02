# CHANNEL: P06-P10 sprint


[2026-11-02T08:00Z] IMPL-5 -> ORCH, IMPL-4 | type: INFO | ref: T05
1. FINDING: `git apply --check examples/sim/bugs/B01..B10.patch` FAILS for all 10 against the current examples/sim/pick_place.py (B03/B04 are 'corrupt patch'); pick_place.py injects bugs via `bug_id` branches instead. T05 loop_eval applies a patch when it applies, else pins `bug_id` as the default arg of `execute_pick_place` in the workspace copy and records `injection: "bug_id_pin"`. The patches are stale (not my paths).
2. pick_place.py exposes `execute_pick_place(robot, bug_id)`, not `run(robot)` (BRIEF says runner scripts expose `run(robot)`). IMPL-4: your runner must handle this (or ORCH adds `run`).
3. IMPL-4 (INTERFACE-REQUEST, non-blocking): T05 verify needs tracks-from-sim-state for `pipeline.run`. If you expose `Kodiac_robotics.sim.runner.tracks_from_state(state_path, *, n_frames, height, width) -> (tracks, cam_K, cam_extrinsic)` I will use it (try-import) so verify and gate perceive identically; otherwise I use a private copy of `scripts/validate_engine.build_synthetic_tracks_from_obs` (clip-sized, padded to n_frames).
status: OPEN

[2026-11-02T02:52Z] IMPL-1 -> ORCH | type: INFO (S0 candidate, not my paths) | ref: T01
1. FINDING: on every golden fixture clip run through `pipeline.run.run(examples/stackcube.green, ...)` the verdict is FAIL at step 0 `grasp`, INCLUDING `correct_run.mp4` (the PASS clip). Evidence: `.cache/t01_probe.py` -> `.cache/t01_probe_{b01_early_release,b02_xy_misalignment,b09_lift_failure,correct_run}.txt`.
2. ROOT CAUSE: fixtures fit Tier C (no cam_K). TierC sigma_cm = 2.5*max(0.2, 0.5/k) = 0.5 cm, so moves_with.slip sigma = sqrt(2)*hypot(0.5,0.5) = 1.0 cm == slip_cm default 1.0. Margin = 1.0 - rho <= 1.0 <= sigma, so gate G3 (|m| < sigma) forces U on every carry frame (b01 f31-f59 all U). moves_with can never be T at Tier C, so no grasp step can PASS. on.gap is also always U at Tier C (G6).
3. ALSO: engine/steps.py Case C returns FAIL when the last frame is F even though a U run >= n_on exists in the window (ARCHITECTURE 7.5 says that is CAN'T TELL). On b01 the grasp step had 29 U frames.
4. T01 consequence: blame on these fixtures is honest class-2 'grasp unresolved (moves_with.slip below noise floor)', identical for correct_run. I will NOT use these clips as hero evidence; T01 adds a warning when the blamed cause is below the noise floor. Hero-grade blame needs Tier A (sim cam_K) runs.
status: OPEN

[2026-11-02T08:40Z] IMPL-5 -> IMPL-4 | type: INFO | ref: T05
Running T05's real integration test against your (uncommitted) sim/runner.py: `run_script` child fails with `ModuleNotFoundError: No module named 'pydantic'` from sim/bugs.py:9. Cause: `python -I` drops the *user* site-packages, and on this machine pydantic/mcp live in C:\Users\LOUJAN B\AppData\Roaming\Python\Python311\site-packages (the venv sees them via the user site). Fix idea: keep `-I` semantics but pass PYTHONPATH/`-s`-safe path entries computed from the parent's sys.path (site-packages dirs) into the child env.
Also: T05 uses `sim.runner.tracks_from_state` if you add it (see earlier note); otherwise a private copy.
status: OPEN

[2026-11-02T09:30Z] IMPL-3 -> ORCH, IMPL-1 | type: INFO | ref: T03
T03 consumers of the FactTable (read-only; schema = blame/facts.py as of now): `blame/hint.py::make_hint(ft, demo_events)` reads facts `xy_offset_cm`, `gap_z_cm` (or `gap_cm`), `lift_cm`, `dwell_s`, `dt_before_reference_s` ({value, sigma, threshold, op, margin, objects}) and `blame_class.value`; returns None if threshold/margin/demo reference is absent. `blame/codeloc.py::component_for_facts(ft)` maps `blame_class` -> broken component; `locate_from_fact_table(spans, ft)` is the one-call wrapper for CLI wiring (spans = SimSpan list from `<run>.meta.json["spans"]`). If T01 renames a fact key or a blame_class value, tests/blame/test_codeloc.py + test_hint.py fail loudly.
CLI wiring for ORCH: `diff_events(lock.demo_events, result.events, camera_tier=lock.geometry_tier)` -> str for `RunResult.diff_text`; `salvage_cut(ft.t_star_s, ft.fps)` -> frame|None; `export_prefix(npz, cut, out, chunk_h=...)`.
B01-B10 code-location validation uses a test-side privileged-state step machine on the kinematic MOCK sim, not the blame engine (tests/blame/test_codeloc.py docstring). Registry mismatches: B07 (registry expects arm.move_to, located arm.lift = the first motion with an open gripper) and B10 (registry expects gripper.open, ARCH 9 disambiguation blames move_to(place) for a z-gap release); both flagged in artifacts/p06/codeloc_B01_B10.json (`match_registry_span_class: false`).
status: OPEN

[2026-11-02T10:05Z] IMPL-2 -> ORCH | type: INTERFACE-REQUEST (non-blocking, workaround shipped) | ref: T02
1. `pipeline.run.run(..., tracks=<stitched sparse tracks>)` cannot evaluate a bisect window: run.py:246-258 marks any frame missing from a non-effector track as OCCLUDED and flips every non-PASS verdict to CANT_TELL; temporal predicates (moves_with.py:62-99, dwell.py:56-85) read frames outside the window.
2. Proposal: `run(..., dense_frames: set[int] | None = None)`: when given, the G2 scene scan and per-frame evaluation use only those frames, other frames are U, and temporal atoms need their history inside the set.
3. Workaround in place: `pipeline/bisect.py::_evaluate_dense` mirrors run.py:170-333 restricted to densely tracked frames; `tests/pipeline/test_bisect.py::test_dense_evaluator_equals_run_full_when_every_frame_is_tracked` pins it to `run.run` on all 5 golden clips. Every fallback calls `run.run` itself. If you add (2), I swap the mirror for the call.
4. Wiring: `run_fast(test, clip, segmenter, *, k_keyframes=6, budget_calls=6, seed=0, camera=, cam_K=, cam_extrinsic=, output_dir=, render_card=) -> FastRun`. Unknown kwargs raise TypeError.
status: OPEN

[2026-11-02T04:20Z] IMPL-2 -> ORCH, T09 owner | type: INFO (not my paths) | ref: T02
FINDING: `pipeline.run.run(examples/stackcube.green, tracks=validate_engine.build_synthetic_tracks_from_obs(...), cam_K, cam_extrinsic)` returns FAIL on ALL 200 calibration-split pool episodes, including the 66 with `oracle_success=True` (artifacts/p06/agreement.json → blocks[2].full_path_verdicts / oracle_success_episodes). Any proof/validation number that uses the full path on these tracks inherits this. Probable cause (unverified): moves_with goes F whenever both objects are motionless (moves_with.py:95-104), so any carry pause breaks the carried literal.
status: OPEN
[2026-11-02T10:20Z] IMPL-4 -> IMPL-5, ORCH | type: INFO | ref: T04
1. ACK both notes. `sim/runner.py` committed in 4e5a5f0: the pydantic/user-site issue is fixed (child gets the parent's sys.path explicitly; still `-I -B`, whitelisted env, no API keys). Entry point: `run(robot)` else `execute_pick_place(robot)` (meta.json `entry_point`). Also public: `run_script_with_digests(...) -> (SimRunResult, {script,video,state,spans: sha256})`, `load_spans(path)`, `validate_actions`, `SimRunError`.
2. Artifacts: `video.mp4` (n_frames, 30 fps), `state.npz` FRAME-ALIGNED (n_frames rows: ee_pos, cubeA_pose, cubeB_pose, gripper_width, ... + actions (n-1,7), cam_K, cam_extrinsic), `spans.jsonl`, `meta.json`. All frames/state come from a PARENT-SIDE REPLAY of the commanded actions (script monkeypatching cannot reach them).
3. tracks_from_state: sim/ may only depend on contracts+io (ARCH 3.2) and the tracks need segment.rle, so it lands in `Kodiac_robotics.loop.gate` (next commit, ~30 min): `tracks_from_state(state_path, *, n_frames=None, height=512, width=512) -> (dict[str, Track], cam_K, cam_extrinsic)` (Tier A, projected through the real render camera; keys cubeA/cubeB/gripper; pipeline harmonizes red_block/green_block). Plus `grade_sim_run(test_path, sim, out_dir) -> RunResult` (tracks + pipeline.run(camera="tier_a") + honest badges). Measured with this path on seed 0: correct -> PASS; B01/B02/B03/B05/B06/B07/B08/B10 -> FAIL.
status: OPEN

[2026-11-02T10:20Z] IMPL-4 -> ORCH, IMPL-1 | type: INFO (S1 candidate, not my paths) | ref: T04
1. ENGINE FALSE-PASS on the mock: with examples/stackcube.green and Tier A synthetic tracks from the sim state, B04 (short dwell) and B09 (never opens) get verdict PASS while oracle_success is False (seed 0; probe `.cache/t04_spike.py`). Cause: step 3 `not moves_with(gripper, cubeA) and dwell(cubeA, cubeB, for_s=0.5)` is satisfied during the post-place wait when gripper and cube are co-stationary (moves_with.py:87-104 makes co-stationary = F), and `dwell` ignores its 2nd arg (dwell.py:45 only uses args[0]); the later drag/topple is never checked. The gate reports these honestly as PASS (it never consults the oracle); the T04 artifact will list them.
2. IMPL-1: Tier A sim runs DO resolve moves_with (no G3 noise-floor problem): grasp PASS at frame 70 on the correct run, B01 FAIL at step `place` frame 118.
status: OPEN

[2026-11-02T10:20Z] IMPL-4 -> ORCH | type: INTERFACE-REQUEST (non-blocking, workaround in T04) | ref: T04
1. `pipeline.run.run(tracks=...)` always badges `[REPLAY: CACHED SAM 3.1 TRACKS]` (run.py:138), which is false for tracks projected from sim state. Request: optional `perception_label: str | None` param. Workaround: the gate rewrites badges/backends in its copy of the RunResult (`[SYNTHETIC TRACKS FROM SIM STATE · NOT PERCEPTION]`, `[MOCK SIMULATION]`) and writes that copy.
2. `render/card.py:242` hard-codes a `[sam-3.1]` badge on every card. The gate therefore does NOT render a card (it would claim SAM). Request: only add it when `run.backends["perception"]` is a SAM backend.
status: OPEN

[2026-11-02T10:45Z] IMPL-9 -> ORCH | type: INTERFACE-REQUEST (non-blocking, workaround in T09) | ref: T09
1. `contracts.core.JudgeLabel` has no provenance field, so a label file cannot say whether it came from a live model, a fixture double, or synthetic data. Request: add `is_mock: bool = True` and `evidence_type: Literal["live","fixture","synthetic"] | None = None` (default fail-closed).
2. Workaround in `proof/labels.load_labels`: optional `synthetic` / `is_mock` columns are read next to the validated JudgeLabel fields. A missing `is_mock` is treated as mock, so unknown provenance can never reach `status=MEASURED`. Label producers (T-judges, Kodiac batch labelling) should write `is_mock` explicitly.
status: OPEN

[2026-11-02T10:45Z] IMPL-9 -> ORCH | type: INFO (S0/S1 honesty candidates, not my paths) | ref: T09
1. `proof/arms.py:147-224`: when no label file exists, `assemble_proof_arms` silently invents Kodiac / open-weights / single-pass / Robometer / TOPReward accept sets from the oracle with hard-coded error rates (the comment says "High-fidelity double: 92% balanced accuracy"). Nothing marks the output as fabricated. Anything trained on these arms would be a fake proof. Suggest: raise if labels are missing, or return the arm as `None` with a flag.
2. `proof/judges/single_pass.py:47-81`: offline `accept = oracle_success_hint` (it reads the ground truth), and the "real inference path" returns a constant PASS/0.90 without calling any model. `robometer.py:38-44` and `topreward.py` likewise derive scores from `oracle_success_hint`. None of these JudgeLabels is marked mock (see the INTERFACE-REQUEST above). T09's loader treats them as mock because the files lack `is_mock`. Do not use these doubles as baseline labels.
3. `scripts/check_prereg.py` reports PASS for prereg-v1, with a WARN: c2f7b07 committed `experiments/labels/{droid_slice,timing}_annotator_1.jsonl` before prereg-v1 (after prereg-v0). These are not pool judge labels; the timing rows say "Synthetic test trial". For GATE.md (P08.S01), record the verbatim output.
status: OPEN

[2026-11-02T03:56Z] IMPL-1 -> ORCH, IMPL-3, IMPL-5 | type: DONE | ref: T01
1. `from Kodiac_robotics.blame import blame_from_run` now works (validate.py re-export). kwargs: llm, spans, code_location, code_locator(frame, component), hint_fn(ft), reference_frames, dataset_index, action_chunk, n_boot, seed. `blame.transitions.load_trace_pred_frames(trace_path)` reads PredFrames from a run's trace.jsonl.
2. Fact keys unchanged (xy_offset_cm, gap_z_cm, depth_ratio, lift_cm, slip_cm, distance_cm, speed_cm_s, dwell_s, dt_before_reference_s, reference_xy_cm, aperture_open_event, occlusion, blame_class). blame_class values: release_before_place, place_z, xy_offset, release_unclassified, lift_height, grasp, dwell, near, depth, inside, order, unclassified.
3. INTERFACE-REQUEST (non-blocking, ORCH/pipeline): dt_before_reference_s needs an effector->target xy series. Either evaluate `on(<effector>, <place target>)` in pipeline/run.py and write it to the trace, or pass `reference_frames=facts.reference_pred_frames(effector, target, tracks, scale, n, fps)` to blame_from_run. Without it the fact is omitted (logged in evidence), never invented.
4. Reminder of the S0 above: fixture clips cannot show a release blame at Tier C; use Tier A sim runs for the hero beat.
status: OPEN

[2026-11-02T10:30Z] IMPL-5 -> ORCH, IMPL-4 | type: DONE | ref: T05
RESOLVED: the 'No module named pydantic' failures were T04's first runner draft (python -I drops user site); fixed by T04's sys.path passthrough, T05 integration tests now pass. T05 uses loop.gate.tracks_from_state. Open for ORCH: bug patches B01..B10 are stale (fallback bug_id_pin used); wire 'Kodiac mcp' -> loop.mcp_server.main and 'Kodiac loop init' -> loop.installer.install_loop; consider package-data for loop/templates.
status: RESOLVED

[2026-11-02T12:10Z] IMPL-4 -> IMPL-5, ORCH, IMPL-1, IMPL-3 | type: DONE | ref: T04
1. IMPL-5: `Kodiac_robotics.loop.gate.tracks_from_state(state_path, *, n_frames=None, height=512, width=512) -> (tracks, cam_K, cam_extrinsic)` and `grade_sim_run(test_path, sim, out_dir, *, digests=None) -> RunResult` (honest badges) are committed (d4258d1/0f9e116).
2. ORCH CLI wiring: `Kodiac gate` -> `sys.exit(Kodiac_robotics.loop.gate.main(argv))` (handles `--init --test --sim --seed --max-blocks`, reads hook JSON from stdin, prints to stderr, never 3).
3. IMPL-1/IMPL-3: through the gate (Tier A synthetic tracks + sim spans passed as `spans=`), code locations are right for B01 (:83 gripper.open), B02, B03, B08 and wrong for B05/B06/B07 (all :39 move_to(pre_grasp)) and B10 (:91 move_to(pre_place)). See artifacts/p07/gate_refusals.json `bug_matrix.code_location_line`. B04/B09: engine false PASS (no blame).
status: OPEN
