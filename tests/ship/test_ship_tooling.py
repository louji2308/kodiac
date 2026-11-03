from __future__ import annotations

import os
import random
import re
import shutil
import string
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))

import compliance_check as cc  # noqa: E402
import lint_public as lp  # noqa: E402
import lint_script as ls  # noqa: E402

# ---------------------------------------------------------------- script lint
CONCEPTS8 = "concepts:\n" + "".join(f"  - {{id: C{i}, text: c{i}}}\n" for i in range(1, 9))


def _write_script(tmp_path: Path, vo_extra: str = "", n_concepts: int = 8, concepts: str | None = None) -> tuple[Path, Path]:
    beats = []
    for i in range(1, n_concepts + 1):
        s, e = (i - 1) * 20, i * 20
        text = vo_extra if i == 1 else ""
        beats.append(
            f"## {s // 60}:{s % 60:02d}-{e // 60}:{e % 60:02d} [C{i}]\n"
            f"SCREEN: visual {string.ascii_lowercase[i]}\nVO: beat words {text}\n"
        )
    beats.append(f"## 2:40-2:59 [C{n_concepts}]\nVO: {ls.TAGLINE}\n")
    sp = tmp_path / "SCRIPT.md"
    sp.write_text("\n".join(beats), encoding="utf-8")
    cp = tmp_path / "concepts.yaml"
    cp.write_text(concepts if concepts is not None else "concepts:\n" + "".join(f"  - {{id: C{i}, text: c}}\n" for i in range(1, n_concepts + 1)), encoding="utf-8")
    return sp, cp


def _rules(res: dict) -> set[str]:
    return {v["rule"] for v in res["violations"]}


def test_banned_list_parsed_from_idea():
    idea_path = REPO / "docs" / "architecture" / "IDEA.md"
    if not idea_path.exists():
        idea_path = REPO / "IDEA.md"
    words = ls.parse_banned_words(idea_path.read_text(encoding="utf-8"))
    lowered = {w.lower() for w in words}
    assert {"receipts", "image analyzer", "unknown", "first ever", "muse alone"} <= lowered


def test_banned_list_missing_fails_loudly():
    with pytest.raises(ls.LintSetupError):
        ls.parse_banned_words("# nothing here")


def test_clean_script_has_no_violations(tmp_path):
    sp, cp = _write_script(tmp_path)
    res = ls.lint(sp, cp, REPO)
    assert res["violations"] == []


def test_banned_word_caught(tmp_path):
    sp, cp = _write_script(tmp_path, vo_extra="we keep the receipts")
    assert "banned" in _rules(ls.lint(sp, cp, REPO))


def test_unmeasured_number_caught(tmp_path):
    sp, cp = _write_script(tmp_path, vo_extra="plus 42 points")
    res = ls.lint(sp, cp, REPO)
    assert any(v["rule"] == "numbers" and "42" in v["message"] for v in res["violations"])


def test_pending_marker_is_a_violation(tmp_path):
    sp, cp = _write_script(tmp_path, vo_extra=ls.PENDING)
    assert "numbers" in _rules(ls.lint(sp, cp, REPO))


def test_measured_registered_number_passes(tmp_path):
    root = tmp_path / "root"
    (root / "docs").mkdir(parents=True)
    idea_src = REPO / "docs" / "architecture" / "IDEA.md"
    shutil.copy(idea_src if idea_src.exists() else REPO / "IDEA.md", root / "IDEA.md")
    (root / "docs" / "VIDEO_NUMBERS.md").write_text(
        "| Item | Registered Value | Unit | CI | Evidence Type | Source | Git SHA | Status |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| a | 42 | pts | - | live | x | abc | Measured |\n"
        "| b | 7 | pts | - | none | x | abc | Target |\n",
        encoding="utf-8",
    )
    sp, cp = _write_script(tmp_path, vo_extra="plus 42 points")
    assert ls.lint(sp, cp, root)["violations"] == []
    sp2, cp2 = _write_script(tmp_path, vo_extra="plus 7 points")
    assert "numbers" in _rules(ls.lint(sp2, cp2, root))


def test_more_than_8_concepts_caught(tmp_path):
    sp, cp = _write_script(tmp_path, n_concepts=9)
    res = ls.lint(sp, cp, REPO)
    assert any(v["rule"] == "concepts" and "cap" in v["message"] for v in res["violations"])


def test_concept_without_script_line_caught(tmp_path):
    sp, cp = _write_script(tmp_path, concepts=CONCEPTS8 + "  - {id: C9, text: orphan}\n")
    res = ls.lint(sp, cp, REPO)
    assert any("C9" in v["message"] for v in res["violations"])


def test_tagline_and_length_and_hook(tmp_path):
    sp, cp = _write_script(tmp_path)
    sp.write_text(sp.read_text(encoding="utf-8").replace(ls.TAGLINE, "something else"), encoding="utf-8")
    assert "tagline" in _rules(ls.lint(sp, cp, REPO))
    sp.write_text(sp.read_text(encoding="utf-8").replace("## 0:00-0:20", "## 0:08-0:20"), encoding="utf-8")
    assert "hook" in _rules(ls.lint(sp, cp, REPO))
    long = " ".join(["word"] * 500)
    sp2, cp2 = _write_script(tmp_path, vo_extra=long)
    assert "length" in _rules(ls.lint(sp2, cp2, REPO))


def test_draft_script_reports_pending_numbers_and_is_not_ok():
    res = ls.lint(REPO / "video" / "SCRIPT.md", REPO / "video" / "concepts.yaml", REPO)
    pend = [v for v in res["violations"] if "PENDING" in v["message"]]
    assert pend, "draft must surface its pending numbers"
    assert not [v for v in res["violations"] if v["rule"] in ("banned", "lineage", "tagline", "hook", "length")]
    assert not [v for v in res["violations"] if v["rule"] == "concepts"]
    assert res["ok"] is False


def test_lineage_missing_is_unverifiable_in_script_lint(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    idea_src = REPO / "docs" / "architecture" / "IDEA.md"
    shutil.copy(idea_src if idea_src.exists() else REPO / "IDEA.md", root / "IDEA.md")
    sp, cp = _write_script(tmp_path)
    res = ls.lint(sp, cp, root)
    assert res["unverifiable"] and res["ok"] is False


# ------------------------------------------------------------ temp git repos
def _git(repo: Path, *args: str, date: str | None = None) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


def _fake_secret() -> str:
    rng = random.Random(7)
    s = "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(40))
    return s if any(c.isdigit() for c in s) else s + "7"


@pytest.fixture
def good_repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    (r / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
    (r / "BUILD_LOG.md").write_text("# log\n\n### 2026-10-28T09:20Z - start\n", encoding="utf-8")
    (r / "ATTRIBUTIONS.md").write_text(
        "| c | l |\n|---|---|\n| SAM 3.1 | x |\n| DROID | CC-BY |\n| LeRobot | Apache |\n"
        "| ManiSkill3 | Apache |\n| Robometer | x |\n| cookbook | MIT |\n",
        encoding="utf-8",
    )
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "init", date="2026-10-28T10:00:00+00:00")
    return r


def _checks(res: dict) -> set[str]:
    return {x["check"] for x in res["findings"]}


def test_good_repo_only_reports_missing_lineage(good_repo):
    res = cc.run_checks(good_repo)
    assert _checks(res) == {"lineage"}
    assert res["findings"][0]["severity"] == "UNVERIFIABLE"
    assert res["ok"] is False


def test_good_repo_with_lineage_file_is_ok(good_repo):
    (good_repo / "docs" / "private").mkdir(parents=True)
    (good_repo / "docs" / "private" / "lineage_terms.txt").write_text("zzqq-term\n", encoding="utf-8")
    res = cc.run_checks(good_repo)
    assert res["ok"] is True, res


def test_secret_in_history_caught_even_after_removal(good_repo):
    sec = _fake_secret()
    (good_repo / "cfg.py").write_text(f'api_key = "{sec}"\n', encoding="utf-8")
    _git(good_repo, "add", "cfg.py")
    _git(good_repo, "commit", "-q", "-m", "oops", date="2026-10-29T10:00:00+00:00")
    _git(good_repo, "rm", "-q", "cfg.py")
    _git(good_repo, "commit", "-q", "-m", "remove", date="2026-10-30T10:00:00+00:00")
    res = cc.run_checks(good_repo)
    hist = [x for x in res["findings"] if x["check"] == "secret-history"]
    assert hist and hist[0]["severity"] == "S0"
    assert sec not in str(res), "report must redact secret values"


def test_secret_in_worktree_caught(good_repo):
    (good_repo / "a.py").write_text(f"TOKEN = '{_fake_secret()}'\n", encoding="utf-8")
    _git(good_repo, "add", "a.py")
    assert "secret" in _checks(cc.run_checks(good_repo))


def test_env_style_placeholders_not_flagged():
    assert lp.find_secrets('export MODEL_API_KEY="..."\napi_key = os.environ["X"]\n') == []


def test_large_tracked_file_caught(good_repo):
    big = good_repo / "big.bin"
    with open(big, "wb") as fh:
        fh.truncate(21 * 1024 * 1024)
    _git(good_repo, "add", "big.bin")
    assert "large-file" in _checks(cc.run_checks(good_repo))


def test_private_dir_tracked_caught(good_repo):
    (good_repo / "docs" / "private").mkdir(parents=True)
    (good_repo / "docs" / "private" / "n.txt").write_text("x", encoding="utf-8")
    _git(good_repo, "add", "-f", "docs/private/n.txt")
    assert "private-tracked" in _checks(cc.run_checks(good_repo))


def test_pre_event_commit_caught(tmp_path, good_repo):
    (good_repo / "old.txt").write_text("x", encoding="utf-8")
    _git(good_repo, "add", "old.txt")
    _git(good_repo, "commit", "-q", "-m", "old", date="2026-10-01T10:00:00+00:00")
    assert "first-commit" in _checks(cc.run_checks(good_repo))


def test_missing_attribution_rows_reported_open_not_edited(good_repo):
    p = good_repo / "ATTRIBUTIONS.md"
    p.write_text("| c | l |\n|---|---|\n| SAM | x |\n", encoding="utf-8")
    before = p.read_text(encoding="utf-8")
    res = cc.run_checks(good_repo)
    open_ = [x for x in res["findings"] if x["check"] == "attributions"]
    assert len(open_) == 5 and all(x["severity"] == "OPEN" for x in open_)
    assert p.read_text(encoding="utf-8") == before


def test_lineage_term_in_commit_message_and_file_caught(good_repo):
    (good_repo / "docs" / "private").mkdir(parents=True)
    (good_repo / "docs" / "private" / "lineage_terms.txt").write_text("zzqq-term\n", encoding="utf-8")
    (good_repo / "n.md").write_text("mentions ZZQQ-term here\n", encoding="utf-8")
    _git(good_repo, "add", "n.md")
    _git(good_repo, "commit", "-q", "-m", "msg with zzqq-term", date="2026-10-29T10:00:00+00:00")
    c = _checks(cc.run_checks(good_repo))
    assert {"lineage", "lineage-history", "lineage-message"} <= c


def test_lint_public_flags_forbidden_paths_in_history(good_repo):
    (good_repo / "HACKATHON.md").write_text("strategy", encoding="utf-8")
    _git(good_repo, "add", "HACKATHON.md")
    _git(good_repo, "commit", "-q", "-m", "s", date="2026-10-29T10:00:00+00:00")
    _git(good_repo, "rm", "-q", "HACKATHON.md")
    _git(good_repo, "commit", "-q", "-m", "r", date="2026-10-30T10:00:00+00:00")
    assert not [f for f in lp.lint_repo(good_repo, history=False) if f["check"] == "forbidden-path"]
    assert [f for f in lp.lint_repo(good_repo, history=True) if f["check"] == "forbidden-path"]


def test_compliance_cli_exit_codes(good_repo):
    p = subprocess.run([sys.executable, str(SCRIPTS / "compliance_check.py"), "--repo", str(good_repo)], capture_output=True, text=True)
    assert p.returncode == 1 and "UNVERIFIABLE" in p.stdout


# --------------------------------------------------------- mirror/ops safety
SCRIPT_FILES = ["compliance_check.py", "lint_script.py", "lint_public.py", "make_public_mirror.sh", "make_public_mirror.ps1"]


def test_no_publish_commands_executed():
    bad = re.compile(r"(twine\s+upload|gh\s+(repo|release|pr|issue)|huggingface-cli\s+upload|hf\s+upload|curl\s+.*-X\s*POST|git\s+remote\s+set-url)", re.I)
    for name in SCRIPT_FILES:
        for ln, line in enumerate((SCRIPTS / name).read_text(encoding="utf-8").splitlines(), 1):
            s = line.strip()
            assert not bad.search(s), f"{name}:{ln}: {s}"
            if re.search(r"\bpush\b", s) and not s.startswith("#"):
                assert re.match(r'(echo|Write-Output)\b', s), f"{name}:{ln}: push must only be printed: {s}"


def test_mirror_scripts_strip_required_paths_and_default_to_dry_run():
    for name in ("make_public_mirror.sh", "make_public_mirror.ps1"):
        t = (SCRIPTS / name).read_text(encoding="utf-8")
        for p in ("HACKATHON.md", "docs/research/", "docs/private/", ".agents/", "HUMAN_TODO.md"):
            assert p in t, (name, p)
        assert "DRY RUN" in t and "exit 3" in t


@pytest.mark.skipif(shutil.which("powershell") is None, reason="needs Windows PowerShell")
def test_ps1_exit3_without_filter_repo_and_dry_run_otherwise():
    p = subprocess.run(
        ["git", "filter-repo", "--version"], capture_output=True
    )
    have = p.returncode == 0
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPTS / "make_public_mirror.ps1")],
        capture_output=True, text=True,
    )
    assert r.returncode == (0 if have else 3)
    if have:
        assert "DRY RUN" in r.stdout


def test_docs_exist_and_carry_pending_markers():
    sub_path = REPO / "docs" / "operations" / "SUBMISSION.md"
    if not sub_path.exists():
        sub_path = REPO / "docs" / "SUBMISSION.md"
    sub = sub_path.read_text(encoding="utf-8")
    assert "[PENDING]" in sub and "Push the Frontier" in sub and "Indie" in sub
    ops_path = REPO / "docs" / "operations" / "OPS_RUNBOOK.md"
    if not ops_path.exists():
        ops_path = REPO / "docs" / "OPS_RUNBOOK.md"
    ops = ops_path.read_text(encoding="utf-8")
    assert "Nov 9" in ops and "CACHED" in ops


def test_no_todo_or_notimplemented_in_owned_scripts():
    pat = re.compile(r"(?<!\w)TODO|NotImplemented")
    for name in SCRIPT_FILES:
        t = (SCRIPTS / name).read_text(encoding="utf-8")
        assert not pat.search(t), name
