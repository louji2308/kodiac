"""`Kodiac loop init`: install the Muse Code /goal loop configuration into a project.

Writes (idempotent, nothing else is ever touched):
  .mcp.json                         MCP server declaration `Kodiac` (env passthrough, no secret values)
  .muse/hooks.json                  Stop hook -> `Kodiac gate --max-blocks N` (hook timeout 600 s)
  GOAL.md                           the /goal recipe (same text for every bug)
  examples/sim/gate.template.json   arguments for `Kodiac gate --init` (gate template lives in examples/sim only)

Existing files are merged where they are JSON (user entries are kept); any file that would change is
first copied to `<name>.bak` (`.bak.1`, `.bak.2` ... if a backup already exists). The hook file shape is
modelled on Claude-Code-style hooks and is [UNVERIFIED] against Muse Code.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
SERVER_KEY = "Kodiac"
GATE_COMMAND_PREFIX = "Kodiac gate"
_SECRET_ENV_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)", re.IGNORECASE)
_SECRET_SHAPES = re.compile(r"(sk-[A-Za-z0-9]{16,}|Bearer\s+[A-Za-z0-9._-]{16,}|[A-Fa-f0-9]{40,})")


def _template(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def _render(text: str, values: dict[str, Any], *, as_json: bool) -> str:
    for key, value in values.items():
        rendered = json.dumps(str(value))[1:-1] if as_json and isinstance(value, str) else str(value)
        text = text.replace("{{" + key + "}}", rendered)
    if "{{" in text:
        raise ValueError("unrendered placeholder left in template")
    return text


def _assert_no_secrets(text: str, where: str) -> None:
    for name, value in os.environ.items():
        if len(value) >= 8 and _SECRET_ENV_NAME.search(name) and value in text:
            raise ValueError(f"refusing to write {where}: it would contain the value of ${name}")
    if _SECRET_SHAPES.search(text):
        raise ValueError(f"refusing to write {where}: content looks like a secret")


def _write_text(path: Path, text: str) -> None:
    """Write UTF-8 text, retrying briefly when a Windows scanner/indexer holds the file."""
    for attempt in range(5):
        try:
            path.write_text(text, encoding="utf-8")
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.2 * (attempt + 1))


def _backup_path(path: Path) -> Path:
    candidate = path.with_name(path.name + ".bak")
    n = 0
    while candidate.exists():
        n += 1
        candidate = path.with_name(f"{path.name}.bak.{n}")
    return candidate


def _dump_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2) + "\n"


def _merge_mcp(existing: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    servers = dict(merged.get("mcpServers") or {})
    servers[SERVER_KEY] = template["mcpServers"][SERVER_KEY]
    merged["mcpServers"] = servers
    return merged


def _is_gate_group(group: Any) -> bool:
    return isinstance(group, dict) and any(
        isinstance(h, dict) and str(h.get("command", "")).startswith(GATE_COMMAND_PREFIX)
        for h in group.get("hooks", [])
    )


def _merge_hooks(existing: dict[str, Any], template: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    hooks = dict(merged.get("hooks") or {})
    stop = list(hooks.get("Stop") or [])
    ours = template["hooks"]["Stop"][0]
    for i, group in enumerate(stop):
        if _is_gate_group(group):
            stop[i] = ours
            break
    else:
        stop.append(ours)
    hooks["Stop"] = stop
    merged["hooks"] = hooks
    return merged


def _plan_json(path: Path, rendered: str, merge: Any) -> tuple[str, str]:
    """Return (new_text, action) for a JSON config file."""
    template = json.loads(rendered)
    if not path.exists():
        return _dump_json(template), "create"
    try:
        existing = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(existing, dict):
            raise ValueError("not an object")
    except ValueError:
        return _dump_json(template), "replace-invalid"
    merged = merge(existing, template)
    new_text = _dump_json(merged)
    return new_text, ("unchanged" if merged == existing else "update")


def _plan_text(path: Path, text: str) -> tuple[str, str]:
    if not path.exists():
        return text, "create"
    return text, ("unchanged" if path.read_text(encoding="utf-8") == text else "update")


def install_loop(
    project_dir: Path,
    *,
    test: str,
    sim_script: str,
    seed: int = 0,
    max_blocks: int = 8,
    dry_run: bool = False,
) -> dict[str, str]:
    """Install the loop config into `project_dir`. Returns {relative path: action}.

    Actions: create | unchanged | update (backup written) | replace-invalid (backup written);
    with `dry_run=True` they are prefixed `would-` and nothing is written.
    """
    project = Path(project_dir)
    if not project.is_dir():
        raise FileNotFoundError(f"project directory not found: {project}")
    if max_blocks < 1:
        raise ValueError("max_blocks must be >= 1")
    values: dict[str, Any] = {
        "test": Path(test).as_posix(),
        "sim_script": Path(sim_script).as_posix(),
        "seed": int(seed),
        "max_blocks": int(max_blocks),
    }

    plans: list[tuple[str, str, str]] = []  # (relative path, text, action)
    for rel, name, merge in ((".mcp.json", "mcp.json", _merge_mcp), (".muse/hooks.json", "hooks.json", _merge_hooks)):
        text, action = _plan_json(project / rel, _render(_template(name), values, as_json=True), merge)
        plans.append((rel, text, action))
    for rel, name, as_json in (
        ("GOAL.md", "GOAL.md", False),
        ("examples/sim/gate.template.json", "gate.template.json", True),
    ):
        rendered = _render(_template(name), values, as_json=as_json)
        if as_json:
            rendered = _dump_json(json.loads(rendered))
        text, action = _plan_text(project / rel, rendered)
        plans.append((rel, text, action))

    for rel, text, _ in plans:
        _assert_no_secrets(text, rel)

    result: dict[str, str] = {}
    for rel, text, action in plans:
        path = project / rel
        if dry_run:
            result[rel] = f"would-{action}"
            continue
        if action != "unchanged":
            if path.exists():
                _backup_path(path).write_bytes(path.read_bytes())
                action = f"{action} (backup written)"
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_text(path, text)
        result[rel] = action
    return result


__all__ = ["install_loop"]
