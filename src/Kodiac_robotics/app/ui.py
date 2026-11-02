"""Gradio front end for the hosted demo (F53-F57).

Gradio is imported lazily inside ``build_ui`` so this module (and its pure rendering helpers) import and test
without it. The page never presents a cached replay as a live grade: replays render the ``⚡ CACHED`` badge and a
lookup time; ``Grade`` runs the engine now and shows only the measured wall-clock.
"""

from __future__ import annotations

import html
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np

from Kodiac_robotics.app.content import (
    CACHED_EXPLAINER,
    FIXTURE_EXPLAINER,
    LIMITS,
    MODEL_TABLE,
    PRIVACY,
    TAGLINE,
)
from Kodiac_robotics.app.errors import AppError

if TYPE_CHECKING:
    import gradio as gr

    from Kodiac_robotics.app.client import Client

VERDICT_COLORS = {"PASS": "#1a9850", "FAIL": "#d73027", "CANT_TELL": "#e08a00"}
VERDICT_LABEL = {"PASS": "PASS", "FAIL": "FAIL", "CANT_TELL": "CAN'T TELL"}

CSS = """
.kd-badge{display:inline-block;margin:2px 6px 2px 0;padding:2px 8px;border-radius:10px;
  background:#263238;color:#e0f7fa;font:600 12px/1.6 ui-monospace,monospace}
.kd-badge.kd-cached{background:#fff3cd;color:#7a5b00}
.kd-timer{font:700 28px/1.2 ui-monospace,monospace}
.kd-pill{display:inline-block;padding:4px 14px;border-radius:6px;color:#fff;font-weight:700;font-size:18px}
.kd-note{color:#555;font-size:13px}
"""

TICK_START_JS = """() => {
  const el = document.getElementById('kd-live-timer');
  if (!el) return;
  window.__kdT0 = performance.now();
  clearInterval(window.__kdTick);
  window.__kdTick = setInterval(() => {
    el.textContent = '⏱ running… ' + ((performance.now() - window.__kdT0) / 1000).toFixed(1) + ' s';
  }, 100);
}"""
TICK_STOP_JS = "() => { clearInterval(window.__kdTick); const el = document.getElementById('kd-live-timer'); if (el) el.textContent = ''; }"


def _badge_html(badges: list[str]) -> str:
    out = []
    for b in badges:
        cls = "kd-badge kd-cached" if "CACHED" in b else "kd-badge"
        out.append(f'<span class="{cls}">{html.escape(b)}</span>')
    return "".join(out)


def _fmt_s(ms: int | float) -> str:
    return f"{float(ms) / 1000.0:.2f} s"


def render_timer(payload: dict[str, Any], browser_ms: int | None = None) -> str:
    """HTML for the timer. Live: measured wall-clock only. Cached: lookup time + the original measured time."""
    if payload.get("cached"):
        rep = payload.get("replay", {})
        orig = payload.get("original_run_total_ms")
        return (
            f'<div class="kd-timer">⚡ CACHED replay · lookup {_fmt_s(payload["timer_ms"])}</div>'
            f'<div class="kd-note">Precomputed earlier (engine time then: {_fmt_s(orig or 0)}, '
            f"commit {html.escape(str(rep.get('source_commit', 'unknown')))}). "
            "This is not a live grade; press Grade to run the engine now.</div>"
        )
    extra = f" · browser round trip {_fmt_s(browser_ms)}" if browser_ms is not None else ""
    run_ms = payload.get("run", {}).get("timings_ms", {}).get("total_ms")
    inner = f" · engine {_fmt_s(run_ms)}" if run_ms is not None else ""
    return (
        f'<div class="kd-timer">⏱ {_fmt_s(payload["timer_ms"])} measured wall-clock</div>'
        f'<div class="kd-note">Server handler time{inner}{extra}. Shown as measured; no target is claimed.</div>'
    )


def render_verdict(payload: dict[str, Any]) -> str:
    run = payload["run"]
    v = str(run["verdict"])
    pill = f'<span class="kd-pill" style="background:{VERDICT_COLORS.get(v, "#555")}">{html.escape(VERDICT_LABEL.get(v, v))}</span>'
    reasons = ", ".join(str(r) for r in run.get("reasons", []))
    why = f' <span class="kd-note">reason: {html.escape(reasons)}</span>' if reasons else ""
    return f"{pill}{why}<div>{_badge_html(payload.get('badges', []))}</div>"


def render_details(payload: dict[str, Any]) -> str:
    """Markdown: per-step verdicts with measured numbers, occlusion info, compiled test, notes."""
    run = payload["run"]
    lines = [f"**Test:** `{run['test_name']}` · **Clip:** `{run['clip']['uri']}` · **Run:** `{run['run_id']}`", ""]
    lines += ["| step | verdict | measurement (value ± σ vs threshold) | reasons |", "|---|---|---|---|"]
    for s in run.get("steps", []):
        verdict = s.get("verdict")
        label = VERDICT_LABEL.get(str(verdict), "not evaluated") if verdict else "not evaluated"
        comps = "; ".join(
            f"{c['name']} {c['value']:.2f}±{c['sigma']:.2f}{c['unit']} (thr {c['threshold']:.2f})"
            for c in s.get("decisive", [])[:3]
        )
        reasons = ", ".join(str(r) for r in s.get("reasons", []))
        lines.append(f"| {s['index'] + 1}. {s['name']} | {label} | {comps or ' '} | {reasons or ' '} |")
    occ = payload.get("occlusion")
    if occ:
        cov = occ.get("max_covered_fraction", {})
        worst = ", ".join(f"{k} {v * 100:.0f}%" for k, v in cov.items() if v > 0) or "none of the tracked objects"
        how = " Masks emulated on cached tracks." if occ.get("emulated_on_cached_masks") else ""
        lines += ["", f"**Occluder:** {len(occ.get('rects', []))} rectangle(s) blackened on every frame. "
                      f"Max mask area covered: {worst}.{how}"]
    blame = run.get("blame")
    if blame:
        lines += ["", f"**Blame:** {blame.get('summary', '')}"]
    if payload.get("compiled_green"):
        lines += ["", "**Compiled test (template compiler, not a language model):**", "```", payload["compiled_green"], "```"]
    for n in payload.get("notes", []):
        lines.append(f"\n_{n}_")
    return "\n".join(lines)


def friendly_error_markdown(err: AppError) -> str:
    text = f"**{err.message}**"
    if err.hint:
        text += f"\n\n{err.hint}"
    if err.replay_url:
        text += "\n\nMeanwhile, open a ⚡ CACHED replay below (precomputed, not a live grade)."
    return text


def first_frame_rgb(video_path: str | Path) -> np.ndarray | None:
    cap = cv2.VideoCapture(str(video_path))
    try:
        ok, frame = cap.read()
    finally:
        cap.release()
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) if ok else None


def percent_rect_to_pixels(
    left: float, top: float, right: float, bottom: float, width: int, height: int
) -> list[int]:
    """Convert a rectangle given in percent of the frame to ``[x0, y0, x1, y1]`` pixels."""
    xs = sorted((left, right))
    ys = sorted((top, bottom))
    return [
        int(round(xs[0] / 100.0 * width)),
        int(round(ys[0] / 100.0 * height)),
        int(round(xs[1] / 100.0 * width)),
        int(round(ys[1] / 100.0 * height)),
    ]


def model_table_markdown() -> str:
    rows = ["| Meta model | What it does for Kodiac | On this page today |", "|---|---|---|"]
    rows += [f"| {m['model']} | {m['role']} | {m['status']} |" for m in MODEL_TABLE]
    return "\n".join(rows)


def build_ui(api_base: str | None = None, client: "Client | None" = None) -> "gr.Blocks":
    """Build the Blocks UI. ``api_base`` selects an HTTP server; otherwise an in-process app is created."""
    import gradio as gr

    from Kodiac_robotics.app.client import HttpClient, LocalClient

    if client is None:
        if api_base:
            client = HttpClient(api_base)
        else:
            from Kodiac_robotics.app.core import AppCore
            from Kodiac_robotics.app.settings import AppSettings

            client = LocalClient(AppCore(AppSettings()))

    cat = client.catalog()
    clip_choices = [(f"{c['id']} — {c['description']}", c["id"]) for c in cat["clips"]]
    clip_dims = {c["id"]: (c["width"], c["height"]) for c in cat["clips"]}
    test_choices = cat["tests"] or ["stackcube"]
    replay_choices = [(f"{r['title']} ({r['verdict']})", r["id"]) for r in cat["replays"]]
    health = client.health()

    def _peer(req: "gr.Request | None") -> str:
        host = getattr(getattr(req, "client", None), "host", None) if req is not None else None
        return host or "ui"

    def _show(payload: dict[str, Any], browser_ms: int | None = None):
        return (
            render_timer(payload, browser_ms),
            client.card_image(payload),
            render_verdict(payload),
            render_details(payload),
        )

    def _error(err: AppError):
        return ("", None, "", friendly_error_markdown(err))

    def _rects(use: bool, vals: tuple[float, float, float, float], dims: tuple[int, int] | None):
        if not use or dims is None:
            return None
        return [percent_rect_to_pixels(*vals, dims[0], dims[1])]

    def do_grade(
        source: str, clip_id, test_id, video, instruction, use_brush, bl, bt, br, bb, req: "gr.Request"
    ):
        t0 = time.perf_counter()
        try:
            if source == "dataset":
                dims = clip_dims.get(clip_id)
                payload = client.grade(
                    clip_id=clip_id,
                    test_id=test_id,
                    typed_instruction=instruction or None,
                    occlusion_rects=_rects(use_brush, (bl, bt, br, bb), dims),
                    client_hint=_peer(req),
                )
            else:
                if not video:
                    raise AppError("E_NO_VIDEO", "Choose or record a video first.")
                frame = first_frame_rgb(video)
                dims = (frame.shape[1], frame.shape[0]) if frame is not None else None
                payload = client.grade(
                    video_path=video,
                    test_id=test_id,
                    typed_instruction=instruction or None,
                    occlusion_rects=_rects(use_brush, (bl, bt, br, bb), dims),
                    client_hint=_peer(req),
                )
        except AppError as err:
            return _error(err)
        return _show(payload, int(round((time.perf_counter() - t0) * 1000)))

    def do_replay(replay_id):
        if not replay_id:
            return _error(AppError("E_NO_REPLAY", "Pick a cached replay first."))
        try:
            return _show(client.replay(replay_id))
        except AppError as err:
            return _error(err)

    def do_compile(text):
        try:
            res = client.compile(text)
        except AppError as err:
            return friendly_error_markdown(err)
        return (
            f"{_badge_html(res['badges'])}\n\n```\n{res['green']}\n```\n"
            f"Compiled in {_fmt_s(res['timer_ms'])} (deterministic template compiler)."
        )

    with gr.Blocks(title="Kodiac: Robots can finally fail a test.", css=CSS) as demo:
        gr.Markdown(f"# Kodiac: {TAGLINE}\nTests, `git bisect` and `git blame` for robots. Zero login.")
        gr.Markdown(
            f"**Backend:** `{health['backend']}` · **Mode:** `{health['mode']}`. "
            f"{FIXTURE_EXPLAINER if health['backend'] == 'fixture' else ''}\n\n{CACHED_EXPLAINER}"
        )

        with gr.Tabs():
            with gr.Tab("Dataset"):
                clip_dd = gr.Dropdown(clip_choices, value=clip_choices[0][1] if clip_choices else None, label="Curated clip")
                test_dd = gr.Dropdown(test_choices, value=test_choices[0], label="Example test")
                grade_ds = gr.Button("▶ GRADE (runs the engine now)", variant="primary")
            with gr.Tab("Upload"):
                up_video = gr.Video(label="Upload a clip (≤ 20 s, ≤ 50 MB)", sources=["upload"])
                up_test = gr.Dropdown(test_choices, value=test_choices[0], label="Example test")
                grade_up = gr.Button("▶ GRADE", variant="primary")
                gr.Markdown(
                    "Without a perception key this deployment can only grade the curated clips; an arbitrary "
                    "upload gets a clear message, never an invented verdict."
                )
            with gr.Tab("Webcam"):
                wc_video = gr.Video(label="Record ≤ 15 s (cover the lens to see CAN'T TELL)", sources=["webcam"])
                wc_test = gr.Dropdown(test_choices, value=test_choices[0], label="Example test")
                grade_wc = gr.Button("▶ GRADE", variant="primary")
            with gr.Tab("Teach it live"):
                gr.Markdown(
                    "Voice needs the Muse Voice key, which is not available here. Type the instruction; the "
                    "deterministic template compiler turns it into a test (badged as such)."
                )
                instr = gr.Textbox(label="Instruction", placeholder="stack cubeA on cubeB")
                compile_btn = gr.Button("Compile test")
                compiled_md = gr.Markdown()
                teach_clip = gr.Dropdown(clip_choices, value=clip_choices[0][1] if clip_choices else None, label="Curated clip to grade")
                grade_teach = gr.Button("▶ GRADE with this instruction", variant="primary")

        with gr.Accordion("Occlusion brush (apply a black rectangle to every frame)", open=False):
            use_brush = gr.Checkbox(label="Paint occluder", value=False)
            bl = gr.Slider(0, 100, value=60, step=1, label="left %")
            bt = gr.Slider(0, 100, value=55, step=1, label="top %")
            br = gr.Slider(0, 100, value=80, step=1, label="right %")
            bb = gr.Slider(0, 100, value=80, step=1, label="bottom %")
            gr.Markdown("The result shows how much of each tracked object the occluder covered.")

        timer_html = gr.HTML(elem_id="kd-timer-box", value="")
        gr.HTML('<div id="kd-live-timer" class="kd-timer"></div>')
        verdict_html = gr.HTML()
        card_img = gr.Image(label="Verdict card", type="filepath", interactive=False)
        details_md = gr.Markdown()

        gr.Markdown("### ⚡ Instant cached replays (precomputed, not live)")
        with gr.Row():
            replay_dd = gr.Dropdown(replay_choices, label="Cached replay", value=replay_choices[0][1] if replay_choices else None)
            replay_btn = gr.Button("⚡ Open cached replay")

        outs = [timer_html, card_img, verdict_html, details_md]
        brush_inputs = [use_brush, bl, bt, br, bb]
        src_ds, src_up, src_wc, src_teach = (gr.State(s) for s in ("dataset", "upload", "upload", "dataset"))
        none_state = gr.State(None)
        empty_text = gr.State("")

        def _bind(btn, src, clip, test, video, instruction):
            btn.click(None, js=TICK_START_JS, queue=False)
            btn.click(
                do_grade,
                [src, clip, test, video, instruction, *brush_inputs],
                outs,
            ).then(None, js=TICK_STOP_JS, queue=False)

        _bind(grade_ds, src_ds, clip_dd, test_dd, none_state, empty_text)
        _bind(grade_up, src_up, none_state, up_test, up_video, empty_text)
        _bind(grade_wc, src_wc, none_state, wc_test, wc_video, empty_text)
        _bind(grade_teach, src_teach, teach_clip, none_state, none_state, instr)
        compile_btn.click(do_compile, [instr], [compiled_md])
        replay_btn.click(do_replay, [replay_dd], outs)

        gr.Markdown("## Which Meta model does what\n" + model_table_markdown())
        gr.Markdown("## Limits we are honest about\n" + "\n".join(f"- {t}" for t in LIMITS))
        gr.Markdown(f"## Privacy\n{PRIVACY}")
    return demo


__all__ = [
    "build_ui",
    "first_frame_rgb",
    "friendly_error_markdown",
    "model_table_markdown",
    "percent_rect_to_pixels",
    "render_details",
    "render_timer",
    "render_verdict",
]

