"""Tests for proof/labels.py (T09): schema validation, provenance, calibration-only thresholds."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from Kodiac_robotics.proof import labels as L

FX = Path(__file__).resolve().parents[1] / "fixtures" / "proof"


def _row(judge: str, ep: str, accept: bool = True, verdict: str | None = "PASS",
         score: float | None = None, **extra) -> dict:
    r = {"judge": judge, "episode_id": ep, "accept": accept, "verdict": verdict, "score": score,
         "latency_ms": 1, "cost_usd": 0.0}
    r.update(extra)
    return r


def _jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def test_fixture_regenerates_identically(tmp_path: Path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("gen", FX / "make_synthetic_proof_fixtures.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    written = gen.generate(tmp_path)
    assert written
    for p in written:
        rel = p.relative_to(tmp_path)
        assert "SYNTHETIC" in str(rel)
        new, old = p.read_text(encoding="utf-8"), (FX / rel).read_text(encoding="utf-8")
        assert [json.loads(x) for x in new.splitlines()] == [json.loads(x) for x in old.splitlines()]


def test_load_fixture_labels_flags_and_columns() -> None:
    df = L.load_labels(sorted(FX.glob("SYNTHETIC_labels_*.jsonl")))
    assert len(df) == 750 and set(df["judge"]) == {"kodiac", "single_pass_spark_1.3", "robometer-4b"}
    assert df["synthetic"].all() and not df["is_mock"].any()
    assert df.attrs == {"synthetic": True, "is_mock": False, "provenance_declared": True}


def test_load_labels_rejects_invalid_rows(tmp_path: Path) -> None:
    bad = _row("k", "e1")
    del bad["latency_ms"]
    with pytest.raises(ValueError, match="invalid JudgeLabel"):
        L.load_labels([_jsonl(tmp_path / "a.jsonl", [bad])])
    with pytest.raises(ValueError, match="invalid JudgeLabel"):
        L.load_labels([_jsonl(tmp_path / "b.jsonl", [_row("k", "e1", verdict="MAYBE")])])


def test_load_labels_rejects_duplicates_across_files(tmp_path: Path) -> None:
    a = _jsonl(tmp_path / "a.jsonl", [_row("k", "e1")])
    b = _jsonl(tmp_path / "b.jsonl", [_row("k", "e1", accept=False, verdict="FAIL")])
    with pytest.raises(ValueError, match="duplicate"):
        L.load_labels([a, b])
    assert len(L.load_labels([a, _jsonl(tmp_path / "c.jsonl", [_row("s", "e1")])])) == 2


def test_unknown_provenance_is_mock_and_filename_marks_synthetic(tmp_path: Path) -> None:
    df = L.load_labels([_jsonl(tmp_path / "plain.jsonl", [_row("k", "e1")])])
    assert df["is_mock"].all() and not df["provenance_declared"].any()
    assert df.attrs["is_mock"] is True and df.attrs["provenance_declared"] is False
    df2 = L.load_labels(
        [_jsonl(tmp_path / "x_SYNTHETIC.jsonl", [_row("k", "e1", synthetic=False, is_mock=False)])]
    )
    assert df2.attrs["synthetic"] is True and df2.attrs["is_mock"] is False


def test_load_labels_parquet_roundtrip(tmp_path: Path) -> None:
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    rows = [_row("k", "e1", is_mock=False), _row("k", "e2", accept=False, verdict="FAIL",
                                                 is_mock=False)]
    pq.write_table(pa.Table.from_pylist(rows), tmp_path / "k.parquet")
    df = L.load_labels([tmp_path / "k.parquet"])
    assert list(df["accept"]) == [True, False] and df.attrs["is_mock"] is False


def test_fit_max_ba_threshold_hand_example_and_tie_break() -> None:
    # tau=.35 -> BA .75 ; tau=.8 -> BA .75 ; ties go to the highest tau
    tau, ba = L.fit_max_ba_threshold([0.1, 0.4, 0.35, 0.8], [False, False, True, True])
    assert (tau, ba) == (0.8, 0.75)
    tau, ba = L.fit_max_ba_threshold([0.2, 0.3, 0.7, 0.9], [False, False, True, True])
    assert (tau, ba) == (0.7, 1.0)
    with pytest.raises(ValueError):
        L.fit_max_ba_threshold([0.1, 0.2], [True, True])


def _score_frame(tmp_path: Path, calib_scores: dict, train_scores: dict):
    rows = [_row("robometer-4b", e, accept=True, verdict=None, score=s, is_mock=False)
            for e, s in {**calib_scores, **train_scores}.items()]
    return L.load_labels([_jsonl(tmp_path / f"r{len(rows)}{sum(train_scores.values())}.jsonl",
                                 rows)])


def test_threshold_fit_uses_calibration_split_only(tmp_path: Path) -> None:
    oracle = {"c1": True, "c2": False, "c3": True, "c4": False, "t1": True, "t2": False}
    calib = {"c1", "c2", "c3", "c4"}
    cal = {"c1": 0.9, "c2": 0.3, "c3": 0.6, "c4": 0.65}
    a = L.apply_thresholds(_score_frame(tmp_path, cal, {"t1": 0.95, "t2": 0.1}), calib, oracle)
    b = L.apply_thresholds(_score_frame(tmp_path, cal, {"t1": 0.01, "t2": 0.99}), calib, oracle)
    assert set(a["threshold"]) == {0.9} == set(b["threshold"])  # train scores cannot move tau
    assert set(a["threshold_source"]) == {"calibration_max_ba"}
    acc_a = dict(zip(a["episode_id"], a["accept"]))
    assert bool(acc_a["t1"]) and not bool(acc_a["t2"])
    acc = dict(zip(b["episode_id"], b["accept"]))
    assert acc["t2"] and not acc["t1"]  # tau applied to train rows
    c = L.apply_thresholds(
        _score_frame(tmp_path, {**cal, "c2": 0.95}, {"t1": 0.95, "t2": 0.1}), calib, oracle
    )
    assert set(c["threshold"]) != {0.9}  # calibration scores do move tau
    assert dict(zip(a["episode_id"], a["split"])) == {
        "c1": "calibration", "c2": "calibration", "c3": "calibration", "c4": "calibration",
        "t1": "train", "t2": "train"}


def test_apply_thresholds_forces_cant_tell_to_reject_and_guards(tmp_path: Path) -> None:
    rows = [_row("kodiac", "e1", accept=True, verdict="CANT_TELL", is_mock=False),
            _row("kodiac", "e2", accept=True, verdict="PASS", is_mock=False)]
    df = L.load_labels([_jsonl(tmp_path / "k.jsonl", rows)])
    out = L.apply_thresholds(df, {"c"}, {"e1": True, "e2": True})
    assert dict(zip(out["episode_id"], out["accept"])) == {"e1": False, "e2": True}
    assert out.attrs["n_cant_tell_forced_reject"] == 1
    assert out.attrs["is_mock"] is True  # plain-dict oracle => provenance unknown
    with pytest.raises(ValueError, match="calibration split is empty"):
        L.apply_thresholds(df, set(), {})
    noscore = L.load_labels([_jsonl(tmp_path / "n.jsonl",
                                    [_row("robometer-4b", "e1", verdict=None, score=None)])])
    with pytest.raises(ValueError):
        L.apply_thresholds(noscore, {"e1"}, {"e1": True})


def test_load_oracle_and_arm_evals_from_fixture() -> None:
    oracle = L.load_oracle(FX / "SYNTHETIC_oracle_manifest.json")
    assert len(oracle) == 250 and oracle.synthetic is True
    assert sum(1 for s in oracle.splits.values() if s == "calibration") == 50
    arms = L.load_arm_evals(FX / "evals_SYNTHETIC")
    assert set(arms) == {"kodiac", "single_pass", "accept_all", "oracle", "oracle_k_10"}
    for a in arms.values():
        assert sorted(a) == [42, 43, 44] and all(len(v) == 200 for v in a.values())
        assert a.synthetic is True and a.is_mock is False


def test_load_arm_evals_provenance_and_duplicates(tmp_path: Path) -> None:
    assert L.load_arm_evals(tmp_path / "missing") == {}
    (tmp_path / "a.json").write_text(json.dumps({"arm": "kodiac", "seed": 1, "success": [1, 0]}),
                                     encoding="utf-8")
    arms = L.load_arm_evals(tmp_path)
    assert arms["kodiac"].is_mock is True  # no is_mock key => unknown provenance => mock
    (tmp_path / "b.json").write_text(json.dumps({"arm": "kodiac", "seed": 1, "success": [1]}),
                                     encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        L.load_arm_evals(tmp_path)


def test_size_matched_control() -> None:
    oracle = {f"e{i}": i % 2 == 0 for i in range(20)}
    train = [f"e{i}" for i in range(4, 20)]
    ctrl = L.size_matched_control(["e4", "e5", "e7"], oracle, train, seed=3)
    assert len(ctrl) == 3 and all(oracle[e] and e in train for e in ctrl)
    assert ctrl == L.size_matched_control(["e4", "e5", "e7"], oracle, train, seed=3)
    with pytest.raises(ValueError):
        L.size_matched_control([f"x{i}" for i in range(9)], oracle, train)
