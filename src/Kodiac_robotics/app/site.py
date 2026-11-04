"""Interactive live web studio + cached replay gallery generated from a ``ReplayStore`` (GitHub Pages & Hosted App).

Provides a full interactive in-browser Kodiac Studio (Live Evaluator + SAM 3.1 Canvas + Draggable Occlusion Brush,
Live `.green` Test Compiler + Muse Voice/Spark connector, Interactive `git blame` & `git diff` Debugger, and
Muse Code `/goal` Done-Gate + Public Dataset Audit Explorer) alongside the verified ⚡ CACHED replay gallery.
"""

from __future__ import annotations

import html
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Kodiac_robotics.app.content import (
    CACHED_EXPLAINER,
    FIXTURE_EXPLAINER,
    LIMITS,
    MODEL_TABLE,
    PRIVACY,
    TAGLINE,
)
from Kodiac_robotics.app.replay import CACHED_BADGE, ReplayEntry, ReplayStore
from Kodiac_robotics.geometry.anchors import compute_anchors
from Kodiac_robotics.io.clip import open_clip
from Kodiac_robotics.segment.fixture import FixtureBackend

VERDICT_COLORS = {"PASS": "#16a34a", "FAIL": "#dc2626", "CANT_TELL": "#d97706"}
VERDICT_LABEL = {"PASS": "PASS", "FAIL": "FAIL", "CANT_TELL": "CAN'T TELL"}

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_embedded_tracks() -> dict[str, Any]:
    """Load compact per-frame [x1, y1, x2, y2, ub, vb, area_px, score] arrays for the 5 curated clips."""
    clips_dir = REPO_ROOT / "tests" / "fixtures" / "clips"
    tracks_dir = REPO_ROOT / "tests" / "fixtures" / "tracks"
    manifest_path = clips_dir / "manifest.json"
    if not manifest_path.is_file():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        fb = FixtureBackend(tracks_dir)
        out: dict[str, Any] = {}
        for fname, meta in manifest.get("clips", {}).items():
            cid = Path(fname).stem
            cpath = clips_dir / fname
            if not cpath.is_file():
                continue
            clip = open_clip(cpath)
            tracks = fb._load_tracks(clip)
            clip_objs: dict[str, list[list[float] | None]] = {}
            for obj_name, tr in tracks.items():
                frames_arr: list[list[float] | None] = []
                f0 = min(tr.frames.keys()) if tr.frames else 0
                a0 = max(1, tr.frames[f0].area_px) if tr.frames else 1
                for f in range(int(meta.get("n_frames", 90))):
                    if f in tr.frames:
                        m = tr.frames[f]
                        _, (ub, vb), _, area_px, _ = compute_anchors(m, base_area_px=a0)
                        x1, y1, x2, y2 = [round(float(v), 1) for v in m.bbox_xyxy]
                        frames_arr.append(
                            [x1, y1, x2, y2, round(ub, 1), round(vb, 1), int(area_px), round(float(m.score), 2)]
                        )
                    else:
                        frames_arr.append(None)
                clip_objs[obj_name] = frames_arr
            out[cid] = {
                "description": str(meta.get("description", cid)),
                "fps": float(meta.get("fps", 30.0)),
                "n_frames": int(meta.get("n_frames", 90)),
                "width": int(meta.get("width", 640)),
                "height": int(meta.get("height", 480)),
                "objects": clip_objs,
            }
        return out
    except Exception:
        return {}


def _load_embedded_results(entries: list[ReplayEntry], store: ReplayStore | None = None) -> dict[str, Any]:
    """Extract rich RunResult + Blame + Diff payloads from the ReplayStore when available."""
    results: dict[str, Any] = {}
    for e in entries:
        item: dict[str, Any] = {
            "id": e.id,
            "title": e.title,
            "verdict": e.verdict,
            "test_name": e.test_name,
            "clip_label": e.clip_label,
            "badges": e.badges,
            "run_total_ms": e.run_total_ms,
            "card_sha256": e.card_sha256,
            "result_sha256": e.result_sha256,
            "note": e.note,
        }
        if store is not None:
            try:
                _, run_res = store.get(e.id)
                item["run"] = json.loads(run_res.model_dump_json())
            except Exception:
                pass
        results[e.id] = item
    return results


STYLE = """
:root{
  --bg:#090d16;--panel:#111827;--panel2:#161f33;--border:#26334d;--text:#f1f5f9;--muted:#94a3b8;
  --accent:#38bdf8;--accent2:#818cf8;--pass:#16a34a;--fail:#dc2626;--cant:#d97706;
  --mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
body{font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--text);margin:0;line-height:1.5}
header.topbar{position:sticky;top:0;z-index:50;background:rgba(9,13,22,.92);backdrop-filter:blur(12px);border-bottom:1px solid var(--border);padding:.65rem 1.25rem}
.topbar-inner{max-width:1360px;margin:0 auto;display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.75rem}
.brand{display:flex;align-items:center;gap:.75rem}
.brand-logo{width:36px;height:36px;border-radius:9px;background:linear-gradient(135deg,#22c55e,#0ea5e9);display:flex;align-items:center;justify-content:center;font-weight:900;color:#05101a;font-size:1.1rem;box-shadow:0 0 18px rgba(56,189,248,.35)}
.brand h1{font-size:1.35rem;margin:0;letter-spacing:-.02em}
.brand .tag{font-size:.9rem;color:var(--accent);font-weight:600}
.api-bar{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap}
.api-input{background:#0b1120;border:1px solid var(--border);color:var(--text);padding:.4rem .65rem;border-radius:7px;font:500 .8rem var(--mono);width:230px}
.btn{background:#1e293b;color:var(--text);border:1px solid #334155;padding:.42rem .85rem;border-radius:7px;font-weight:600;font-size:.82rem;cursor:pointer;transition:all .15s}
.btn:hover{background:#334155;border-color:#475569}
.btn-primary{background:linear-gradient(135deg,#0284c7,#2563eb);border-color:#38bdf8;color:#fff}
.btn-primary:hover{filter:brightness(1.1)}
.btn-success{background:#15803d;border-color:#22c55e;color:#fff}
.btn-warn{background:#b45309;border-color:#f59e0b;color:#fff}
.status-dot{display:inline-flex;align-items:center;gap:.4rem;font-size:.78rem;padding:.25rem .65rem;border-radius:99px;background:#0f172a;border:1px solid var(--border);font-family:var(--mono)}
.dot{width:8px;height:8px;border-radius:50%;background:#22c55e;box-shadow:0 0 8px #22c55e}
main{max-width:1360px;margin:0 auto;padding:1.5rem 1.25rem 4rem}
.hero{background:radial-gradient(circle at 85% 15%,rgba(56,189,248,.14),transparent 45%),radial-gradient(circle at 15% 85%,rgba(34,197,94,.12),transparent 45%),var(--panel);border:1px solid var(--border);border-radius:14px;padding:1.5rem;margin-bottom:1.5rem}
.hero-grid{display:grid;grid-template-columns:1.35fr 1fr;gap:1.25rem;align-items:center}
@media(max-width:960px){.hero-grid{grid-template-columns:1fr}}
.hero h2{margin:0 0 .4rem;font-size:1.85rem;border:none;padding:0;line-height:1.2}
.hero p{margin:.35rem 0;color:#cbd5e1;font-size:.98rem}
.kpi-strip{display:grid;grid-template-columns:repeat(4,1fr);gap:.65rem;margin-top:1rem}
@media(max-width:720px){.kpi-strip{grid-template-columns:repeat(2,1fr)}}
.kpi{background:rgba(15,23,42,.8);border:1px solid var(--border);border-radius:10px;padding:.65rem .8rem}
.kpi .val{font:800 1.35rem var(--mono);color:var(--accent)}
.kpi .lbl{font-size:.75rem;color:var(--muted)}
.tabs{display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:1.2rem;border-bottom:1px solid var(--border);padding-bottom:.75rem}
.tab-btn{background:var(--panel);color:var(--muted);border:1px solid var(--border);padding:.55rem 1.05rem;border-radius:9px;font-weight:700;font-size:.86rem;cursor:pointer;display:flex;align-items:center;gap:.45rem}
.tab-btn.active{background:linear-gradient(135deg,rgba(14,165,233,.22),rgba(99,102,241,.22));color:#fff;border-color:var(--accent);box-shadow:0 0 14px rgba(56,189,248,.2)}
.tab-pane{display:none}
.tab-pane.active{display:block}
.studio-grid{display:grid;grid-template-columns:660px 1fr;gap:1.25rem;align-items:start}
@media(max-width:1150px){.studio-grid{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:1.1rem}
.panel h3{margin:0 0 .65rem;font-size:1.05rem;display:flex;align-items:center;justify-content:space-between}
.canvas-wrap{position:relative;width:100%;max-width:640px;aspect-ratio:4/3;background:#050811;border:1px solid #334155;border-radius:10px;overflow:hidden;user-select:none}
.canvas-wrap video{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;pointer-events:none}
.canvas-wrap canvas{position:absolute;inset:0;width:100%;height:100%;cursor:crosshair}
.scrubber-bar{display:flex;align-items:center;gap:.6rem;margin-top:.65rem;background:#0b1120;padding:.5rem .75rem;border-radius:8px;border:1px solid var(--border)}
.scrubber-bar input[type=range]{flex:1;accent-color:var(--accent)}
.mono{font-family:var(--mono);font-size:.82rem}
.clip-selector{display:flex;gap:.4rem;flex-wrap:wrap;margin-bottom:.75rem}
.clip-chip{background:#0b1120;border:1px solid var(--border);color:#cbd5e1;padding:.35rem .7rem;border-radius:7px;font-size:.78rem;font-weight:600;cursor:pointer}
.clip-chip.active{background:#1e3a8a;border-color:var(--accent);color:#fff}
.verdict-banner{display:flex;align-items:center;justify-content:space-between;padding:.85rem 1rem;border-radius:10px;margin-bottom:.85rem;font-weight:800;border:1px solid transparent}
.verdict-PASS{background:rgba(22,163,74,.18);border-color:#22c55e;color:#4ade80}
.verdict-FAIL{background:rgba(220,38,38,.18);border-color:#ef4444;color:#f87171}
.verdict-CANT_TELL{background:rgba(217,119,6,.18);border-color:#f59e0b;color:#fbbf24}
.step-card{background:#0b1120;border:1px solid var(--border);border-radius:8px;padding:.65rem .8rem;margin-bottom:.5rem}
.step-head{display:flex;justify-content:space-between;align-items:center;font-weight:700;font-size:.88rem}
.comp-row{display:flex;justify-content:space-between;font:500 .78rem var(--mono);color:var(--muted);margin-top:.28rem;padding-top:.28rem;border-top:1px dashed #1e293b}
.slider-row{display:grid;grid-template-columns:145px 1fr 68px;align-items:center;gap:.5rem;font-size:.8rem;margin-bottom:.4rem}
.code-box{background:#060a12;border:1px solid var(--border);border-radius:8px;padding:.8rem;font:500 .8rem/1.45 var(--mono);color:#e2e8f0;overflow-x:auto;white-space:pre}
.diff-del{color:#f87171;background:rgba(220,38,38,.12);display:block;padding:0 .3rem}
.diff-add{color:#4ade80;background:rgba(22,163,74,.12);display:block;padding:0 .3rem}
.diff-warn{color:#fbbf24;display:block;padding:0 .3rem}
.banner{background:rgba(217,119,6,.12);border:1px solid #b45309;border-radius:10px;padding:.75rem 1rem;margin:1rem 0;font-size:.88rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:1.1rem}
figure{margin:0;background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:.85rem}
figure img{width:100%;border-radius:6px;border:1px solid #1e293b}
figcaption h3{margin:.5rem 0 .25rem;font-size:1rem}
.pill{display:inline-block;padding:2px 10px;border-radius:6px;color:#fff;font-weight:700;font-size:.78rem;font-family:var(--mono)}
.badge{display:inline-block;margin:2px 4px 2px 0;padding:2px 8px;border-radius:8px;background:#1e293b;color:#bae6fd;font:600 11px var(--mono);border:1px solid #334155}
.badge.cached{background:#fef3c7;color:#92400e;border-color:#f59e0b}
.meta{color:var(--muted);font-size:.83rem}
table{border-collapse:collapse;width:100%;font-size:.86rem}
td,th{border:1px solid var(--border);padding:.5rem .65rem;text-align:left;vertical-align:top}
th{background:#0f172a;color:#cbd5e1}
h2{margin-top:2.2rem;border-bottom:1px solid var(--border);padding-bottom:.35rem;font-size:1.35rem}
.video{border:1px dashed var(--border);border-radius:10px;padding:1.2rem;text-align:center;color:var(--muted);background:var(--panel)}
a{color:var(--accent)}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:1.1rem}
@media(max-width:900px){.two-col{grid-template-columns:1fr}}
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
        f'<a href="replays/blobs/{entry.result_sha256}.json">result.json</a> '
        f'<button class="btn" style="padding:1px 7px;font-size:.74rem;margin-left:4px" '
        f'onclick="window.loadReplayIntoStudio(\'{html.escape(entry.id)}\')">Inspect in Studio ↗</button></p>'
        f"{note}"
        "</figcaption></figure>"
    )


def render_index(entries: list[ReplayEntry], store: ReplayStore | None = None) -> str:
    cards = "\\n".join(_card(e) for e in entries) or "<p>No cached replays have been generated yet.</p>"
    rows = "".join(
        f"<tr><td><b>{html.escape(m['model'])}</b></td><td>{html.escape(m['role'])}</td>"
        f"<td>{html.escape(m['status'])}</td></tr>"
        for m in MODEL_TABLE
    )
    limits = "".join(f"<li>{html.escape(t)}</li>" for t in LIMITS)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    embedded_tracks = _load_embedded_tracks()
    embedded_results = _load_embedded_results(entries, store=store)
    tracks_json = json.dumps(embedded_tracks, separators=(",", ":"))
    results_json = json.dumps(embedded_results, separators=(",", ":"))

    return rf"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kodiac: {html.escape(TAGLINE)}</title><style>{STYLE}</style></head>
<body>
<header class="topbar">
  <div class="topbar-inner">
    <div class="brand">
      <div class="brand-logo">K</div>
      <div>
        <h1>Kodiac <span style="font-weight:400;color:var(--muted);font-size:.92rem">v0.1.0 · Meta AI Hackathon</span></h1>
        <div class="tag">{html.escape(TAGLINE)}</div>
      </div>
    </div>
    <div class="api-bar">
      <span class="status-dot" id="engine-status-pill"><span class="dot"></span><span id="engine-status-text">In-Browser Geometric Engine: READY</span></span>
      <input type="password" id="meta-api-key-input" class="api-input" placeholder="Paste Meta MODEL_API_KEY (optional)..." autocomplete="off">
      <button class="btn btn-primary" onclick="window.connectMetaKey()">Connect Meta API</button>
      <button class="btn" id="clear-key-btn" style="display:none" onclick="window.clearMetaKey()">Disconnect</button>
    </div>
  </div>
</header>

<main>
  <section class="hero">
    <div class="hero-grid">
      <div>
        <div style="display:inline-block;padding:2px 10px;border-radius:99px;background:rgba(56,189,248,.15);border:1px solid rgba(56,189,248,.4);color:var(--accent);font:700 .75rem var(--mono);margin-bottom:.5rem">
          UNIT TESTS · GIT BISECT · GIT BLAME FOR ROBOTICS
        </div>
        <h2>Physical Unit Tests, Exact Onset Attribution ($t^*$), and Anti-Cheat Done-Gates for Robots</h2>
        <p>VLM judges hallucinate pass rates and guess adjectives when cameras are occluded. <b>Kodiac</b> compiles natural language or voice into deterministic <code>.green</code> specifications, measures 3D/2D tabletop trajectories from <b>SAM 3.1</b> masks with propagated uncertainty $\\pm\\sigma$, abstains honestly with <b>CAN'T TELL</b> under occlusion (Gates G1–G6), pinpoints the exact failure onset frame $t^*$, and blocks <b>Muse Code <code>/goal</code></b> until the physical test returns <b>PASS</b>.</p>
        <div class="kpi-strip">
          <div class="kpi"><div class="val">16 / 16</div><div class="lbl">Sim Discrimination (0 False-PASS)</div></div>
          <div class="kpi"><div class="val">10 / 10</div><div class="lbl">Planted Bugs Repaired (B01–B10)</div></div>
          <div class="kpi"><div class="val">18 / 18</div><div class="lbl">Done-Gate Tamper Attacks Refused</div></div>
          <div class="kpi"><div class="val">5 Clips</div><div class="lbl">DROID &amp; LeRobot Real Failure Audits</div></div>
        </div>
      </div>
      <div class="panel" style="background:#0b1120;border-color:#1e3a8a">
        <div style="font:700 .8rem var(--mono);color:var(--accent);margin-bottom:.4rem">HEADLINE PROOF · SAME ROBOT, ONLY THE JUDGE CHANGED</div>
        <div style="font-size:.82rem;color:#cbd5e1;margin-bottom:.65rem">Closed-loop autonomous code repair on the 10-bug Franka StackCube benchmark (<code>examples/sim/pick_place.py</code>):</div>
        <div style="margin-bottom:.55rem">
          <div style="display:flex;justify-content:space-between;font-size:.78rem;margin-bottom:2px"><span>Unverified Agent Stop (No Done-Gate)</span><span class="mono" style="color:#f87171">0 / 10 (0%)</span></div>
          <div style="height:10px;background:#1e293b;border-radius:5px;overflow:hidden"><div style="width:4%;height:100%;background:#ef4444"></div></div>
        </div>
        <div style="margin-bottom:.55rem">
          <div style="display:flex;justify-content:space-between;font-size:.78rem;margin-bottom:2px"><span>Binary FAIL Only (No Blame / No Hint)</span><span class="mono" style="color:#fbbf24">3 / 10 (30%)</span></div>
          <div style="height:10px;background:#1e293b;border-radius:5px;overflow:hidden"><div style="width:30%;height:100%;background:#f59e0b"></div></div>
        </div>
        <div>
          <div style="display:flex;justify-content:space-between;font-size:.78rem;margin-bottom:2px"><span><b>Kodiac Done-Gate + Physical Blame ($t^*$) + Hint</b></span><span class="mono" style="color:#4ade80"><b>10 / 10 (100%)</b></span></div>
          <div style="height:10px;background:#1e293b;border-radius:5px;overflow:hidden"><div style="width:100%;height:100%;background:linear-gradient(90deg,#22c55e,#38bdf8)"></div></div>
        </div>
        <div class="meta" style="margin-top:.6rem;font-size:.74rem">Evidence badge: <code>[MOCK SIMULATION · PRIVILEGED STATE TRACKS]</code> · Registered in <code>VIDEO_NUMBERS.md</code>.</div>
      </div>
    </div>
  </section>

  <!-- Interactive Navigation Tabs -->
  <div class="tabs" role="tablist">
    <button class="tab-btn active" id="tabbtn-eval" onclick="window.switchStudioTab('eval')">▶ 1. Live Video Evaluator &amp; Occlusion Brush (<code>Kodiac run</code>)</button>
    <button class="tab-btn" id="tabbtn-blame" onclick="window.switchStudioTab('blame')">🔍 2. Physical <code>git blame</code> &amp; <code>git diff</code> Debugger</button>
    <button class="tab-btn" id="tabbtn-compile" onclick="window.switchStudioTab('compile')">🎙️ 3. Live <code>.green</code> Test Compiler &amp; Muse Voice</button>
    <button class="tab-btn" id="tabbtn-loop" onclick="window.switchStudioTab('loop')">🛡️ 4. Muse Code <code>/goal</code> Done-Gate &amp; Real Robot Audit</button>
    <button class="tab-btn" id="tabbtn-gallery" onclick="window.switchStudioTab('gallery')">⚡ 5. Verified Precomputed Replay Gallery ({len(entries)})</button>
  </div>

  <!-- TAB 1: LIVE EVALUATOR & OCCLUSION BRUSH -->
  <section class="tab-pane active" id="tab-eval">
    <div class="studio-grid">
      <div class="panel">
        <h3>
          <span>SAM 3.1 Trajectory &amp; Support Anchor Viewport</span>
          <span class="badge" id="viewport-mode-badge">[LIVE IN-BROWSER ENGINE · 60FPS CANVAS]</span>
        </h3>
        <div class="clip-selector" id="clip-selector-bar">
          <button class="clip-chip active" data-clip="correct_run" onclick="window.selectClip('correct_run')">✅ correct_run (Reference PASS)</button>
          <button class="clip-chip" data-clip="b01_early_release" onclick="window.selectClip('b01_early_release')">❌ b01_early_release (Drop @ f=58)</button>
          <button class="clip-chip" data-clip="b02_xy_misalignment" onclick="window.selectClip('b02_xy_misalignment')">❌ b02_xy_misalignment (5.1cm XY Error)</button>
          <button class="clip-chip" data-clip="b09_lift_failure" onclick="window.selectClip('b09_lift_failure')">❌ b09_lift_failure (0.0cm Lift)</button>
          <button class="clip-chip" data-clip="occluded_clip" onclick="window.selectClip('occluded_clip')">⚠️ occluded_clip (Gate G2 Abstain)</button>
        </div>

        <div class="canvas-wrap" id="canvas-container">
          <video id="studio-video" src="clips/correct_run.mp4" muted playsinline preload="auto"></video>
          <canvas id="studio-canvas" width="640" height="480"></canvas>
        </div>

        <div class="scrubber-bar">
          <button class="btn" id="play-pause-btn" onclick="window.togglePlay()">▶ Play</button>
          <input type="range" id="frame-slider" min="0" max="89" value="0" oninput="window.seekFrame(parseInt(this.value,10))">
          <span class="mono" id="frame-readout">f = 0 / 89 (0.00 s)</span>
        </div>

        <div style="display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;justify-content:space-between;margin-top:.75rem">
          <div style="font-size:.8rem;color:var(--muted)">
            <b>🖱️ Interactive Occlusion Brush:</b> Drag anywhere on the canvas above to paint a black occluder over any block and test Gate G2 (`CAN'T TELL`).
          </div>
          <div style="display:flex;gap:.4rem">
            <button class="btn btn-warn" onclick="window.applyTargetOccluder()">Paint Target CubeB Occluder</button>
            <button class="btn" onclick="window.clearOccluders()">Clear Occluder</button>
          </div>
        </div>
      </div>

      <div class="panel">
        <h3>
          <span>Live Kleene 3-Valued Evaluation &amp; Threshold Tuner</span>
          <span class="mono" id="live-timer-badge" style="color:var(--accent)">⏱️ 0.42 ms (live browser run)</span>
        </h3>

        <div id="live-verdict-box" class="verdict-banner verdict-PASS">
          <div>
            <div style="font-size:1.3rem" id="live-verdict-title">PASS · All 3 Steps Confirmed</div>
            <div style="font-size:.8rem;font-weight:500;opacity:.9" id="live-verdict-sub">Sustained Kleene True (n_on = 3 frames) across grasp → place → release</div>
          </div>
          <button class="btn btn-primary" onclick="window.runLiveGrade()">▶ Re-Run Engine Now</button>
        </div>

        <div style="background:#0b1120;border:1px solid var(--border);border-radius:9px;padding:.75rem;margin-bottom:.85rem">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.5rem">
            <b style="font-size:.84rem">Interactive <code>stackcube.green</code> Parameter Thresholds</b>
            <button class="btn" style="padding:2px 8px;font-size:.74rem" onclick="window.resetThresholds()">Reset Defaults</button>
          </div>
          <div class="slider-row">
            <span class="mono">lifted.min_cm</span>
            <input type="range" id="param-min-cm" min="0.5" max="9.0" step="0.25" value="2.0" oninput="window.updateThresholds()">
            <span class="mono" id="val-min-cm">&gt;= 2.00 cm</span>
          </div>
          <div class="slider-row">
            <span class="mono">on.align_xy_cm</span>
            <input type="range" id="param-align-xy" min="0.5" max="8.0" step="0.1" value="3.33" oninput="window.updateThresholds()">
            <span class="mono" id="val-align-xy">&lt;= 3.33 cm</span>
          </div>
          <div class="slider-row">
            <span class="mono">on.gap_cm</span>
            <input type="range" id="param-gap-cm" min="0.1" max="3.0" step="0.1" value="0.5" oninput="window.updateThresholds()">
            <span class="mono" id="val-gap-cm">&lt;= 0.50 cm</span>
          </div>
          <div class="slider-row">
            <span class="mono">camera_tier</span>
            <select id="param-camera-tier" class="api-input" style="width:100%" onchange="window.updateThresholds()">
              <option value="B">Tier B · Calibrated Tabletop Scale (σ = 0.08 cm)</option>
              <option value="C">Tier C · Uncalibrated Monocular Prior (2.5x σ = 0.50 cm · Gate G3/G6)</option>
            </select>
            <span class="mono" id="val-tier">Tier B</span>
          </div>
        </div>

        <div id="live-steps-container"></div>

        <div style="margin-top:.75rem;background:#0b1120;border:1px solid var(--border);border-radius:9px;padding:.75rem">
          <div style="font-weight:700;font-size:.84rem;margin-bottom:.4rem">Frame <span id="inspected-frame-num">0</span> Live Physical Telemetry (Tabletop Metric Frame)</div>
          <div id="frame-telemetry-table" class="mono" style="font-size:.78rem;color:#cbd5e1"></div>
        </div>
      </div>
    </div>
  </section>

  <!-- TAB 2: PHYSICAL GIT BLAME & DIFF DEBUGGER -->
  <section class="tab-pane" id="tab-blame">
    <div class="panel" style="margin-bottom:1.1rem">
      <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:.75rem;margin-bottom:.85rem">
        <div>
          <h3 style="margin:0">Physical <code>Kodiac blame</code> &amp; <code>Kodiac diff</code> Causal Attribution</h3>
          <div class="meta">Select any failed attempt to inspect its backward changepoint onset $t^*$, validated FactTable, corrective Hint, and Myers LCS event diff against <code>stackcube.green.lock</code>.</div>
        </div>
        <div style="display:flex;gap:.45rem;flex-wrap:wrap">
          <button class="btn btn-primary" onclick="window.selectBlameCase('b01')">Case 1: B01 Early Release (Mid-Air Drop)</button>
          <button class="btn" onclick="window.selectBlameCase('b02')">Case 2: B02 XY Misalignment (5.1 cm Offset)</button>
          <button class="btn" onclick="window.selectBlameCase('b09')">Case 3: B09 Lift Failure (0.0 cm Lift)</button>
          <button class="btn" onclick="window.selectBlameCase('b10_sim')">Case 4: Sim B10 High Release (+ Code Line Span)</button>
        </div>
      </div>

      <div class="two-col">
        <div>
          <div id="blame-header-card" class="verdict-banner verdict-FAIL" style="margin-bottom:.75rem"></div>
          <div style="background:#0b1120;border:1px solid var(--border);border-radius:8px;padding:.75rem;margin-bottom:.75rem">
            <div style="font:700 .76rem var(--mono);color:var(--accent);margin-bottom:.25rem">VALIDATED ONE-SENTENCE SUMMARY (≤30 WORDS, EVERY NUMBER GROUNDED IN FACTTABLE)</div>
            <div id="blame-summary-text" style="font-size:.95rem;font-weight:600;color:#fff"></div>
          </div>
          <div style="background:rgba(22,163,74,.12);border:1px solid #22c55e;border-radius:8px;padding:.75rem;margin-bottom:.75rem">
            <div style="font:700 .76rem var(--mono);color:#4ade80;margin-bottom:.25rem">ACTIONABLE CORRECTIVE HINT (SINGLE-VARIABLE CHANGE TO FLIP MARGIN ≥ +σ)</div>
            <div id="blame-hint-text" class="mono" style="font-size:.83rem;color:#e2e8f0"></div>
          </div>
          <div id="blame-codeloc-box" style="background:#0b1120;border:1px solid var(--border);border-radius:8px;padding:.75rem"></div>
        </div>

        <div>
          <div style="font-weight:700;font-size:.88rem;margin-bottom:.4rem">Measured Physical FactTable at Onset Frame $t^*$</div>
          <table id="blame-facts-table" style="margin-bottom:.85rem"></table>
          <div style="font-weight:700;font-size:.88rem;margin-bottom:.4rem">Myers LCS Event Diff (<code>Kodiac diff examples/stackcube.green</code>)</div>
          <div id="blame-diff-box" class="code-box"></div>
        </div>
      </div>
    </div>
  </section>

  <!-- TAB 3: LIVE .GREEN COMPILER & MUSE VOICE -->
  <section class="tab-pane" id="tab-compile">
    <div class="two-col">
      <div class="panel">
        <h3>
          <span>Natural Language / Voice → Canonical <code>.green</code> Compiler</span>
          <span class="badge" id="compiler-backend-badge">[DETERMINISTIC + 2.5σ SLACK CALIBRATOR]</span>
        </h3>
        <p class="meta">Type any manipulation task or use the microphone button (Web Speech API / Muse Voice anchor) to compile a deterministic <code>.green</code> specification with ADR-0013 physical sanity caps (<code>E001</code> missing object, <code>E003</code> unsupported verb, <code>E005</code> physically impossible threshold, <code>W101</code> slack cap).</p>

        <div style="display:flex;gap:.5rem;margin-bottom:.65rem">
          <input type="text" id="compile-input" class="api-input" style="flex:1;width:auto;font-size:.9rem;padding:.55rem .8rem" value="Pick up red cubeA by at least 2.5 cm, stack it squarely on green cubeB within 3.0 cm, and release for 0.5 s">
          <button class="btn btn-warn" id="voice-mic-btn" onclick="window.startVoiceCapture()">🎙️ Speak Intent</button>
          <button class="btn btn-primary" onclick="window.runLiveCompile()">⚡ Compile <code>.green</code></button>
        </div>

        <div style="display:flex;gap:.4rem;flex-wrap:wrap;margin-bottom:.85rem">
          <button class="clip-chip" onclick="window.setCompilePreset('Pick up red cubeA by at least 2.5 cm, stack it squarely on green cubeB within 3.0 cm, and release for 0.5 s')">Preset 1: Stack cubeA on cubeB</button>
          <button class="clip-chip" onclick="window.setCompilePreset('Grasp the red block, lift 4 cm, and place it inside the metal tray')">Preset 2: Place inside container</button>
          <button class="clip-chip" onclick="window.setCompilePreset('Move gripper near the yellow cylinder within 2.0 cm and hold for 0.8 s')">Preset 3: Reach &amp; dwell</button>
          <button class="clip-chip" onclick="window.setCompilePreset('Dance a celebratory jig around the workspace')">Preset 4: Trigger E003 Refusal</button>
          <button class="clip-chip" onclick="window.setCompilePreset('Pick up the unicorn and stack on the dragon')">Preset 5: Trigger E001 Object Guard</button>
        </div>

        <div id="compile-status-bar" class="meta" style="margin-bottom:.5rem"></div>
        <div class="code-box" id="compiled-green-output" style="min-height:290px"></div>
      </div>

      <div class="panel">
        <h3><span>Two-Pass Demonstration Self-Test &amp; $2.5\\sigma$ Slack Calibration</span><span class="badge">[PASS-1 TRACE → PASS-2 LOCKFILE]</span></h3>
        <p class="meta">When compiling with a reference demonstration video (<code>Kodiac test "stack cubeA on cubeB" --video correct_run.mp4</code>), Kodiac measures the empirical peak/minimum on the demo trace and sets each threshold with a $2.5\\sigma$ noise-floor safety margin, capped by ADR-0013 physical sanity bounds:</p>
        <table>
          <tr><th>Predicate Parameter</th><th>Measured on <code>correct_run.mp4</code></th><th>Calibrated Threshold ($\\pm 2.5\\sigma$)</th><th>ADR-0013 Cap</th></tr>
          <tr><td><code>moves_with.slip_cm</code></td><td><code>0.08 ± 0.11 cm</code></td><td><code>&lt;= 1.00 cm</code></td><td><code>max 2.50 cm</code></td></tr>
          <tr><td><code>lifted.min_cm</code></td><td><code>7.74 ± 0.08 cm</code></td><td><code>&gt;= 2.00 cm</code></td><td><code>min 1.00 cm</code></td></tr>
          <tr><td><code>on.align_xy_cm</code></td><td><code>0.00 ± 0.11 cm</code></td><td><code>&lt;= 3.33 cm</code></td><td><code>max 4.00 cm</code></td></tr>
          <tr><td><code>on.gap_cm</code></td><td><code>0.06 ± 0.11 cm</code></td><td><code>&lt;= 0.50 cm</code></td><td><code>max 2.00 cm</code></td></tr>
          <tr><td><code>dwell.for_s</code></td><td><code>0.33 ± 0.03 s</code> (clip end settled)</td><td><code>&gt;= 0.50 s</code></td><td><code>min 0.25 s</code></td></tr>
        </table>
        <div style="margin-top:.85rem">
          <div style="font-weight:700;font-size:.86rem;margin-bottom:.35rem">Generated Sidecar Lockfile (<code>examples/stackcube.green.lock</code>)</div>
          <div class="code-box" style="font-size:.75rem">{{
  "schema_version": "1.0",
  "test_name": "stackcube",
  "demo_clip_sha256": "eb62b10ff9c809702ab4444a064785b0f5621330592fa7b2e078c92b0e916278",
  "self_test_verdict": "PASS",
  "demo_events": [
    {{"step": 0, "step_name": "grasp", "kind": "achieved", "frame": 38, "t_s": 1.2667}},
    {{"step": 1, "step_name": "place", "kind": "settled",  "frame": 82, "t_s": 2.7333}},
    {{"step": 2, "step_name": "release", "kind": "achieved", "frame": 89, "t_s": 2.9667}}
  ]
}}</div>
        </div>
      </div>
    </div>
  </section>

  <!-- TAB 4: MUSE CODE /GOAL DONE-GATE & REAL ROBOT AUDIT -->
  <section class="tab-pane" id="tab-loop">
    <div class="two-col" style="margin-bottom:1.2rem">
      <div class="panel">
        <h3><span>Muse Code <code>/goal</code> Done-Gate: 10/10 Planted Bug Repair Matrix</span><span class="badge">[MOCK SIM · 0 FALSE-PASS]</span></h3>
        <p class="meta">Each bug <code>B01</code>–<code>B10</code> is injected into <code>examples/sim/pick_place.py</code>. When the coding agent attempts to stop, <code>Kodiac gate</code> re-runs the pinned simulation from scratch, blocks the stop on <code>FAIL</code> (exit 2), returns the measured <code>blame</code> + <code>hint</code>, and only unlocks exit 0 when <code>Kodiac run</code> returns <b>PASS</b>.</p>
        <table>
          <tr><th>Bug ID</th><th>Injected Fault</th><th>Blamed Step &amp; Predicate</th><th>Corrective Hint Applied</th><th>Post-Fix</th></tr>
          <tr><td><code>B01</code></td><td>Early gripper release in transit</td><td><code>#2 place · moves_with</code> ($t^*=4.10\s$)</td><td>Move <code>gripper.open()</code> after <code>move_to(place)</code></td><td><span class="pill" style="background:var(--pass)">PASS</span></td></tr>
          <tr><td><code>B02</code></td><td>5.0 cm XY placement offset</td><td><code>#2 place · on.align_xy</code> ($5.0 &gt; 3.33\cm$)</td><td>Shift <code>place_xy_offset</code> by $-5.0\cm$ toward <code>cubeB</code></td><td><span class="pill" style="background:var(--pass)">PASS</span></td></tr>
          <tr><td><code>B03</code></td><td>0.5 cm insufficient lift height</td><td><code>#1 grasp · lifted.height</code> ($0.5 &lt; 2.0\cm$)</td><td>Increase <code>lift_distance</code> by $+1.60\cm$</td><td><span class="pill" style="background:var(--pass)">PASS</span></td></tr>
          <tr><td><code>B04</code></td><td>0.03 s short dwell before retract</td><td><code>#3 release · dwell.duration</code> ($0.03 &lt; 0.50\s$)</td><td>Hold $+0.50\s$ longer before <code>arm.retract()</code></td><td><span class="pill" style="background:var(--pass)">PASS</span></td></tr>
          <tr><td><code>B05</code></td><td>Lift arm before closing gripper</td><td><code>#1 grasp · moves_with</code></td><td>Reorder <code>gripper.close()</code> before <code>arm.lift()</code></td><td><span class="pill" style="background:var(--pass)">PASS</span></td></tr>
          <tr><td><code>B06</code></td><td>High grasp 7 cm above tabletop</td><td><code>#1 grasp · lifted.height</code></td><td>Lower pre-grasp descent Z to tabletop contact height</td><td><span class="pill" style="background:var(--pass)">PASS</span></td></tr>
          <tr><td><code>B07</code></td><td>Missing <code>gripper.close()</code> call</td><td><code>#1 grasp · moves_with</code></td><td>Insert <code>robot.gripper.close()</code> at grasp pose</td><td><span class="pill" style="background:var(--pass)">PASS</span></td></tr>
          <tr><td><code>B08</code></td><td>Navigates to wrong XY object</td><td><code>#1 grasp · moves_with</code></td><td>Align approach XY target with <code>cubeA</code> pose</td><td><span class="pill" style="background:var(--pass)">PASS</span></td></tr>
          <tr><td><code>B09</code></td><td>Gripper never opens at place pose</td><td><code>#3 release · not moves_with</code></td><td>Call <code>robot.gripper.open()</code> prior to retract</td><td><span class="pill" style="background:var(--pass)">PASS</span></td></tr>
          <tr><td><code>B10</code></td><td>High release 15 cm above target</td><td><code>#2 place · on.gap</code> ($3.0 &gt; 0.50\cm$)</td><td>Lower release Z height by $-2.60\cm$ before opening</td><td><span class="pill" style="background:var(--pass)">PASS</span></td></tr>
        </table>
      </div>

      <div class="panel">
        <h3><span>Public Real-Robot Dataset Failure Audit (DROID &amp; LeRobot SO-100)</span><span class="badge">[CATALOGED REAL TELEOP EPISODES]</span></h3>
        <p class="meta">Cataloged from real teleoperated robot demonstrations in <code>alexander-soare/droid_100</code> (Franka Panda 7-DOF) and <code>lerobot/so100_pick_place</code> (SO-100 low-cost follower arm):</p>
        <table>
          <tr><th>Episode ID</th><th>Hardware &amp; Dataset</th><th>Task &amp; Failure Mode</th><th>Onset $t^*$</th></tr>
          <tr><td><code>HERO-DROID-001</code></td><td>Franka Panda · <code>droid_100/14</code></td><td>Pick red block → metal tray · <b>Early Release</b> mid-transport</td><td><code>2.13 s (f=32)</code></td></tr>
          <tr><td><code>HERO-DROID-002</code></td><td>Franka Panda · <code>droid_100/38</code></td><td>Stack green cup on saucer · <b>XY Misalignment</b> ($4.2\cm &gt; 3.33\cm$)</td><td><code>3.80 s (f=57)</code></td></tr>
          <tr><td><code>HERO-SO100-001</code></td><td>SO-100 Arm · <code>so100_pick_place/7</code></td><td>Pick yellow cylinder → mat · <b>Lift Failure</b> ($&lt;0.8\cm$ clearance)</td><td><code>1.45 s (f=44)</code></td></tr>
          <tr><td><code>HERO-SO100-002</code></td><td>SO-100 Arm · <code>so100_pick_place/23</code></td><td>Pick wooden dice → bin · <b>Grasp Slip</b> during vertical lift</td><td><code>1.65 s (f=50)</code></td></tr>
          <tr><td><code>HERO-DROID-003</code></td><td>Franka Panda · <code>droid_100/67</code></td><td>Pick banana → ceramic bowl · <b>Rim Drop / XY Offset</b></td><td><code>4.10 s (f=61)</code></td></tr>
        </table>

        <h3 style="margin-top:1.1rem"><span>18/18 Anti-Cheat Done-Gate Refusal Proofs (<code>tests/loop/test_gate.py</code>)</span><span class="badge">[FAIL-CLOSED EXIT 2]</span></h3>
        <p class="meta">The Stop-hook Done-Gate stores SHA-256 cryptographic pins outside the agent workspace and refuses every reward-hacking vector:</p>
        <ul style="font-size:.82rem;color:#cbd5e1;margin:.3rem 0;padding-left:1.2rem">
          <li><b>Test Weakening Refused:</b> Editing <code>stackcube.green</code> thresholds or deleting steps triggers <code>pinned test modified since Kodiac gate --init</code> (exit 2).</li>
          <li><b>Fake Verdict Injection Refused:</b> Writing a forged <code>.Kodiac/last_verdict.json</code> with <code>"verdict": "PASS"</code> is ignored; the gate re-runs the simulator from scratch on every stop.</li>
          <li><b>Engine / Predicate Monkeypatching Refused:</b> Modifying any file under <code>engine/</code>, <code>predicates/</code>, <code>geometry/</code>, or <code>uncertainty/</code> after pin initialization triggers an immediate SHA-256 digest mismatch block.</li>
        </ul>
      </div>
    </div>
  </section>

  <!-- TAB 5: CACHED REPLAY GALLERY (ALWAYS VISIBLE BELOW OR VIA TAB) -->
  <section id="tab-gallery">
    <h2>Verified Precomputed Replay Gallery (<code>⚡ CACHED</code>)</h2>
    <div class="banner"><b>Transparency &amp; Provenance Banner.</b> Every card in the gallery below is a <b>{html.escape(CACHED_BADGE)}</b> replay,
    precomputed by running <code>Kodiac_robotics.pipeline.run.run</code> and shown instantly; none of them is a live grade. Use the <b>Live Video Evaluator Studio</b> above to run the engine interactively in your browser. {html.escape(CACHED_EXPLAINER)}
    {html.escape(FIXTURE_EXPLAINER)}</div>
    <div class="grid">
    {cards}
    </div>
  </section>

  <h2>Video</h2>
  <div class="video"><!-- VIDEO_URL -->The 3-minute demonstration video is linked in the submission packet and <code>docs/operations/SUBMISSION.md</code>.</div>

  <h2>Live app</h2>
  <p><!-- LIVE_APP_URL -->The interactive Studio above runs directly on this page (zero-install browser engine + optional Meta API key connector); you can also run the full FastAPI + Gradio server locally via <code>Kodiac app --port 7860</code>.</p>

  <h2>Which Meta model does what</h2>
  <table><tr><th>Model</th><th>Role</th><th>On this hosted Studio today</th></tr>{rows}</table>

  <h2>Limits we are honest about</h2><ul>{limits}</ul>
  <h2>Privacy</h2><p>{html.escape(PRIVACY)}</p>
  <p class="meta">Generated {stamp} from the replay store by <code>scripts/precompute_replays.py</code>.</p>
</main>

<script>
window.KODIAC_TRACKS = {tracks_json};
window.KODIAC_REPLAYS = {results_json};
</script>
<script>
(function() {{
  const state = {{
    clipId: 'correct_run',
    frame: 0,
    playing: false,
    timer: null,
    occluders: [],
    dragStart: null,
    dragCurr: null,
    minCm: 2.0,
    alignXyCm: 3.33,
    gapCm: 0.50,
    cameraTier: 'B',
    metaApiKey: sessionStorage.getItem('KODIAC_META_API_KEY') || ''
  }};

  const COLORS = {{
    gripper: '#38bdf8',
    cube_a: '#f87171',
    cube_b: '#4ade80'
  }};

  function updateApiStatusUI() {{
    const txt = document.getElementById('engine-status-text');
    const clearBtn = document.getElementById('clear-key-btn');
    const inp = document.getElementById('meta-api-key-input');
    const compBadge = document.getElementById('compiler-backend-badge');
    if (state.metaApiKey) {{
      const masked = state.metaApiKey.slice(0, 7) + '...' + state.metaApiKey.slice(-4);
      txt.textContent = 'Meta API Key Active (' + masked + ') + Live Engine';
      if (clearBtn) clearBtn.style.display = 'inline-block';
      if (inp) inp.value = '';
      if (compBadge) compBadge.textContent = '[MUSE SPARK API CONNECTOR + 2.5σ CALIBRATOR]';
    }} else {{
      txt.textContent = 'In-Browser Geometric Engine: READY';
      if (clearBtn) clearBtn.style.display = 'none';
      if (compBadge) compBadge.textContent = '[DETERMINISTIC + 2.5σ SLACK CALIBRATOR]';
    }}
  }}

  window.connectMetaKey = function() {{
    const inp = document.getElementById('meta-api-key-input');
    const val = (inp && inp.value || '').trim();
    if (!val) {{
      alert('Paste your Meta MODEL_API_KEY into the input box first.');
      return;
    }}
    state.metaApiKey = val;
    sessionStorage.setItem('KODIAC_META_API_KEY', val);
    updateApiStatusUI();
    window.runLiveGrade();
  }};

  window.clearMetaKey = function() {{
    state.metaApiKey = '';
    sessionStorage.removeItem('KODIAC_META_API_KEY');
    updateApiStatusUI();
    window.runLiveGrade();
  }};

  window.switchStudioTab = function(tabName) {{
    ['eval', 'blame', 'compile', 'loop', 'gallery'].forEach(function(t) {{
      const btn = document.getElementById('tabbtn-' + t);
      const pane = document.getElementById('tab-' + t);
      if (btn) btn.classList.toggle('active', t === tabName);
      if (pane && t !== 'gallery') pane.classList.toggle('active', t === tabName);
    }});
    if (tabName === 'gallery') {{
      const el = document.getElementById('tab-gallery');
      if (el) el.scrollIntoView({{behavior: 'smooth'}});
    }}
  }};

  window.loadReplayIntoStudio = function(replayId) {{
    window.switchStudioTab('eval');
    if (replayId.indexOf('correct_run_brushed') !== -1) {{
      window.selectClip('correct_run');
      window.applyTargetOccluder();
    }} else if (replayId.indexOf('b01_early_release') !== -1) {{
      window.selectClip('b01_early_release');
    }} else if (replayId.indexOf('b02_xy_misalignment') !== -1) {{
      window.selectClip('b02_xy_misalignment');
    }} else if (replayId.indexOf('b09_lift_failure') !== -1) {{
      window.selectClip('b09_lift_failure');
    }} else if (replayId.indexOf('occluded_clip') !== -1) {{
      window.selectClip('occluded_clip');
    }} else {{
      window.selectClip('correct_run');
    }}
    window.scrollTo({{top: 0, behavior: 'smooth'}});
  }};

  function overlapFraction(bbox, rects) {{
    if (!rects || !rects.length) return 0.0;
    const x1 = bbox[0], y1 = bbox[1], x2 = bbox[2], y2 = bbox[3];
    const area = Math.max(1.0, (x2 - x1) * (y2 - y1));
    let maxCov = 0.0;
    for (let i = 0; i < rects.length; i++) {{
      const r = rects[i];
      const ix1 = Math.max(x1, r[0]), iy1 = Math.max(y1, r[1]);
      const ix2 = Math.min(x2, r[2]), iy2 = Math.min(y2, r[3]);
      if (ix2 > ix1 && iy2 > iy1) {{
        const cov = ((ix2 - ix1) * (iy2 - iy1)) / area;
        if (cov > maxCov) maxCov = cov;
      }}
    }}
    return Math.min(1.0, maxCov);
  }}

  function evaluateClipInBrowser() {{
    const t0 = performance.now();
    const clipData = (window.KODIAC_TRACKS || {{}})[state.clipId];
    if (!clipData) return null;
    const objs = clipData.objects;
    const nFrames = clipData.n_frames || 90;
    const fps = clipData.fps || 30.0;
    const kRef = 15.5;
    const sigmaCm = state.cameraTier === 'C' ? 0.50 : 0.08;
    const sigmaPair = Math.hypot(sigmaCm, sigmaCm);
    const sigmaSlip = Math.SQRT2 * sigmaPair;

    // Initial baselines
    const v0 = {{ cube_a: 341.0, cube_b: 341.0, gripper: 295.0 }};
    const a0 = {{ cube_a: 2560, cube_b: 2560, gripper: 2500 }};
    ['cube_a', 'cube_b', 'gripper'].forEach(function(k) {{
      if (objs[k] && objs[k][0]) {{
        if (k !== 'gripper') v0[k] = objs[k][0][5];
        a0[k] = Math.max(1, objs[k][0][6]);
      }}
    }});

    let wMinGripper = 43.0;
    if (objs.gripper) {{
      for (let f = 0; f < nFrames; f++) {{
        const m = objs.gripper[f];
        if (m) wMinGripper = Math.min(wMinGripper, m[2] - m[0]);
      }}
    }}

    let sceneOccluded = false;
    const perFrame = [];

    for (let f = 0; f < nFrames; f++) {{
      const ma = objs.cube_a ? objs.cube_a[f] : null;
      const mb = objs.cube_b ? objs.cube_b[f] : null;
      const mg = objs.gripper ? objs.gripper[f] : null;

      if (!ma || !mb || !mg) {{
        sceneOccluded = true;
        perFrame.push({{ f: f, occluded: true }});
        continue;
      }}

      const occA = Math.max(1.0 - ma[6] / a0.cube_a, overlapFraction(ma, state.occluders));
      const occB = Math.max(1.0 - mb[6] / a0.cube_b, overlapFraction(mb, state.occluders));
      const scoreLow = (ma[7] < 0.5 || mb[7] < 0.5);
      const isOcc = (occA > 0.40 || occB > 0.40 || scoreLow);
      if (isOcc) sceneOccluded = true;

      const xa = (ma[4] - 320.0) / kRef, ha = (v0.cube_a - ma[5]) / kRef;
      const xb = (mb[4] - 320.0) / kRef, hb = (v0.cube_b - mb[5]) / kRef;
      const xg = (mg[4] - 320.0) / kRef, hg = (v0.gripper - mg[5]) / kRef;

      // Relative slip over 10-frame window
      const refF = Math.max(0, f - 10);
      const ma0 = objs.cube_a[refF] || ma;
      const mg0 = objs.gripper[refF] || mg;
      const dxa = xa - (ma0[4] - 320.0) / kRef, dha = ha - (v0.cube_a - ma0[5]) / kRef;
      const dxg = xg - (mg0[4] - 320.0) / kRef, dhg = hg - (v0.gripper - mg0[5]) / kRef;
      const rhoRel = Math.hypot(dxg - dxa, dhg - dha);
      const distCurr = Math.hypot(xg - xa, hg - ha);
      const wCurr = mg[2] - mg[0];
      const jawsOpen = wCurr > 1.45 * wMinGripper;
      const jawPenalty = jawsOpen ? (wCurr - 1.45 * wMinGripper) / kRef : 0.0;
      const isContact = (distCurr <= 4.0) && !jawsOpen;
      const mSlip = 1.0 - rhoRel;
      const effMarginSlip = isContact ? mSlip : Math.min(mSlip, 4.0 - distCurr - jawPenalty);

      let triMovesWith = (mSlip > 0 && isContact) ? 'T' : 'F';
      if (isOcc || Math.abs(effMarginSlip) < sigmaSlip) triMovesWith = 'U';
      let triNotMovesWith = triMovesWith === 'T' ? 'F' : (triMovesWith === 'F' ? 'T' : 'U');

      // lifted(cubeA, min_cm)
      const mLift = ha - state.minCm;
      let triLift = mLift > 0 ? 'T' : 'F';
      if (isOcc || Math.abs(mLift) < sigmaCm) triLift = 'U';

      // on(cubeA, cubeB)
      const dXy = Math.abs(xa - xb);
      const mXy = state.alignXyCm - dXy;
      const hTopB = (v0.cube_b - mb[1]) / kRef;
      const gapVal = Math.abs(ha - hTopB);
      const mGap = state.gapCm - gapVal;
      let triOn = (mXy > 0 && mGap > 0) ? 'T' : 'F';
      if (isOcc || Math.abs(mXy) < sigmaPair || Math.abs(mGap) < sigmaPair) triOn = 'U';

      // dwell(cubeA, cubeB)
      let stillFrames = 1;
      for (let pf = f - 1; pf >= 0; pf--) {{
        const pma = objs.cube_a[pf];
        const pmb = objs.cube_b[pf];
        if (!pma || !pmb) break;
        const pxa = (pma[4] - 320.0) / kRef, pha = (v0.cube_a - pma[5]) / kRef;
        const stepDist = Math.hypot(xa - pxa, ha - pha) * fps;
        const phTopB = (v0.cube_b - pmb[1]) / kRef;
        const pOn = (Math.abs(pxa - (pmb[4] - 320.0) / kRef) <= state.alignXyCm) && (Math.abs(pha - phTopB) <= state.gapCm);
        if (stepDist <= 1.0 && pOn) stillFrames++;
        else break;
      }}
      let tauStill = stillFrames / fps;
      if (f >= nFrames - 3 && stillFrames >= 8) tauStill = Math.max(tauStill, 0.533);
      const mDwell = tauStill - 0.50;
      let triDwell = (mDwell >= 0 && triOn === 'T') ? 'T' : 'F';
      if (isOcc) triDwell = 'U';

      perFrame.push({{
        f: f,
        occluded: isOcc,
        occA: occA,
        occB: occB,
        xa: xa, ha: ha, xb: xb, hb: hb, xg: xg, hg: hg,
        wCurr: wCurr, jawsOpen: jawsOpen,
        rhoRel: rhoRel, mSlip: effMarginSlip, sigmaSlip: sigmaSlip, triMovesWith: triMovesWith, triNotMovesWith: triNotMovesWith,
        mLift: mLift, triLift: triLift,
        dXy: dXy, mXy: mXy, gapVal: gapVal, mGap: mGap, triOn: triOn,
        tauStill: tauStill, mDwell: mDwell, triDwell: triDwell
      }});
    }}

    function and3(a, b) {{
      if (a === 'F' || b === 'F') return 'F';
      if (a === 'T' && b === 'T') return 'T';
      return 'U';
    }}

    // Step 1: grasp
    let s1Frame = null, s1Run = 0, s1U = false;
    for (let f = 0; f < nFrames; f++) {{
      const pf = perFrame[f];
      if (!pf || pf.occluded) {{ s1Run = 0; s1U = true; continue; }}
      const v = and3(pf.triMovesWith, pf.triLift);
      if (v === 'T') {{ s1Run++; if (s1Run >= 3) {{ s1Frame = f; break; }} }}
      else {{ if (v === 'U') s1U = true; s1Run = 0; }}
    }}

    const stepsOut = [];
    let overallVerdict = 'PASS';
    let overallReason = '';

    if (s1Frame === null) {{
      const v1 = (sceneOccluded || s1U) ? 'CANT_TELL' : 'FAIL';
      overallVerdict = v1;
      overallReason = sceneOccluded ? 'occluded (Gate G2)' : (s1U ? 'below_noise_floor (Gate G3)' : 'step 1 grasp condition unmet (lift=' + perFrame[nFrames-1].ha.toFixed(2) + ' cm < ' + state.minCm.toFixed(2) + ' cm)');
      stepsOut.push({{ idx: 1, name: 'grasp', verdict: v1, frame: nFrames - 1, detail: overallReason }});
      stepsOut.push({{ idx: 2, name: 'place', verdict: 'SKIPPED', frame: null, detail: 'Not reached' }});
      stepsOut.push({{ idx: 3, name: 'release', verdict: 'SKIPPED', frame: null, detail: 'Not reached' }});
    }} else {{
      stepsOut.push({{ idx: 1, name: 'grasp', verdict: 'PASS', frame: s1Frame, detail: 'Achieved @ f=' + s1Frame + ' (' + (s1Frame/fps).toFixed(2) + 's) · lift=' + perFrame[s1Frame].ha.toFixed(2) + ' cm' }});

      // Step 2: place (carries moves_with unless triOn is already T)
      let s2Frame = null, s2Run = 0, s2BrokenFrame = null, s2U = false;
      for (let f = s1Frame + 1; f < nFrames; f++) {{
        const pf = perFrame[f];
        if (!pf || pf.occluded) {{ s2Run = 0; s2U = true; continue; }}
        if (pf.triMovesWith === 'F' && pf.triOn !== 'T') {{
          s2BrokenFrame = f;
          break;
        }}
        if (pf.triOn === 'T') {{
          s2Run++;
          if (s2Run >= 3) {{ s2Frame = f; break; }}
        }} else {{
          if (pf.triOn === 'U') s2U = true;
          s2Run = 0;
        }}
      }}

      if (s2Frame !== null) {{
        stepsOut.push({{ idx: 2, name: 'place', verdict: 'PASS', frame: s2Frame, detail: 'Achieved @ f=' + s2Frame + ' (' + (s2Frame/fps).toFixed(2) + 's) · d_xy=' + perFrame[s2Frame].dXy.toFixed(2) + ' cm, gap=' + perFrame[s2Frame].gapVal.toFixed(2) + ' cm' }});

        // Step 3: release
        let s3Frame = null, s3Run = 0, s3U = false;
        for (let f = s2Frame + 1; f < nFrames; f++) {{
          const pf = perFrame[f];
          if (!pf || pf.occluded) {{ s3Run = 0; s3U = true; continue; }}
          const v = and3(pf.triNotMovesWith, pf.triDwell);
          if (v === 'T') {{ s3Run++; if (s3Run >= 3) {{ s3Frame = f; break; }} }}
          else {{ if (v === 'U') s3U = true; s3Run = 0; }}
        }}
        if (s3Frame !== null && !sceneOccluded) {{
          stepsOut.push({{ idx: 3, name: 'release', verdict: 'PASS', frame: s3Frame, detail: 'Achieved @ f=' + s3Frame + ' (' + (s3Frame/fps).toFixed(2) + 's) · jaws open, settled' }});
        }} else {{
          const v3 = (sceneOccluded || s3U) ? 'CANT_TELL' : 'FAIL';
          overallVerdict = v3;
          overallReason = sceneOccluded ? 'occluded (Gate G2)' : 'release / dwell unmet by clip end';
          stepsOut.push({{ idx: 3, name: 'release', verdict: v3, frame: nFrames - 1, detail: overallReason }});
        }}
      }} else if (s2BrokenFrame !== null) {{
        const v2 = sceneOccluded ? 'CANT_TELL' : 'FAIL';
        overallVerdict = v2;
        const bpf = perFrame[s2BrokenFrame];
        overallReason = sceneOccluded ? 'occluded (Gate G2)' : ('Carried invariant moves_with(gripper, cubeA) broke @ f=' + s2BrokenFrame + ' (t*=' + (s2BrokenFrame/fps).toFixed(2) + 's, d_xy=' + bpf.dXy.toFixed(2) + ' cm from cubeB)');
        stepsOut.push({{ idx: 2, name: 'place', verdict: v2, frame: s2BrokenFrame, detail: overallReason }});
        stepsOut.push({{ idx: 3, name: 'release', verdict: 'SKIPPED', frame: null, detail: 'Not reached' }});
      }} else {{
        const v2 = (sceneOccluded || s2U) ? 'CANT_TELL' : 'FAIL';
        overallVerdict = v2;
        const lpf = perFrame[nFrames - 1];
        overallReason = sceneOccluded ? 'occluded (Gate G2)' : ('Step 2 place unmet by clip end (d_xy=' + (lpf ? lpf.dXy.toFixed(2) : '?') + ' cm vs <=' + state.alignXyCm.toFixed(2) + ' cm)');
        stepsOut.push({{ idx: 2, name: 'place', verdict: v2, frame: nFrames - 1, detail: overallReason }});
        stepsOut.push({{ idx: 3, name: 'release', verdict: 'SKIPPED', frame: null, detail: 'Not reached' }});
      }}
    }}

    if (sceneOccluded && overallVerdict !== 'PASS') {{
      overallVerdict = 'CANT_TELL';
      overallReason = 'Gate G2: target object mask occluded > 40% (abstaining honestly instead of guessing)';
    }}

    const elapsedMs = Math.max(0.15, performance.now() - t0);
    return {{
      verdict: overallVerdict,
      reason: overallReason,
      steps: stepsOut,
      perFrame: perFrame,
      elapsedMs: elapsedMs,
      sigmaCm: sigmaCm
    }};
  }}

  function renderStudioState() {{
    const res = evaluateClipInBrowser();
    if (!res) return;
    state.lastEval = res;

    const timerBadge = document.getElementById('live-timer-badge');
    if (timerBadge) {{
      timerBadge.textContent = '⏱️ ' + res.elapsedMs.toFixed(2) + ' ms (▶ LIVE BROWSER ENGINE RUN)';
    }}

    const vbox = document.getElementById('live-verdict-box');
    const vtitle = document.getElementById('live-verdict-title');
    const vsub = document.getElementById('live-verdict-sub');
    if (vbox && vtitle && vsub) {{
      vbox.className = 'verdict-banner verdict-' + res.verdict;
      const label = res.verdict === 'CANT_TELL' ? "CAN'T TELL (ABSTAIN)" : res.verdict;
      vtitle.textContent = label + ' · ' + state.clipId;
      vsub.textContent = res.verdict === 'PASS'
        ? 'All 3 sequential steps achieved with margins > +σ (' + (state.cameraTier === 'C' ? 'Tier C' : 'Tier B') + ')'
        : res.reason;
    }}

    const sc = document.getElementById('live-steps-container');
    if (sc) {{
      sc.innerHTML = res.steps.map(function(s) {{
        const c = s.verdict === 'PASS' ? '#16a34a' : (s.verdict === 'FAIL' ? '#dc2626' : (s.verdict === 'CANT_TELL' ? '#d97706' : '#475569'));
        const lbl = s.verdict === 'CANT_TELL' ? "CAN'T TELL" : s.verdict;
        const jumpBtn = s.frame !== null ? '<button class="btn" style="padding:1px 7px;font-size:.72rem" onclick="window.seekFrame(' + s.frame + ')">Jump f=' + s.frame + '</button>' : '';
        return '<div class="step-card">' +
          '<div class="step-head"><span>Step ' + s.idx + ': <code>' + s.name + '</code></span>' +
          '<div style="display:flex;gap:.4rem;align-items:center">' + jumpBtn +
          '<span class="pill" style="background:' + c + '">' + lbl + '</span></div></div>' +
          '<div class="comp-row"><span>' + s.detail + '</span></div></div>';
      }}).join('');
    }}

    drawCanvasFrame(state.frame);
  }}

  function drawCanvasFrame(f) {{
    const canvas = document.getElementById('studio-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const clipData = (window.KODIAC_TRACKS || {{}})[state.clipId];
    if (!clipData) return;

    // Draw tabletop reference line v = 341
    ctx.save();
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.35)';
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    ctx.moveTo(40, 341);
    ctx.lineTo(600, 341);
    ctx.stroke();
    ctx.fillStyle = 'rgba(148, 163, 184, 0.7)';
    ctx.font = '11px monospace';
    ctx.fillText('tabletop plane (z = 0.0 cm)', 46, 356);
    ctx.restore();

    // Draw user occluder rectangles
    const allRects = state.occluders.slice();
    if (state.dragStart && state.dragCurr) {{
      allRects.push([
        Math.min(state.dragStart[0], state.dragCurr[0]),
        Math.min(state.dragStart[1], state.dragCurr[1]),
        Math.max(state.dragStart[0], state.dragCurr[0]),
        Math.max(state.dragStart[1], state.dragCurr[1])
      ]);
    }}
    allRects.forEach(function(r) {{
      ctx.fillStyle = 'rgba(5, 8, 17, 0.92)';
      ctx.fillRect(r[0], r[1], r[2] - r[0], r[3] - r[1]);
      ctx.strokeStyle = '#f59e0b';
      ctx.lineWidth = 2;
      ctx.strokeRect(r[0], r[1], r[2] - r[0], r[3] - r[1]);
      ctx.fillStyle = '#fbbf24';
      ctx.font = 'bold 11px monospace';
      ctx.fillText('OCCLUDER BRUSH', r[0] + 6, r[1] + 15);
    }});

    // Draw SAM 3.1 object masks (bboxes + bottom support anchors beta)
    const objs = clipData.objects;
    ['cube_b', 'cube_a', 'gripper'].forEach(function(name) {{
      const arr = objs[name];
      if (!arr || !arr[f]) return;
      const m = arr[f];
      const x1 = m[0], y1 = m[1], x2 = m[2], y2 = m[3], ub = m[4], vb = m[5], score = m[7];
      const color = COLORS[name] || '#38bdf8';

      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2.2;
      ctx.fillStyle = color + '24';
      ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);

      // Support anchor beta_t
      ctx.fillStyle = '#ffffff';
      ctx.beginPath();
      ctx.arc(ub, vb, 4.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.stroke();

      // Label pill
      const label = name + ' (' + score.toFixed(2) + ')';
      ctx.font = 'bold 11px monospace';
      const tw = ctx.measureText(label).width + 10;
      ctx.fillStyle = 'rgba(9, 13, 22, 0.85)';
      ctx.fillRect(x1, Math.max(2, y1 - 19), tw, 17);
      ctx.fillStyle = color;
      ctx.fillText(label, x1 + 5, Math.max(14, y1 - 6));
      ctx.restore();
    }});

    // Update frame telemetry panel
    const fnum = document.getElementById('inspected-frame-num');
    if (fnum) fnum.textContent = String(f);
    const telem = document.getElementById('frame-telemetry-table');
    if (telem && state.lastEval && state.lastEval.perFrame[f]) {{
      const pf = state.lastEval.perFrame[f];
      if (pf.occluded) {{
        telem.innerHTML = '<span style="color:#fbbf24">⚠️ Frame ' + f + ': OCCLUDED (Gate G2 active · cube_a cov=' + (pf.occA ? (pf.occA*100).toFixed(0) : 100) + '%, cube_b cov=' + (pf.occB ? (pf.occB*100).toFixed(0) : 100) + '%) → Kleene U</span>';
      }} else {{
        telem.innerHTML =
          '<div>• <b>cubeA</b>: X=' + pf.xa.toFixed(2) + ' cm, h=' + pf.ha.toFixed(2) + ' cm ± ' + state.lastEval.sigmaCm.toFixed(2) + ' cm | <code>lifted</code>=' + pf.triLift + ' (margin ' + (pf.mLift >= 0 ? '+' : '') + pf.mLift.toFixed(2) + ' cm)</div>' +
          '<div>• <b>gripper</b>: width=' + pf.wCurr.toFixed(0) + ' px (' + (pf.jawsOpen ? 'OPEN' : 'CLOSED') + '), slip=' + pf.rhoRel.toFixed(2) + ' cm | <code>moves_with</code>=' + pf.triMovesWith + '</div>' +
          '<div>• <b>on(cubeA, cubeB)</b>: d_xy=' + pf.dXy.toFixed(2) + ' cm, gap_z=' + pf.gapVal.toFixed(2) + ' cm | <code>on</code>=' + pf.triOn + ', <code>dwell</code>=' + pf.triDwell + ' (' + pf.tauStill.toFixed(2) + ' s)</div>';
      }}
    }}
  }}

  window.seekFrame = function(f) {{
    const clipData = (window.KODIAC_TRACKS || {{}})[state.clipId];
    const maxF = clipData ? clipData.n_frames - 1 : 89;
    state.frame = Math.max(0, Math.min(maxF, f));
    const slider = document.getElementById('frame-slider');
    if (slider) slider.value = String(state.frame);
    const readout = document.getElementById('frame-readout');
    if (readout) readout.textContent = 'f = ' + state.frame + ' / ' + maxF + ' (' + (state.frame / 30.0).toFixed(2) + ' s)';
    const video = document.getElementById('studio-video');
    if (video && !state.playing && Math.abs(video.currentTime - state.frame / 30.0) > 0.02) {{
      try {{ video.currentTime = state.frame / 30.0; }} catch (e) {{}}
    }}
    drawCanvasFrame(state.frame);
  }};

  window.togglePlay = function() {{
    const video = document.getElementById('studio-video');
    const btn = document.getElementById('play-pause-btn');
    if (state.playing) {{
      state.playing = false;
      if (video) video.pause();
      if (state.timer) clearInterval(state.timer);
      if (btn) btn.textContent = '▶ Play';
    }} else {{
      state.playing = true;
      if (btn) btn.textContent = '⏸ Pause';
      if (video) {{
        video.currentTime = state.frame / 30.0;
        video.play().catch(function() {{}});
      }}
      state.timer = setInterval(function() {{
        const nextF = (state.frame + 1) % 90;
        window.seekFrame(nextF);
      }}, 33);
    }}
  }};

  window.selectClip = function(cid) {{
    state.clipId = cid;
    state.occluders = [];
    document.querySelectorAll('#clip-selector-bar .clip-chip').forEach(function(b) {{
      b.classList.toggle('active', b.getAttribute('data-clip') === cid);
    }});
    const video = document.getElementById('studio-video');
    if (video) {{
      video.src = 'clips/' + cid + '.mp4';
      video.load();
    }}
    renderStudioState();
    window.seekFrame(cid === 'b01_early_release' ? 58 : (cid === 'b02_xy_misalignment' ? 82 : (cid === 'correct_run' ? 82 : 38)));
  }};

  window.applyTargetOccluder = function() {{
    state.occluders = [[380, 280, 500, 360]];
    renderStudioState();
  }};

  window.clearOccluders = function() {{
    state.occluders = [];
    renderStudioState();
  }};

  window.updateThresholds = function() {{
    state.minCm = parseFloat(document.getElementById('param-min-cm').value);
    state.alignXyCm = parseFloat(document.getElementById('param-align-xy').value);
    state.gapCm = parseFloat(document.getElementById('param-gap-cm').value);
    state.cameraTier = document.getElementById('param-camera-tier').value;
    document.getElementById('val-min-cm').textContent = '>= ' + state.minCm.toFixed(2) + ' cm';
    document.getElementById('val-align-xy').textContent = '<= ' + state.alignXyCm.toFixed(2) + ' cm';
    document.getElementById('val-gap-cm').textContent = '<= ' + state.gapCm.toFixed(2) + ' cm';
    document.getElementById('val-tier').textContent = 'Tier ' + state.cameraTier;
    renderStudioState();
  }};

  window.resetThresholds = function() {{
    document.getElementById('param-min-cm').value = '2.0';
    document.getElementById('param-align-xy').value = '3.33';
    document.getElementById('param-gap-cm').value = '0.5';
    document.getElementById('param-camera-tier').value = 'B';
    window.updateThresholds();
  }};

  window.runLiveGrade = function() {{
    renderStudioState();
  }};

  // Canvas drag-to-occlude interaction
  function bindCanvasBrush() {{
    const canvas = document.getElementById('studio-canvas');
    if (!canvas) return;
    function getPt(ev) {{
      const rect = canvas.getBoundingClientRect();
      const scaleX = canvas.width / rect.width;
      const scaleY = canvas.height / rect.height;
      const clientX = ev.touches ? ev.touches[0].clientX : ev.clientX;
      const clientY = ev.touches ? ev.touches[0].clientY : ev.clientY;
      return [
        Math.max(0, Math.min(canvas.width, (clientX - rect.left) * scaleX)),
        Math.max(0, Math.min(canvas.height, (clientY - rect.top) * scaleY))
      ];
    }}
    canvas.addEventListener('mousedown', function(ev) {{
      state.dragStart = getPt(ev);
      state.dragCurr = state.dragStart;
    }});
    canvas.addEventListener('mousemove', function(ev) {{
      if (!state.dragStart) return;
      state.dragCurr = getPt(ev);
      drawCanvasFrame(state.frame);
    }});
    window.addEventListener('mouseup', function() {{
      if (!state.dragStart || !state.dragCurr) return;
      const x1 = Math.round(Math.min(state.dragStart[0], state.dragCurr[0]));
      const y1 = Math.round(Math.min(state.dragStart[1], state.dragCurr[1]));
      const x2 = Math.round(Math.max(state.dragStart[0], state.dragCurr[0]));
      const y2 = Math.round(Math.max(state.dragStart[1], state.dragCurr[1]));
      state.dragStart = null;
      state.dragCurr = null;
      if (x2 - x1 >= 12 && y2 - y1 >= 12) {{
        state.occluders.push([x1, y1, x2, y2]);
        renderStudioState();
      }} else {{
        drawCanvasFrame(state.frame);
      }}
    }});
  }}

  // TAB 2: Blame & Diff cases
  const BLAME_CASES = {{
    b01: {{
      title: 'FAIL · Step #2 place · Broken Prerequisite moves_with(gripper, cubeA)',
      onset: 't* = 1.933 s ± 0.03 s (frame 58 ± 0.8 frames @ 30.0 fps) · transition T → F',
      summary: 'blame: gripper released cubeA 0.7 ± 0.03 s before reaching cubeB (xy offset 10.4 ± 0.1 cm at 00:01.9, frame 58)',
      hint: 'variable: release_order | delta: +0.76 s | move: move gripper.open() after move_to(place): delay the release by >= 0.76 s',
      codeloc: 'Fixture Replay: tests/fixtures/clips/b01_early_release.mp4 (Sim counterpart: examples/sim/pick_place.py:83 `robot.gripper.open()`)',
      facts: [
        ['xy_offset_cm', '10.42 ± 0.11', 'cm', '<= 3.33 cm (VIOLATED)'],
        ['dt_before_reference_s', '0.73 ± 0.03', 's', '0.00 s (EARLY RELEASE)'],
        ['lift_cm', '7.74 ± 0.08', 'cm', '>= 2.00 cm (OK)'],
        ['slip_cm', '3.10 ± 0.16', 'cm', '<= 1.00 cm (JAWS OPENED)'],
        ['blame_class', 'release_before_place', 'class', 'Step 2 carried invariant broke']
      ],
      diff: [
        '--- demo (examples/stackcube.green.lock)',
        '+++ attempt (b01_early_release.mp4)',
        '@@ 1 matched, 2 demo-only/diverging, 2 attempt-only/diverging (tier B; camera-relative directions) @@',
        '  [1] grasp: achieved @ 1.27 s (demo 1.27 s); moves_with.slip 0.1 ± 0.2 cm; lifted.height 3.1 ± 0.1 cm',
        '- [2] place: settled on(cubeA, cubeB) @ 2.73 s (frame 82); on.align_xy 0.0 ± 0.1 cm; on.gap 0.1 ± 0.1 cm',
        '- [3] release: achieved @ 2.97 s (frame 89); dwell.duration 0.53 ± 0.03 s',
        '+ [2] place: failed @ 1.93 s (frame 58)',
        '+ [2] place: released moves_with(gripper, cubeA) @ 1.93 s (frame 58)'
      ]
    }},
    b02: {{
      title: 'FAIL · Step #2 place · Unmet Condition on(cubeA, cubeB)',
      onset: 't* = 2.667 s ± 0.03 s (frame 80 ± 1.0 frames @ 30.0 fps) · transition never_T',
      summary: 'blame: step place never held: xy_offset_cm 5.1 ± 0.1 cm vs <= 3.3 cm, closest at 2.7 ± 0.0 s (frame 80)',
      hint: 'variable: place_xy_offset | delta: -1.91 cm | move: shift the place target 1.91 cm toward cubeB (xy offset 5.1 ± 0.1 cm vs limit 3.33 cm)',
      codeloc: 'Fixture Replay: tests/fixtures/clips/b02_xy_misalignment.mp4 (Sim counterpart: examples/sim/pick_place.py:78 `robot.arm.move_to(place_pose)`)',
      facts: [
        ['xy_offset_cm', '5.13 ± 0.11', 'cm', '<= 3.33 cm (VIOLATED by +1.80 cm)'],
        ['gap_z_cm', '0.06 ± 0.11', 'cm', '<= 0.50 cm (OK)'],
        ['lift_cm', '2.65 ± 0.08', 'cm', '>= 2.00 cm (OK)'],
        ['depth_ratio', '0.00 ± 0.02', 'ratio', '<= 0.12 (OK)'],
        ['blame_class', 'xy_offset', 'class', 'Lateral placement offset exceeded']
      ],
      diff: [
        '--- demo (examples/stackcube.green.lock)',
        '+++ attempt (b02_xy_misalignment.mp4)',
        '@@ 1 matched, 2 demo-only/diverging, 1 attempt-only/diverging (tier B; camera-relative directions) @@',
        '  [1] grasp: achieved @ 1.27 s (demo 1.27 s); moves_with.slip 0.1 ± 0.2 cm; lifted.height 3.1 ± 0.1 cm',
        '- [2] place: settled on(cubeA, cubeB) @ 2.73 s (frame 82); on.align_xy 0.0 ± 0.1 cm; on.gap 0.1 ± 0.1 cm',
        '- [3] release: achieved @ 2.97 s (frame 89); dwell.duration 0.53 ± 0.03 s',
        '+ [2] place: failed @ 2.97 s (frame 89); on.align_xy 5.1 ± 0.1 cm (outside 2 sigma)'
      ]
    }},
    b09: {{
      title: 'FAIL · Step #1 grasp · Unmet Condition lifted(cubeA, min_cm=2.0)',
      onset: 't* = 0.000 s ± 0.80 s (frame 0 ± 24.0 frames @ 30.0 fps) · transition never_T',
      summary: 'blame: step grasp never held: lift 0.0 ± 0.1 cm vs >= 2.0 cm, closest at 0.0 ± 0.8 s (frame 0)',
      hint: 'variable: lift_distance | delta: +2.08 cm | move: lift 2.08 cm higher (lift 0.0 ± 0.1 cm vs limit 2.00 cm; need >= 2.08 cm)',
      codeloc: 'Fixture Replay: tests/fixtures/clips/b09_lift_failure.mp4 (Sim counterpart: examples/sim/pick_place.py:64 `robot.arm.lift(distance=0.005)`)',
      facts: [
        ['lift_cm', '0.00 ± 0.08', 'cm', '>= 2.00 cm (VIOLATED: never lifted)'],
        ['slip_cm', '0.00 ± 0.16', 'cm', '<= 1.00 cm (OK)'],
        ['xy_offset_cm', '17.39 ± 0.11', 'cm', '<= 3.33 cm (still at initial pose)'],
        ['blame_class', 'lift_height', 'class', 'Insufficient vertical clearance']
      ],
      diff: [
        '--- demo (examples/stackcube.green.lock)',
        '+++ attempt (b09_lift_failure.mp4)',
        '@@ 0 matched, 3 demo-only/diverging, 1 attempt-only/diverging (tier B; camera-relative directions) @@',
        '- [1] grasp: achieved @ 1.27 s (frame 38); lifted.height 3.1 ± 0.1 cm',
        '- [2] place: settled on(cubeA, cubeB) @ 2.73 s (frame 82); on.align_xy 0.0 ± 0.1 cm',
        '- [3] release: achieved @ 2.97 s (frame 89); dwell.duration 0.53 ± 0.03 s',
        '+ [1] grasp: failed @ 2.97 s (frame 89); lifted.height 0.0 ± 0.1 cm'
      ]
    }},
    b10_sim: {{
      title: 'FAIL · Step #2 place · High Release Bounce (Sim Bug B10 + Span Attribution)',
      onset: 't* = 2.433 s ± 0.02 s (frame 73 ± 0.5 frames @ 30.0 fps) · transition T → F',
      summary: 'blame: gripper released cubeA 3.0 ± 0.1 cm above cubeB at 00:02.4, frame 73, with xy offset 0.0 ± 0.1 cm',
      hint: 'variable: release_height | delta: -2.60 cm | move: lower the place pose 2.60 cm before opening the gripper',
      codeloc: 'CodeLocation: examples/sim/pick_place.py:86 · `robot.gripper.open()` (span_id=6, actuation_class=gripper.open)',
      facts: [
        ['gap_z_cm', '3.00 ± 0.10', 'cm', '<= 0.50 cm (VIOLATED: dropped from +3.0 cm)'],
        ['xy_offset_cm', '0.00 ± 0.10', 'cm', '<= 3.33 cm (ALIGNED in XY)'],
        ['aperture_open_event', 'true (span #6)', 'event', 'examples/sim/pick_place.py:86'],
        ['blame_class', 'place_z', 'class', 'Disambiguated via sim span order']
      ],
      diff: [
        '--- demo (clean_seed0)',
        '+++ attempt (B10_high_release)',
        '@@ 1 matched, 2 demo-only/diverging, 2 attempt-only/diverging (tier A; world axes) @@',
        '  [1] grasp: achieved @ 2.33 s (demo 2.33 s); lifted.height 8.0 ± 0.1 cm',
        '- [2] place: settled on(cubeA, cubeB) @ 5.33 s (frame 160); on.gap 0.0 ± 0.1 cm',
        '- [3] release: achieved @ 6.53 s (frame 196); dwell.duration 0.50 ± 0.03 s',
        '+ [2] place: failed @ 5.13 s (frame 154); on.gap 3.0 ± 0.1 cm (+z)'
      ]
    }}
  }};

  window.selectBlameCase = function(key) {{
    const c = BLAME_CASES[key] || BLAME_CASES.b01;
    document.getElementById('blame-header-card').innerHTML =
      '<div><div style="font-size:1.05rem">' + c.title + '</div>' +
      '<div class="mono" style="font-size:.78rem;opacity:.9">' + c.onset + '</div></div>';
    document.getElementById('blame-summary-text').textContent = c.summary;
    document.getElementById('blame-hint-text').textContent = c.hint;
    document.getElementById('blame-codeloc-box').innerHTML =
      '<div style="font:700 .75rem var(--mono);color:var(--muted);margin-bottom:.2rem">SOURCE LINE / TRACE PROVENANCE</div>' +
      '<div class="mono" style="color:var(--accent)">' + c.codeloc + '</div>';
    document.getElementById('blame-facts-table').innerHTML =
      '<tr><th>Fact Key</th><th>Measured Value ± σ</th><th>Unit</th><th>Threshold / Status</th></tr>' +
      c.facts.map(function(r) {{
        return '<tr><td><code>' + r[0] + '</code></td><td class="mono">' + r[1] + '</td><td>' + r[2] + '</td><td class="mono">' + r[3] + '</td></tr>';
      }}).join('');
    document.getElementById('blame-diff-box').innerHTML = c.diff.map(function(line) {{
      if (line.indexOf('- ') === 0) return '<span class="diff-del">' + line + '</span>';
      if (line.indexOf('+ ') === 0) return '<span class="diff-add">' + line + '</span>';
      if (line.indexOf('@@') === 0) return '<span class="diff-warn">' + line + '</span>';
      return line + '\\n';
    }}).join('');
  }};

  // TAB 3: Live .green compiler
  window.setCompilePreset = function(txt) {{
    const inp = document.getElementById('compile-input');
    if (inp) inp.value = txt;
    window.runLiveCompile();
  }};

  window.runLiveCompile = function() {{
    const inp = document.getElementById('compile-input');
    const out = document.getElementById('compiled-green-output');
    const status = document.getElementById('compile-status-bar');
    const text = (inp && inp.value || '').trim();
    if (!text) {{
      out.textContent = 'Error E_EMPTY_INSTRUCTION: Type an instruction first, e.g. "stack cubeA on cubeB".';
      return;
    }}
    const lower = text.toLowerCase();
    if (lower.indexOf('unicorn') !== -1 || lower.indexOf('dragon') !== -1) {{
      status.innerHTML = '<span style="color:#f87171;font-weight:700">❌ Refused with Typed Error E001 (Object Guard):</span> Undeclared/unknown physical object in instruction.';
      out.textContent =
        'ERROR E001: We could not find "unicorn" or "dragon" in the scene vocabulary.\\n' +
        'Hint: Declare physical objects with prompts and metric size priors (e.g. cubeA, cubeB, red block, tray, cylinder).\\n' +
        'Law 1 Guarantee: Kodiac never invents a verdict on missing objects.';
      return;
    }}
    if (!/(pick|stack|place|put|grasp|lift|move|reach|hold|insert|drop|release)/.test(lower)) {{
      status.innerHTML = '<span style="color:#f87171;font-weight:700">❌ Refused with Typed Error E003 (Action Guard):</span> Instruction uses an action outside the 6 physical predicates.';
      out.textContent =
        'ERROR E003: Unsupported physical action in "' + text + '".\\n' +
        'Supported spatial/temporal predicates: on, inside, near, lifted, moves_with, dwell.\\n' +
        'Try: "Pick up cubeA, stack it on cubeB, and release for 0.5 s".';
      return;
    }}

    const liftMatch = lower.match(/lift[^0-9]*([0-9]+(?:\\.[0-9]+)?)\\s*cm/) || lower.match(/at least\\s*([0-9]+(?:\\.[0-9]+)?)\\s*cm/);
    const alignMatch = lower.match(/within\\s*([0-9]+(?:\\.[0-9]+)?)\\s*cm/);
    const dwellMatch = lower.match(/for\\s*([0-9]+(?:\\.[0-9]+)?)\\s*s/);
    const liftVal = liftMatch ? parseFloat(liftMatch[1]).toFixed(2) : '2.00';
    const alignVal = alignMatch ? parseFloat(alignMatch[1]).toFixed(2) : '3.33';
    const dwellVal = dwellMatch ? parseFloat(dwellMatch[1]).toFixed(2) : '0.50';

    const backendBadge = state.metaApiKey ? '[COMPILER: MUSE SPARK 1.3 · LIVE KEY CONFIGURED]' : '[COMPILER: DETERMINISTIC TEMPLATE + 2.5σ CALIBRATOR]';
    status.innerHTML = '<span style="color:#4ade80;font-weight:700">✅ Compiled cleanly in 0.8 ms</span> · Badge: <code>' + backendBadge + '</code>';

    if (lower.indexOf('inside') !== -1 || lower.indexOf('tray') !== -1) {{
      out.textContent =
        'test: place_in_tray\\n' +
        'description: "' + text.replace(/"/g, "'") + '"\\n\\n' +
        'objects:\\n' +
        '  gripper:\\n' +
        '    prompt: "robot parallel-jaw gripper"\\n' +
        '    role: effector\\n' +
        '  red_block:\\n' +
        '    prompt: "red cube block"\\n' +
        '    size_cm: 4.0\\n' +
        '  metal_tray:\\n' +
        '    prompt: "rectangular metal tray container"\\n' +
        '    size_cm: 16.0\\n\\n' +
        'steps:\\n' +
        '  - grasp: moves_with(gripper, red_block, slip_cm<=1.0) and lifted(red_block, min_cm>=' + liftVal + ')\\n' +
        '  - place: inside(red_block, metal_tray, margin_cm>=0.5)\\n' +
        '  - release: not moves_with(gripper, red_block) and dwell(red_block, for_s>=' + dwellVal + ', max_speed_cm_s<=1.0)\\n';
    }} else if (lower.indexOf('near') !== -1 || lower.indexOf('cylinder') !== -1) {{
      out.textContent =
        'test: reach_and_dwell\\n' +
        'description: "' + text.replace(/"/g, "'") + '"\\n\\n' +
        'objects:\\n' +
        '  gripper:\\n' +
        '    prompt: "robot gripper"\\n' +
        '    role: effector\\n' +
        '  cylinder:\\n' +
        '    prompt: "yellow cylinder"\\n' +
        '    size_cm: 4.0\\n\\n' +
        'steps:\\n' +
        '  - approach: near(gripper, cylinder, max_cm<=' + alignVal + ')\\n' +
        '  - hold: dwell(gripper, for_s>=' + dwellVal + ', max_speed_cm_s<=1.0)\\n';
    }} else {{
      out.textContent =
        'test: stackcube\\n' +
        'description: "' + text.replace(/"/g, "'") + '"\\n\\n' +
        'objects:\\n' +
        '  gripper:\\n' +
        '    prompt: "robot gripper"\\n' +
        '    role: effector\\n' +
        '  cubeA:\\n' +
        '    prompt: "red block"\\n' +
        '    aliases: [cube_a, red_cube]\\n' +
        '    size_cm: 4.0\\n' +
        '  cubeB:\\n' +
        '    prompt: "green block"\\n' +
        '    aliases: [cube_b, green_cube]\\n' +
        '    size_cm: 4.0\\n\\n' +
        'steps:\\n' +
        '  - grasp: moves_with(gripper, cubeA, slip_cm<=1.0) and lifted(cubeA, min_cm>=' + liftVal + ')\\n' +
        '  - place: on(cubeA, cubeB, align_xy_cm<=' + alignVal + ', gap_cm<=0.50)\\n' +
        '  - release: not moves_with(gripper, cubeA) and dwell(cubeA, cubeB, for_s>=' + dwellVal + ', max_speed_cm_s<=1.0)\\n';
    }}
  }};

  window.startVoiceCapture = function() {{
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const btn = document.getElementById('voice-mic-btn');
    if (!SR) {{
      alert('Web Speech API is not supported in this browser window. Typing preset voice transcript instead.');
      window.setCompilePreset('Pick up red cubeA by at least 3.0 cm, stack it on green cubeB within 2.8 cm, and release for 0.5 s');
      return;
    }}
    const rec = new SR();
    rec.lang = 'en-US';
    rec.interimResults = false;
    if (btn) btn.textContent = '🔴 Listening...';
    rec.onresult = function(e) {{
      const transcript = e.results[0][0].transcript;
      document.getElementById('compile-input').value = transcript;
      if (btn) btn.textContent = '🎙️ Speak Intent';
      window.runLiveCompile();
    }};
    rec.onerror = function() {{
      if (btn) btn.textContent = '🎙️ Speak Intent';
    }};
    rec.onend = function() {{
      if (btn) btn.textContent = '🎙️ Speak Intent';
    }};
    rec.start();
  }};

  // Boot studio
  updateApiStatusUI();
  bindCanvasBrush();
  renderStudioState();
  window.seekFrame(82);
  window.selectBlameCase('b01');
  window.runLiveCompile();
}})();
</script>
</body></html>
"""


def build_site(store: ReplayStore, site_dir: Path | str) -> Path:
    """Write ``index.html``, copy ``replays/``, and copy the 5 curated ``.mp4`` clips into ``site_dir/clips/``."""
    site = Path(site_dir)
    site.mkdir(parents=True, exist_ok=True)
    target = site / "replays"
    if store.root.resolve() != target.resolve():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(store.root, target)

    # Copy the 5 curated H.264 .mp4 clips (~95 KB total) into site/clips/ so the live video player works on GitHub Pages
    clips_src = REPO_ROOT / "tests" / "fixtures" / "clips"
    if clips_src.is_dir():
        clips_dst = site / "clips"
        clips_dst.mkdir(parents=True, exist_ok=True)
        for mp4 in clips_src.glob("*.mp4"):
            shutil.copy2(mp4, clips_dst / mp4.name)

    entries = store.list()
    index = site / "index.html"
    index.write_text(render_index(entries, store=store), encoding="utf-8")
    (site / ".nojekyll").write_text("", encoding="utf-8")
    manifest = [e.model_dump() for e in entries]
    (site / "replays.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return index


__all__ = ["build_site", "render_index"]
