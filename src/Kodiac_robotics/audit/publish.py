"""Guarded publish step (F52, KD-19, AGENTS.md section 12.3).

This module performs NO network action, ever: it imports nothing capable of one. Posting a report
(HF discussion / PR) is a manual step a human takes after this function has allowed it and
returned the exact text. It refuses unless every guard below passes.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from Kodiac_robotics.audit.rows import DEMO_BANNER

APPROVAL_DIR = Path(".Kodiac") / "human_approval"
_TICKET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class PublishRefused(RuntimeError):
    """Raised whenever a publish precondition is not met."""


def _in_ci() -> bool:
    return os.environ.get("CI", "").strip().lower() not in ("", "0", "false", "no")


def publish(
    report_md: Path,
    *,
    approval_ticket: str | None,
    dry_run: bool = True,
    approval_dir: Path = APPROVAL_DIR,
) -> str:
    """Return the text a human would post, or raise :class:`PublishRefused`.

    Allowed only when ALL hold: ``approval_ticket`` is a well-formed non-empty string,
    ``dry_run`` is False, the file ``<approval_dir>/<ticket>`` exists (a human created it),
    we are not running in CI, the report exists, is non-empty, and is not demonstration data.
    """
    if approval_ticket is None or not str(approval_ticket).strip():
        raise PublishRefused("no approval ticket: publishing requires recorded human approval")
    ticket = str(approval_ticket).strip()
    if not _TICKET.match(ticket) or ".." in ticket:
        raise PublishRefused("malformed approval ticket (letters, digits, '.', '_', '-' only)")
    if dry_run:
        raise PublishRefused("dry_run is True: pass dry_run=False only after human approval")
    if _in_ci():
        raise PublishRefused("refusing to publish in CI (KD-19)")
    approval_file = Path(approval_dir) / ticket
    if not approval_file.is_file():
        raise PublishRefused(f"approval file not found: {approval_file.as_posix()}")
    report = Path(report_md)
    if not report.is_file():
        raise PublishRefused(f"report not found: {report.as_posix()}")
    text = report.read_text(encoding="utf-8")
    if not text.strip():
        raise PublishRefused("report is empty")
    if DEMO_BANNER.lower() in text.lower() or "demonstration data" in text.lower():
        raise PublishRefused("report is marked DEMONSTRATION DATA and must not be published")
    return text


__all__ = ["APPROVAL_DIR", "PublishRefused", "publish"]
