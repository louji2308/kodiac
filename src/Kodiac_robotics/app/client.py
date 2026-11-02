"""Clients the Gradio UI uses to reach the grading API: in-process (``LocalClient``) or HTTP (``HttpClient``).

Both return the same payload shapes as the server and raise ``AppError`` with the server's friendly message.
Card images are returned as local file paths (or downloaded to a temp file for HTTP) for Gradio to display.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Protocol

from Kodiac_robotics.app.core import AppCore
from Kodiac_robotics.app.errors import AppError


class Client(Protocol):
    def catalog(self) -> dict[str, Any]: ...
    def health(self) -> dict[str, Any]: ...
    def compile(self, instruction: str) -> dict[str, Any]: ...
    def replay(self, replay_id: str) -> dict[str, Any]: ...
    def grade(
        self,
        *,
        video_path: str | None = None,
        clip_id: str | None = None,
        test_id: str | None = None,
        typed_instruction: str | None = None,
        occlusion_rects: list[list[int]] | None = None,
        client_hint: str = "ui",
    ) -> dict[str, Any]: ...
    def card_image(self, payload: dict[str, Any]) -> str | None: ...


class LocalClient:
    """Calls ``AppCore`` directly (same rate limit, caps and logging as the HTTP route)."""

    def __init__(self, core: AppCore) -> None:
        self.core = core

    def catalog(self) -> dict[str, Any]:
        return self.core.catalog()

    def health(self) -> dict[str, Any]:
        return self.core.health()

    def compile(self, instruction: str) -> dict[str, Any]:
        return self.core.compile(instruction)

    def replay(self, replay_id: str) -> dict[str, Any]:
        return self.core.replay(replay_id)

    def grade(
        self,
        *,
        video_path: str | None = None,
        clip_id: str | None = None,
        test_id: str | None = None,
        typed_instruction: str | None = None,
        occlusion_rects: list[list[int]] | None = None,
        client_hint: str = "ui",
    ) -> dict[str, Any]:
        key = self.core.client_key(client_hint)
        if video_path:
            with open(video_path, "rb") as fh:
                return self.core.grade(
                    key,
                    upload=(fh, Path(video_path).name),
                    test_id=test_id,
                    typed_instruction=typed_instruction,
                    occlusion_rects=occlusion_rects,
                )
        return self.core.grade(
            key,
            clip_id=clip_id,
            test_id=test_id,
            typed_instruction=typed_instruction,
            occlusion_rects=occlusion_rects,
        )

    def card_image(self, payload: dict[str, Any]) -> str | None:
        url = payload.get("card_url") or ""
        if url.startswith("/card/live/"):
            path = self.core.settings.run_dir / url.rsplit("/", 1)[-1] / "card.png"
            return str(path) if path.is_file() else None
        if url.startswith("/card/replay/"):
            data = self.core.store.card_bytes(url.rsplit("/", 1)[-1])
            if data is None:
                return None
            return _write_temp_png(data)
        return None


class HttpClient:
    """Calls a running Kodiac server over HTTP (``requests``)."""

    def __init__(self, api_base: str, timeout_s: float = 120.0) -> None:
        self.base = api_base.rstrip("/")
        self.timeout = timeout_s

    def _json(self, resp: Any) -> dict[str, Any]:
        try:
            data = resp.json()
        except ValueError:
            raise AppError("E_BAD_RESPONSE", "The server sent an unreadable response.", status=502) from None
        if resp.status_code >= 400:
            err = data.get("error", {}) if isinstance(data, dict) else {}
            extra = {k: v for k, v in err.items() if k not in ("code", "message", "hint", "replay_url")}
            raise AppError(
                err.get("code", "E_HTTP"),
                err.get("message", f"The server returned HTTP {resp.status_code}."),
                status=resp.status_code,
                hint=err.get("hint"),
                replay_url=err.get("replay_url"),
                extra=extra,
            )
        return data

    def _get(self, path: str) -> dict[str, Any]:
        import requests

        try:
            return self._json(requests.get(self.base + path, timeout=self.timeout))
        except requests.RequestException as err:
            raise AppError("E_UNREACHABLE", "Could not reach the grading server.", status=503) from err

    def catalog(self) -> dict[str, Any]:
        return self._get("/catalog")

    def health(self) -> dict[str, Any]:
        return self._get("/health")

    def replay(self, replay_id: str) -> dict[str, Any]:
        return self._get(f"/replay/{replay_id}")

    def compile(self, instruction: str) -> dict[str, Any]:
        import requests

        try:
            return self._json(
                requests.post(self.base + "/compile", data={"instruction": instruction}, timeout=self.timeout)
            )
        except requests.RequestException as err:
            raise AppError("E_UNREACHABLE", "Could not reach the grading server.", status=503) from err

    def grade(
        self,
        *,
        video_path: str | None = None,
        clip_id: str | None = None,
        test_id: str | None = None,
        typed_instruction: str | None = None,
        occlusion_rects: list[list[int]] | None = None,
        client_hint: str = "ui",
    ) -> dict[str, Any]:
        import json

        import requests

        data: dict[str, str] = {}
        if clip_id:
            data["clip_id"] = clip_id
        if test_id:
            data["test_id"] = test_id
        if typed_instruction:
            data["typed_instruction"] = typed_instruction
        if occlusion_rects:
            data["occlusion_rects"] = json.dumps(occlusion_rects)
        try:
            if video_path:
                with open(video_path, "rb") as fh:
                    resp = requests.post(
                        self.base + "/grade",
                        data=data,
                        files={"file": (Path(video_path).name, fh)},
                        timeout=self.timeout,
                    )
            else:
                resp = requests.post(self.base + "/grade", data=data, timeout=self.timeout)
        except requests.RequestException as err:
            raise AppError("E_UNREACHABLE", "Could not reach the grading server.", status=503) from err
        return self._json(resp)

    def card_image(self, payload: dict[str, Any]) -> str | None:
        import requests

        url = payload.get("card_url")
        if not url:
            return None
        try:
            resp = requests.get(self.base + url, timeout=self.timeout)
        except requests.RequestException:
            return None
        return _write_temp_png(resp.content) if resp.status_code == 200 else None


def _write_temp_png(data: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
        fh.write(data)
        return fh.name


__all__ = ["Client", "HttpClient", "LocalClient"]

