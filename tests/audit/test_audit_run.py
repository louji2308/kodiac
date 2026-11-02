"""audit_run: filtering, resumability, failure isolation, labelling (stubbed + real pipeline)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from audit_helpers import STACK_GREEN, load_episodes, stub_run_fn

from Kodiac_robotics.audit.rows import DEMO_BANNER, to_verdict_row
from Kodiac_robotics.audit.run import audit_run, text_compile_resolver
from Kodiac_robotics.contracts.core import Verdict, VerdictRow

DS = "fixture/demo-stack"
VERDICTS = {
    0: Verdict.FAIL,
    1: Verdict.FAIL,
    2: Verdict.CANT_TELL,
    3: Verdict.PASS,
    4: Verdict.PASS,
    5: Verdict.FAIL,
}


def _run(tmp_path: Path, run_fn, **kw) -> pd.DataFrame:
    return audit_run(
        DS,
        kw.pop("task_filter", "stack|put|pick"),
        kw.pop("camera", "cam_top"),
        kw.pop("limit", 10),
        episodes=load_episodes(),
        out_dir=tmp_path,
        test_for_task=kw.pop("test_for_task", lambda task: STACK_GREEN),
        run_fn=run_fn,
    )


def test_filters_rows_are_verdictrow_conformant_and_labelled(tmp_path: Path) -> None:
    df = _run(tmp_path, stub_run_fn(VERDICTS))
    # camera cam_top only, "wipe the table" excluded by the task regex, cam_side excluded
    assert list(df["episode_index"]) == [0, 1, 2, 3]
    for rec in df.to_dict("records"):
        assert isinstance(to_verdict_row(rec), VerdictRow)
        assert to_verdict_row(rec).human_verified is None
    assert df["human_verified"].isna().all()
    assert df["is_demonstration_data"].all()
    assert df["notes"].str.contains(DEMO_BANNER, regex=False).all()
    fail0 = df[df["episode_index"] == 0].iloc[0]
    assert fail0["verdict"] == "FAIL" and fail0["step"] == "release"
    assert fail0["predicate"] == "moves_with.slip" and fail0["margin"] == -2.5
    assert fail0["evidence_uri"].endswith("card.png")
    assert (tmp_path / "verdicts.parquet").is_file()


def test_limit_and_empty_selection(tmp_path: Path) -> None:
    df = _run(tmp_path, stub_run_fn(VERDICTS), limit=2)
    assert list(df["episode_index"]) == [0, 1]
    empty = _run(tmp_path / "e", stub_run_fn(VERDICTS), task_filter="nomatch")
    assert len(empty) == 0
    with pytest.raises(ValueError):
        _run(tmp_path / "z", stub_run_fn(VERDICTS), limit=0)


def test_resumable_reuses_cached_episodes(tmp_path: Path) -> None:
    calls: list[int] = []
    first = _run(tmp_path, stub_run_fn(VERDICTS, calls))
    assert sorted(calls) == [0, 1, 2, 3]
    calls.clear()
    second = _run(tmp_path, stub_run_fn(VERDICTS, calls))
    assert calls == []
    pd.testing.assert_frame_equal(first, second)


def test_changed_green_invalidates_cache(tmp_path: Path) -> None:
    calls: list[int] = []
    _run(tmp_path, stub_run_fn(VERDICTS, calls), limit=1)
    other = tmp_path / "other.green"
    other.write_text(STACK_GREEN.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")
    calls.clear()
    _run(tmp_path, stub_run_fn(VERDICTS, calls), limit=1, test_for_task=lambda t: other)
    assert calls == [0]


def test_per_episode_failure_isolation_and_retry(tmp_path: Path) -> None:
    good = stub_run_fn(VERDICTS)

    def flaky(test_path, clip_path, out_dir, is_fixture):
        if out_dir.name.endswith("000001"):
            raise RuntimeError("boom")
        return good(test_path, clip_path, out_dir, is_fixture)

    df = _run(tmp_path, flaky)
    assert len(df) == 4
    bad = df[df["episode_index"] == 1].iloc[0]
    assert bad["verdict"] == "CANT_TELL" and list(bad["reasons"]) == ["run_error"]
    assert "RuntimeError: boom" in bad["error"]
    assert df[df["episode_index"] == 0].iloc[0]["verdict"] == "FAIL"

    calls: list[int] = []
    again = _run(tmp_path, stub_run_fn(VERDICTS, calls))
    assert calls == [1]  # only the errored episode is retried
    assert again[again["episode_index"] == 1].iloc[0]["error"] is None


def test_compile_failure_is_isolated_and_cached_per_task(tmp_path: Path) -> None:
    seen: list[str] = []

    def resolver(task: str) -> Path:
        seen.append(task)
        raise ValueError("E003: unsupported manipulation action")

    df = _run(tmp_path, stub_run_fn(VERDICTS), test_for_task=resolver)
    assert len(df) == 4 and (df["verdict"] == "CANT_TELL").all()
    assert seen == ["stack cubeA on cubeB"]  # one compile attempt per (dataset, task)


def test_template_fallback_badge_propagates(tmp_path: Path) -> None:
    resolver = text_compile_resolver(tmp_path / "compiled")
    df = _run(tmp_path / "out", stub_run_fn(VERDICTS), test_for_task=resolver, limit=1)
    assert "[COMPILER: DETERMINISTIC TEMPLATE FALLBACK]" in df.iloc[0]["notes"]
    assert len(list((tmp_path / "compiled").glob("*.green"))) == 1


def test_real_pipeline_on_fixture_clips(tmp_path: Path) -> None:
    df = audit_run(
        DS,
        "stack",
        "cam_top",
        3,
        episodes=load_episodes(),
        out_dir=tmp_path,
        test_for_task=lambda task: STACK_GREEN,
    )
    by_idx = {int(r["episode_index"]): r for r in df.to_dict("records")}
    assert by_idx[0]["verdict"] == "FAIL" and by_idx[0]["step"] == "grasp"
    assert by_idx[0]["predicate"] and by_idx[0]["sigma"] > 0
    assert by_idx[2]["verdict"] == "CANT_TELL" and "occluded" in list(by_idx[2]["reasons"])
    assert all(r["is_demonstration_data"] for r in by_idx.values())
    assert "[REPLAY: CACHED SAM 3.1 TRACKS]" in by_idx[0]["notes"]
    assert (tmp_path / by_idx[0]["evidence_uri"]).is_file()
