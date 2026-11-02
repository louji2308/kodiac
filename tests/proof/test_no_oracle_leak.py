"""Static audit: nothing that acts as a judge may read the oracle; test doubles are unreachable from src/."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import Kodiac_robotics
from Kodiac_robotics.proof.arms import assemble_proof_arms

SRC = Path(Kodiac_robotics.__file__).parent
JUDGES = SRC / "proof" / "judges"
FORBIDDEN = ("oracle_success_hint", "oracle_success")


def _judge_modules() -> list[Path]:
    return [p for p in sorted(JUDGES.glob("*.py")) if p.name != "_test_doubles.py"]


def test_judge_modules_exist_and_never_mention_the_oracle() -> None:
    mods = _judge_modules()
    assert {p.name for p in mods} >= {"single_pass.py", "robometer.py", "topreward.py", "base.py"}
    for path in mods:
        text = path.read_text(encoding="utf-8")
        for word in FORBIDDEN:
            assert word not in text, f"{path.name} references {word}"
        for node in ast.walk(ast.parse(text)):
            names = [getattr(node, "id", None), getattr(node, "attr", None), getattr(node, "arg", None)]
            assert not any(n and "oracle" in n.lower() for n in names), f"{path.name}: {names}"


def test_test_doubles_not_imported_by_production_code() -> None:
    offenders = []
    for path in SRC.rglob("*.py"):
        if path.name == "_test_doubles.py":
            continue
        if "_test_doubles" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(SRC)))
    assert offenders == [], f"production modules import test doubles: {offenders}"


def test_arms_module_has_no_hard_coded_judge_error_rates() -> None:
    tree = ast.parse((SRC / "proof" / "arms.py").read_text(encoding="utf-8"))
    random_calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in {"random", "choice", "uniform"}
    ]
    assert random_calls == [], "arms.py draws random accept decisions; only rng.sample is allowed"


def test_empty_labels_dir_yields_no_judge_arms(tmp_path: Path) -> None:
    manifest = tmp_path / "m.json"
    manifest.write_text(
        json.dumps(
            [{"episode_id": f"t{i}", "split": "train", "oracle_success": i % 2 == 0, "is_mock": True} for i in range(50)]
            + [{"episode_id": f"c{i}", "split": "calibration", "oracle_success": i % 2 == 0, "is_mock": True} for i in range(10)]
        )
    )
    (tmp_path / "labels").mkdir()
    arms = assemble_proof_arms(manifest, tmp_path / "labels")
    allowed = {"oracle", "ground_truth", "accept_all", "oracle_k_percent", "oracle_k_5", "oracle_k_10", "oracle_k_20", "oracle_k_30"}
    assert set(arms) == allowed
    assert set(arms.absent) >= {
        "kodiac_cloud", "kodiac_open_weights", "kodiac_salvage", "single_pass_spark_2fps",
        "robometer_4b", "topreward", "size_matched_control",
    }
    assert all(arms.provenance[a]["is_mock"] for a in arms)
