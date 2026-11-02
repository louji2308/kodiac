"""Diff tests: Myers LCS properties and golden snapshots on constructed event lists.

The event lists below are hand-constructed (labelled synthetic) to exercise each diff branch;
they are not measurements. Golden files live in tests/blame/golden/ and were reviewed by hand.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from Kodiac_robotics.blame.diff import diff_events, myers_lcs
from Kodiac_robotics.contracts.core import Event, Verdict

GOLDEN = Path(__file__).parent / "golden"


def _lcs_len(a: list[str], b: list[str]) -> int:
    dp = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) - 1, -1, -1):
        for j in range(len(b) - 1, -1, -1):
            dp[i][j] = dp[i + 1][j + 1] + 1 if a[i] == b[j] else max(dp[i + 1][j], dp[i][j + 1])
    return dp[0][0]


def _check_structure(a: list[str], b: list[str], pairs: list[tuple[int | None, int | None]]) -> None:
    left = [i for i, _ in pairs if i is not None]
    right = [j for _, j in pairs if j is not None]
    assert left == list(range(len(a))), "every index of a appears exactly once, in order"
    assert right == list(range(len(b))), "every index of b appears exactly once, in order"
    for i, j in pairs:
        if i is not None and j is not None:
            assert a[i] == b[j]


# ------------------------------------------------------------------- LCS
def test_lcs_empty_inputs() -> None:
    assert myers_lcs([], []) == []
    assert myers_lcs([], ["x", "y"]) == [(None, 0), (None, 1)]
    assert myers_lcs(["x", "y"], []) == [(0, None), (1, None)]


def test_lcs_identical() -> None:
    seq = list("abcde")
    assert myers_lcs(seq, seq) == [(i, i) for i in range(5)]


def test_lcs_disjoint_deletions_before_insertions() -> None:
    assert myers_lcs(["a", "b"], ["x", "y"]) == [(0, None), (1, None), (None, 0), (None, 1)]


def test_lcs_reorder_keeps_longest_common_subsequence() -> None:
    a, b = list("abcd"), list("acbd")
    pairs = myers_lcs(a, b)
    _check_structure(a, b, pairs)
    assert sum(1 for i, j in pairs if i is not None and j is not None) == 3


def test_lcs_insertion_and_deletion_in_middle() -> None:
    a, b = list("abcd"), list("abxcd")
    assert myers_lcs(a, b) == [(0, 0), (1, 1), (None, 2), (2, 3), (3, 4)]
    assert myers_lcs(b, a) == [(0, 0), (1, 1), (2, None), (3, 2), (4, 3)]


def test_lcs_matches_dp_on_random_sequences() -> None:
    rng = random.Random(1234)
    for _ in range(300):
        a = [rng.choice("abc") for _ in range(rng.randint(0, 9))]
        b = [rng.choice("abc") for _ in range(rng.randint(0, 9))]
        pairs = myers_lcs(a, b)
        _check_structure(a, b, pairs)
        matches = sum(1 for i, j in pairs if i is not None and j is not None)
        assert matches == _lcs_len(a, b), (a, b)


# ---------------------------------------------------------- event fixtures
def _ev(
    step: int,
    name: str,
    kind: str,
    t: float,
    source: str,
    predicate: str | None = None,
    args: list[str] | None = None,
    measurements: dict[str, tuple[float, float]] | None = None,
    verdict: Verdict | None = None,
) -> Event:
    return Event(
        step=step,
        step_name=name,
        kind=kind,  # type: ignore[arg-type]
        predicate=predicate,
        args=args or [],
        t_s=t,
        frame=round(t * 30),
        fps=30.0,
        measurements=measurements or {},
        source=source,  # type: ignore[arg-type]
        verdict=verdict,
    )


def _demo() -> list[Event]:
    return [
        _ev(0, "grasp", "grasped", 2.0, "demo", "moves_with", ["gripper", "cubeA"],
            {"moves_with.slip": (0.3, 0.1)}, Verdict.PASS),
        _ev(1, "place", "settled", 4.1, "demo", "on", ["cubeA", "cubeB"],
            {"on.align_xy": (0.8, 0.2), "on.gap": (0.1, 0.1)}, Verdict.PASS),
        _ev(2, "release", "achieved", 5.0, "demo", "dwell", ["cubeA", "cubeB"],
            {"dwell.duration": (0.6, 0.03)}, Verdict.PASS),
    ]


def _golden(name: str, text: str) -> None:
    path = GOLDEN / name
    assert path.is_file(), f"missing golden file {path}"
    assert text == path.read_text(encoding="utf-8"), f"snapshot mismatch for {name}:\n{text}"


def test_identical_events_are_all_context_lines() -> None:
    demo = _demo()
    attempt = [e.model_copy(update={"source": "attempt"}) for e in demo]
    text = diff_events(demo, attempt)
    body = text.splitlines()[3:]
    assert len(body) == 3 and all(ln.startswith("  [") for ln in body)
    assert "@@ 3 matched, 0 demo-only/diverging, 0 attempt-only/diverging" in text


def test_within_sigma_is_context_and_outside_is_minus_plus() -> None:
    demo = _demo()
    near = [e.model_copy(update={"source": "attempt"}) for e in demo]
    near[1] = near[1].model_copy(
        update={"measurements": {"on.align_xy": (1.1, 0.2), "on.gap": (0.1, 0.1)}}
    )  # |1.1-0.8| = 0.3 <= 2 * hypot(0.2, 0.2) = 0.57
    assert "\n- " not in diff_events(demo, near)
    far = near[:]
    far[1] = far[1].model_copy(
        update={"measurements": {"on.align_xy": (5.0, 0.3), "on.gap": (0.1, 0.1)}}
    )
    text = diff_events(demo, far)
    assert "\n- [1] place: settled" in text and "\n+ [1] place: settled" in text
    assert "outside 2 sigma: on.align_xy" in text
    assert "on.gap" not in text.split("outside 2 sigma:")[1].splitlines()[0]


def test_sigma_k_widens_the_context_band() -> None:
    demo = _demo()
    att = [e.model_copy(update={"source": "attempt"}) for e in demo]
    att[1] = att[1].model_copy(
        update={"measurements": {"on.align_xy": (2.0, 0.2), "on.gap": (0.1, 0.1)}}
    )
    assert "\n- [1]" in diff_events(demo, att, sigma_k=2.0)  # 1.2 > 0.57
    assert "\n- [1]" not in diff_events(demo, att, sigma_k=5.0)  # 1.2 <= 1.41


def test_snapshot_early_release_failure() -> None:
    demo = _demo()
    attempt = [
        _ev(0, "grasp", "grasped", 2.1, "attempt", "moves_with", ["gripper", "cubeA"],
            {"moves_with.slip": (0.4, 0.1)}, Verdict.PASS),
        _ev(1, "place", "failed", 3.8, "attempt", verdict=Verdict.FAIL),
        _ev(1, "place", "released", 3.8, "attempt", "moves_with", ["gripper", "cubeA"],
            {"moves_with.slip": (4.7, 0.3)}, Verdict.FAIL),
    ]
    _golden("diff_early_release.txt", diff_events(demo, attempt))


def test_snapshot_xy_offset_diverging_measurement() -> None:
    demo = _demo()
    attempt = [
        _ev(0, "grasp", "grasped", 2.0, "attempt", "moves_with", ["gripper", "cubeA"],
            {"moves_with.slip": (0.3, 0.1)}, Verdict.PASS),
        _ev(1, "place", "settled", 4.3, "attempt", "on", ["cubeA", "cubeB"],
            {"on.align_xy": (5.0, 0.3), "on.gap": (0.1, 0.1)}, Verdict.PASS),
        _ev(2, "release", "achieved", 5.2, "attempt", "dwell", ["cubeA", "cubeB"],
            {"dwell.duration": (0.6, 0.03)}, Verdict.PASS),
    ]
    _golden("diff_xy_offset.txt", diff_events(demo, attempt))


@pytest.mark.parametrize(
    ("tier", "golden"), [("C", "diff_direction_tier_c.txt"), ("A", "diff_direction_tier_a.txt")]
)
def test_snapshot_direction_words_by_tier(tier: str, golden: str) -> None:
    demo = [
        _ev(1, "place", "settled", 4.1, "demo", "on", ["cubeA", "cubeB"],
            {"on.offset_dx": (0.2, 0.2), "on.offset_dy": (-0.1, 0.2)}, Verdict.PASS)
    ]
    attempt = [
        _ev(1, "place", "settled", 4.3, "attempt", "on", ["cubeA", "cubeB"],
            {"on.offset_dx": (-4.6, 0.3), "on.offset_dy": (2.4, 0.3)}, Verdict.PASS)
    ]
    _golden(golden, diff_events(demo, attempt, camera_tier=tier))  # type: ignore[arg-type]


def test_demo_only_events_print_as_minus() -> None:
    demo = _demo()
    text = diff_events(demo, [])
    assert [ln[:2] for ln in text.splitlines()[3:]] == ["- ", "- ", "- "]
    assert "@@ 0 matched, 3 demo-only/diverging, 0 attempt-only/diverging" in text


def test_empty_both_has_header_only() -> None:
    assert diff_events([], []).splitlines()[:2] == ["--- demo", "+++ attempt"]
