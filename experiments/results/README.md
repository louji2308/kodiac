# experiments/results/

Outputs of the headline proof experiment (Invariant I8: *"Same robot, same practice data, only the judge
changed: +Y points of success"*).

## Current truth (2026-11-02)

**Nothing has been measured. `Y` does not exist yet.**

- No judge has labelled the practice pool (`experiments/labels/*.parquet`: none).
- No policy arm has been trained or evaluated (`experiments/evals/`: none).
- The practice pool (`experiments/pool/manifest.parquet`) is 250 kinematic-mock episodes (`is_mock=True`),
  which the pre-registration does not accept (PREREG §2 requires ManiSkill3 physics; target 1,000 episodes).

So `headline.json` has `"status": "NOT_MEASURED"`, `"Y_points": null`, `"sentence": null`, and
`artifacts/p08/proof_chart.{png,svg}` shows only the watermark **"NOT MEASURED: NO TRAINED ARMS YET"**, with no bars
or points. Do not quote any number from this folder in the README, the video, or `docs/VIDEO_NUMBERS.md`
until `status` is `MEASURED`.

Regenerate both from whatever real inputs exist:

```
python -m Kodiac_robotics.proof.chart --real-state
```

(In the agent sandbox Python can only write under `.cache/`, so the committed copies were produced with
`--out-json/--out-png/--out-svg` pointing at `.cache/t09_real/` and then copied in unchanged.)

## Contract (how a number gets here)

Code: `src/Kodiac_robotics/proof/{labels,stats,chart,ablation}.py`. Every metric is computed as
pre-registered in `experiments/PREREGISTRATION.md` (cited as PREREG §n in the docstrings).

| Output | Rule |
|---|---|
| Judge metrics | Training split only (800 in the design). false-PASS = FP/(FP+TN), false-REJECT = FN/(FN+TP), coverage = adjudicated/total, each with a Wilson 95% CI (PREREG §6). Balanced accuracy and AUROC: 1,000-sample episode bootstrap (PREREG §6). Contamination = FP/(TP+FP), episode bootstrap (ARCHITECTURE §5.7). CAN'T TELL = not accepted. A missing label counts as not accepted and not adjudicated, and is reported in `n_missing`. |
| Thresholds | Score judges (Robometer-4B, TOPReward): τ maximises balanced accuracy on the **calibration split only**. Ties go to the higher τ (the baseline's lowest false-PASS). Training rows never move τ (tested). |
| Paired judge tests | Exact McNemar vs Kodiac on per-episode correctness, plus a false-PASS-only variant, each Holm-corrected. |
| Headline | Kodiac − single-pass success difference, using the mean of per-seed means. Primary test: two-sided Welch t on seed means with its Welch CI, Holm-corrected across the PREREG baselines (PREREG §1 H2, §6). Secondary: a paired hierarchical bootstrap CI (seeds, then eval episodes, 10,000 resamples, seed 0). Dose-response: oracle + k% injected false-PASS arms. The pre-registered target (Δ ≥ +5 points, Holm p < 0.05) is reported as `meets_prereg_target`; if the result is not significant, the sentence says so. |
| `status` | `MEASURED` requires ≥ 4 arms, ≥ 2 training seeds per arm (fewer than the 3 registered is disclosed in `prereg_deviations`), ≥ 200 eval episodes per seed (PREREG §5), and every arm explicitly declared `synthetic=false, is_mock=false`. Synthetic, mock, or undeclared inputs give `SYNTHETIC_TEST_ONLY`, with numbers for testing only and no sentence. Inputs that are declared real but fail a gate give `NOT_MEASURED`, and the numbers are withheld. |
| Chart | Bars or points are drawn **only** for an unflagged `MEASURED` headline. `SYNTHETIC_TEST_ONLY` gets a hatched watermark. Anything else gets the NOT MEASURED watermark. |
| Ablation | R1..R5 specificity (Wilson CI). Each "adds" step uses a Newcombe CI and is reported only between adjacent rungs on the same benchmark. Missing rungs are `NOT_MEASURED`. |
| Pre-registration | `python scripts/check_prereg.py` checks three things: tag `prereg-v1` exists, PREREGISTRATION.md and pool_config.yaml are unchanged since the tag, and the tag strictly precedes every commit touching `experiments/labels/**/*.parquet` or `experiments/results/**`. |

Eval file format for `experiments/evals/*.json` (one file per arm and training seed):
`{"arm": str, "seed": int, "success": [0/1 per eval episode, in eval-env-seed order], "is_mock": bool, "synthetic": bool, "source": str}`.
A missing `is_mock` is treated as mock.

The statistics are verified only on **synthetic** fixtures (`tests/fixtures/proof/`, every file named
`SYNTHETIC_*`). Those numbers are not results.
