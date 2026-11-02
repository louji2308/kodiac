"""Static landing page + cached replay gallery generated from a ``ReplayStore`` (GitHub Pages mirror).

The page is the fallback when the hosted app is down (ARCHITECTURE §12). Every card is a ⚡ CACHED replay and carries
its run badges; the video embed is a clearly marked placeholder (``<!-- VIDEO_URL -->``), never a fake link.
"""

from __future__ import annotations

import html
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from Kodiac_robotics.app.content import (
    CACHED_EXPLAINER,
    FIXTURE_EXPLAINER,
    LIMITS,
    MODEL_TABLE,
    PRIVACY,
    TAGLINE,
)
from Kodiac_robotics.app.replay import CACHED_BADGE, ReplayEntry, ReplayStore

VERDICT_COLORS = {"PASS": "#1a9850", "FAIL": "#d73027", "CANT_TELL": "#e08a00"}
VERDICT_LABEL = {"PASS": "PASS", "FAIL": "FAIL", "CANT_TELL": "CAN'T TELL"}

STYLE = """
body{font-family:system-ui,Segoe UI,sans-serif;background:#0f1419;color:#e6edf3;margin:0;line-height:1.5}
main{max-width:1100px;margin:0 auto;padding:2rem 1rem 4rem}
h1{font-size:2.2rem;margin:.2rem 0}h2{margin-top:2.5rem;border-bottom:1px solid #30363d;padding-bottom:.3rem}
.tag{font-size:1.2rem;color:#7ee0ff}.banner{background:#3a2f00;border:1px solid #7a5b00;border-radius:8px;
padding:.8rem 1rem;margin:1rem 0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(480px,1fr));gap:1.2rem}
figure{margin:0;background:#161b22;border:1px solid #30363d;border-radius:10px;padding:.8rem}
figure img{width:100%;border-radius:6px}figcaption h3{margin:.5rem 0 .2rem}
.pill{display:inline-block;padding:2px 12px;border-radius:6px;color:#fff;font-weight:700}
.badge{display:inline-block;margin:2px 4px 2px 0;padding:1px 8px;border-radius:10px;background:#263238;
color:#e0f7fa;font:600 12px ui-monospace,monospace}.badge.cached{background:#fff3cd;color:#7a5b00}
.meta{color:#9aa4ae;font-size:.85rem}table{border-collapse:collapse;width:100%}
td,th{border:1px solid #30363d;padding:.4rem .6rem;text-align:left;vertical-align:top}
.video{border:2px dashed #30363d;border-radius:10px;padding:2rem;text-align:center;color:#9aa4ae}
a{color:#7ee0ff}
"""


def _badges(badges: list[str]) -> str:
    out = []
    for b in [*badges, CACHED_BADGE]:
        cls = "badge cached" if "CACHED" in b and "SAM" not in b else "badge"
        out.append(f'<span class="{cls}">{html.escape(b)}</span>')
    return "".join(out)


def _card(entry: ReplayEntry) -> str:
    color = VERDICT_COLORS.get(entry.verdict, "#555")
    label = VERDICT_LABEL.get(entry.verdict, entry.verdict)
    note = f'<p class="meta">{html.escape(entry.note)}</p>' if entry.note else ""
    return (
        "<figure>"
        f'<img loading="lazy" src="replays/blobs/{entry.card_sha256}.png" '
        f'alt="Verdict card: {html.escape(entry.title)}: {html.escape(label)}">'
        "<figcaption>"
        f"<h3>{html.escape(entry.title)}</h3>"
        f'<span class="pill" style="background:{color}">{html.escape(label)}</span> '
        f"<span class=\"meta\">test <code>{html.escape(entry.test_name)}</code></span>"
        f"<div>{_badges(entry.badges)}</div>"
        f'<p class="meta">{html.escape(entry.clip_label)}<br>'
        f"Engine time when recorded: {entry.run_total_ms / 1000:.2f} s (measured then; this page is not a live "
        f"grade). Commit <code>{html.escape(entry.source_commit)}</code>. "
        f'<a href="replays/blobs/{entry.result_sha256}.json">result.json</a></p>'
        f"{note}"
        "</figcaption></figure>"
    )


def render_index(entries: list[ReplayEntry]) -> str:
    cards = "\n".join(_card(e) for e in entries) or "<p>No cached replays have been generated yet.</p>"
    rows = "".join(
        f"<tr><td>{html.escape(m['model'])}</td><td>{html.escape(m['role'])}</td>"
        f"<td>{html.escape(m['status'])}</td></tr>"
        for m in MODEL_TABLE
    )
    limits = "".join(f"<li>{html.escape(t)}</li>" for t in LIMITS)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kodiac: {html.escape(TAGLINE)}</title><style>{STYLE}</style></head>
<body><main>
<h1>Kodiac</h1><div class="tag">{html.escape(TAGLINE)}</div>
<p>Tests, <code>git bisect</code> and <code>git blame</code> for robots: a clip goes in, a verdict
(PASS, FAIL or CAN'T TELL) comes out, with the measured numbers behind it.</p>
<div class="banner"><b>Static mirror.</b> Every card below is a <b>{html.escape(CACHED_BADGE)}</b> replay,
precomputed and shown instantly; none of them is a live grade. {html.escape(CACHED_EXPLAINER)}
{html.escape(FIXTURE_EXPLAINER)}</div>
<h2>Video</h2>
<div class="video"><!-- VIDEO_URL -->The 3-minute video will be embedded here at submission.</div>
<h2>Live app</h2>
<p><!-- LIVE_APP_URL -->The interactive page (grade a clip with a wall-clock timer, occlusion brush,
Teach it) is deployed separately; its URL is added here when it is published.</p>
<h2>Cached replays</h2>
<div class="grid">
{cards}
</div>
<h2>Which Meta model does what</h2>
<table><tr><th>Model</th><th>Role</th><th>On the hosted page today</th></tr>{rows}</table>
<h2>Limits we are honest about</h2><ul>{limits}</ul>
<h2>Privacy</h2><p>{html.escape(PRIVACY)}</p>
<p class="meta">Generated {stamp} from the replay store by <code>scripts/precompute_replays.py</code>.</p>
</main></body></html>
"""


def build_site(store: ReplayStore, site_dir: Path | str) -> Path:
    """Write ``index.html`` (and copy the store under ``site_dir/replays`` when it lives elsewhere)."""
    site = Path(site_dir)
    site.mkdir(parents=True, exist_ok=True)
    target = site / "replays"
    if store.root.resolve() != target.resolve():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(store.root, target)
    index = site / "index.html"
    index.write_text(render_index(store.list()), encoding="utf-8")
    (site / ".nojekyll").write_text("", encoding="utf-8")
    manifest = [e.model_dump() for e in store.list()]
    (site / "replays.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return index


__all__ = ["build_site", "render_index"]
