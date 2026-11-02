"""Verify pre-registration hygiene in git (IMPLEMENTATION_PLAN P08.S01, ADR-0006, Invariant I8).

Checks, each printed with its evidence:
1. the tag (default ``prereg-v1``) exists;
2. ``experiments/PREREGISTRATION.md`` and ``experiments/pool_config.yaml`` are unchanged since the tag
   (in HEAD and in the working tree): metrics were not re-defined after registration;
3. the tagged commit is a strict ancestor of, and not later than, EVERY commit touching
   ``experiments/labels/**/*.parquet`` or ``experiments/results/**`` (the first one is shown).

Transparency lines (never change the result): other ``experiments/labels`` files committed outside the
tag's descendants, and local label parquet files git cannot date (``*.parquet`` is gitignored).

Prints ``RESULT: PASS`` / ``RESULT: FAIL``; exits 1 on FAIL.
Usage: ``python scripts/check_prereg.py [--repo PATH] [--tag prereg-v1]``
"""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

PREREG_FILES = ("experiments/PREREGISTRATION.md", "experiments/pool_config.yaml")
GUARDED_PATHSPECS = (":(glob)experiments/labels/**/*.parquet", ":(glob)experiments/results/**")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", check=False
    )


def _date(repo: Path, rev: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(_git(repo, "show", "-s", "--format=%cI", rev).stdout.strip())


def _is_ancestor(repo: Path, older: str, newer: str) -> bool:
    return _git(repo, "merge-base", "--is-ancestor", older, newer).returncode == 0


def _touched(repo: Path, sha: str, *pathspecs: str) -> list[str]:
    out = _git(repo, "show", "--name-only", "--format=", sha, "--", *pathspecs).stdout
    return [line for line in out.splitlines() if line.strip()]


def check(repo: Path, tag: str) -> tuple[bool, list[str]]:
    lines: list[str] = []
    ok = True
    res = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}")
    if res.returncode != 0 or not res.stdout.strip():
        return False, [f"[FAIL] tag {tag} not found (git rev-parse refs/tags/{tag})"]
    tag_sha = res.stdout.strip()
    tag_date = _date(repo, tag_sha)
    lines.append(f"[PASS] tag {tag} -> {tag_sha[:12]} (committed {tag_date.isoformat()})")

    prereg_doc = repo / PREREG_FILES[0]
    if prereg_doc.is_file():
        m = re.search(r"Git Tag:\*\*\s*`([^`]+)`", prereg_doc.read_text(encoding="utf-8"))
        if m and m.group(1) != tag:
            lines.append(f"[INFO] {PREREG_FILES[0]} declares tag {m.group(1)}; checking {tag}")

    for path in PREREG_FILES:
        if _git(repo, "cat-file", "-e", f"{tag_sha}:{path}").returncode != 0:
            ok = False
            lines.append(f"[FAIL] {path} is not part of {tag}")
            continue
        head_changed = _git(repo, "diff", "--quiet", tag_sha, "HEAD", "--", path).returncode != 0
        tree_changed = _git(repo, "diff", "--quiet", tag_sha, "--", path).returncode != 0
        if head_changed or tree_changed:
            ok = False
            where = "HEAD" if head_changed else "working tree"
            lines.append(f"[FAIL] {path} changed since {tag} (in {where}): git diff {tag} -- {path}")
        else:
            lines.append(f"[PASS] {path} unchanged since {tag} (git diff --quiet {tag} HEAD)")

    log = _git(repo, "log", "--reverse", "--format=%H", "--", *GUARDED_PATHSPECS).stdout.split()
    if not log:
        lines.append(
            "[PASS] no commit touches experiments/labels/**/*.parquet or experiments/results/** yet"
        )
    else:
        bad = [
            c
            for c in log
            if c == tag_sha or not _is_ancestor(repo, tag_sha, c) or _date(repo, c) < tag_date
        ]
        first = log[0]
        files = ", ".join(_touched(repo, first, *GUARDED_PATHSPECS)[:4])
        if bad:
            ok = False
            for c in bad[:5]:
                lines.append(
                    f"[FAIL] {c[:12]} ({_date(repo, c).isoformat()}) touches guarded paths "
                    f"[{', '.join(_touched(repo, c, *GUARDED_PATHSPECS)[:4])}] but does not descend "
                    f"from / follow {tag}"
                )
        else:
            lines.append(
                f"[PASS] {tag} precedes all {len(log)} label/result commit(s); first: {first[:12]} "
                f"({_date(repo, first).isoformat()}) [{files}]"
            )

    other = _git(repo, "log", "--format=%H", "--", "experiments/labels").stdout.split()
    for c in other:
        if not _is_ancestor(repo, tag_sha, c):
            names = ", ".join(_touched(repo, c, "experiments/labels")[:4])
            lines.append(
                f"[WARN] {c[:12]} committed experiments/labels files before {tag}: [{names}] "
                "(not judge-label parquet; outside the guarded scope, listed for transparency)"
            )
    labels_dir = repo / "experiments" / "labels"
    local = sorted(p.name for p in labels_dir.glob("**/*.parquet")) if labels_dir.is_dir() else []
    if local:
        lines.append(
            f"[INFO] local, gitignored label parquet files git cannot date: {local[:6]} "
            "(commit a hash manifest of them to bring them under this check)"
        )
    else:
        lines.append("[INFO] no local label parquet files in experiments/labels/")
    return ok, lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--tag", default="prereg-v1")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    ok, lines = check(repo, args.tag)
    print(f"check_prereg: repo={repo} tag={args.tag}")
    for line in lines:
        print(line)
    print(f"RESULT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
