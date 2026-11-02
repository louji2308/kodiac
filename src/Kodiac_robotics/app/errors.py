"""Typed, user-friendly errors for the hosted app (no stack traces reach the browser)."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """A friendly, typed application error mapped to an HTTP status by the server."""

    def __init__(
        self,
        code: str,
        message: str,
        status: int = 422,
        hint: str | None = None,
        replay_url: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.hint = hint
        self.replay_url = replay_url
        self.extra = extra or {}

    def to_payload(self) -> dict[str, Any]:
        body: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.hint:
            body["hint"] = self.hint
        if self.replay_url:
            body["replay_url"] = self.replay_url
        body.update(self.extra)
        return {"error": body}


def object_not_found(name: str) -> AppError:
    """E001: a declared object has no track in the clip."""
    return AppError(
        "E001",
        f"We couldn't find '{name}'. Try Teach it or an example test.",
        status=422,
        hint="Pick a curated example test (stackcube / stack_blocks) or rephrase the instruction.",
    )


__all__ = ["AppError", "object_not_found"]
