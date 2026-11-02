"""Two-way antonym crop judge with Muse Wonder escalation (ARCHITECTURE.md §8.2-8.3).

The same crop is asked twice in parallel with antonym questions (never "not"), so a yes-biased
model cannot pass a test: only (yes, no) -> T and (no, yes) -> F decide. Anything else escalates to
Muse Wonder under a wall-clock cap; if that does not decide either, the answer is U with reason
``appearance_unresolved`` (CAN'T TELL). Backends flagged ``is_fixture`` tag every reason ``[FIXTURE]``.
"""

from __future__ import annotations

import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from Kodiac_robotics.cache import cached_call
from Kodiac_robotics.contracts.core import Atom, ObjMask, ReasonCode, Tri
from Kodiac_robotics.judge.backends import (
    FIXTURE_MARKER,
    SYSTEM_PROMPT,
    JudgeAnswer,
    JudgeBackend,
    get_backend,
    get_escalator,
)
from Kodiac_robotics.judge.crops import make_crop

logger = logging.getLogger(__name__)

UNRESOLVED = ReasonCode.APPEARANCE_UNRESOLVED.value

_ANTONYM_PAIRS: tuple[tuple[str, str], ...] = (
    ("flush", "ajar"),
    ("open", "closed"),
    ("full", "empty"),
    ("upright", "tilted"),
    ("level", "tilted"),
    ("straight", "crooked"),
    ("aligned", "misaligned"),
    ("centered", "off-center"),
    ("attached", "detached"),
    ("lifted", "lowered"),
    ("grasped", "released"),
    ("visible", "hidden"),
    ("clean", "dirty"),
    ("intact", "broken"),
    ("stacked", "separated"),
    ("pressed", "released"),
    ("raised", "lowered"),
    ("lit", "dark"),
    ("tight", "loose"),
    ("neat", "messy"),
)
ANTONYMS: dict[str, str] = {}
for _a, _b in _ANTONYM_PAIRS:
    ANTONYMS.setdefault(_a, _b)
    ANTONYMS.setdefault(_b, _a)


def antonym_questions(obj: str, state: str) -> tuple[str, str]:
    """Return ("Is the {obj} {state}?", "Is the {obj} {opposite}?") using the antonym table.

    Raises ValueError when no antonym is known or ``state`` is itself a negation: the negative
    question must be a genuine opposite, never "not {state}".
    """
    key = state.strip().lower()
    if key.startswith("not ") or "n't" in key:
        raise ValueError(f"state {state!r} is a negation; supply a positive state")
    opposite = ANTONYMS.get(key)
    if opposite is None:
        raise ValueError(f"no antonym known for state {state!r}; add it to the table or give looks() both states")
    return f"Is the {obj} {key}?", f"Is the {obj} {opposite}?"


@dataclass
class TwoWayResult:
    tri: Tri
    reason: str
    pos: JudgeAnswer | None = None
    neg: JudgeAnswer | None = None
    escalated: bool = False
    esc_pos: JudgeAnswer | None = None
    esc_neg: JudgeAnswer | None = None
    escalation_timed_out: bool = False
    is_fixture: bool = False
    backends: list[str] = field(default_factory=list)


def _decide(pos: str | None, neg: str | None) -> Tri | None:
    if pos == "yes" and neg == "no":
        return Tri.T
    if pos == "no" and neg == "yes":
        return Tri.F
    return None


class TwoWayJudge:
    """Implements ``contracts.core.VLMJudge`` with antonym two-way asking and Wonder escalation.

    ``cache``: a cache directory (Path/str); None uses the configured default cache dir; False disables.
    Fixture backends are never cached. ``clock`` is injectable for escalation-cap tests.
    """

    def __init__(
        self,
        backend: JudgeBackend,
        escalator: JudgeBackend | None = None,
        *,
        escalation_cap_s: float = 3.0,
        cache: Path | str | bool | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.backend = backend
        self.escalator = escalator
        self.escalation_cap_s = float(escalation_cap_s)
        self.cache = cache
        self.clock = clock

    def _ask_one(self, backend: JudgeBackend, crop_png: bytes, question: str) -> JudgeAnswer:
        def call() -> dict[str, str]:
            return backend.ask(crop_png, question, SYSTEM_PROMPT).model_dump()

        try:
            if backend.is_fixture or self.cache is False:
                raw = call()
            else:
                key = {
                    "kind": "judge_v1",
                    "backend": backend.name,
                    "model": backend.model_id,
                    "crop_sha256": hashlib.sha256(crop_png).hexdigest(),
                    "question": question,
                    "system_sha256": hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
                }
                raw = cached_call(key, call, cache_dir=None if self.cache is None else self.cache)
            return JudgeAnswer.model_validate(raw)
        except Exception as exc:  # backend failure must degrade to an abstention, never a guess
            logger.warning("judge backend %s failed: %s", backend.name, type(exc).__name__)
            return JudgeAnswer(answer="cant_tell", reason=f"backend_error:{type(exc).__name__}")

    def _ask_pair(
        self, backend: JudgeBackend, crop_png: bytes, q_pos: str, q_neg: str, timeout: float | None
    ) -> tuple[JudgeAnswer, JudgeAnswer] | None:
        pool = ThreadPoolExecutor(max_workers=2)
        try:
            f_pos = pool.submit(self._ask_one, backend, crop_png, q_pos)
            f_neg = pool.submit(self._ask_one, backend, crop_png, q_neg)
            done, _ = wait([f_pos, f_neg], timeout=timeout)
            if len(done) < 2:
                return None
            return f_pos.result(), f_neg.result()
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def ask_two_way_detailed(self, crop_png: bytes, q_pos: str, q_neg: str) -> TwoWayResult:
        used = [self.backend]
        pair = self._ask_pair(self.backend, crop_png, q_pos, q_neg, timeout=None)
        assert pair is not None
        pos, neg = pair
        res = TwoWayResult(tri=Tri.U, reason=UNRESOLVED, pos=pos, neg=neg)

        verdict = _decide(pos.answer, neg.answer)
        if verdict is None and self.escalator is not None:
            res.escalated = True
            used.append(self.escalator)
            start = self.clock()
            esc = self._ask_pair(self.escalator, crop_png, q_pos, q_neg, timeout=self.escalation_cap_s)
            if esc is None or (self.clock() - start) > self.escalation_cap_s:
                res.escalation_timed_out = True
            else:
                res.esc_pos, res.esc_neg = esc
                verdict = _decide(esc[0].answer, esc[1].answer)
                if verdict is not None:
                    res.reason = (
                        f"two-way disagreement/abstention on {self.backend.name}; escalated to "
                        f"{self.escalator.name}:{self.escalator.model_id} -> {verdict.value}"
                    )
        elif verdict is not None:
            res.reason = (
                f"two-way agreement on {self.backend.name}:{self.backend.model_id} "
                f"(pos={pos.answer}, neg={neg.answer}) -> {verdict.value}"
            )

        res.tri = verdict if verdict is not None else Tri.U
        res.backends = [b.name for b in used]
        res.is_fixture = any(b.is_fixture for b in used)
        if res.is_fixture:
            res.reason = f"{res.reason} {FIXTURE_MARKER}"
        return res

    def ask_two_way(self, crop_png: bytes, q_pos: str, q_neg: str) -> tuple[Tri, str]:
        r = self.ask_two_way_detailed(crop_png, q_pos, q_neg)
        return r.tri, r.reason


def get_judge(
    name: str | None = None,
    *,
    cache: Path | str | bool | None = None,
    escalation_cap_s: float = 3.0,
) -> TwoWayJudge:
    """Build a TwoWayJudge from the environment (backend + Wonder escalator). Fixture-labelled without keys."""
    primary = get_backend(name)
    return TwoWayJudge(primary, get_escalator(primary), escalation_cap_s=escalation_cap_s, cache=cache)


def _is_question(text: str) -> bool:
    return text.strip().endswith("?")


def judge_atom(
    atom: Atom,
    frame_bgr: np.ndarray,
    mask: ObjMask | None,
    judge: TwoWayJudge | None = None,
) -> tuple[Tri, ReasonCode | None]:
    """Evaluate an ``Atom(kind="looks")`` on a frame + object mask for the engine to call.

    ``atom.args[0]`` is the object, ``looks_pos`` the state (or a full question), ``looks_neg`` an
    optional explicit opposite state (else the antonym table is used). Returns (T|F, None) when
    decided, (U, APPEARANCE_UNRESOLVED) when unresolved, and (U, NOT_VISIBLE) with no usable mask.
    """
    if atom.kind != "looks" or not atom.looks_pos:
        raise ValueError("judge_atom requires an Atom(kind='looks') with looks_pos")
    if mask is None or not mask.rle:
        return Tri.U, ReasonCode.NOT_VISIBLE
    try:
        crop = make_crop(frame_bgr, mask.rle, mask.rle_size)
    except ValueError:
        return Tri.U, ReasonCode.NOT_VISIBLE

    obj = atom.args[0] if atom.args else mask.obj
    try:
        if _is_question(atom.looks_pos):
            if not (atom.looks_neg and _is_question(atom.looks_neg)):
                raise ValueError("a full-question looks() needs an explicit opposite question")
            q_pos, q_neg = atom.looks_pos, atom.looks_neg
        elif atom.looks_neg:
            q_pos, q_neg = f"Is the {obj} {atom.looks_pos}?", f"Is the {obj} {atom.looks_neg}?"
        else:
            q_pos, q_neg = antonym_questions(obj, atom.looks_pos)
    except ValueError as exc:
        logger.warning("looks() cannot build antonym questions: %s", exc)
        return Tri.U, ReasonCode.APPEARANCE_UNRESOLVED

    judge = judge or get_judge()
    tri, _reason = judge.ask_two_way(crop, q_pos, q_neg)
    if tri is Tri.U:
        return Tri.U, ReasonCode.APPEARANCE_UNRESOLVED
    return tri, None
