"""Baseline judges fail closed: no key/model -> JudgeUnavailable, never a stand-in decision (Law 1)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from Kodiac_robotics.contracts.core import JudgeLabel, Verdict
from Kodiac_robotics.proof.judges import (
    JudgeUnavailable,
    RobometerJudge,
    SinglePassSparkJudge,
    TOPRewardJudge,
)
from Kodiac_robotics.proof.judges._test_doubles import DOUBLE_SUFFIX, OracleCopyDouble


@pytest.fixture(autouse=True)
def _no_ambient_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MODEL_API_KEY", "KODIAC_MODEL_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("KODIAC_ENV_FILE", str(Path(__file__).parent / "_absent.env"))


def _video(tmp_path: Path) -> Path:
    p = tmp_path / "ep.mp4"
    p.write_bytes(b"not a real video: frames come from the injected extractor")
    return p


def _transport(answer: str, seen: list[dict]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"answer": answer, "reason": "r"})}}]})

    return httpx.MockTransport(handler)


def test_single_pass_without_key_raises_not_a_constant(tmp_path: Path) -> None:
    with pytest.raises(JudgeUnavailable, match="MODEL_API_KEY"):
        SinglePassSparkJudge().evaluate_episode("ep1", video_path=_video(tmp_path))


def test_single_pass_without_video_raises(tmp_path: Path) -> None:
    judge = SinglePassSparkJudge(api_key="k")
    with pytest.raises(JudgeUnavailable):
        judge.evaluate_episode("ep1", video_path=None)
    with pytest.raises(JudgeUnavailable):
        judge.evaluate_episode("ep1", video_path=tmp_path / "missing.mp4")


@pytest.mark.parametrize(
    ("answer", "accept", "verdict"),
    [("yes", True, Verdict.PASS), ("no", False, Verdict.FAIL), ("cant_tell", False, Verdict.CANT_TELL)],
)
def test_single_pass_label_follows_model_reply_and_marks_fixture(
    tmp_path: Path, answer: str, accept: bool, verdict: Verdict
) -> None:
    seen: list[dict] = []
    judge = SinglePassSparkJudge(
        api_key="k",
        base_url="https://example.invalid/v1",
        model_id="muse-spark-test",
        transport=_transport(answer, seen),
        frame_extractor=lambda path, fps: [b"\x89PNG-a", b"\x89PNG-b"],
    )
    label = judge.evaluate_episode("ep1", video_path=_video(tmp_path))
    assert isinstance(label, JudgeLabel)
    assert (label.accept, label.verdict) == (accept, verdict)
    assert label.judge == "single_pass_spark_1.3" and label.score is None
    assert label.is_mock is True and label.evidence_type == "fixture"  # injected transport can never claim live
    content = seen[0]["messages"][1]["content"]
    assert sum(1 for part in content if part["type"] == "image_url") == 2
    assert seen[0]["model"] == "muse-spark-test"


def test_single_pass_unparseable_reply_is_cant_tell_not_pass(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "looks great!"}}]})

    judge = SinglePassSparkJudge(
        api_key="k",
        transport=httpx.MockTransport(handler),
        frame_extractor=lambda path, fps: [b"x"],
    )
    label = judge.evaluate_episode("ep1", video_path=_video(tmp_path))
    assert label.verdict == Verdict.CANT_TELL and label.accept is False


def test_robometer_without_scorer_raises() -> None:
    with pytest.raises(JudgeUnavailable, match="not been run"):
        RobometerJudge().evaluate_episode("ep2", video_path="x.mp4")


def test_topreward_without_scorer_raises() -> None:
    with pytest.raises(JudgeUnavailable, match="not been run"):
        TOPRewardJudge().evaluate_episode("ep3", state_npz_path="x.npz")


def test_scorer_requires_declared_provenance() -> None:
    with pytest.raises(ValueError, match="provenance"):
        RobometerJudge(scorer=lambda p: 0.9)
    with pytest.raises(ValueError, match="provenance"):
        TOPRewardJudge(scorer=lambda p: 0.9)


def test_robometer_scorer_label_provenance_and_threshold() -> None:
    live = RobometerJudge(calibration_threshold=0.6, scorer=lambda p: 0.7, provenance="live")
    label = live.evaluate_episode("ep2", video_path="v.mp4")
    assert label.accept is True and label.score == 0.7
    assert (label.is_mock, label.evidence_type) == (False, "live")
    replay = RobometerJudge(calibration_threshold=0.8, scorer=lambda p: 0.7, provenance="fixture")
    label = replay.evaluate_episode("ep2", video_path="v.mp4")
    assert label.accept is False and label.verdict == Verdict.FAIL
    assert (label.is_mock, label.evidence_type) == (True, "fixture")


def test_topreward_scorer_label_provenance() -> None:
    judge = TOPRewardJudge(calibration_threshold=0.55, scorer=lambda p: 0.9, provenance="fixture")
    label = judge.evaluate_episode("ep3", state_npz_path="s.npz")
    assert label.accept is True and label.is_mock is True and label.evidence_type == "fixture"


def test_threshold_tuning_on_calibration_pairs() -> None:
    cal_data = [(0.85, True), (0.75, True), (0.65, True), (0.55, False), (0.40, False), (0.20, False)]
    assert 0.50 <= RobometerJudge(calibration_threshold=0.60).tune_threshold_on_calibration(cal_data) <= 0.70
    assert 0.50 <= TOPRewardJudge(calibration_threshold=0.55).tune_threshold_on_calibration(cal_data) <= 0.70
    assert RobometerJudge(calibration_threshold=0.61).tune_threshold_on_calibration([]) == 0.61


def test_oracle_copy_double_is_loudly_marked() -> None:
    label = OracleCopyDouble("robometer-4b").label("e1", True)
    assert label.judge.endswith(DOUBLE_SUFFIX)
    assert label.is_mock is True and label.evidence_type == "synthetic"
    assert label.accept is True and OracleCopyDouble().label("e2", False).accept is False
