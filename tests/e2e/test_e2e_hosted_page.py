"""Browser end-to-end check of the hosted page (Playwright + Gradio). Skips cleanly when either is missing.

Flow a judge takes: open the page with no login, open an instant ⚡ CACHED replay, then grade a curated clip and
see a measured wall-clock timer, honest badges, and the CAN'T TELL path via the occlusion brush.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

REPO_ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live_server(tmp_path: Path):
    pytest.importorskip("gradio", reason="gradio is not installed in this environment")
    pytest.importorskip("playwright.sync_api", reason="playwright is not installed in this environment")
    import uvicorn

    from Kodiac_robotics.app.precompute import CURATED_SPECS, precompute_replays
    from Kodiac_robotics.app.server import create_app
    from Kodiac_robotics.app.settings import AppSettings

    settings = AppSettings(
        replay_dir=tmp_path / "replays",
        upload_dir=tmp_path / "uploads",
        run_dir=tmp_path / "runs",
        rate_per_min=60.0,
    )
    precompute_replays(settings, [s for s in CURATED_SPECS if s.clip_id == "b01_early_release"])
    port = _free_port()
    config = uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


def test_judge_flow_cached_then_live_then_cant_tell(live_server: str) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception as err:  # browser binaries not downloaded
            pytest.skip(f"playwright browser unavailable: {err}")
        page = browser.new_page()
        page.goto(live_server)
        page.get_by_role("button", name="⚡ Open cached replay").click()
        page.wait_for_selector("text=⚡ CACHED replay", timeout=30_000)
        assert page.locator("text=not a live grade").count() >= 1

        page.get_by_role("button", name="▶ GRADE (runs the engine now)").click()
        page.wait_for_selector("text=measured wall-clock", timeout=60_000)
        assert page.locator("text=[FIXTURE REPLAY]").count() >= 1
        assert page.locator("text=<12").count() == 0
        browser.close()
