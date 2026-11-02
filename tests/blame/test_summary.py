"""Summary: deterministic template always validates; injected LLM is accepted only when it validates."""

from __future__ import annotations

import pytest

from Kodiac_robotics.blame.summary import (
    build_prompt,
    fmt_clock,
    fmt_num,
    render_template_summary,
    summarize,
)
from Kodiac_robotics.blame.validate import blame_from_run, validate_summary

from .test_transitions import FPS, scenario


def _ft(name: str):
    sc = scenario(name)
    b = blame_from_run(sc.result, sc.test, sc.frames, FPS, reference_frames=sc.reference)
    assert b is not None
    return sc, b.facts


@pytest.mark.parametrize("name", ["b01_early_release", "b02_xy_offset", "b10_place_high", "b09_low_lift"])
def test_template_is_valid_one_sentence_with_value_sigma(name: str) -> None:
    sc, ft = _ft(name)
    text = render_template_summary(ft)
    assert text.startswith("blame: ")
    assert "±" in text
    assert validate_summary(text, ft, sc.test) == []


def test_template_b01_matches_architecture_wording() -> None:
    _, ft = _ft("b01_early_release")
    text = render_template_summary(ft)
    assert text.startswith("blame: gripper released cubeA ")
    assert " s before reaching cubeB (xy offset 9.0 ± 0.1 cm at 00:01.5, frame 46)" in text


def test_no_llm_gives_template() -> None:
    sc, ft = _ft("b02_xy_offset")
    text, src = summarize(ft, sc.test)
    assert src == "template" and text == render_template_summary(ft)


def test_valid_llm_sentence_is_accepted_as_muse_spark() -> None:
    sc, ft = _ft("b02_xy_offset")
    calls: list[str] = []

    def llm(prompt: str) -> str:
        calls.append(prompt)
        return "blame: the gripper let go of cubeA 4.5 ± 0.1 cm away from cubeB at 00:02.4 (frame 73)."

    text, src = summarize(ft, sc.test, llm=llm)
    assert src == "muse-spark"
    assert "4.5 ± 0.1 cm" in text
    assert len(calls) == 1
    assert "FACTS (JSON)" in calls[0] and "moves_with(gripper, cubeA)" in calls[0]


def test_bad_llm_twice_falls_back_to_template() -> None:
    sc, ft = _ft("b02_xy_offset")
    calls: list[str] = []

    def llm(prompt: str) -> str:
        calls.append(prompt)
        return "blame: the gripper released cubeA 7.3 ± 0.2 cm from cubeB."

    text, src = summarize(ft, sc.test, llm=llm)
    assert src == "template"
    assert text == render_template_summary(ft)
    assert len(calls) == 2
    assert "rejected for" in calls[1] and "7.3" in calls[1]


def test_bad_then_good_llm_is_accepted_after_retry() -> None:
    sc, ft = _ft("b02_xy_offset")
    answers = iter([
        "blame: the gripper opened and dropped cubeA near the bowl.",
        "blame: gripper released cubeA 4.5 ± 0.1 cm from cubeB in xy at 00:02.4, frame 73",
    ])
    text, src = summarize(ft, sc.test, llm=lambda _p: next(answers))
    assert src == "muse-spark" and "4.5 ± 0.1" in text


def test_llm_exception_falls_back_to_template() -> None:
    sc, ft = _ft("b09_low_lift")

    def llm(_prompt: str) -> str:
        raise TimeoutError("spark timeout")

    text, src = summarize(ft, sc.test, llm=llm)
    assert src == "template" and text == render_template_summary(ft)


def test_prompt_contains_only_facts_and_green_text() -> None:
    sc, ft = _ft("b09_low_lift")
    prompt = build_prompt(ft, sc.test)
    assert "TEST (.green)" in prompt and "lifted(cubeA" in prompt
    assert '"lift_cm"' in prompt


def test_formatters() -> None:
    assert fmt_clock(1.5333) == "00:01.5"
    assert fmt_clock(75.04) == "01:15.0"
    assert fmt_num(0.0006) == "0.0"
    assert fmt_num(0.017) == "0.02"
    assert fmt_num(-0.01) == "-0.01"
    assert fmt_num(8.998) == "9.0"
