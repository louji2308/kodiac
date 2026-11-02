"""Lint a repository (normally the filtered public mirror) for kill-shot content.

Usage: python scripts/lint_public.py [--repo PATH] [--history] [--lineage-file FILE] [--json]

Checks: forbidden (strategy/private) paths present, secrets in files, files > 20 MB,
lineage terms (from docs/private/lineage_terms.txt; UNVERIFIABLE if absent, never invented).
With --history: secrets, forbidden paths and lineage terms across every commit patch,
and lineage terms in commit messages.

Exit codes: 0 clean, 1 findings, 2 only UNVERIFIABLE items.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

MAX_BYTES = 20 * 1024 * 1024
FORBIDDEN_PUBLIC = ["HACKATHON.md", "docs/research/", "docs/private/", ".agents/", "HUMAN_TODO.md"]
LINEAGE_REL = "docs/private/lineage_terms.txt"

ASSIGN_RE = re.compile(
    r"""(?i)\b(?:api[_-]?key|secret|token|passw(?:or)?d|auth)\w*["']?\s*[:=]\s*["']?([A-Za-z0-9_\-+/]{20,})"""
)
PREFIX_RES = [
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{30,}"),
    re.compile(r"\bhf_[A-Za-z0-9]{30,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


def git(repo: Path, *args: str) -> str:
    p = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, check=False
    )
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.decode('utf-8', 'replace').strip()}")
    return p.stdout.decode("utf-8", "replace")


def _entropy(s: str) -> float:
    return -sum(s.count(c) / len(s) * math.log2(s.count(c) / len(s)) for c in set(s))


def find_secrets(text: str) -> list[str]:
    """Return redacted descriptions of secret-looking tokens in text."""
    hits = []
    for rx in PREFIX_RES:
        for m in rx.finditer(text):
            hits.append(f"{rx.pattern[:12]}... pattern ({m.group(0)[:4]}***)")
    for m in ASSIGN_RE.finditer(text):
        val = m.group(1)
        if (
            any(c.isdigit() for c in val)
            and any(c.isalpha() for c in val)
            and _entropy(val) >= 3.5
            and not val.lower().startswith(("http", "os.environ"))
        ):
            hits.append(f"credential-like assignment value ({val[:4]}***, len {len(val)})")
    return hits


def load_lineage(repo: Path, lineage_file: Path | None = None) -> list[str] | None:
    p = lineage_file or (repo / LINEAGE_REL)
    if not p.exists():
        return None
    return [t.strip() for t in p.read_text(encoding="utf-8").splitlines() if t.strip() and not t.startswith("#")]


def _finding(sev: str, check: str, message: str, where: str = "") -> dict:
    return {"severity": sev, "check": check, "message": message, "where": where}


def _is_forbidden(path: str) -> bool:
    p = path.replace("\\", "/")
    return any(p == f or (f.endswith("/") and p.startswith(f)) for f in FORBIDDEN_PUBLIC)


def tracked_files(repo: Path) -> list[str]:
    return [f for f in git(repo, "ls-files", "-z").split("\0") if f]


def scan_forbidden_paths(repo: Path, history: bool) -> list[dict]:
    out = []
    names = set(tracked_files(repo))
    if history:
        for ln in git(repo, "log", "--all", "--name-only", "--format=").splitlines():
            if ln.strip():
                names.add(ln.strip())
    for n in sorted(names):
        if _is_forbidden(n):
            out.append(_finding("S0", "forbidden-path", "strategy/private path present" + (" (in history)" if history else ""), n))
    return out


def scan_large_files(repo: Path) -> list[dict]:
    out = []
    for f in tracked_files(repo):
        p = repo / f
        if p.is_file() and p.stat().st_size > MAX_BYTES:
            out.append(_finding("S1", "large-file", f"{p.stat().st_size / 1e6:.1f} MB tracked (limit 20 MB)", f))
    return out


def _read_text(p: Path) -> str | None:
    try:
        if p.stat().st_size > 5_000_000:
            return None
        b = p.read_bytes()
    except OSError:
        return None
    if b"\0" in b[:8192]:
        return None
    return b.decode("utf-8", "replace")


def scan_worktree(repo: Path, lineage: list[str] | None) -> list[dict]:
    out = []
    for f in tracked_files(repo):
        text = _read_text(repo / f)
        if text is None:
            continue
        for h in find_secrets(text):
            out.append(_finding("S0", "secret", h, f))
        for t in lineage or []:
            if re.search(re.escape(t), text, re.I):
                out.append(_finding("S0", "lineage", "lineage term present in file", f))
                break
    return out


def scan_history(repo: Path, lineage: list[str] | None) -> list[dict]:
    out = []
    seen: set[tuple] = set()
    commit = fname = ""
    log = git(repo, "log", "--all", "-p", "--no-color", "--format=@@COMMIT %H")
    for line in log.splitlines():
        if line.startswith("@@COMMIT "):
            commit, fname = line[9:19], ""
        elif line.startswith("+++ b/"):
            fname = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            for h in find_secrets(line):
                key = ("secret", commit, fname, h)
                if key not in seen:
                    seen.add(key)
                    out.append(_finding("S0", "secret-history", h, f"{fname}@{commit}"))
            for t in lineage or []:
                if re.search(re.escape(t), line, re.I):
                    key = ("lin", commit, fname)
                    if key not in seen:
                        seen.add(key)
                        out.append(_finding("S0", "lineage-history", "lineage term in commit patch", f"{fname}@{commit}"))
    for chunk in git(repo, "log", "--all", "--format=@@COMMIT %H%n%B").split("@@COMMIT ")[1:]:
        sha, _, body = chunk.partition("\n")
        for t in lineage or []:
            if re.search(re.escape(t), body, re.I):
                out.append(_finding("S0", "lineage-message", "lineage term in commit message", sha[:10]))
                break
        for h in find_secrets(body):
            out.append(_finding("S0", "secret-message", h, sha[:10]))
    return out


def lint_repo(repo: Path, history: bool = False, lineage_file: Path | None = None) -> list[dict]:
    lineage = load_lineage(repo, lineage_file)
    findings: list[dict] = []
    if lineage is None:
        findings.append(_finding("UNVERIFIABLE", "lineage", f"UNVERIFIABLE: {LINEAGE_REL} missing (no list invented)"))
    findings += scan_forbidden_paths(repo, history)
    findings += scan_large_files(repo)
    findings += scan_worktree(repo, lineage)
    if history:
        findings += scan_history(repo, lineage)
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--history", action="store_true")
    ap.add_argument("--lineage-file", type=Path, default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        findings = lint_repo(a.repo.resolve(), a.history, a.lineage_file)
    except RuntimeError as e:
        print(f"LINT ERROR: {e}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps({"repo": str(a.repo), "history": a.history, "findings": findings}, indent=2))
    else:
        for f in findings:
            print(f"[{f['severity']}] {f['check']}: {f['message']} {f['where']}".rstrip())
        print(f"{len(findings)} finding(s)")
    real = [f for f in findings if f["severity"] != "UNVERIFIABLE"]
    if real:
        return 1
    return 2 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
