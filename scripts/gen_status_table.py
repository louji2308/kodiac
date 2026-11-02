"""Regenerate the README shipped-status block from ``docs/features.yaml``.

``docs/features.yaml`` is the ground truth for what shipped (AGENTS.md 7.1 DOC-RECONCILE). This
script renders the human-readable view of it between two markers in ``README.md`` so the two can
never disagree; ``tests/unit/infra/test_infra.py`` fails if the committed block is stale.

Usage::

    python scripts/gen_status_table.py            # rewrite README.md
    python scripts/gen_status_table.py --check     # exit 1 if README.md is stale
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import yaml

BEGIN = "<!-- BEGIN GENERATED STATUS (scripts/gen_status_table.py) -->"
END = "<!-- END GENERATED STATUS -->"

STATUS_ORDER = ("done", "partial", "planned", "blocked", "in_progress")
STATUS_TITLE = {
    "done": "Built and tested",
    "partial": "Built or partly built, with an evidence caveat",
    "planned": "Not built",
    "blocked": "Blocked",
    "in_progress": "In progress",
}
EVIDENCE_LABEL = {
    "unit_tests": "deterministic tests",
    "fixture_replay": "recorded fixtures only",
    "synthetic": "synthetic data only",
    "mock_sim": "mock simulator only",
    "live": "live model run",
    None: "no evidence",
}


def _rows(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"{path}: root must be a list of feature rows")
    return data


def _bullet(row: dict) -> str:
    name = row["name"]
    status = row.get("status")
    evidence = row.get("evidence_type")
    note = (row.get("note") or "").strip().replace("\n", " ")
    head = f"- `{row['id']}` **{name}** ({row.get('tier', '?')}) - {EVIDENCE_LABEL.get(evidence, evidence)}"
    if status == "done" or not note:
        return head
    # Wrap the honesty note so the raw markdown stays readable; every word is kept.
    body = f"{head}. {note}"
    wrapped = textwrap.wrap(
        body, width=100, subsequent_indent="  ", break_long_words=False, break_on_hyphens=False
    )
    return "\n".join(wrapped)


def render(rows: list[dict]) -> str:
    counts = {s: sum(1 for r in rows if r.get("status") == s) for s in STATUS_ORDER}
    live = [r for r in rows if r.get("evidence_type") == "live"]
    out: list[str] = [BEGIN, ""]
    out.append("## Status (generated from `docs/features.yaml`)")
    out.append("")
    summary = " · ".join(f"**{counts[s]} {s}**" for s in STATUS_ORDER if counts[s])
    out.append(f"{len(rows)} tracked features: {summary}.")
    out.append("")
    if not live:
        out.append(
            "> **Nothing is `live`.** No Meta Model API key, Modal token or HF gated-weight access was used, "
            "so every row below is backed by deterministic tests, recorded fixtures, synthetic data or the "
            "mock simulator. The registry's `evidence_type` column, not this list, is the authority."
        )
        out.append("")
    for status in STATUS_ORDER:
        group = [r for r in rows if r.get("status") == status]
        if not group:
            continue
        out.append(f"### {STATUS_TITLE[status]} ({len(group)})")
        out.append("")
        out.extend(_bullet(r) for r in group)
        out.append("")
    out.append(END)
    return "\n".join(out)


def _replace(text: str, block: str) -> str:
    start = text.find(BEGIN)
    end = text.find(END)
    if start == -1 or end == -1 or end < start:
        raise SystemExit(f"README.md is missing the {BEGIN} / {END} markers")
    return text[:start] + block + text[end + len(END) :]


def _write(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically, surviving the Windows sharing quirks of this repo.

    A direct ``write_text`` and a rename both fail with EACCES/EPERM on some Windows setups (an
    antivirus or editor can hold the file with a restrictive share mode), while a plain byte copy
    through ``cmd /c copy`` succeeds. Try the cheap path first, then degrade once.
    """
    tmp_dir = Path(".cache")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / f"{path.name}.gen.tmp"
    tmp.write_text(text, encoding="utf-8", newline="\n")
    try:
        os.replace(tmp, path)
        return
    except OSError:
        if os.name != "nt":
            raise
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["cmd", "/c", "copy", "/y", str(tmp), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"could not write {path}: {result.stderr or result.stdout}")
    tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    parser.add_argument("--features", type=Path, default=Path("docs/features.yaml"))
    parser.add_argument("--check", action="store_true", help="exit 1 if README.md is stale")
    parser.add_argument("--stdout", action="store_true", help="print the generated block instead of writing")
    args = parser.parse_args(argv)

    current = args.readme.read_text(encoding="utf-8")
    block = render(_rows(args.features))
    if args.stdout:
        print(block)
        return 0
    updated = _replace(current, block)

    if args.check:
        if updated != current:
            print("README.md status block is stale; run: python scripts/gen_status_table.py", file=sys.stderr)
            return 1
        print("README.md status block is in sync with docs/features.yaml")
        return 0

    if updated == current:
        print("README.md status block already in sync")
        return 0
    _write(args.readme, updated)
    print(f"updated {args.readme}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
