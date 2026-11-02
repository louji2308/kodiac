"""Failure-Norm Digest (F50): deterministic numbers, optional Muse Wonder narration.

All numbers are computed here from *human-verified* flags only (histogram + Wilson interval).
The narration layer may phrase them but may not introduce any number that is not in the digest:
every numeric token is validated and the deterministic template is used on any violation.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Callable
from typing import Any, Literal

import pandas as pd

from Kodiac_robotics.audit.rows import DEMO_BANNER, clean, is_demo_frame

Z_95 = 1.959963984540054
_DEFAULT_SAMPLING = (
    "Episodes exactly as supplied to `audit run` (filtered by dataset, camera and task regex, "
    "ordered by episode index, truncated to the limit); no random sampling is claimed."
)
_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?![\w])")


def wilson_interval(k: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Two-sided Wilson score interval for k successes in n trials."""
    if n <= 0:
        raise ValueError("n must be positive")
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _r(x: float) -> float:
    return round(float(x), 6)


def failure_norm_digest(df: pd.DataFrame, sampling: str | None = None) -> dict[str, Any]:
    """Deterministic digest. Flags without a human ``confirmed`` decision never count."""
    n_total = len(df)
    errored = df["error"].map(lambda v: clean(v) is not None) if "error" in df else None
    checked = df[~errored] if errored is not None else df
    n_errors = n_total - len(checked)
    n_checked = len(checked)

    verdicts = checked["verdict"].astype(str) if n_checked else pd.Series([], dtype=str)
    fails = checked[verdicts == "FAIL"]
    hv = fails["human_verified"].map(clean) if len(fails) else pd.Series([], dtype=object)
    verified = fails[hv == True]  # noqa: E712 - object column holding True/False/None
    n_verified = len(verified)
    n_rejected = int((hv == False).sum()) if len(hv) else 0  # noqa: E712
    n_flagged = len(fails)

    x_lower: float | None = None
    fraction: float | None = None
    if n_checked > 0 and n_verified > 0:
        x_lower = _r(wilson_interval(n_verified, n_checked)[0])
        fraction = _r(n_verified / n_checked)

    steps = Counter(str(clean(s) or "unknown") for s in verified["step"]) if n_verified else {}
    hist_step: list[dict[str, Any]] = []
    for step, count in sorted(steps.items(), key=lambda kv: (-kv[1], kv[0])):
        lo, hi = wilson_interval(count, n_verified)
        hist_step.append(
            {
                "step": step,
                "count": count,
                "share": _r(count / n_verified),
                "share_ci_low": _r(lo),
                "share_ci_high": _r(hi),
            }
        )
    pairs = (
        Counter(
            (str(clean(s) or "unknown"), str(clean(p) or "unknown"))
            for s, p in zip(verified["step"], verified["predicate"], strict=True)
        )
        if n_verified
        else {}
    )
    hist_pred = [
        {"step": s, "predicate": p, "count": c}
        for (s, p), c in sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    demo = is_demo_frame(df)
    return {
        "schema": "kodiac.audit.digest/1",
        "is_demonstration_data": demo,
        "demonstration_banner": DEMO_BANNER if demo else None,
        "datasets": sorted({str(d) for d in df["dataset"]}) if n_total else [],
        "cameras": sorted({str(c) for c in df["camera"]}) if n_total else [],
        "N": n_checked,
        "n_errors": n_errors,
        "n_pass": int((verdicts == "PASS").sum()) if n_checked else 0,
        "n_cant_tell": int((verdicts == "CANT_TELL").sum()) if n_checked else 0,
        "n_flagged": n_flagged,
        "n_verified": n_verified,
        "n_rejected": n_rejected,
        "n_unreviewed": n_flagged - n_verified - n_rejected,
        "verified_fraction": fraction,
        "X_lower_bound": x_lower,
        "ci_level": 0.95,
        "ci_method": "wilson",
        "verified_flags_only": True,
        "top_step": hist_step[0]["step"] if hist_step else None,
        "histogram_by_step": hist_step,
        "histogram_by_step_predicate": hist_pred,
        "sampling": sampling or _DEFAULT_SAMPLING,
    }


def digest_json(digest: dict[str, Any]) -> str:
    """Canonical JSON (sorted keys, fixed separators): byte-identical for equal digests."""
    return json.dumps(digest, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _numeric_leaves(obj: Any) -> list[float]:
    out: list[float] = []
    if isinstance(obj, bool) or obj is None:
        return out
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, str):
        out.extend(float(t.replace(",", "")) for t in _NUMBER.findall(obj) if _parsable(t))
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_numeric_leaves(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_numeric_leaves(v))
    return out


def _parsable(token: str) -> bool:
    try:
        float(token.replace(",", ""))
    except ValueError:
        return False
    return True


def validate_narration_numbers(text: str, digest: dict[str, Any]) -> list[str]:
    """Return numeric tokens in ``text`` that are not derivable from ``digest``.

    A token is allowed when it equals a digest number (or that number as a percentage) rounded
    to the number of decimals the token is written with.
    """
    allowed: list[float] = []
    for v in _numeric_leaves(digest):
        allowed.extend((v, v * 100.0))
    bad: list[str] = []
    for token in _NUMBER.findall(text):
        if not _parsable(token):
            bad.append(token)
            continue
        value = float(token.replace(",", ""))
        decimals = len(token.split(".")[1]) if "." in token else 0
        if not any(abs(round(a, decimals) - value) < 1e-9 for a in allowed):
            bad.append(token)
    return bad


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _template_narration(digest: dict[str, Any]) -> str:
    parts: list[str] = []
    if digest["is_demonstration_data"]:
        parts.append(f"{DEMO_BANNER}.")
    n, flagged, verified = digest["N"], digest["n_flagged"], digest["n_verified"]
    if verified == 0 or digest["X_lower_bound"] is None:
        parts.append(
            f"{n} episodes were checked and {flagged} candidate flags were raised, but none are "
            "hand-verified yet, so no failure rate is claimed."
        )
        return " ".join(parts)
    parts.append(
        f"{n} episodes were checked; {verified} flagged episodes were hand-verified as failing "
        f"the physics test, so at least {_pct(digest['X_lower_bound'])} of the checked episodes "
        "failed (95% Wilson lower bound over verified flags only)."
    )
    top = digest["histogram_by_step"][0]
    parts.append(
        f"Most verified failures happen at step '{top['step']}': {_pct(top['share'])} of "
        f"verified flags [{_pct(top['share_ci_low'])} to {_pct(top['share_ci_high'])}]."
    )
    return " ".join(parts)


def narrate(
    digest: dict[str, Any], wonder: Callable[[str], str] | None
) -> tuple[str, Literal["muse-wonder", "template"]]:
    """Narrate the digest. Wonder output is used only if every number is in the digest."""
    template = _template_narration(digest)
    if wonder is None:
        return template, "template"
    prompt = (
        "Narrate this failure-norm digest for robot-dataset maintainers in 2-3 plain sentences. "
        "Use ONLY numbers that appear in the JSON; do not introduce, round differently, or "
        "extrapolate any figure. Mention only hand-verified flags.\n\n" + digest_json(digest)
    )
    try:
        text = wonder(prompt)
    except Exception:  # noqa: BLE001 - any Wonder failure falls back to the template
        return template, "template"
    if not isinstance(text, str) or not text.strip():
        return template, "template"
    text = text.strip()
    if validate_narration_numbers(text, digest):
        return template, "template"
    if digest["is_demonstration_data"] and "demonstration data" not in text.lower():
        text = f"{DEMO_BANNER}. {text}"
    return text, "muse-wonder"


def render_report(
    digest: dict[str, Any], narration: str, source: Literal["muse-wonder", "template"]
) -> str:
    """Markdown report draft (never posted by this package; see audit.publish)."""
    lines = ["# Kodiac dataset audit report", ""]
    if digest["is_demonstration_data"]:
        lines += [f"> **{DEMO_BANNER}**", ""]
    lines += [narration, "", f"_Narration source: {source}. Numbers are computed deterministically._", ""]
    lines += [
        "| episodes checked | candidate flags | hand-verified | rejected | not yet reviewed |",
        "|---|---|---|---|---|",
        f"| {digest['N']} | {digest['n_flagged']} | {digest['n_verified']} | "
        f"{digest['n_rejected']} | {digest['n_unreviewed']} |",
        "",
        f"Sampling: {digest['sampling']}",
        "",
    ]
    return "\n".join(lines)


__all__ = [
    "digest_json",
    "failure_norm_digest",
    "narrate",
    "render_report",
    "validate_narration_numbers",
    "wilson_interval",
]
