"""Seeded generator of SYNTHETIC fixtures for the proof-statistics tests (T09).

THESE FILES ARE NOT EXPERIMENTAL DATA. Every file name contains ``SYNTHETIC`` and every row carries
``"synthetic": true``. They exist only to prove the statistics code correct on known structure.

Regenerate (byte-for-byte reproducible content; optional output dir, default: this folder):
    python tests/fixtures/proof/make_synthetic_proof_fixtures.py [OUT_DIR]
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

SEED = 20261102
N_CALIB = 50
N_TRAIN = 200
EVAL_SEEDS = (42, 43, 44)
EVAL_EPISODES = 200
#: Synthetic per-arm success probabilities (made up; NOT results).
ARM_P = {"kodiac": 0.62, "single_pass": 0.50, "accept_all": 0.40, "oracle": 0.66, "oracle_k_10": 0.60}
SOURCE = "tests/fixtures/proof/make_synthetic_proof_fixtures.py (SYNTHETIC)"
HERE = Path(__file__).resolve().parent


def _dump(path: Path, obj: object) -> None:
    path.write_bytes((json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n").encode())


def _dump_jsonl(path: Path, rows: list[dict]) -> None:
    text = "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows)
    path.write_bytes(text.encode())


def _row(judge: str, ep: str, accept: bool, verdict: str | None, score: float | None) -> dict:
    return {
        "judge": judge,
        "episode_id": ep,
        "accept": bool(accept),
        "verdict": verdict,
        "score": score,
        "latency_ms": 0,
        "cost_usd": 0.0,
        "synthetic": True,
        "is_mock": False,
    }


def generate(out_dir: Path = HERE) -> list[Path]:
    rng = np.random.default_rng(SEED)
    out_dir.mkdir(parents=True, exist_ok=True)
    n = N_CALIB + N_TRAIN
    eps = [f"SYN_ep_{i:04d}" for i in range(n)]
    splits = ["calibration" if i < N_CALIB else "train" for i in range(n)]
    truth = rng.random(n) < 0.45
    written: list[Path] = []

    manifest = [
        {"episode_id": e, "split": s, "oracle_success": bool(y), "synthetic": True, "is_mock": False}
        for e, s, y in zip(eps, splits, truth)
    ]
    p = out_dir / "SYNTHETIC_oracle_manifest.json"
    _dump(p, manifest)
    written.append(p)

    kodiac, single, robo = [], [], []
    for e, y in zip(eps, truth):
        if rng.random() < 0.08:
            kodiac.append(_row("kodiac", e, bool(rng.random() < 0.5), "CANT_TELL", None))
        else:
            acc = bool(y) if rng.random() < 0.95 else not bool(y)
            kodiac.append(_row("kodiac", e, acc, "PASS" if acc else "FAIL", None))
        acc = bool(rng.random() > 0.10) if y else bool(rng.random() < 0.25)
        single.append(_row("single_pass_spark_1.3", e, acc, "PASS" if acc else "FAIL", None))
        score = float(np.clip(rng.normal(0.68 if y else 0.52, 0.10), 0.0, 1.0))
        robo.append(_row("robometer-4b", e, score >= 0.65, None, round(score, 4)))
    for name, rows in (("kodiac", kodiac), ("single_pass", single), ("robometer", robo)):
        p = out_dir / f"SYNTHETIC_labels_{name}.jsonl"
        _dump_jsonl(p, rows)
        written.append(p)

    evals = out_dir / "evals_SYNTHETIC"
    evals.mkdir(exist_ok=True)
    for seed in EVAL_SEEDS:
        difficulty = rng.random(EVAL_EPISODES)  # shared per eval env => arms are paired
        shift = rng.normal(0.0, 0.02)
        for arm, prob in ARM_P.items():
            success = (difficulty < prob + shift).astype(int).tolist()
            p = evals / f"SYNTHETIC_{arm}_seed{seed}.json"
            _dump(
                p,
                {
                    "arm": arm,
                    "seed": seed,
                    "success": success,
                    "synthetic": True,
                    "is_mock": False,
                    "source": SOURCE,
                },
            )
            written.append(p)
    return written


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE
    for path in generate(target):
        print(path.relative_to(target))
