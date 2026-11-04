"""Root pytest configuration and fixtures for Kodiac test suite.

Ensures test executions are hermetic and deterministic by default,
avoiding unintended live API or network calls when run offline or in sandboxes.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import sys
import pytest

# Windows sandbox hermeticity:
# On Windows, asyncio and anyio create event loops whose self-pipe invokes socket.socketpair(),
# which attempts local TCP loopback connections on 127.0.0.1. In sandboxed environments without
# network access, loopback connects hang indefinitely.
# We bypass loopback sockets on Windows by waking IOCP directly via PostQueuedCompletionStatus.
if sys.platform == "win32":
    try:
        import _overlapped
        from asyncio.proactor_events import BaseProactorEventLoop

        def _patched_make_self_pipe(self):
            self._ssock = None
            self._csock = None
            self._self_reading_future = None
            self._internal_fds += 1
            self._dummy_ov = _overlapped.Overlapped()

        def _patched_close_self_pipe(self):
            self._internal_fds -= 1

        def _patched_write_to_self(self):
            if hasattr(self, "_proactor") and hasattr(self._proactor, "_iocp") and hasattr(self, "_dummy_ov"):
                try:
                    _overlapped.PostQueuedCompletionStatus(self._proactor._iocp, 0, 0, self._dummy_ov.address)
                except OSError:
                    pass

        def _patched_loop_self_reading(self, f=None):
            return

        BaseProactorEventLoop._make_self_pipe = _patched_make_self_pipe
        BaseProactorEventLoop._close_self_pipe = _patched_close_self_pipe
        BaseProactorEventLoop._write_to_self = _patched_write_to_self
        BaseProactorEventLoop._loop_self_reading = _patched_loop_self_reading
    except Exception:
        pass

_orig_asyncio_run = asyncio.run


def _hermetic_asyncio_run(main, *args, **kwargs):
    if inspect.iscoroutine(main):
        try:
            main.send(None)
        except StopIteration as exc:
            return exc.value
    return _orig_asyncio_run(main, *args, **kwargs)


asyncio.run = _hermetic_asyncio_run


@pytest.fixture(autouse=True)
def _hermetic_test_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default test environment to fixture backend and template compiler if not set."""
    if "KODIAC_SAM_BACKEND" not in os.environ and "SAM_BACKEND" not in os.environ:
        monkeypatch.setenv("KODIAC_SAM_BACKEND", "fixture")
    if "KODIAC_COMPILER_BACKEND" not in os.environ and "COMPILER_BACKEND" not in os.environ:
        monkeypatch.setenv("KODIAC_COMPILER_BACKEND", "template")
