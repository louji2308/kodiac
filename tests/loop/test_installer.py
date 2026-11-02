"""Tests for loop/installer.py (`Kodiac loop init`)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from Kodiac_robotics.loop.installer import TEMPLATE_DIR, install_loop

KW = {"test": "examples/stackcube.green", "sim_script": "examples/sim/pick_place.py", "seed": 7, "max_blocks": 6}
EXPECTED = {".mcp.json", ".muse/hooks.json", "GOAL.md", "examples/sim/gate.template.json"}


def _tree(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def test_creates_exactly_the_four_files(tmp_path: Path) -> None:
    actions = install_loop(tmp_path, **KW)
    assert set(actions) == EXPECTED and set(actions.values()) == {"create"}
    assert _tree(tmp_path) == EXPECTED


def test_mcp_json_declares_server_with_env_passthrough_and_no_secret_values(tmp_path: Path) -> None:
    install_loop(tmp_path, **KW)
    server = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["Kodiac"]
    assert server["command"] == "Kodiac" and server["args"] == ["mcp"]
    assert server["env"] and all(v.startswith("${") and v.endswith("}") for v in server["env"].values())


def test_hooks_json_stop_hook_uses_gate_with_max_blocks_and_600s_timeout(tmp_path: Path) -> None:
    install_loop(tmp_path, **KW)
    hook = json.loads((tmp_path / ".muse/hooks.json").read_text(encoding="utf-8"))["hooks"]["Stop"][0]["hooks"][0]
    assert hook["command"] == "Kodiac gate --max-blocks 6" and hook["timeout"] == 600 and hook["type"] == "command"


def test_goal_recipe_says_done_only_on_pass_and_is_identical_text_per_bug(tmp_path: Path) -> None:
    install_loop(tmp_path, **KW)
    goal = (tmp_path / "GOAL.md").read_text(encoding="utf-8")
    assert "Done ONLY when Kodiac run prints PASS" in goal
    assert "examples/sim/pick_place.py" in goal and '"seed": 7' in goal
    assert "{{" not in goal
    for bug in (f"B{i:02d}" for i in range(1, 11)):
        assert bug not in goal  # no bug-specific hints in the recipe


def test_gate_template_lives_in_examples_sim_and_holds_pin_arguments_only(tmp_path: Path) -> None:
    install_loop(tmp_path, **KW)
    data = json.loads((tmp_path / "examples/sim/gate.template.json").read_text(encoding="utf-8"))
    assert data["test"] == "examples/stackcube.green" and data["seed"] == 7 and data["max_blocks"] == 6
    assert data["sim_script"] == "examples/sim/pick_place.py"


def test_idempotent_second_run_changes_nothing_and_writes_no_backups(tmp_path: Path) -> None:
    install_loop(tmp_path, **KW)
    before = {p: (tmp_path / p).read_bytes() for p in EXPECTED}
    again = install_loop(tmp_path, **KW)
    assert set(again.values()) == {"unchanged"}
    assert {p: (tmp_path / p).read_bytes() for p in EXPECTED} == before
    assert _tree(tmp_path) == EXPECTED


def test_differing_user_file_is_backed_up_before_overwrite(tmp_path: Path) -> None:
    (tmp_path / "GOAL.md").write_text("my own goal\n", encoding="utf-8")
    actions = install_loop(tmp_path, **KW)
    assert actions["GOAL.md"] == "update (backup written)"
    assert (tmp_path / "GOAL.md.bak").read_text(encoding="utf-8") == "my own goal\n"
    assert "Done ONLY when" in (tmp_path / "GOAL.md").read_text(encoding="utf-8")
    # a second differing change must not clobber the first backup
    (tmp_path / "GOAL.md").write_text("edited again\n", encoding="utf-8")
    install_loop(tmp_path, **KW)
    assert (tmp_path / "GOAL.md.bak").read_text(encoding="utf-8") == "my own goal\n"
    assert (tmp_path / "GOAL.md.bak.1").read_text(encoding="utf-8") == "edited again\n"


def test_existing_mcp_servers_and_hooks_are_merged_not_dropped(tmp_path: Path) -> None:
    (tmp_path / ".muse").mkdir()
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "keep": 1}), encoding="utf-8")
    (tmp_path / ".muse/hooks.json").write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}], "PreToolUse": []}}), encoding="utf-8"
    )
    actions = install_loop(tmp_path, **KW)
    assert actions[".mcp.json"] == "update (backup written)" and actions[".muse/hooks.json"] == "update (backup written)"
    mcp = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp["keep"] == 1 and set(mcp["mcpServers"]) == {"other", "Kodiac"}
    stop = json.loads((tmp_path / ".muse/hooks.json").read_text(encoding="utf-8"))["hooks"]["Stop"]
    assert [g["hooks"][0]["command"] for g in stop] == ["echo mine", "Kodiac gate --max-blocks 6"]
    assert "PreToolUse" in json.loads((tmp_path / ".muse/hooks.json").read_text(encoding="utf-8"))["hooks"]
    # re-running with a changed max_blocks replaces our entry instead of duplicating it
    install_loop(tmp_path, **{**KW, "max_blocks": 3})
    stop = json.loads((tmp_path / ".muse/hooks.json").read_text(encoding="utf-8"))["hooks"]["Stop"]
    assert [g["hooks"][0]["command"] for g in stop] == ["echo mine", "Kodiac gate --max-blocks 3"]


def test_invalid_existing_json_is_backed_up_and_replaced(tmp_path: Path) -> None:
    (tmp_path / ".mcp.json").write_text("{not json", encoding="utf-8")
    actions = install_loop(tmp_path, **KW)
    assert actions[".mcp.json"] == "replace-invalid (backup written)"
    assert (tmp_path / ".mcp.json.bak").read_text(encoding="utf-8") == "{not json"
    json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))


def test_dry_run_lists_actions_and_writes_nothing(tmp_path: Path) -> None:
    actions = install_loop(tmp_path, dry_run=True, **KW)
    assert set(actions) == EXPECTED and set(actions.values()) == {"would-create"}
    assert _tree(tmp_path) == set()
    install_loop(tmp_path, **KW)
    assert set(install_loop(tmp_path, dry_run=True, **KW).values()) == {"would-unchanged"}


def test_never_writes_secret_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_API_KEY", "supersecretvalue-1234567890")
    install_loop(tmp_path, **KW)
    for p in _tree(tmp_path):
        assert "supersecretvalue" not in (tmp_path / p).read_text(encoding="utf-8")
    # a secret smuggled in through an argument is refused, and nothing is written
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(ValueError, match="MODEL_API_KEY"):
        install_loop(other, **{**KW, "test": "supersecretvalue-1234567890.green"})
    assert _tree(other) == set()


def test_windows_style_paths_render_valid_json(tmp_path: Path) -> None:
    install_loop(tmp_path, **{**KW, "sim_script": 'examples\\sim\\"odd".py'})
    data = json.loads((tmp_path / "examples/sim/gate.template.json").read_text(encoding="utf-8"))
    assert data["sim_script"].endswith('"odd".py')


def test_bad_arguments_raise(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        install_loop(tmp_path, **{**KW, "max_blocks": 0})
    with pytest.raises(FileNotFoundError):
        install_loop(tmp_path / "missing", **KW)


def test_templates_ship_in_the_package() -> None:
    assert {p.name for p in TEMPLATE_DIR.iterdir()} >= {"mcp.json", "hooks.json", "GOAL.md", "gate.template.json"}
