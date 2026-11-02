"""Hosted app API tests via FastAPI TestClient (fixture backend: no network, no keys)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from Kodiac_robotics.app.occlusion import occlude_video
from Kodiac_robotics.app.server import create_app
from Kodiac_robotics.contracts.core import Verdict

REPO_ROOT = Path(__file__).resolve().parents[2]
CLIPS = REPO_ROOT / "tests" / "fixtures" / "clips"
TARGET_RECT = "[[380, 280, 500, 360]]"


def _client(make_settings, **overrides) -> TestClient:
    return TestClient(create_app(make_settings(**overrides)))


def test_health(make_settings) -> None:
    body = _client(make_settings).get("/health").json()
    assert body["ok"] is True
    assert body["backend"] == "fixture" and body["mode"] == "live"
    assert body["version"] and body["replays"] == 2


def test_grade_b01_fails_with_card_timer_and_honest_badges(make_settings) -> None:
    c = _client(make_settings)
    r = c.post("/grade", data={"clip_id": "b01_early_release", "test_id": "stackcube"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run"]["verdict"] == Verdict.FAIL.value
    assert body["cached"] is False and body["timer_ms"] > 0
    assert "[FIXTURE REPLAY]" in body["badges"]
    assert not any("CACHED" in b and "SAM" not in b for b in body["badges"])
    assert body["run"]["is_fixture"] is True
    card = c.get(body["card_url"])
    assert card.status_code == 200 and card.content[:4] == b"\x89PNG"
    assert c.get(body["trace_url"]).status_code == 200
    text = json.dumps(body)
    assert "LOUJAN" not in text and "tests/fixtures" not in text and "tests\\\\fixtures" not in text


@pytest.mark.xfail(
    reason="Known upstream engine limitation (T01 finding in sprint CHANNEL.md): every golden clip, "
    "including correct_run, currently FAILs at grasp on the recorded fixture tracks.",
    strict=False,
)
def test_grade_correct_run_passes(make_settings) -> None:
    body = _client(make_settings).post("/grade", data={"clip_id": "correct_run"}).json()
    assert body["run"]["verdict"] == Verdict.PASS.value


def test_occluded_clip_cant_tell_with_reason(make_settings) -> None:
    body = _client(make_settings).post("/grade", data={"clip_id": "occluded_clip"}).json()
    assert body["run"]["verdict"] == Verdict.CANT_TELL.value
    assert body["run"]["reasons"], "CAN'T TELL must carry a reason code"


def test_occlusion_brush_forces_cant_tell_and_is_labelled(make_settings) -> None:
    r = _client(make_settings).post(
        "/grade",
        data={"clip_id": "correct_run", "test_id": "stackcube", "occlusion_rects": TARGET_RECT},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run"]["verdict"] == Verdict.CANT_TELL.value
    assert body["run"]["reasons"] == ["occluded"]
    assert "[OCCLUDER APPLIED TO ALL FRAMES]" in body["badges"]
    assert "[OCCLUSION EMULATED ON CACHED MASKS]" in body["badges"]
    assert body["occlusion"]["max_covered_fraction"]["cube_b"] == pytest.approx(1.0)


def test_bad_occlusion_payload_is_a_friendly_422(make_settings) -> None:
    r = _client(make_settings).post(
        "/grade", data={"clip_id": "b01_early_release", "occlusion_rects": "not json"}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "E_BAD_OCCLUSION"


def test_typed_instruction_compiles_and_is_badged(make_settings) -> None:
    r = _client(make_settings).post(
        "/grade",
        data={"clip_id": "b01_early_release", "typed_instruction": "stack cubeA on cubeB"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["compiled_green"] and "objects:" in body["compiled_green"]
    assert any("TEMPLATE FALLBACK" in b for b in body["badges"])


def test_object_not_found_is_the_friendly_e001(make_settings) -> None:
    r = _client(make_settings).post(
        "/grade",
        data={"clip_id": "b01_early_release", "typed_instruction": "pick up the unicorn and place on the dragon"},
    )
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "E001"
    assert err["message"].startswith("We couldn't find '")
    assert "Try Teach it or an example test." in err["message"]
    assert err["replay_url"].startswith("/replay/")


def test_unsupported_instruction_falls_back_to_typed_error(make_settings) -> None:
    c = _client(make_settings)
    r = c.post("/grade", data={"clip_id": "b01_early_release", "typed_instruction": "dance a jig"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "E003"
    assert c.post("/compile", data={"instruction": ""}).json()["error"]["code"] == "E_EMPTY_INSTRUCTION"
    ok = c.post("/compile", data={"instruction": "stack cubeA on cubeB"}).json()
    assert ok["objects"][0] == "gripper" and ok["badges"]


def test_unknown_clip_and_test(make_settings) -> None:
    c = _client(make_settings)
    assert c.post("/grade", data={"clip_id": "nope"}).json()["error"]["code"] == "E_UNKNOWN_CLIP"
    r = c.post("/grade", data={"clip_id": "b01_early_release", "test_id": "nope"})
    assert r.json()["error"]["code"] == "E_UNKNOWN_TEST"


def test_upload_of_curated_clip_bytes_grades(make_settings) -> None:
    c = _client(make_settings)
    with (CLIPS / "b01_early_release.mp4").open("rb") as fh:
        r = c.post("/grade", data={"test_id": "stackcube"}, files={"file": ("mine.mp4", fh, "video/mp4")})
    assert r.status_code == 200, r.text
    assert r.json()["run"]["verdict"] == "FAIL"
    assert r.json()["run"]["clip"]["uri"].startswith("upload:")
    assert not list(Path(make_settings().upload_dir).glob("*")), "upload deleted after grading"


def test_unknown_upload_is_refused_honestly_not_invented(make_settings, tmp_path: Path) -> None:
    novel = occlude_video(CLIPS / "b01_early_release.mp4", tmp_path / "novel.mp4", [(0, 0, 50, 50)], 30.0)
    c = _client(make_settings)
    with novel.open("rb") as fh:
        r = c.post("/grade", files={"file": ("novel.mp4", fh, "video/mp4")})
    assert r.status_code == 503
    err = r.json()["error"]
    assert err["code"] == "E_NO_LIVE_BACKEND"
    assert "no perception API key" in err["message"]
    assert "run" not in r.json() and "card_url" not in r.json()
    assert err["replay_url"].startswith("/replay/")


def test_oversize_upload_is_a_friendly_413(make_settings) -> None:
    c = _client(make_settings, max_upload_mb=0.001)
    with (CLIPS / "b01_early_release.mp4").open("rb") as fh:
        r = c.post("/grade", files={"file": ("big.mp4", fh, "video/mp4")})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "E_TOO_LARGE" and "MB limit" in r.json()["error"]["message"]


def test_overlong_upload_is_a_friendly_413(make_settings) -> None:
    c = _client(make_settings, max_clip_seconds=1.0)
    with (CLIPS / "b01_early_release.mp4").open("rb") as fh:
        r = c.post("/grade", files={"file": ("long.mp4", fh, "video/mp4")})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "E_TOO_LONG" and "limit is 1 s" in r.json()["error"]["message"]


def test_garbage_upload_is_a_friendly_error(make_settings) -> None:
    r = _client(make_settings).post("/grade", files={"file": ("x.mp4", b"not a video", "video/mp4")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "E_BAD_VIDEO"


def test_rate_limit_returns_429_with_replay_link(make_settings) -> None:
    c = _client(make_settings, rate_per_min=2.0, trust_proxy=True)
    hdr = {"X-Forwarded-For": "198.51.100.7"}
    for _ in range(2):
        assert c.post("/grade", data={"clip_id": "nope"}, headers=hdr).status_code == 422
    r = c.post("/grade", data={"clip_id": "nope"}, headers=hdr)
    assert r.status_code == 429
    err = r.json()["error"]
    assert err["code"] == "E_RATE_LIMIT" and err["replay_url"].startswith("/replay/")
    assert int(r.headers["Retry-After"]) >= 1
    other = c.post("/grade", data={"clip_id": "nope"}, headers={"X-Forwarded-For": "198.51.100.8"})
    assert other.status_code == 422, "another client is unaffected"
    page = c.post("/grade", data={"clip_id": "nope"}, headers={**hdr, "Accept": "text/html"})
    assert page.status_code == 429 and "text/html" in page.headers["content-type"]
    assert "⚡ CACHED" in page.text and "/replay/" in page.text


def test_replay_is_marked_cached_and_not_a_live_run(make_settings) -> None:
    c = _client(make_settings)
    r = c.get("/replay/stackcube__b01_early_release")
    assert r.status_code == 200
    body = r.json()
    assert body["cached"] is True and "⚡ CACHED" in body["badges"]
    assert not any("ENGINE RUN" in b for b in body["badges"])
    assert "[FIXTURE REPLAY]" in body["badges"]
    assert body["replay"]["is_fixture"] is True and body["replay"]["source_commit"]
    assert body["original_run_total_ms"] > 0
    assert c.get(body["card_url"]).content[:4] == b"\x89PNG"
    assert c.get("/replay/does_not_exist").status_code == 404
    assert c.get("/replay/..%2Fetc").status_code in (404, 422)


def test_tampered_replay_is_refused(make_settings) -> None:
    settings = make_settings()
    entry = json.loads((settings.replay_dir / "index.json").read_text())["stackcube__b01_early_release"]
    (settings.replay_dir / "blobs" / f"{entry['result_sha256']}.json").write_text("{}")
    r = TestClient(create_app(settings)).get("/replay/stackcube__b01_early_release")
    assert r.status_code == 500 and r.json()["error"]["code"] == "E_REPLAY_CORRUPT"


def test_cache_only_mode_serves_cached_and_refuses_live(make_settings) -> None:
    c = _client(make_settings, mode="cache-only")
    assert c.get("/health").json()["mode"] == "cache-only"
    ok = c.post("/grade", data={"clip_id": "b01_early_release", "test_id": "stackcube"})
    assert ok.status_code == 200 and ok.json()["cached"] is True
    no = c.post("/grade", data={"clip_id": "correct_run", "test_id": "stackcube"})
    assert no.status_code == 503 and no.json()["error"]["code"] == "E_CACHE_ONLY"
    up = c.post("/grade", files={"file": ("a.mp4", b"abc", "video/mp4")})
    assert up.status_code == 503


def test_logs_contain_no_raw_ip_or_filename(make_settings, caplog: pytest.LogCaptureFixture) -> None:
    c = _client(make_settings, trust_proxy=True)
    caplog.set_level(logging.DEBUG)
    with (CLIPS / "b01_early_release.mp4").open("rb") as fh:
        c.post(
            "/grade",
            data={"test_id": "stackcube"},
            files={"file": ("my_private_name.mp4", fh, "video/mp4")},
            headers={"X-Forwarded-For": "203.0.113.77"},
        )
    c.post("/grade", data={"clip_id": "nope"}, headers={"X-Forwarded-For": "203.0.113.77"})
    assert any(r.name == "kodiac.app" for r in caplog.records), "expected structured app logs"
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert "203.0.113.77" not in blob and "my_private_name" not in blob
    assert "testclient" not in blob


def test_blame_hook_is_the_integration_point(make_settings) -> None:
    def hook(run, ctx):
        assert ctx.test.name and ctx.clip.n_frames > 0
        return run.model_copy(update={"diff_text": "hook ran"})

    c = TestClient(create_app(make_settings(), blame_hook=hook))
    body = c.post("/grade", data={"clip_id": "b01_early_release"}).json()
    assert body["run"]["diff_text"] == "hook ran"


def test_failing_blame_hook_is_disclosed_not_swallowed(make_settings) -> None:
    def hook(run, ctx):
        raise RuntimeError("boom")

    c = TestClient(create_app(make_settings(), blame_hook=hook))
    body = c.post("/grade", data={"clip_id": "b01_early_release"}).json()
    assert body["run"]["verdict"] == "FAIL"
    assert any("unavailable" in n for n in body["notes"])


def test_reaper_runs_through_service(make_settings) -> None:
    import os
    import time

    settings = make_settings()
    app = create_app(settings)
    old = settings.upload_dir / "stale.mp4"
    old.write_bytes(b"x")
    t = time.time() - 25 * 3600
    os.utime(old, (t, t))
    assert app.state.core.service.reap() >= 1 and not old.exists()


def test_index_without_gradio_lists_cached_replays(make_settings) -> None:
    c = _client(make_settings)
    page = c.get("/")
    assert page.status_code == 200 and "⚡ CACHED" in page.text
