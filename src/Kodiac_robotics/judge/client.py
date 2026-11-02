"""OpenAI-compatible VLM client for the two-way judge (KD-09: one code path, many backends).

Request shape follows ``compiler/spark_compile.py`` (POST ``{base_url}/chat/completions``,
Bearer auth, ``response_format`` json_object). The image goes in as a base64 data URL.
The API key is held privately and is never part of ``repr`` or error text.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any, Literal

import httpx
from pydantic import BaseModel

SYSTEM_PROMPT = "Answer only from the outlined region."
JSON_INSTRUCTION = (
    'Reply with JSON only: {"answer": "yes" | "no" | "cant_tell", "reason": "<one short sentence>"}. '
    "Use cant_tell if the outlined region does not let you decide."
)
GLIMMER_SAMPLING: dict[str, Any] = {"temperature": 1.0, "top_p": 0.95, "top_k": 64}
META_SAMPLING: dict[str, Any] = {"temperature": 0.0}

_CANT_TELL_WORDS = {"cant_tell", "cant tell", "can't tell", "cannot tell", "unknown", "unsure", "unclear"}


class JudgeAnswer(BaseModel):
    """Schema for one judge reply: {answer: yes|no|cant_tell, reason}."""

    answer: Literal["yes", "no", "cant_tell"]
    reason: str


def parse_answer(text: str) -> JudgeAnswer:
    """Parse a model reply into a JudgeAnswer. Anything unparseable becomes cant_tell (never a guess)."""
    raw = (text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
    data: Any = None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except (ValueError, TypeError):
                data = None
    if not isinstance(data, dict):
        return JudgeAnswer(answer="cant_tell", reason="unparseable_response")
    answer = str(data.get("answer", "")).strip().lower().strip(" .!\"'")
    reason = str(data.get("reason", ""))[:300]
    if answer in ("yes", "no"):
        return JudgeAnswer(answer=answer, reason=reason)  # type: ignore[arg-type]
    if answer in _CANT_TELL_WORDS:
        return JudgeAnswer(answer="cant_tell", reason=reason)
    return JudgeAnswer(answer="cant_tell", reason="unrecognized_answer")


class OpenAICompatClient:
    """Minimal OpenAI-compatible multimodal chat client returning a JudgeAnswer."""

    def __init__(
        self,
        base_url: str,
        model_id: str,
        api_key: str | None = None,
        *,
        sampling: dict[str, Any] | None = None,
        timeout: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id
        self._api_key = api_key
        self.sampling = dict(META_SAMPLING if sampling is None else sampling)
        self.timeout = timeout
        self._transport = transport

    def __repr__(self) -> str:
        return (
            f"OpenAICompatClient(base_url={self.base_url!r}, model_id={self.model_id!r}, "
            f"has_key={bool(self._api_key)})"
        )

    def build_payload(self, crop_png: bytes, question: str, system: str) -> dict[str, Any]:
        data_url = "data:image/png;base64," + base64.b64encode(crop_png).decode("ascii")
        return {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"{question}\n{JSON_INSTRUCTION}"},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
            **self.sampling,
        }

    def complete(self, crop_png: bytes, question: str, system: str = SYSTEM_PROMPT) -> JudgeAnswer:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        url = f"{self.base_url}/chat/completions"
        with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
            resp = client.post(url, headers=headers, json=self.build_payload(crop_png, question, system))
            resp.raise_for_status()
            body = resp.json()
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return JudgeAnswer(answer="cant_tell", reason="malformed_response")
        return parse_answer(content if isinstance(content, str) else json.dumps(content))
