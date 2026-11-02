import itertools

import judge_synth as synth
import numpy as np
import pytest

from Kodiac_robotics.contracts.core import Atom, ObjMask, ReasonCode, Tri
from Kodiac_robotics.judge.backends import FixtureBackend, JudgeAnswer
from Kodiac_robotics.judge.two_way import (
    ANTONYMS,
    TwoWayJudge,
    antonym_questions,
    judge_atom,
)

CROP = b"not-a-real-png-but-hashable"
QP, QN = "Is the drawer flush?", "Is the drawer ajar?"
ANSWERS = ("yes", "no", "cant_tell")


class ScriptedBackend:
    """Test double answering from a {question: answer} script; counts calls."""

    def __init__(self, pos, neg, name="scripted", fixture=False, delay=None, clock=None):
        self.name, self.model_id, self.is_fixture = name, f"{name}-model", fixture
        self.script = {QP: pos, QN: neg}
        self.calls = 0
        self.delay, self.clock = delay, clock

    def ask(self, crop_png, question, system):
        self.calls += 1
        if self.clock is not None and self.delay:
            self.clock.t += self.delay
        return JudgeAnswer(answer=self.script[question], reason="scripted")


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def judge(primary, escalator=None, **kw):
    kw.setdefault("cache", False)
    return TwoWayJudge(primary, escalator, **kw)


def expected(pos, neg):
    if (pos, neg) == ("yes", "no"):
        return Tri.T
    if (pos, neg) == ("no", "yes"):
        return Tri.F
    return None


# ---- antonyms -------------------------------------------------------------

def test_antonym_questions_flush():
    assert antonym_questions("drawer", "flush") == ("Is the drawer flush?", "Is the drawer ajar?")


def test_antonym_table_is_symmetric_and_never_uses_not():
    assert ANTONYMS
    for a, b in ANTONYMS.items():
        assert b in ANTONYMS, f"{b} has no entry of its own"
        assert "not" not in b.split() and "n't" not in b
    for state in ANTONYMS:
        q_pos, q_neg = antonym_questions("lid", state)
        assert " not " not in q_neg and q_pos != q_neg


@pytest.mark.parametrize("state", ["not flush", "isn't open"])
def test_negated_state_rejected(state):
    with pytest.raises(ValueError):
        antonym_questions("drawer", state)


def test_unknown_state_has_no_invented_antonym():
    with pytest.raises(ValueError):
        antonym_questions("drawer", "purple")


# ---- decision table -------------------------------------------------------

@pytest.mark.parametrize("pos,neg", list(itertools.product(ANSWERS, ANSWERS)))
def test_primary_decision_table_no_escalator(pos, neg):
    tri, reason = judge(ScriptedBackend(pos, neg)).ask_two_way(CROP, QP, QN)
    want = expected(pos, neg)
    assert tri is (want if want is not None else Tri.U)
    if want is None:
        assert reason.startswith("appearance_unresolved")


@pytest.mark.parametrize("pos,neg", list(itertools.product(ANSWERS, ANSWERS)))
@pytest.mark.parametrize("epos,eneg", list(itertools.product(ANSWERS, ANSWERS)))
def test_escalation_matrix(pos, neg, epos, eneg):
    prim, esc = ScriptedBackend(pos, neg, "prim"), ScriptedBackend(epos, eneg, "esc")
    tri, reason = judge(prim, esc).ask_two_way(CROP, QP, QN)
    direct = expected(pos, neg)
    if direct is not None:
        assert tri is direct
        assert esc.calls == 0  # agreement never escalates
    else:
        assert esc.calls == 2
        want = expected(epos, eneg)
        assert tri is (want if want is not None else Tri.U)
        if want is None:
            assert reason.startswith("appearance_unresolved")


def test_questions_are_asked_in_parallel_threads():
    import threading

    seen = set()

    class B(ScriptedBackend):
        def ask(self, crop_png, question, system):
            seen.add(threading.get_ident())
            return super().ask(crop_png, question, system)

    main = threading.get_ident()
    r = judge(B("yes", "no")).ask_two_way_detailed(CROP, QP, QN)
    assert main not in seen  # asked on worker threads, not the caller
    assert (r.pos.answer, r.neg.answer) == ("yes", "no")


def test_system_prompt_is_outlined_region_only():
    got = []

    class B(ScriptedBackend):
        def ask(self, crop_png, question, system):
            got.append(system)
            return super().ask(crop_png, question, system)

    judge(B("yes", "no")).ask_two_way(CROP, QP, QN)
    assert got == ["Answer only from the outlined region."] * 2


# ---- yes-bias defeat ------------------------------------------------------

def test_always_yes_never_passes():
    class AlwaysYes(ScriptedBackend):
        def ask(self, crop_png, question, system):
            return JudgeAnswer(answer="yes", reason="biased")

    assert judge(AlwaysYes("yes", "yes")).ask_two_way(CROP, QP, QN)[0] is Tri.U
    assert judge(AlwaysYes("yes", "yes"), AlwaysYes("yes", "yes")).ask_two_way(CROP, QP, QN)[0] is Tri.U


def test_always_no_never_fails():
    tri, _ = judge(ScriptedBackend("no", "no"), ScriptedBackend("no", "no")).ask_two_way(CROP, QP, QN)
    assert tri is Tri.U


# ---- escalation cap -------------------------------------------------------

def test_escalation_timeout_by_injected_clock_is_unresolved():
    clock = FakeClock()
    prim = ScriptedBackend("yes", "yes", "prim")
    esc = ScriptedBackend("yes", "no", "esc", delay=5.0, clock=clock)  # would decide T, but too late
    j = judge(prim, esc, escalation_cap_s=3.0, clock=clock)
    r = j.ask_two_way_detailed(CROP, QP, QN)
    assert r.tri is Tri.U and r.escalated and r.escalation_timed_out
    assert r.reason.startswith("appearance_unresolved")


def test_escalation_within_cap_decides():
    clock = FakeClock()
    esc = ScriptedBackend("no", "yes", "esc", delay=1.0, clock=clock)
    r = judge(ScriptedBackend("cant_tell", "yes"), esc, escalation_cap_s=3.0, clock=clock).ask_two_way_detailed(CROP, QP, QN)
    assert r.tri is Tri.F and not r.escalation_timed_out


def test_escalation_hang_is_cut_off_by_wall_clock():
    import time

    class Slow(ScriptedBackend):
        def ask(self, crop_png, question, system):
            time.sleep(0.6)
            return JudgeAnswer(answer="yes" if question == QP else "no", reason="late")

    t0 = time.monotonic()
    tri, _ = judge(ScriptedBackend("yes", "yes"), Slow("yes", "no"), escalation_cap_s=0.05).ask_two_way(CROP, QP, QN)
    assert tri is Tri.U
    assert time.monotonic() - t0 < 0.5


def test_backend_exception_degrades_to_abstention_not_a_guess():
    class Boom(ScriptedBackend):
        def ask(self, crop_png, question, system):
            raise RuntimeError("secret-bearing-text-should-not-leak")

    r = judge(Boom("yes", "no")).ask_two_way_detailed(CROP, QP, QN)
    assert r.tri is Tri.U
    assert "secret-bearing" not in r.reason and "secret-bearing" not in r.pos.reason


# ---- cache ----------------------------------------------------------------

def test_cache_hit_avoids_second_backend_call(tmp_path):
    b = ScriptedBackend("yes", "no")
    j = TwoWayJudge(b, cache=tmp_path / "jc")
    assert j.ask_two_way(CROP, QP, QN)[0] is Tri.T
    assert b.calls == 2
    assert j.ask_two_way(CROP, QP, QN)[0] is Tri.T
    assert b.calls == 2  # both answers served from cache


def test_cache_key_includes_backend_model_and_crop(tmp_path):
    b1, b2 = ScriptedBackend("yes", "no", "a"), ScriptedBackend("yes", "no", "b")
    TwoWayJudge(b1, cache=tmp_path).ask_two_way(CROP, QP, QN)
    TwoWayJudge(b2, cache=tmp_path).ask_two_way(CROP, QP, QN)
    TwoWayJudge(b1, cache=tmp_path).ask_two_way(CROP + b"x", QP, QN)
    assert (b1.calls, b2.calls) == (4, 2)


def test_fixture_answers_are_not_cached(tmp_path):
    b = ScriptedBackend("yes", "no", fixture=True)
    j = TwoWayJudge(b, cache=tmp_path)
    j.ask_two_way(CROP, QP, QN)
    j.ask_two_way(CROP, QP, QN)
    assert b.calls == 4
    assert not list(tmp_path.rglob("*.json"))


# ---- fixture labelling ----------------------------------------------------

def test_fixture_marker_on_every_fixture_result():
    r = judge(ScriptedBackend("yes", "no", fixture=True)).ask_two_way_detailed(CROP, QP, QN)
    assert r.is_fixture and "[FIXTURE]" in r.reason
    r = judge(ScriptedBackend("cant_tell", "no", fixture=True)).ask_two_way_detailed(CROP, QP, QN)
    assert r.tri is Tri.U and "[FIXTURE]" in r.reason and r.reason.startswith("appearance_unresolved")


def test_real_backends_carry_no_fixture_marker():
    r = judge(ScriptedBackend("yes", "no")).ask_two_way_detailed(CROP, QP, QN)
    assert not r.is_fixture and "[FIXTURE]" not in r.reason


def test_mixed_real_primary_fixture_escalator_is_still_labelled():
    r = judge(ScriptedBackend("yes", "yes"), ScriptedBackend("yes", "no", fixture=True)).ask_two_way_detailed(CROP, QP, QN)
    assert r.tri is Tri.T and r.is_fixture and "[FIXTURE]" in r.reason


# ---- recorded synthetic fixtures end to end -------------------------------

def _fixture_judge():
    return judge(FixtureBackend(), FixtureBackend(role="escalator"))


def test_fixture_flush_is_true():
    tri, reason = _fixture_judge().ask_two_way(synth.scene_crop("flush"), synth.Q_POS, synth.Q_NEG)
    assert tri is Tri.T and "[FIXTURE]" in reason


def test_fixture_ajar_is_false():
    tri, _ = _fixture_judge().ask_two_way(synth.scene_crop("ajar"), synth.Q_POS, synth.Q_NEG)
    assert tri is Tri.F


def test_fixture_blur_escalates_to_wonder_fixture():
    r = _fixture_judge().ask_two_way_detailed(synth.scene_crop("blur_escalates_to_flush"), synth.Q_POS, synth.Q_NEG)
    assert r.tri is Tri.T and r.escalated and r.backends == ["fixture", "fixture-wonder"]
    assert "muse-wonder-1.0" in r.reason and "[FIXTURE]" in r.reason


def test_fixture_dark_is_cant_tell():
    r = _fixture_judge().ask_two_way_detailed(synth.scene_crop("dark_stays_unresolved"), synth.Q_POS, synth.Q_NEG)
    assert r.tri is Tri.U and r.escalated and r.reason.startswith("appearance_unresolved")


def test_fixture_miss_is_abstention():
    ans = FixtureBackend().ask(b"unknown crop", "Is the drawer flush?", "sys")
    assert ans.answer == "cant_tell" and ans.reason.startswith("[FIXTURE]")


# ---- judge_atom (engine wiring helper) ------------------------------------

def _mask_for(case):
    frame, rle, size = synth.render_scene(case)
    return frame, ObjMask(obj="drawer", frame=0, score=0.9, bbox_xyxy=(75, 85, 245, 150), rle=rle, area_px=1, rle_size=size)


def _atom(**kw):
    return Atom(kind="looks", args=["drawer"], looks_pos="flush", **kw)


def test_judge_atom_true_false_and_unresolved():
    j = _fixture_judge()
    frame, m = _mask_for("flush")
    assert judge_atom(_atom(), frame, m, j) == (Tri.T, None)
    frame, m = _mask_for("ajar")
    assert judge_atom(_atom(), frame, m, j) == (Tri.F, None)
    frame, m = _mask_for("dark_stays_unresolved")
    assert judge_atom(_atom(), frame, m, j) == (Tri.U, ReasonCode.APPEARANCE_UNRESOLVED)


def test_judge_atom_explicit_opposite_state():
    j = _fixture_judge()
    frame, m = _mask_for("ajar")
    assert judge_atom(_atom(looks_neg="ajar"), frame, m, j)[0] is Tri.F


def test_judge_atom_without_mask_is_not_visible():
    frame, _ = _mask_for("flush")
    assert judge_atom(_atom(), frame, None, _fixture_judge()) == (Tri.U, ReasonCode.NOT_VISIBLE)


def test_judge_atom_unknown_antonym_is_unresolved_not_guessed():
    frame, m = _mask_for("flush")
    atom = Atom(kind="looks", args=["drawer"], looks_pos="purple")
    assert judge_atom(atom, frame, m, _fixture_judge()) == (Tri.U, ReasonCode.APPEARANCE_UNRESOLVED)


def test_judge_atom_rejects_non_looks_atoms():
    with pytest.raises(ValueError):
        judge_atom(Atom(kind="manual", manual_text="x"), np.zeros((4, 4, 3), np.uint8), None)


def test_judge_atom_yes_biased_backend_is_not_true():
    class Yes:
        name, model_id, is_fixture = "yes", "yes-1", False

        def ask(self, crop_png, question, system):
            return JudgeAnswer(answer="yes", reason="biased")

    frame, m = _mask_for("ajar")
    out = judge_atom(_atom(), frame, m, TwoWayJudge(Yes(), cache=False))
    assert out == (Tri.U, ReasonCode.APPEARANCE_UNRESOLVED)
