# tests/fixtures/proof: SYNTHETIC test data only

Everything here is **synthetic**: made-up numbers produced by the seeded script
`make_synthetic_proof_fixtures.py` (seed `20261102`). File names contain `SYNTHETIC` and every row carries
`"synthetic": true`. These are **not** experimental results and must never feed `experiments/results/`,
`artifacts/p08/`, the README, or `docs/VIDEO_NUMBERS.md`.

They exist to check the proof statistics (`src/Kodiac_robotics/proof/{labels,stats,chart,ablation}.py`)
against known structure and to check that the `synthetic` flag propagates to every output
(`status = "SYNTHETIC_TEST_ONLY"`).

| File | Content |
|---|---|
| `SYNTHETIC_oracle_manifest.json` | 250 episodes (50 calibration, 200 train), oracle success ~ Bernoulli(0.45) |
| `SYNTHETIC_labels_kodiac.jsonl` | verdict judge, 8% CAN'T TELL (some with `accept=true` to test forced rejection) |
| `SYNTHETIC_labels_single_pass.jsonl` | verdict judge, ~25% false-PASS, ~10% false-REJECT |
| `SYNTHETIC_labels_robometer.jsonl` | score judge (threshold refit on the calibration split) |
| `evals_SYNTHETIC/SYNTHETIC_<arm>_seed<s>.json` | 5 arms × 3 seeds × 200 paired eval episodes |

Regenerate: `python tests/fixtures/proof/make_synthetic_proof_fixtures.py`.
