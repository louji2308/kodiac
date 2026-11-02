"""FastAPI server for the hosted demo: /health, /grade, /replay/{id} (+ card/trace/catalog helpers).

All behaviour lives in ``core.AppCore`` (see its honesty contract); this module is transport only.
"""

from __future__ import annotations

import html
import re
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from Kodiac_robotics import __version__
from Kodiac_robotics.app.core import LIVE_BADGE, AppCore
from Kodiac_robotics.app.errors import AppError
from Kodiac_robotics.app.guards import log_event
from Kodiac_robotics.app.replay import CACHED_BADGE, valid_replay_id
from Kodiac_robotics.app.service import BlameHook
from Kodiac_robotics.app.settings import AppSettings

_RUN_ID_RE = re.compile(r"^[0-9a-f]{16}$")


def _client_address(request: Request, settings: AppSettings) -> str:
    ip = request.client.host if request.client else "unknown"
    if settings.trust_proxy:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd.strip():
            ip = fwd.split(",")[0].strip()
    return ip


def create_app(
    settings: AppSettings | None = None,
    *,
    blame_hook: BlameHook | None = None,
) -> FastAPI:
    """Build the FastAPI app. ``blame_hook`` is the integration point ORCH uses for blame/fast path."""
    settings = settings or AppSettings()
    core = AppCore(settings, blame_hook=blame_hook)
    store = core.store

    app = FastAPI(title="Kodiac hosted demo", version=__version__, docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.core = core

    # ---- error mapping ---------------------------------------------------------------------
    def _rate_limited_page(err: AppError) -> HTMLResponse:
        links = "".join(
            f'<li><a href="/replay/{html.escape(e.id)}">{html.escape(e.title)}</a> '
            f"({html.escape(e.verdict)}, {html.escape(CACHED_BADGE)})</li>"
            for e in store.list()
        )
        body = (
            "<!doctype html><meta charset=utf-8><title>Kodiac: busy</title>"
            "<body style='font-family:system-ui;max-width:42rem;margin:3rem auto;padding:0 1rem'>"
            f"<h1>Busy right now</h1><p>{html.escape(err.message)}</p>"
            f"<p>These are <b>{html.escape(CACHED_BADGE)}</b> replays (precomputed, not live grades):</p>"
            f"<ul>{links}</ul>"
        )
        return HTMLResponse(
            body, status_code=429, headers={"Retry-After": str(err.extra.get("retry_after_s", 10))}
        )

    @app.exception_handler(AppError)
    async def _app_error(request: Request, err: AppError) -> Response:
        if err.code == "E_RATE_LIMIT" and "text/html" in request.headers.get("accept", ""):
            return _rate_limited_page(err)
        headers = (
            {"Retry-After": str(err.extra["retry_after_s"])} if "retry_after_s" in err.extra else None
        )
        return JSONResponse(err.to_payload(), status_code=err.status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, err: RequestValidationError) -> Response:
        payload = AppError(
            "E_BAD_REQUEST", "That request wasn't understood. Check the form fields and try again."
        ).to_payload()
        return JSONResponse(payload, status_code=422)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, err: Exception) -> Response:
        log_event("unhandled_error", error_type=type(err).__name__, path=request.url.path)
        payload = AppError(
            "E_INTERNAL",
            "Something went wrong on our side. Try a cached replay instead.",
            status=500,
            replay_url=core.first_replay_url(),
        ).to_payload()
        return JSONResponse(payload, status_code=500)

    # ---- routes ----------------------------------------------------------------------------
    @app.get("/health")
    def health() -> dict[str, Any]:
        return core.health()

    @app.get("/catalog")
    def catalog() -> dict[str, Any]:
        return core.catalog()

    @app.get("/replays")
    def replays() -> list[dict[str, Any]]:
        return [e.model_dump() for e in store.list()]

    @app.post("/compile")
    def compile_route(instruction: str = Form("")) -> dict[str, Any]:
        return core.compile(instruction)

    @app.post("/grade")
    def grade(
        request: Request,
        file: UploadFile | None = File(None),
        clip_id: str | None = Form(None),
        test_id: str | None = Form(None),
        typed_instruction: str | None = Form(None),
        occlusion_rects: str | None = Form(None),
    ) -> dict[str, Any]:
        client = core.client_key(_client_address(request, settings))
        upload = (file.file, file.filename) if file is not None and file.filename else None
        return core.grade(
            client,
            upload=upload,
            clip_id=clip_id,
            test_id=test_id,
            typed_instruction=typed_instruction,
            occlusion_rects=occlusion_rects,
        )

    @app.get("/replay/{replay_id}")
    def replay(replay_id: str) -> dict[str, Any]:
        return core.replay(replay_id)

    @app.get("/card/replay/{replay_id}")
    def card_replay(replay_id: str) -> Response:
        data = None
        if valid_replay_id(replay_id):
            try:
                data = store.card_bytes(replay_id)
            except ValueError:
                data = None
        if data is None:
            raise AppError("E_REPLAY_NOT_FOUND", "No cached card with that id.", status=404)
        return Response(data, media_type="image/png")

    @app.get("/card/live/{run_id}")
    def card_live(run_id: str) -> Response:
        path = settings.run_dir / run_id / "card.png"
        if not _RUN_ID_RE.match(run_id) or not path.is_file():
            raise AppError(
                "E_CARD_EXPIRED", "That card is gone (live results are kept for at most 24 h).", status=404
            )
        return FileResponse(path, media_type="image/png")

    @app.get("/trace/{run_id}")
    def trace(run_id: str) -> Response:
        path = settings.run_dir / run_id / "trace.jsonl"
        if not _RUN_ID_RE.match(run_id) or not path.is_file():
            raise AppError(
                "E_TRACE_EXPIRED", "That trace is gone (live results are kept for at most 24 h).", status=404
            )
        return FileResponse(path, media_type="application/x-ndjson", filename="trace.jsonl")

    mounted = False
    if settings.mount_ui:
        try:
            import gradio as gr
        except ImportError:
            gr = None
        if gr is not None:
            from Kodiac_robotics.app.client import LocalClient
            from Kodiac_robotics.app.ui import build_ui

            app = gr.mount_gradio_app(app, build_ui(client=LocalClient(core)), path="/")
            mounted = True
    app.state.ui_mounted = mounted

    if not mounted:

        @app.get("/", response_class=HTMLResponse)
        def index() -> str:
            items = "".join(
                f'<li><a href="/replay/{html.escape(e.id)}">{html.escape(e.title)}</a>: '
                f"{html.escape(e.verdict)} <b>{html.escape(CACHED_BADGE)}</b></li>"
                for e in store.list()
            )
            return (
                "<!doctype html><meta charset=utf-8><title>Kodiac</title>"
                "<body style='font-family:system-ui;max-width:42rem;margin:3rem auto;padding:0 1rem'>"
                "<h1>Kodiac: Robots can finally fail a test.</h1>"
                "<p>The interactive UI needs the optional <code>gradio</code> package, which is not installed "
                "here. The API is live: <code>POST /grade</code>, <code>GET /replay/{id}</code>, "
                "<code>GET /health</code>.</p>"
                f"<h2>Cached replays</h2><ul>{items}</ul>"
            )

    return app


__all__ = ["LIVE_BADGE", "create_app"]
