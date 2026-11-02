"""Benchmark arm episode partitioner for Kodiac proof evaluation (fail-closed, Law 1).

Assembles accepted-episode sets for the 10 pre-registered arms (PREREGISTRATION.md §4):

* **Oracle-only arms** (need nothing but the practice-pool manifest): ``oracle``, ``accept_all``,
  ``size_matched_control`` (needs the Kodiac arm's size) and the injected-noise dose arms
  ``oracle_k_{5,10,20,30}``. The dose arms are *injected noise, not a judge*.
* **Judge arms** (``kodiac_cloud``, ``kodiac_open_weights``, ``single_pass_spark_2fps``, ``robometer_4b``,
  ``topreward``) and ``kodiac_salvage``: built **only** from a real judge label file in ``labels_dir``.
  If the file is missing the arm is *absent* with the reason ``"no labels: judge not run"``. An arm is
  never synthesised from the oracle.

The result is a :class:`ProofArms` mapping that contains only arms that could be built. Absent arms are
listed with a reason in ``.absent``; every present arm has a provenance record in ``.provenance``
(``is_mock``, ``evidence_type``, ...). Nothing here uses hard-coded judge error rates.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from Kodiac_robotics.proof import labels as _labels

NO_LABELS_REASON = "no labels: judge not run"
DOSES = (5, 10, 20, 30)
MIN_PREFIX_FRAMES = 30  # >= 1.0 s at 30 fps (PREREGISTRATION §4 arm 5)

# arm key -> judge label file stem in ``labels_dir``
JUDGE_ARMS: dict[str, str] = {
    "kodiac_cloud": "kodiac_cloud",
    "kodiac_open_weights": "kodiac_open_weights",
    "single_pass_spark_2fps": "single_pass_spark_1.3",
    "robometer_4b": "robometer-4b",
    "topreward": "topreward-lerobot-v0.6",
}
ARM_ALIASES: dict[str, str] = {
    "kodiac_sam31": "kodiac_cloud",
    "kodiac_kinematic": "kodiac_open_weights",
    "single_pass": "single_pass_spark_2fps",
}


class ProofArms(dict):
    """``{arm: [episode_id, ...]}`` holding only the arms that could be built.

    ``absent``: ``{arm: reason}`` for arms that could not be built. ``provenance``: ``{arm: {...}}``.
    """

    def __init__(self) -> None:
        super().__init__()
        self.absent: dict[str, str] = {}
        self.provenance: dict[str, dict[str, Any]] = {}


def _read_records(manifest_path: Path | str) -> list[dict[str, Any]]:
    """Read episode/label records from a Parquet, JSON or JSONL file."""
    p = Path(manifest_path)
    if not p.is_file():
        raise FileNotFoundError(f"file not found: {manifest_path}")
    if p.suffix == ".parquet":
        return pq.read_table(p).to_pylist()
    if p.suffix in (".json", ".jsonl"):
        text = p.read_text(encoding="utf-8")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("episodes", "labels"):
                if key in data:
                    return data[key]
            return list(data.values())
    raise ValueError(f"Unsupported file format: {p.suffix}")


def _find_label_file(labels_dir: Path | str, stem: str) -> Path | None:
    ldir = Path(labels_dir)
    if not ldir.is_dir():
        return None
    for suffix in (".parquet", ".json", ".jsonl"):
        candidate = ldir / f"{stem}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def _truthy(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "t"}
    return bool(value)


def _load_judge_arm(
    path: Path,
    calibration_ids: set[str],
    oracle: dict[str, bool],
) -> tuple[dict[str, bool], dict[str, Any], dict[str, int]]:
    """Load one judge's labels. Returns ``({episode: accept}, provenance, {episode: t_star_frame})``.

    Labels are validated as ``JudgeLabel`` rows. Score judges get their threshold fitted on the calibration
    split only; CAN'T TELL is never accepted (PREREGISTRATION §4 arm 3).
    """
    df = _labels.load_labels([path])
    if len(df) == 0:
        raise ValueError(f"{path}: label file has no rows")
    if df["judge"].nunique() != 1:
        raise ValueError(f"{path}: expected one judge per label file, found {sorted(df['judge'].unique())}")
    if calibration_ids:
        df = _labels.apply_thresholds(df, calibration_ids, oracle)
    else:
        # No calibration split available: only native verdict judges are usable.
        if not df["verdict"].notna().all():
            raise ValueError(f"{path}: score judge needs a calibration split to fit its threshold")
        df = df.copy()
        df["accept"] = df["accept"].astype(bool) & (df["verdict"] != "CANT_TELL")
    accept = {str(e): bool(a) for e, a in zip(df["episode_id"], df["accept"])}

    raw = _read_records(path)
    evidence = sorted({str(r.get("evidence_type")) for r in raw if r.get("evidence_type")})
    t_star = {
        str(r["episode_id"]): int(r["t_star_frame"])
        for r in raw
        if r.get("t_star_frame") is not None and r.get("episode_id") is not None
    }
    provenance = {
        "kind": "judge",
        "judge": str(df["judge"].iloc[0]),
        "source": str(path),
        "is_mock": bool(df["is_mock"].any()),
        "synthetic": bool(df.attrs.get("synthetic", False)),
        "provenance_declared": bool(df["provenance_declared"].all()),
        "evidence_types": evidence,
        "n_labelled": int(len(accept)),
    }
    return accept, provenance, t_star


def assemble_proof_arms(
    manifest_path: Path | str,
    labels_dir: Path | str,
    train_split_only: bool = True,
    seed: int = 42,
) -> ProofArms:
    """Assemble accepted-episode lists for every pre-registered arm that can honestly be built.

    Args:
        manifest_path: Practice pool manifest (Parquet or JSON); needs ``episode_id`` and ``oracle_success``.
        labels_dir: Directory of judge label files (``<judge>.parquet|json|jsonl`` of ``JudgeLabel`` rows).
        train_split_only: Restrict arms to ``split == 'train'`` (PREREGISTRATION §3/§6).
        seed: Seed for the size-matched control and the injected-noise doses.

    Returns:
        :class:`ProofArms`. Judge arms whose label file is missing are absent (``NO_LABELS_REASON``).
    """
    all_records = _read_records(manifest_path)
    for r in all_records:
        if "episode_id" not in r or "oracle_success" not in r:
            raise ValueError("manifest rows need 'episode_id' and 'oracle_success'")
    calibration_ids = {
        str(r["episode_id"]) for r in all_records if str(r.get("split", "")) == "calibration"
    }
    oracle_all = {str(r["episode_id"]): bool(r["oracle_success"]) for r in all_records}

    records = all_records
    if train_split_only:
        records = [r for r in all_records if str(r.get("split", "train")) == "train"]
        if not records:
            raise ValueError("train_split_only=True but the manifest has no split=='train' episodes")

    manifest_mock = any(_truthy(r.get("is_mock"), default=True) for r in records)
    train_ids = [str(r["episode_id"]) for r in records]
    oracle = {e: oracle_all[e] for e in train_ids}
    oracle_accepted = [e for e in train_ids if oracle[e]]
    oracle_failed = [e for e in train_ids if not oracle[e]]
    rng = random.Random(seed)

    out = ProofArms()
    oracle_evidence = "synthetic" if manifest_mock else "live"

    def add(name: str, ids: list[str], prov: dict[str, Any]) -> None:
        out[name] = ids
        out.provenance[name] = prov

    oracle_prov = {
        "kind": "oracle",
        "is_mock": manifest_mock,
        "evidence_type": oracle_evidence,
        "source": str(manifest_path),
    }
    add("oracle", list(oracle_accepted), dict(oracle_prov))
    add("ground_truth", list(oracle_accepted), dict(oracle_prov))
    add("accept_all", list(train_ids), {**oracle_prov, "kind": "accept_all"})

    # Judge arms: label files only.
    t_stars: dict[str, dict[str, int]] = {}
    for arm, stem in JUDGE_ARMS.items():
        path = _find_label_file(labels_dir, stem)
        if path is None:
            out.absent[arm] = NO_LABELS_REASON
            continue
        accept, prov, t_star = _load_judge_arm(path, calibration_ids, oracle_all)
        ids = [e for e in train_ids if accept.get(e, False)]
        prov["n_episodes"] = len(train_ids)
        prov["coverage"] = round(sum(1 for e in train_ids if e in accept) / max(1, len(train_ids)), 4)
        add(arm, ids, prov)
        t_stars[arm] = t_star
    for alias, target in ARM_ALIASES.items():
        if target in out:
            add(alias, list(out[target]), {**out.provenance[target], "alias_of": target})
        else:
            out.absent[alias] = out.absent[target]

    # Prefix salvage: only from the Kodiac judge's own rejections that carry a *measured* t*.
    if "kodiac_cloud" not in out:
        out.absent["kodiac_salvage"] = out.absent["kodiac_cloud"]
    else:
        kod = out.provenance["kodiac_cloud"]
        stars = t_stars["kodiac_cloud"]
        accepted = set(out["kodiac_cloud"])
        prefixes = [
            f"{e}_prefix"
            for e in train_ids
            if e not in accepted and stars.get(e, -1) >= MIN_PREFIX_FRAMES
        ]
        if not stars:
            out.absent["kodiac_salvage"] = (
                "kodiac_cloud labels carry no measured t_star_frame: salvage cut points unavailable"
            )
        else:
            add(
                "kodiac_salvage",
                list(out["kodiac_cloud"]) + prefixes,
                {**kod, "kind": "judge_salvage", "n_prefixes": len(prefixes), "t_star_source": "labels"},
            )

    # Size-matched random control: |D| = |D_Kodiac|.
    if "kodiac_cloud" not in out:
        out.absent["size_matched_control"] = "needs the kodiac_cloud arm size: " + out.absent["kodiac_cloud"]
    else:
        try:
            ids = _labels.size_matched_control(out["kodiac_cloud"], oracle, train_ids, seed=seed)
        except ValueError as exc:
            out.absent["size_matched_control"] = str(exc)
        else:
            add(
                "size_matched_control",
                ids,
                {**oracle_prov, "kind": "random_control", "matched_to": "kodiac_cloud"},
            )

    # Injected-noise doses: oracle successes + k% oracle-failed episodes. NOT a judge.
    for k in DOSES:
        name = f"oracle_k_{k}"
        n_contaminate = int(round(len(oracle_accepted) * (k / 100.0)))
        if n_contaminate > len(oracle_failed):
            out.absent[name] = (
                f"need {n_contaminate} oracle-failed episodes to inject, only {len(oracle_failed)}"
            )
            continue
        injected = rng.sample(oracle_failed, n_contaminate)
        add(
            name,
            list(oracle_accepted) + injected,
            {
                "kind": "injected_noise",
                "note": "oracle successes plus injected false-PASS labels; not a judge",
                "k_percent": k,
                "n_injected": n_contaminate,
                "is_mock": manifest_mock,
                "evidence_type": "synthetic",
                "source": str(manifest_path),
            },
        )
    if "oracle_k_10" in out:
        add("oracle_k_percent", list(out["oracle_k_10"]), {**out.provenance["oracle_k_10"], "alias_of": "oracle_k_10"})
    else:
        out.absent["oracle_k_percent"] = out.absent["oracle_k_10"]
    return out
