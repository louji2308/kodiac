"""Human-verification queue for audit flags (F49, AGENTS.md section 12.3 spirit).

Only FAIL rows become candidates. ``human_verified`` is set exclusively from a reviewer decision
file (jsonl) via :func:`apply_reviews`; nothing else in the audit package ever writes it.
The review page is static HTML with no network access: it records decisions locally and offers
them as a downloadable ``reviews.jsonl``.
"""

from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from Kodiac_robotics.audit.rows import DEMO_BANNER, clean, is_demo_frame, load_verdicts

DECISIONS = ("confirmed", "rejected", "unsure")
_KEY = ("dataset", "episode_index", "camera")


def _fmt(value: Any, digits: int = 3) -> str:
    value = clean(value)
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _evidence_href(evidence_uri: Any, base_dir: Path, out_html: Path) -> str | None:
    uri = clean(evidence_uri)
    if not uri:
        return None
    target = base_dir / str(uri)
    try:
        return Path(os.path.relpath(target, out_html.parent)).as_posix()
    except ValueError:
        return target.resolve().as_uri()


def _candidates(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["verdict"] == "FAIL"].reset_index(drop=True)


def build_candidates_html(verdicts_parquet: Path, out_html: Path) -> None:
    """Write a static review page listing only FAIL candidates (deterministic output)."""
    verdicts_parquet = Path(verdicts_parquet)
    out_html = Path(out_html)
    df = load_verdicts(verdicts_parquet)
    cands = _candidates(df)
    demo = is_demo_frame(df)

    items: list[dict[str, Any]] = []
    rows_html: list[str] = []
    for i, rec in enumerate(cands.to_dict("records")):
        key = {
            "dataset": str(rec["dataset"]),
            "episode_index": int(rec["episode_index"]),
            "camera": str(rec["camera"]),
        }
        items.append(key)
        margin, sigma = clean(rec["margin"]), clean(rec["sigma"])
        ratio = (
            f"{abs(float(margin)) / float(sigma):.2f}"
            if margin is not None and sigma not in (None, 0)
            else "n/a"
        )
        href = _evidence_href(rec["evidence_uri"], verdicts_parquet.parent, out_html)
        evidence = (
            f'<a href="{html.escape(href, quote=True)}"><img src="{html.escape(href, quote=True)}"'
            f' alt="evidence card" width="320"></a>'
            if href
            else "no evidence image"
        )
        rows_html.append(
            f'<tr data-i="{i}"><td>{html.escape(key["dataset"])}</td>'
            f"<td>{key['episode_index']}</td><td>{html.escape(key['camera'])}</td>"
            f"<td>{html.escape(str(clean(rec['task']) or ''))}</td>"
            f"<td>{html.escape(_fmt(rec['step']))}</td>"
            f"<td>{html.escape(_fmt(rec['predicate']))}</td>"
            f"<td>{_fmt(rec['t_star_s'])}</td><td>{_fmt(margin)}</td><td>{_fmt(sigma)}</td>"
            f"<td>{ratio}</td><td>{evidence}</td>"
            f"<td>{html.escape(str(clean(rec['notes']) or ''))}</td>"
            f'<td><label><input type="radio" name="d{i}" value="confirmed"> confirmed</label><br>'
            f'<label><input type="radio" name="d{i}" value="rejected"> rejected</label><br>'
            f'<label><input type="radio" name="d{i}" value="unsure"> unsure</label><br>'
            f'<input type="text" class="note" placeholder="note" aria-label="note"></td></tr>'
        )

    banner = f'<div class="banner">{html.escape(DEMO_BANNER)}</div>' if demo else ""
    payload = json.dumps(items, sort_keys=True).replace("</", "<\\/")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Kodiac audit: candidate flags for human review</title>
<style>
body{{font-family:system-ui,sans-serif;margin:1.5rem}}
.banner{{background:#7a1f1f;color:#fff;padding:.6rem 1rem;font-weight:700;margin-bottom:1rem}}
table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #bbb;padding:.35rem;vertical-align:top;font-size:.85rem}}
</style></head><body>
{banner}
<h1>Candidate flags: {len(items)} FAIL episode(s) awaiting human review</h1>
<p>Only a decision you record here can mark a flag <code>human_verified</code>. Undecided rows
stay unverified and never appear in any summary. Decisions are kept in this page only; click
&ldquo;Download reviews.jsonl&rdquo; and pass the file to <code>apply_reviews</code>.</p>
<p><label>Reviewer name (required): <input type="text" id="reviewer"></label>
<button type="button" id="dl">Download reviews.jsonl</button> <span id="msg"></span></p>
<table><thead><tr><th>dataset</th><th>episode</th><th>camera</th><th>task</th><th>step</th>
<th>predicate</th><th>t* (s)</th><th>margin</th><th>&sigma;</th><th>|margin|/&sigma;</th>
<th>evidence</th><th>notes</th><th>decision</th></tr></thead>
<tbody>
{chr(10).join(rows_html)}
</tbody></table>
<script id="items" type="application/json">{payload}</script>
<script>
document.getElementById("dl").addEventListener("click", function () {{
  var items = JSON.parse(document.getElementById("items").textContent);
  var reviewer = document.getElementById("reviewer").value.trim();
  var msg = document.getElementById("msg");
  if (!reviewer) {{ msg.textContent = "Enter a reviewer name first."; return; }}
  var lines = [];
  document.querySelectorAll("tbody tr").forEach(function (tr) {{
    var i = parseInt(tr.getAttribute("data-i"), 10);
    var picked = tr.querySelector("input[type=radio]:checked");
    if (!picked) {{ return; }}
    var rec = Object.assign({{}}, items[i], {{
      decision: picked.value, reviewer: reviewer,
      note: tr.querySelector(".note").value, decided_at: new Date().toISOString()
    }});
    lines.push(JSON.stringify(rec));
  }});
  var blob = new Blob([lines.join("\\n") + "\\n"], {{type: "application/x-ndjson"}});
  var a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = "reviews.jsonl"; a.click();
  msg.textContent = lines.length + " decision(s) exported.";
}});
</script></body></html>
"""
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(page, encoding="utf-8")


def read_reviews(reviews_jsonl: Path) -> list[dict[str, Any]]:
    """Parse and validate a reviewer decision file (strict: bad lines raise ValueError)."""
    records: list[dict[str, Any]] = []
    text = Path(reviews_jsonl).read_text(encoding="utf-8")
    for n, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"reviews line {n}: invalid JSON ({exc})") from exc
        if not isinstance(rec, dict):
            raise ValueError(f"reviews line {n}: expected a JSON object")
        missing = [k for k in (*_KEY, "decision", "reviewer") if k not in rec]
        if missing:
            raise ValueError(f"reviews line {n}: missing fields {missing}")
        if rec["decision"] not in DECISIONS:
            raise ValueError(
                f"reviews line {n}: decision must be one of {DECISIONS}, got {rec['decision']!r}"
            )
        if not isinstance(rec["reviewer"], str) or not rec["reviewer"].strip():
            raise ValueError(f"reviews line {n}: reviewer must be a non-empty name")
        records.append(rec)
    return records


def apply_reviews(verdicts_parquet: Path, reviews_jsonl: Path) -> pd.DataFrame:
    """Return the verdict frame with ``human_verified`` set only from reviewer decisions.

    Every row starts at ``None`` (any pre-existing value is discarded). Later lines override
    earlier ones for the same episode. confirmed -> True, rejected -> False, unsure -> None.
    Decisions about rows that are missing or not FAIL candidates are rejected with ValueError.
    """
    df = load_verdicts(Path(verdicts_parquet))
    df["human_verified"] = pd.Series([None] * len(df), index=df.index, dtype=object)
    df["review_decision"] = pd.Series([None] * len(df), index=df.index, dtype=object)
    df["reviewer"] = pd.Series([None] * len(df), index=df.index, dtype=object)

    index = {
        (str(r.dataset), int(r.episode_index), str(r.camera)): i
        for i, r in enumerate(df.itertuples(index=False))
    }
    for rec in read_reviews(Path(reviews_jsonl)):
        key = (str(rec["dataset"]), int(rec["episode_index"]), str(rec["camera"]))
        if key not in index:
            raise ValueError(f"review refers to unknown episode {key}")
        i = index[key]
        if df.at[i, "verdict"] != "FAIL":
            raise ValueError(f"review refers to non-FAIL episode {key}; only FAIL flags are reviewed")
        decision = rec["decision"]
        df.at[i, "human_verified"] = {"confirmed": True, "rejected": False}.get(decision)
        df.at[i, "review_decision"] = decision
        df.at[i, "reviewer"] = rec["reviewer"].strip()
    return df


__all__ = ["DECISIONS", "apply_reviews", "build_candidates_html", "read_reviews"]
