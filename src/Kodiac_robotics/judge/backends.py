"""Judge backends (KD-09): Meta API, open-weights OpenAI-compatible servers, and a labelled fixture replay.

Law 1: with no API key, ``get_backend`` returns a ``FixtureBackend`` with ``is_fixture=True`` (and logs
a warning). Fixture answers are replayed recordings keyed by ``(crop sha256, question)``; they are never
model output and every reason string they emit starts with ``[FIXTURE]``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

import httpx

from Kodiac_robotics.judge.client import (
    GLIMMER_SAMPLING,
    META_SAMPLING,
    SYSTEM_PROMPT,
    JudgeAnswer,
    OpenAICompatClient,
)

logger = logging.getLogger(__name__)

__all__ = [
    "BACKEND_NAMES",
    "FIXTURE_MARKER",
    "FixtureBackend",
    "HTTPJudgeBackend",
    "JudgeAnswer",
    "JudgeBackend",
    "SYSTEM_PROMPT",
    "WONDER_MODEL_ID",
    "get_backend",
    "get_escalator",
    "synthetic_entries",
    "write_fixture_file",
]

BACKEND_NAMES = ("meta", "baseten-spark-open", "modal-glimmer-vllm", "llamacpp-glimmer", "fixture")
FIXTURE_MARKER = "[FIXTURE]"
FIXTURE_SCHEMA = "kodiac-judge-fixture-v1"
WONDER_MODEL_ID = "muse-wonder-1.0"
DEFAULT_META_MODEL = "muse-spark-1.3"
DEFAULT_META_URL = "https://api.meta.ai/v1"
DEFAULT_BASETEN_URL = "https://inference.baseten.co/v1"
DEFAULT_BASETEN_MODEL = "muse-spark-open"
DEFAULT_GLIMMER_MODEL = "glimmer"
DEFAULT_LLAMACPP_URL = "http://127.0.0.1:8080/v1"


@runtime_checkable
class JudgeBackend(Protocol):
    name: str
    model_id: str
    is_fixture: bool

    def ask(self, crop_png: bytes, question: str, system: str) -> JudgeAnswer: ...


class HTTPJudgeBackend:
    """A real (non-fixture) OpenAI-compatible backend."""

    is_fixture = False

    def __init__(self, name: str, client: OpenAICompatClient) -> None:
        self.name = name
        self.model_id = client.model_id
        self._client = client

    def __repr__(self) -> str:
        return f"HTTPJudgeBackend(name={self.name!r}, model_id={self.model_id!r})"

    def ask(self, crop_png: bytes, question: str, system: str = SYSTEM_PROMPT) -> JudgeAnswer:
        return self._client.complete(crop_png, question, system)


def _default_fixture_dir() -> Path:
    override = _env("Kodiac_JUDGE_FIXTURE_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "judge"


class FixtureBackend:
    """Replays recorded answers keyed by (crop sha256, question). Always ``is_fixture=True``."""

    is_fixture = True

    def __init__(
        self,
        fixture_dir: Path | str | None = None,
        *,
        role: Literal["primary", "escalator"] = "primary",
        name: str | None = None,
        model_id: str | None = None,
        fallback_reason: str | None = None,
        entries: list[dict[str, Any]] | None = None,
    ) -> None:
        self.role = role
        self.name = name or ("fixture-wonder" if role == "escalator" else "fixture")
        self.model_id = model_id or (
            f"{WONDER_MODEL_ID} {FIXTURE_MARKER} replay" if role == "escalator" else f"fixture-replay {FIXTURE_MARKER}"
        )
        self.fallback_reason = fallback_reason
        self._table: dict[tuple[str, str], tuple[str, str]] = {}
        loaded = entries if entries is not None else self._load(Path(fixture_dir) if fixture_dir else _default_fixture_dir())
        for e in loaded:
            if e.get("role", "primary") != role:
                continue
            self._table[(e["crop_sha256"], e["question"])] = (e["answer"], e.get("reason", ""))

    def __repr__(self) -> str:
        return f"FixtureBackend(name={self.name!r}, role={self.role!r}, n={len(self._table)}, is_fixture=True)"

    @staticmethod
    def _load(directory: Path) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not directory.is_dir():
            return out
        for path in sorted(directory.glob("*.json")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(doc, dict) and doc.get("schema") == FIXTURE_SCHEMA:
                out.extend(doc.get("entries", []))
        return out

    def ask(self, crop_png: bytes, question: str, system: str = SYSTEM_PROMPT) -> JudgeAnswer:
        key = (hashlib.sha256(crop_png).hexdigest(), question)
        hit = self._table.get(key)
        if hit is None:
            return JudgeAnswer(answer="cant_tell", reason=f"{FIXTURE_MARKER} no recorded answer for this crop/question")
        answer, reason = hit
        return JudgeAnswer(answer=answer, reason=f"{FIXTURE_MARKER} {reason}")  # type: ignore[arg-type]


_TRUTH_ANSWERS: dict[str, tuple[str, str]] = {
    "pos": ("yes", "no"),
    "neg": ("no", "yes"),
    "ambiguous": ("cant_tell", "cant_tell"),
}


def synthetic_entries(
    crop_png: bytes,
    q_pos: str,
    q_neg: str,
    truth: Literal["pos", "neg", "ambiguous"],
    *,
    role: Literal["primary", "escalator"] = "primary",
) -> list[dict[str, Any]]:
    """Deterministic SYNTHETIC recorder: derives answers from a ground-truth label, not from any model.

    Used only to build replay fixtures. Each entry is labelled ``provenance: synthetic``.
    """
    if truth not in _TRUTH_ANSWERS:
        raise ValueError(f"truth must be one of {sorted(_TRUTH_ANSWERS)}")
    a_pos, a_neg = _TRUTH_ANSWERS[truth]
    sha = hashlib.sha256(crop_png).hexdigest()
    note = f"synthetic ground-truth label '{truth}'; NOT model output"
    return [
        {"crop_sha256": sha, "question": q, "answer": a, "reason": note, "role": role, "provenance": "synthetic"}
        for q, a in ((q_pos, a_pos), (q_neg, a_neg))
    ]


def write_fixture_file(path: Path | str, entries: list[dict[str, Any]], description: str = "") -> None:
    """Write fixture entries as sorted-key JSON (deterministic, labelled synthetic)."""
    doc = {
        "schema": FIXTURE_SCHEMA,
        "is_fixture": True,
        "description": description or "Synthetic judge replay fixtures. NOT model output.",
        "entries": entries,
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _env(*names: str) -> str | None:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return None


def _resolve_meta_key() -> str | None:
    return _env("Kodiac_JUDGE_KEY", "MODEL_API_KEY", "KODIAC_MODEL_API_KEY")


def _fallback(name: str, why: str) -> FixtureBackend:
    logger.warning("judge backend %r unavailable (%s): using LABELLED FIXTURE backend (is_fixture=True)", name, why)
    return FixtureBackend(fallback_reason=f"{name}: {why}")


def get_backend(name: str | None = None, *, transport: httpx.BaseTransport | None = None) -> JudgeBackend:
    """Select a judge backend (env ``Kodiac_JUDGE_BACKEND``, default ``meta``).

    Missing credentials/URLs never degrade silently: the result is a ``FixtureBackend`` with
    ``is_fixture=True`` and a logged warning. Only key *presence* is ever inspected or reported.
    """
    chosen = (name or _env("Kodiac_JUDGE_BACKEND", "KODIAC_JUDGE_BACKEND") or "meta").strip().lower()
    if chosen not in BACKEND_NAMES:
        raise ValueError(f"unknown judge backend {chosen!r}; expected one of {BACKEND_NAMES}")
    base_override = _env("Kodiac_JUDGE_BASE_URL")
    model_override = _env("Kodiac_JUDGE_MODEL")

    if chosen == "fixture":
        return FixtureBackend()
    if chosen == "meta":
        key = _resolve_meta_key()
        if not key:
            return _fallback(chosen, "no MODEL_API_KEY in environment")
        client = OpenAICompatClient(
            base_override or DEFAULT_META_URL, model_override or DEFAULT_META_MODEL, key,
            sampling=META_SAMPLING, transport=transport,
        )
        return HTTPJudgeBackend("meta", client)
    if chosen == "baseten-spark-open":
        key = _env("BASETEN_API_KEY")
        if not key:
            return _fallback(chosen, "no BASETEN_API_KEY in environment")
        client = OpenAICompatClient(
            base_override or DEFAULT_BASETEN_URL, model_override or DEFAULT_BASETEN_MODEL, key,
            sampling=META_SAMPLING, transport=transport,
        )
        return HTTPJudgeBackend(chosen, client)
    if chosen == "modal-glimmer-vllm":
        if not base_override:
            return _fallback(chosen, "no Kodiac_JUDGE_BASE_URL for the Modal vLLM endpoint")
        client = OpenAICompatClient(
            base_override, model_override or DEFAULT_GLIMMER_MODEL, _env("Kodiac_JUDGE_KEY"),
            sampling=GLIMMER_SAMPLING, transport=transport,
        )
        return HTTPJudgeBackend(chosen, client)
    client = OpenAICompatClient(
        base_override or DEFAULT_LLAMACPP_URL, model_override or DEFAULT_GLIMMER_MODEL, _env("Kodiac_JUDGE_KEY"),
        sampling=GLIMMER_SAMPLING, transport=transport,
    )
    return HTTPJudgeBackend("llamacpp-glimmer", client)


def get_escalator(
    primary: JudgeBackend, *, transport: httpx.BaseTransport | None = None
) -> JudgeBackend | None:
    """Muse Wonder escalation backend for a given primary, or None when Wonder is unreachable.

    Fixture primary -> labelled fixture Wonder. Otherwise Wonder over the Meta API iff a key is present.
    """
    if primary.is_fixture:
        return FixtureBackend(role="escalator")
    key = _resolve_meta_key()
    if not key:
        return None
    client = OpenAICompatClient(
        _env("Kodiac_JUDGE_WONDER_BASE_URL") or DEFAULT_META_URL, WONDER_MODEL_ID, key,
        sampling=META_SAMPLING, transport=transport,
    )
    return HTTPJudgeBackend("meta-wonder", client)
