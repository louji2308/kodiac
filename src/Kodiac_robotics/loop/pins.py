"""Done-gate pins: the ``Kodiac gate --init`` state lives OUTSIDE the workspace (ARCHITECTURE KD-11, §5.5).

``<pin_dir>/<sha256(resolved workspace)>.json`` holds the pinned test sha256, the config sha256, a digest of the Kodiac
engine source on the verdict path, the sim script path, the seed, ``max_blocks`` and the authoritative ``blocks``
counter (``GateState``). ``pin_dir()`` is ``~/.config/Kodiac/gates/`` unless ``KODIAC_GATE_HOME`` overrides it.

Nothing inside the workspace is trusted:

- ``.Kodiac/gate_state.json`` is a read-only mirror for humans; the gate never reads it.
- ``.Kodiac/gate_init.json`` only records that the workspace was initialised, so that deleting the pin file fails
  closed (exit 2) instead of silently disabling the gate.

Stated limits: the pin file carries a self-digest, which catches corruption and naive edits, not a process that can
write to the user's home directory and recompute the digest. An agent that can do that (or edit the installed Kodiac
package, or re-run ``gate --init`` itself) is outside what an in-process check can stop; re-initialisations are kept in
``previous_pins`` and surfaced in every gate message. Sandbox the agent to its workspace for the full guarantee.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import Kodiac_robotics
from Kodiac_robotics.contracts.core import GateState

SCHEMA = "kodiac.gate.pins/v1"
GATE_HOME_ENV = "KODIAC_GATE_HOME"
ENV_FILE_VARS = ("KODIAC_ENV_FILE", "Kodiac_ENV_FILE")
ENGINE_ROOT = Path(Kodiac_robotics.__file__).resolve().parent

# Source files on the gate's verdict path (sim -> synthetic tracks -> pipeline.run). Editing any of them changes
# ``engine_sha256`` and the gate refuses until a human re-runs ``gate --init``.
_ENGINE_DIRS = ("contracts", "engine", "geometry", "predicates", "uncertainty")
_ENGINE_FILES = (
    "pipeline/run.py",
    "pipeline/loader.py",
    "segment/rle.py",
    "segment/fixture.py",
    "sim/env.py",
    "sim/robot.py",
    "sim/spans.py",
    "sim/runner.py",
    "loop/gate.py",
    "loop/pins.py",
)


class PinError(RuntimeError):
    """The pin state exists but cannot be trusted (missing, corrupt, tampered, or for another workspace)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(path: Path) -> str:
    return os.path.normcase(str(Path(path).resolve()))


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def file_sha256(path: Path) -> str | None:
    """sha256 of a file's bytes, or None if it does not exist."""
    p = Path(path)
    if not p.is_file():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pin_dir() -> Path:
    override = os.environ.get(GATE_HOME_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".config" / "Kodiac" / "gates").resolve()


def workspace_key(workspace: Path) -> str:
    return hashlib.sha256(_norm(workspace).encode("utf-8")).hexdigest()


def pin_path(workspace: Path) -> Path:
    return pin_dir() / f"{workspace_key(workspace)}.json"


def marker_path(workspace: Path) -> Path:
    return Path(workspace).resolve() / ".Kodiac" / "gate_init.json"


def mirror_path(workspace: Path) -> Path:
    return Path(workspace).resolve() / ".Kodiac" / "gate_state.json"


def default_config_files(workspace: Path, test: Path) -> list[Path]:
    """Threshold/config files pinned alongside the test: the ``.green.lock`` sidecar and ``Kodiac.toml``.

    Pinned whether or not they exist yet, so creating one after ``--init`` also counts as a modification.
    """
    return [Path(str(Path(test).resolve()) + ".lock"), Path(workspace).resolve() / "Kodiac.toml"]


def config_entries(config_files: list[Path]) -> list[dict[str, str | None]]:
    seen: set[str] = set()
    entries: list[dict[str, str | None]] = []
    for f in config_files:
        key = _norm(f)
        if key in seen:
            continue
        seen.add(key)
        entries.append({"path": str(Path(f).resolve()), "sha256": file_sha256(Path(f))})
    return sorted(entries, key=lambda e: os.path.normcase(str(e["path"])))


def config_sha256(entries: list[dict[str, str | None]]) -> str:
    payload = [[os.path.normcase(str(e["path"])), e["sha256"] or "MISSING"] for e in entries]
    return hashlib.sha256(_canonical(payload)).hexdigest()


def current_config(entries: list[dict[str, Any]]) -> list[dict[str, str | None]]:
    """Re-hash the pinned config paths as they are on disk now."""
    return config_entries([Path(str(e["path"])) for e in entries])


def engine_sha256(root: Path | None = None) -> str:
    """Digest of the Kodiac source files on the gate's verdict path."""
    base = Path(root) if root is not None else ENGINE_ROOT
    files: set[Path] = set()
    for d in _ENGINE_DIRS:
        files.update(p for p in (base / d).rglob("*.py") if "__pycache__" not in p.parts)
    for f in _ENGINE_FILES:
        if (base / f).is_file():
            files.add(base / f)
    h = hashlib.sha256()
    for p in sorted(files, key=lambda q: q.relative_to(base).as_posix()):
        h.update(p.relative_to(base).as_posix().encode("utf-8") + b"\0")
        h.update(hashlib.sha256(p.read_bytes()).hexdigest().encode("ascii") + b"\n")
    return h.hexdigest()


def env_file_from_environ() -> str | None:
    for var in ENV_FILE_VARS:
        value = os.environ.get(var)
        if value:
            return str(Path(value).expanduser().resolve())
    return None


def _digest(payload: dict[str, Any]) -> str:
    body = {k: v for k, v in payload.items() if k != "digest"}
    return hashlib.sha256(_canonical(body)).hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".pin-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _write_mirror(workspace: Path, payload: dict[str, Any]) -> None:
    mirror = {
        "note": "informational mirror; the done-gate never reads this file (authoritative state lives outside the workspace)",
        "pin_path": str(pin_path(workspace)),
        "state": payload["state"],
        "updated_at": _now(),
    }
    try:
        p = mirror_path(workspace)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(mirror, indent=2), encoding="utf-8")
    except OSError:
        pass


def save_pins(workspace: Path, payload: dict[str, Any]) -> None:
    """Re-digest and atomically write the pin payload (authoritative), then refresh the workspace mirror."""
    payload = dict(payload)
    payload["digest"] = _digest(payload)
    _atomic_write(pin_path(workspace), json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"))
    _write_mirror(workspace, payload)


def _read_payload(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def write_pins(
    workspace: Path,
    *,
    test: Path,
    sim_script: Path,
    seed: int,
    config_files: list[Path],
    max_blocks: int,
) -> GateState:
    """Pin the test, config, engine source, script path and seed for ``workspace``; resets ``blocks`` to 0."""
    ws = Path(workspace).resolve()
    test_p = Path(test).resolve()
    script_p = Path(sim_script).resolve()
    test_sha = file_sha256(test_p)
    if test_sha is None:
        raise FileNotFoundError(f"test file not found: {test_p}")
    if not script_p.is_file():
        raise FileNotFoundError(f"sim script not found: {script_p}")
    entries = config_entries(config_files)
    cfg_sha = config_sha256(entries)
    state = GateState(
        pinned_test_sha256=test_sha,
        pinned_config_sha256=cfg_sha,
        blocks=0,
        max_blocks=int(max_blocks),
        last_nonce=None,
    )

    previous: list[dict[str, Any]] = []
    target = pin_path(ws)
    old = _read_payload(target) if target.exists() else None
    if old is not None:
        previous = [p for p in old.get("previous_pins", []) if isinstance(p, dict)]
        previous.append(
            {
                "init_nonce": old.get("init_nonce"),
                "created_at": old.get("created_at"),
                "test_sha256": (old.get("test") or {}).get("sha256"),
                "config_sha256": (old.get("config") or {}).get("sha256"),
                "engine_sha256": old.get("engine_sha256"),
            }
        )

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "workspace": str(ws),
        "init_nonce": secrets.token_hex(8),
        "created_at": _now(),
        "state": state.model_dump(),
        "test": {"path": str(test_p), "sha256": test_sha},
        "sim_script": {"path": str(script_p)},
        "seed": int(seed),
        "backend": "auto",
        "config": {"sha256": cfg_sha, "files": entries},
        "engine_sha256": engine_sha256(),
        "env_file": env_file_from_environ(),
        "previous_pins": previous,
        "last_result": None,
    }
    save_pins(ws, payload)

    marker = {
        "note": "this workspace is gated by `Kodiac gate`; the pins live outside the workspace (see pin_path)",
        "pin_path": str(target),
        "init_nonce": payload["init_nonce"],
        "created_at": payload["created_at"],
    }
    mp = marker_path(ws)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(marker, indent=2), encoding="utf-8")
    return state


def _validate_payload(payload: dict[str, Any], ws: Path) -> GateState:
    if payload.get("schema") != SCHEMA:
        raise PinError(f"pin file has unknown schema {payload.get('schema')!r}")
    if payload.get("digest") != _digest(payload):
        raise PinError("pin file digest mismatch (edited or corrupted outside the gate)")
    if os.path.normcase(str(payload.get("workspace", ""))) != _norm(ws):
        raise PinError("pin file belongs to a different workspace")
    try:
        state = GateState.model_validate(payload["state"])
        test_sha = payload["test"]["sha256"]
        cfg_sha = payload["config"]["sha256"]
        entries = payload["config"]["files"]
        test_path = payload["test"]["path"]
        script_path = payload["sim_script"]["path"]
        seed = payload["seed"]
        engine = payload["engine_sha256"]
    except (KeyError, TypeError, ValueError) as exc:
        raise PinError(f"pin file is missing required fields ({type(exc).__name__})") from exc
    if state.pinned_test_sha256 != test_sha or state.pinned_config_sha256 != cfg_sha:
        raise PinError("pin file is internally inconsistent (state vs pinned hashes)")
    if not all(isinstance(v, str) and v for v in (test_path, script_path, engine)):
        raise PinError("pin file has invalid paths or engine digest")
    if not isinstance(entries, list) or config_sha256(entries) != cfg_sha:
        raise PinError("pin file config entries do not match the pinned config sha256")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise PinError("pin file has an invalid seed")
    if state.max_blocks < 1 or state.blocks < 0:
        raise PinError("pin file has an invalid blocks counter")
    return state


def load_pins(workspace: Path) -> tuple[GateState, dict[str, Any]] | None:
    """Return ``(GateState, pin payload)``; ``None`` means this workspace was never initialised.

    Raises ``PinError`` when the workspace was initialised but its pins are missing, corrupt or tampered with.
    """
    ws = Path(workspace).resolve()
    marker = marker_path(ws)
    try:
        target = pin_path(ws)
    except RuntimeError as exc:
        if marker.exists():
            raise PinError(f"cannot locate the gate pin directory ({exc})") from exc
        return None

    if not target.exists():
        if marker.exists():
            pinned_at = ""
            try:
                pinned_at = str(json.loads(marker.read_text(encoding="utf-8")).get("pin_path", ""))
            except (OSError, ValueError, AttributeError):
                pinned_at = "unreadable marker"
            raise PinError(
                f"pin file missing at {target} although this workspace was initialised"
                + (f" (pins were written to {pinned_at})" if pinned_at else "")
            )
        return None

    payload = _read_payload(target)
    if payload is None:
        raise PinError(f"pin file unreadable or not valid JSON: {target}")
    state = _validate_payload(payload, ws)
    return state, payload


__all__ = [
    "ENGINE_ROOT",
    "GATE_HOME_ENV",
    "PinError",
    "config_entries",
    "config_sha256",
    "current_config",
    "default_config_files",
    "engine_sha256",
    "env_file_from_environ",
    "file_sha256",
    "load_pins",
    "marker_path",
    "mirror_path",
    "pin_dir",
    "pin_path",
    "save_pins",
    "workspace_key",
    "write_pins",
]
