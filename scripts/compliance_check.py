"""Kodiac compliance sweep for the working repo (HACKATHON.md section 2 disqualifiers).

Usage: python scripts/compliance_check.py [--repo PATH] [--json-out FILE] [--json]

Exit code is non-zero on ANY finding, including OPEN (human action needed) and
UNVERIFIABLE (check could not run). Nothing here edits files or touches a remote.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lint_public as lp  # noqa: E402

WINDOW_START = datetime(2026, 10, 26, tzinfo=timezone.utc)

# (label, regexes that must match a row of ATTRIBUTIONS.md)
REQUIRED_ATTRIBUTIONS = [
    ("SAM license", [r"\bSAM\b"]),
    ("DROID (CC-BY)", [r"DROID"]),
    ("LeRobot (Apache-2.0)", [r"LeRobot"]),
    ("ManiSkill (Apache-2.0)", [r"ManiSkill"]),
    ("Robometer / TOPReward", [r"Robometer", r"TOPReward"]),
    ("cookbook (MIT)", [r"cookbook"]),
]


def f(sev: str, check: str, message: str, where: str = "") -> dict:
    return {"severity": sev, "check": check, "message": message, "where": where}


def check_first_commit(repo: Path) -> list[dict]:
    try:
        dates = lp.git(repo, "log", "--all", "--format=%aI").split()
    except RuntimeError as e:
        return [f("UNVERIFIABLE", "first-commit", str(e))]
    if not dates:
        return [f("S0", "first-commit", "no commits")]
    first = min(datetime.fromisoformat(d) for d in dates)
    if first < WINDOW_START:
        return [f("S0", "first-commit", f"earliest commit {first.isoformat()} predates 2026-10-26 (R1 pre-event code)")]
    return []


def check_build_log(repo: Path) -> list[dict]:
    p = repo / "BUILD_LOG.md"
    if not p.exists():
        return [f("S0", "build-log", "BUILD_LOG.md missing")]
    n = len(re.findall(r"^#{2,4}\s+\d{4}-\d{2}-\d{2}", p.read_text(encoding="utf-8"), re.M))
    if n < 1:
        return [f("S1", "build-log", "no dated entries in BUILD_LOG.md")]
    return []


def check_attributions(repo: Path) -> list[dict]:
    p = repo / "ATTRIBUTIONS.md"
    if not p.exists():
        return [f("S1", "attributions", "ATTRIBUTIONS.md missing")]
    rows = [r for r in p.read_text(encoding="utf-8").splitlines() if r.startswith("|")]
    out = []
    for label, pats in REQUIRED_ATTRIBUTIONS:
        if not any(re.search(pt, r, re.I) for r in rows for pt in pats):
            out.append(f("OPEN", "attributions", f"no ATTRIBUTIONS.md row for {label}; human must confirm the licence from the upstream source (not guessed here)"))
    return out


def check_license(repo: Path) -> list[dict]:
    return [] if any((repo / n).is_file() for n in ("LICENSE", "LICENSE.md", "LICENSE.txt")) else [f("S1", "license", "LICENSE file missing")]


def check_private_untracked(repo: Path) -> list[dict]:
    tracked = [t for t in lp.tracked_files(repo) if t.replace("\\", "/").startswith("docs/private/")]
    return [f("S0", "private-tracked", "docs/private is tracked by git", t) for t in tracked]


def _file_of(where: str) -> str:
    return where.split("@")[0]


def check_content(repo: Path, lineage: list[str] | None) -> list[dict]:
    """Secrets / lineage in tracked files and full history. Paths excluded from the public
    mirror (strategy docs) are not flagged for lineage wording, but secrets are always flagged."""
    out = []
    for x in lp.scan_worktree(repo, lineage) + lp.scan_history(repo, lineage):
        if x["check"].startswith("lineage") and x["check"] != "lineage-message" and lp._is_forbidden(_file_of(x["where"])):
            continue
        out.append(x)
    return out


def run_checks(repo: Path) -> dict:
    lineage = lp.load_lineage(repo)
    findings: list[dict] = []
    if lineage is None:
        findings.append(f("UNVERIFIABLE", "lineage", f"UNVERIFIABLE: {lp.LINEAGE_REL} missing (no list invented; lineage scan NOT performed)"))
    findings += check_first_commit(repo)
    findings += check_build_log(repo)
    findings += check_attributions(repo)
    findings += check_license(repo)
    findings += check_private_untracked(repo)
    findings += lp.scan_large_files(repo)
    findings += check_content(repo, lineage)
    counts: dict[str, int] = {}
    for x in findings:
        counts[x["severity"]] = counts.get(x["severity"], 0) + 1
    return {"repo": str(repo), "counts": counts, "findings": findings, "ok": not findings}


def render(res: dict) -> str:
    lines = [f"Kodiac compliance check: {res['repo']}"]
    for x in res["findings"]:
        lines.append(f"[{x['severity']}] {x['check']}: {x['message']} {x['where']}".rstrip())
    lines.append(f"counts: {json.dumps(res['counts'], sort_keys=True)}  ok={res['ok']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--json-out", type=Path, default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    res = run_checks(a.repo.resolve())
    if a.json_out:
        a.json_out.parent.mkdir(parents=True, exist_ok=True)
        a.json_out.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2) if a.json else render(res))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
