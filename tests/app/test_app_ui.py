"""UI helpers (no gradio needed) and the Gradio Blocks build (skipped cleanly when gradio is missing)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from Kodiac_robotics.app.client import LocalClient
from Kodiac_robotics.app.core import AppCore
from Kodiac_robotics.app.errors import AppError
from Kodiac_robotics.app.server import create_app
from Kodiac_robotics.app.ui import (
    friendly_error_markdown,
    model_table_markdown,
    percent_rect_to_pixels,
    render_details,
    render_timer,
    render_verdict,
)


@pytest.fixture
def core(make_settings) -> AppCore:
    return AppCore(make_settings())


def test_live_timer_shows_measured_time_and_no_target_claim(core: AppCore) -> None:
    payload = LocalClient(core).grade(clip_id="b01_early_release", test_id="stackcube")
    html = render_timer(payload, browser_ms=1234)
    assert "measured wall-clock" in html and "1.23 s" in html
    assert "<12" not in html and "&lt;12" not in html and "CACHED" not in html
    verdict = render_verdict(payload)
    assert "FAIL" in verdict and "[FIXTURE REPLAY]" in verdict and "ENGINE RUN (not cached)" in verdict
    details = render_details(payload)
    assert "grasp" in details and "|" in details


def test_cached_replay_is_never_rendered_as_a_live_grade(core: AppCore) -> None:
    payload = LocalClient(core).replay("stackcube__b01_early_release")
    html = render_timer(payload)
    assert "⚡ CACHED replay" in html and "not a live grade" in html
    assert "measured wall-clock" not in html
    assert "⚡ CACHED" in render_verdict(payload)
    assert "kd-cached" in render_verdict(payload)


def test_occlusion_details_report_coverage(core: AppCore) -> None:
    payload = LocalClient(core).grade(
        clip_id="correct_run", test_id="stackcube", occlusion_rects=[[380, 280, 500, 360]]
    )
    details = render_details(payload)
    assert "Occluder" in details and "cube_b 100%" in details and "emulated on cached tracks" in details
    assert "CAN&#x27;T TELL" in render_verdict(payload) or "CAN'T TELL" in render_verdict(payload)


def test_friendly_error_text_and_percent_rects() -> None:
    err = AppError("E001", "We couldn't find 'red block'. Try Teach it or an example test.", replay_url="/replay/x")
    text = friendly_error_markdown(err)
    assert "We couldn't find 'red block'" in text and "⚡ CACHED" in text
    assert percent_rect_to_pixels(80, 55, 60, 80, 640, 480) == [384, 264, 512, 384]
    assert "Muse Spark" in model_table_markdown() and "SAM 3.1" in model_table_markdown()


def test_local_client_surfaces_typed_errors(core: AppCore) -> None:
    with pytest.raises(AppError) as exc:
        LocalClient(core).grade(clip_id="b01_early_release", typed_instruction="dance a jig")
    assert exc.value.code == "E003"


@pytest.mark.slow
def test_gradio_blocks_build_and_mount(make_settings) -> None:
    pytest.importorskip("gradio", reason="gradio is not installed in this environment")
    from Kodiac_robotics.app.ui import build_ui

    core = AppCore(make_settings())
    demo = build_ui(client=LocalClient(core))
    assert demo is not None
    settings = make_settings(mount_ui=True)
    app = create_app(settings)
    assert app.state.ui_mounted is True
    page = TestClient(app).get("/")
    assert page.status_code == 200 and "Kodiac" in page.text
    assert TestClient(app).get("/health").json()["ok"] is True
