"""Pure-helper tests for modal/app_deploy.py (Modal is never imported or called)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modal import app_deploy  # noqa: E402


def test_min_containers_defaults_to_zero_and_is_clamped() -> None:
    assert app_deploy.min_containers_from_env({}) == 0
    assert app_deploy.min_containers_from_env({"KODIAC_MIN_CONTAINERS": "1"}) == 1
    assert app_deploy.min_containers_from_env({"KODIAC_MIN_CONTAINERS": "99"}) == app_deploy.MAX_MIN_CONTAINERS
    assert app_deploy.min_containers_from_env({"KODIAC_MIN_CONTAINERS": "-3"}) == 0
    assert app_deploy.min_containers_from_env({"KODIAC_MIN_CONTAINERS": "lots"}) == 0


def test_function_kwargs_are_cpu_only() -> None:
    kwargs = app_deploy.build_function_kwargs({"KODIAC_MIN_CONTAINERS": "1"})
    assert kwargs["min_containers"] == 1 and "gpu" not in kwargs
    with pytest.raises(ValueError):
        app_deploy.assert_cpu_only({"gpu": "L4"})


def test_module_imports_without_real_modal() -> None:
    assert app_deploy.app is None or hasattr(app_deploy.app, "function")
    assert app_deploy.MAX_INPUTS == 20 and app_deploy.UPLOAD_RETENTION_HOURS == 24.0


def test_reap_uploads_helper(tmp_path: Path) -> None:
    old, fresh = tmp_path / "old.mp4", tmp_path / "fresh.mp4"
    old.write_bytes(b"1")
    fresh.write_bytes(b"2")
    t = time.time() - 25 * 3600
    os.utime(old, (t, t))
    assert app_deploy.reap_uploads([tmp_path]) == 1
    assert fresh.exists() and not old.exists()


class _Chain:
    def __init__(self, log: list) -> None:
        self.log = log

    def __getattr__(self, name: str):
        def call(*args, **kwargs):
            self.log.append((name, args, kwargs))
            return self

        return call


class _FakeModal:
    """Records how build_app wires the app, without any Modal dependency."""

    def __init__(self) -> None:
        self.calls: list = []
        self.functions: list[dict] = []
        outer = self

        class Image:
            @staticmethod
            def debian_slim(**kw):
                outer.calls.append(("debian_slim", kw))
                return _Chain(outer.calls)

        class Volume:
            @staticmethod
            def from_name(name, **kw):
                outer.calls.append(("volume", name))
                return object()

        class App:
            def __init__(self, name):
                outer.calls.append(("app", name))

            def function(self, **kw):
                def deco(fn):
                    outer.functions.append({"fn": fn, **kw})
                    return fn

                return deco

        self.Image, self.Volume, self.App = Image, Volume, App

    def concurrent(self, max_inputs):
        self.calls.append(("concurrent", max_inputs))
        return lambda fn: fn

    def asgi_app(self):
        self.calls.append(("asgi_app",))
        return lambda fn: fn

    def Period(self, **kw):  # noqa: N802 (mirrors modal.Period)
        return ("period", kw)


def test_build_app_wiring_with_fake_modal() -> None:
    fake = _FakeModal()
    app = app_deploy.build_app(fake, {"KODIAC_MIN_CONTAINERS": "0"})
    assert app is not None
    assert ("concurrent", 20) in fake.calls and ("asgi_app",) in fake.calls
    web = next(f for f in fake.functions if f["fn"].__name__ == "web")
    assert web["min_containers"] == 0 and "gpu" not in web
    reaper = next(f for f in fake.functions if f["fn"].__name__ == "upload_reaper")
    assert reaper["schedule"] == ("period", {"hours": 1})
    assert all("gpu" not in f for f in fake.functions)
    assert any(c[0] == "apt_install" and "ffmpeg" in c[1] for c in fake.calls if len(c) > 2)
