# .agents/STATE.md: Current Project State

```yaml
phase: P06-P10 compressed sprint (ADR-0014)
stage: BUILD (integration) + REVIEW pending; T13 is the only open build task
updated: 2026-11-02 by ORCH
deadline:
  feature_freeze: 2026-11-04T04:59:00Z
  internal_submit: 2026-11-04T17:00:00Z
  official_submit: 2026-11-05T02:00:00Z
completed_phases: [P01, P02, P03, P04, P05]   # tags p01-done .. p05-done
schedule_status: >-
  Council/SDM skipped for P06-P10 per ADR-0014 (schedule threat acknowledged by the user). Sprint runs
  as one integrated build on main, not per-phase branches.

runtime_note: >-
  Anthropic API credits are exhausted ("your credit balance is too low"), so no further Opus/Sonnet sessions can
  be spawned. Remaining work runs on free OpenCode models (flint-40b-free for correctness, glm-5.3-flash-free for
  mechanical edits) or is done by ORCH directly.

tracks:
  done:
    T01 blame core             : 56 tests; exact t* on synthetic ramps, sigma ~7 frames on Tier C fixtures
    T02 bisect fast path       : 100% verdict / 100% t*+-2 agreement on 200 mock episodes, target_met FALSE
    T03 diff/hint/codeloc/salvage : 10/10 B01-B10 code lines on mock sim (not blind; B07/B10 registry mismatch)
    T04 done-gate + sim.runner : 18 recorded refusals, never exits 3, mock only
    T05 MCP verify + loop tmpl : real PASS/FAIL integration on mock sim; loop_eval is a plumbing dry run
    T06 honesty reconcile      : features.yaml / VIDEO_NUMBERS / README / REVIEW corrections
    T07 P04 backlog fixes      : pytest-timeout still NOT installed (no network)
    T08 judge layer            : 161 offline tests, [FIXTURE] labels, yes-bias defeated; live HTTP [UNVERIFIED]
    T09 proof stats/chart/ablation : headline NOT_MEASURED, check_prereg PASS
    T10 audit tooling          : DEMONSTRATION DATA banner, publish refusal matrix
    T11 hosted app             : 50 passed / 2 skipped / 1 xfailed; 6 cached replays, all labelled
    T12 compliance/ship tooling : findings disclosed (see compliance below)
    T14 judge-baseline honesty : invented arms absent with reasons; modal/proof_train returns not_trained
    T15 patch regeneration     : all 10 patches apply; oracle fails on each; regression test added
    ORCH CLI wiring            : blame, diff, gate, mcp, loop init/eval, audit + real run --mode fast
  active:
    T13 engine correctness     : flint-40b-free#xhigh, session ses_e6552ff60ffe8A97gIHgoaxhac
                                 MUST resolve artifacts/p04/validation.json vs artifacts/p06/agreement.json first,
                                 then 5 defects (false PASS B04/B09, Case C -> CAN'T TELL, [sam-3.1] badge lie,
                                 false [REPLAY: CACHED SAM 3.1 TRACKS] badge, dense_frames, reference series)
  queued_after_t13:
    - update tests/cli/test_run_cli.py (asserts b01 -> exit 1; Tier C should abstain after the Case C fix)
    - re-run scripts/precompute_replays.py and regenerate site/ (replays predate the engine fix)
    - regenerate README status block with scripts/gen_status_table.py + add the drift test
    - write REVIEW.md (R1/R2), tag and push

background_jobs:
  - id: BG-A
    name: Modal pool tracking + baseline training
    status: NOT RUNNING (no Modal token, no labels, no trained arm; pool is 250 mock-physics episodes)
  - id: BG-B
    name: site replay precompute
    status: STALE (generated at cb44d53, before T13)

blockers:
  - Anthropic credits exhausted -> remaining work on free models or ORCH (see runtime_note)
  - Meta Model API key never provided -> all SAM/Spark/Voice/Wonder evidence is fixture-only (Law 1 labels)
  - Modal token never provided -> no real-physics pool, no arm training; headline stays NOT_MEASURED
  - HF gated weights (facebook/sam3.1) never provided
  - PyPI name Kodiac-robotics never reserved
  - I16 closing-line decision still pending (HUMAN_TODO 3)
  - git-filter-repo not installed -> mirror build cannot run; history has 2 fake test-key literals (HUMAN_TODO 4)

compliance: >-
  scripts/compliance_check.py: ok=False with 3 residual findings, all disclosed rather than hidden:
  2 secret-history hits (fake keys in commits c142535 and d4258d1; working tree is clean, scrub needs human
  approval per AGENTS 12.5) and 1 UNVERIFIABLE (docs/private/lineage_terms.txt does not exist, so no lineage
  scan was possible and no list was invented).

honesty_open_items:
  - cost_usd is unmetered and reads 0.0 everywhere (no billing API, no keys)
  - single_pass multi-image request shape is [UNVERIFIED]
  - .muse/hooks.json format is unverified against Muse Code
  - Meta API endpoint + model ids are [UNVERIFIED] (no key was ever used)
  - baseline judges absent (no labels) -> arms.py omits them with a reason
  - artifacts/p03/sam_bench.json is `simulated_timings`, not a SAM measurement

next_action: >-
  Wait for T13, verify its diff against the contradiction and the five defects (do not trust the free model's
  report), then fix the CLI test, regenerate replays + site, regenerate the README block, run the full suite,
  write REVIEW.md, tag and push.
```
