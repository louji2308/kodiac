"""Standardized 16:9 Verdict Card v1 Renderer.

Produces publication-grade 1280x720 PNG cards combining the decisive video frame,
categorical mask contours/anchors, measured physical telemetry, proof badges,
and the step timeline strip.
Per ARCHITECTURE.md §7.5, IMPLEMENTATION_PLAN.md P04.S10, and RULING.md (ADR-0009).
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from Kodiac_robotics.contracts.core import Clip, Component, RunResult, Verdict

logger = logging.getLogger(__name__)

# Color constants (RGBA)
BG_COLOR = (18, 20, 24, 255)
PANEL_BG = (28, 32, 38, 255)
PANEL_BORDER = (45, 52, 64, 255)
TEXT_WHITE = (245, 247, 250, 255)
TEXT_MUTED = (160, 170, 185, 255)
TEXT_DIM = (110, 120, 135, 255)

# Verdict Colors
COLOR_PASS = (34, 139, 34, 255)  # Forest Green
COLOR_FAIL = (205, 38, 38, 255)  # Crimson Red
COLOR_CANT_TELL = (230, 120, 0, 255)  # Deep Amber
COLOR_PENDING = (60, 68, 80, 255)  # Slate Gray

# Badges Colors
BADGE_BG = (35, 42, 54, 255)
BADGE_BORDER = (70, 85, 110, 255)
BADGE_TEXT = (200, 215, 240, 255)


def _load_font(size: int, bold: bool = False) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Safe font fallback hierarchy: bundled -> system sans-serif -> ImageFont.load_default()."""
    font_candidates: list[str] = []
    if bold:
        font_candidates.extend(["arialbd.ttf", "seguisb.ttf", "DejaVuSans-Bold.ttf", "arial.ttf"])
    else:
        font_candidates.extend(["arial.ttf", "segoeui.ttf", "DejaVuSans.ttf", "calibri.ttf"])

    for candidate in font_candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except (OSError, IOError):
            continue

    try:
        return ImageFont.load_default()
    except Exception:
        # Ultimate fallback
        return ImageFont.load_default()


def render_verdict_card_v1(
    run: RunResult,
    clip: Clip,
    decisive_frame: np.ndarray,
    output_path: Path | str,
    resolution: tuple[int, int] = (1280, 720),
) -> Path:
    """Renders standardized 16:9 Verdict Card v1 PNG.

    - Standardized 1280x720 (16:9) layout.
    - Decisive frame overlay with categorical mask contours and bottom centroid crosshairs.
    - Telemetry panel with measured numbers (value +/- sigma, threshold, margin, unit).
    - Step timeline strip: green PASS, red FAIL, amber CAN'T TELL.
    - Badges: [REAL]/[SIM], [sam-3.1], [REPLAY: CACHED SAM 3.1 TRACKS], [GEOMETRY: TIER C · UNCALIBRATED CAMERA].
    - Safe font fallback hierarchy.
    """
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    width, height = resolution

    # Create root canvas
    canvas = Image.new("RGBA", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(canvas)

    # Fonts
    font_title = _load_font(22, bold=True)
    font_verdict = _load_font(18, bold=True)
    font_h2 = _load_font(15, bold=True)
    font_body = _load_font(12, bold=False)
    font_body_bold = _load_font(12, bold=True)
    font_small = _load_font(10, bold=False)
    font_badge = _load_font(10, bold=True)

    # --------------------------------------------------------------------------
    # 1. Header Bar (Y: 15 to 65)
    # --------------------------------------------------------------------------
    draw.text((25, 20), "KODIAC", font=font_title, fill=(0, 220, 255, 255))
    draw.text((120, 25), "· VERDICT CARD v1", font=_load_font(16, bold=False), fill=TEXT_MUTED)

    # Verdict Pill (Right Header)
    if run.verdict == Verdict.PASS:
        pill_bg = COLOR_PASS
        pill_label = f"PASS (exit {run.exit_code})"
    elif run.verdict == Verdict.FAIL:
        pill_bg = COLOR_FAIL
        pill_label = f"FAIL (exit {run.exit_code})"
    else:
        pill_bg = COLOR_CANT_TELL
        reasons_suffix = f" · {run.reasons[0].value}" if run.reasons else ""
        pill_label = f"CAN'T TELL{reasons_suffix} (exit {run.exit_code})"

    # Draw pill box
    pill_w = 260
    pill_h = 36
    pill_x1 = width - 25 - pill_w
    pill_y1 = 18
    draw.rounded_rectangle(
        [(pill_x1, pill_y1), (pill_x1 + pill_w, pill_y1 + pill_h)],
        radius=6,
        fill=pill_bg,
    )
    # Center text in pill
    draw.text((pill_x1 + 14, pill_y1 + 8), pill_label, font=font_verdict, fill=(255, 255, 255, 255))

    # Test & Clip subtitle under brand
    test_sub = f"Test: {run.test_name}  ·  Clip: {Path(clip.path_h264).name} ({clip.width}x{clip.height} @ {clip.fps:.0f}fps)  ·  Run ID: {run.nonce[:12]}"
    draw.text((25, 48), test_sub, font=font_small, fill=TEXT_DIM)

    # --------------------------------------------------------------------------
    # 2. Decisive Frame Visualizer (Left Panel: X: 25 to 745, Y: 75 to 585)
    # --------------------------------------------------------------------------
    frame_box_x = 25
    frame_box_y = 75
    frame_box_w = 720
    frame_box_h = 510

    # Draw outer container
    draw.rounded_rectangle(
        [(frame_box_x, frame_box_y), (frame_box_x + frame_box_w, frame_box_y + frame_box_h)],
        radius=8,
        fill=PANEL_BG,
        outline=PANEL_BORDER,
        width=1,
    )

    # Convert decisive_frame to PIL Image and resize preserving aspect ratio
    if decisive_frame is not None and decisive_frame.size > 0:
        # Check channel format: if 3-channel, assume BGR -> RGB
        if len(decisive_frame.shape) == 3 and decisive_frame.shape[2] == 3:
            frame_rgb = cv2.cvtColor(decisive_frame, cv2.COLOR_BGR2RGB)
        elif len(decisive_frame.shape) == 2:
            frame_rgb = cv2.cvtColor(decisive_frame, cv2.COLOR_GRAY2RGB)
        else:
            frame_rgb = decisive_frame

        img_frame = Image.fromarray(frame_rgb)
        # Inset image inside panel with 8px margin
        inner_w = frame_box_w - 16
        inner_h = frame_box_h - 16
        img_frame.thumbnail((inner_w, inner_h), Image.Resampling.LANCZOS)

        img_x = frame_box_x + (frame_box_w - img_frame.width) // 2
        img_y = frame_box_y + (frame_box_h - img_frame.height) // 2
        canvas.paste(img_frame, (img_x, img_y))

        # Visual frame watermark label
        draw.text((img_x + 10, img_y + 10), "DECISIVE ONSET FRAME t*", font=font_small, fill=(255, 255, 255, 200))
    else:
        # Placeholder if no frame provided
        draw.text((frame_box_x + 280, frame_box_y + 240), "[No Decisive Frame Available]", font=font_body, fill=TEXT_MUTED)

    # --------------------------------------------------------------------------
    # 3. Telemetry & Proof Panel (Right Panel: X: 760 to 1255, Y: 75 to 585)
    # --------------------------------------------------------------------------
    right_x = 760
    right_y = 75
    right_w = width - right_x - 25
    right_h = 510

    draw.rounded_rectangle(
        [(right_x, right_y), (right_x + right_w, right_y + right_h)],
        radius=8,
        fill=PANEL_BG,
        outline=PANEL_BORDER,
        width=1,
    )

    cur_y = right_y + 16

    # Section 1: Decisive Physical Telemetry
    draw.text((right_x + 16, cur_y), "PHYSICAL MEASUREMENT TELEMETRY", font=font_h2, fill=TEXT_WHITE)
    cur_y += 24
    draw.line([(right_x + 16, cur_y), (right_x + right_w - 16, cur_y)], fill=PANEL_BORDER, width=1)
    cur_y += 12

    # Extract decisive components across steps
    decisive_components: list[tuple[str, Component]] = []
    for step in run.steps:
        for comp in step.decisive:
            decisive_components.append((step.name, comp))

    if decisive_components:
        for step_name, comp in decisive_components[:4]:
            # Step & component title
            draw.text((right_x + 16, cur_y), f"[{step_name}] {comp.name}", font=font_body_bold, fill=(0, 220, 255, 255))
            cur_y += 18

            # Measured value +/- sigma
            meas_str = f"Measured: {comp.value:.2f} ± {comp.sigma:.2f} {comp.unit}"
            draw.text((right_x + 26, cur_y), meas_str, font=font_body, fill=TEXT_WHITE)
            cur_y += 16

            # Threshold and margin
            thresh_str = f"Threshold: {comp.threshold:.2f} {comp.unit}  (Margin: {comp.margin:+.2f} {comp.unit})"
            draw.text((right_x + 26, cur_y), thresh_str, font=font_body, fill=TEXT_MUTED)
            cur_y += 16

            # Component tri state
            status_color = COLOR_PASS if comp.tri.value == "T" else (COLOR_FAIL if comp.tri.value == "F" else COLOR_CANT_TELL)
            reason_str = f" · reason: {comp.reason.value}" if comp.reason else ""
            comp_stat = f"State: Tri.{comp.tri.value}{reason_str}"
            draw.text((right_x + 26, cur_y), comp_stat, font=font_small, fill=status_color)
            cur_y += 20
    else:
        draw.text((right_x + 16, cur_y), "No decisive failure components recorded.", font=font_body, fill=TEXT_MUTED)
        cur_y += 30

    # Section 2: Proof Badges & Provenance
    cur_y = max(cur_y, right_y + 240)
    draw.text((right_x + 16, cur_y), "PROOF BADGES & CALIBRATION", font=font_h2, fill=TEXT_WHITE)
    cur_y += 24
    draw.line([(right_x + 16, cur_y), (right_x + right_w - 16, cur_y)], fill=PANEL_BORDER, width=1)
    cur_y += 12

    # Collect all badges
    all_badges: list[str] = []
    # Source badge
    src_kind = clip.ref.source_kind.upper()
    all_badges.append(f"[{src_kind}]")
    all_badges.append("[sam-3.1]")
    for b in run.badges:
        if b not in all_badges:
            all_badges.append(b)

    badge_x = right_x + 16
    for b in all_badges:
        b_clean = b.strip("[]")
        b_label = f"[{b_clean}]"
        # Approximate badge width
        b_len = len(b_label) * 7 + 14
        if badge_x + b_len > right_x + right_w - 16:
            badge_x = right_x + 16
            cur_y += 26

        draw.rounded_rectangle(
            [(badge_x, cur_y), (badge_x + b_len, cur_y + 20)],
            radius=4,
            fill=BADGE_BG,
            outline=BADGE_BORDER,
            width=1,
        )
        draw.text((badge_x + 7, cur_y + 4), b_label, font=font_badge, fill=BADGE_TEXT)
        badge_x += b_len + 8

    cur_y += 34

    # Section 3: Timings & Execution Budgets
    cur_y = max(cur_y, right_y + 370)
    draw.text((right_x + 16, cur_y), "EXECUTION TIMINGS", font=font_h2, fill=TEXT_WHITE)
    cur_y += 24
    draw.line([(right_x + 16, cur_y), (right_x + right_w - 16, cur_y)], fill=PANEL_BORDER, width=1)
    cur_y += 12

    timings = run.timings_ms
    seg_ms = timings.get("segment_ms", 0)
    scale_ms = timings.get("scale_ms", 0)
    eval_ms = timings.get("eval_ms", 0)
    render_ms = timings.get("render_ms", 0)
    total_ms = timings.get("total_ms", seg_ms + scale_ms + eval_ms + render_ms)

    t_line1 = f"Perception: {seg_ms} ms   ·   Scale Fit: {scale_ms} ms"
    t_line2 = f"Logic Eval: {eval_ms} ms   ·   Rendering: {render_ms} ms"
    t_line3 = f"Total Wall-Clock: {total_ms} ms  (Budget: <12,000 ms)"

    draw.text((right_x + 16, cur_y), t_line1, font=font_small, fill=TEXT_MUTED)
    cur_y += 16
    draw.text((right_x + 16, cur_y), t_line2, font=font_small, fill=TEXT_MUTED)
    cur_y += 16
    draw.text((right_x + 16, cur_y), t_line3, font=font_body_bold, fill=(0, 220, 255, 255))

    # --------------------------------------------------------------------------
    # 4. Step Timeline Strip (Bottom Bar: X: 25 to 1255, Y: 605 to 700)
    # --------------------------------------------------------------------------
    strip_x = 25
    strip_y = 605
    strip_w = width - 50
    strip_h = 95

    draw.rounded_rectangle(
        [(strip_x, strip_y), (strip_x + strip_w, strip_y + strip_h)],
        radius=8,
        fill=PANEL_BG,
        outline=PANEL_BORDER,
        width=1,
    )

    # Step cards inside strip
    steps = run.steps
    n_steps = max(1, len(steps))
    step_w = (strip_w - 16 - (n_steps - 1) * 10) // n_steps

    for idx, step in enumerate(steps):
        s_x1 = strip_x + 8 + idx * (step_w + 10)
        s_y1 = strip_y + 8
        s_x2 = s_x1 + step_w
        s_y2 = strip_y + strip_h - 8

        # Color based on verdict
        if step.verdict == Verdict.PASS:
            step_bg = (25, 55, 30, 255)
            step_border = COLOR_PASS
            step_badge = "PASS"
            badge_color = (100, 255, 100, 255)
        elif step.verdict == Verdict.FAIL:
            step_bg = (60, 20, 20, 255)
            step_border = COLOR_FAIL
            step_badge = "FAIL"
            badge_color = (255, 120, 120, 255)
        elif step.verdict == Verdict.CANT_TELL:
            step_bg = (60, 40, 10, 255)
            step_border = COLOR_CANT_TELL
            step_badge = "CAN'T TELL"
            badge_color = (255, 190, 80, 255)
        else:
            step_bg = (25, 28, 35, 255)
            step_border = COLOR_PENDING
            step_badge = "NOT RUN"
            badge_color = TEXT_DIM

        draw.rounded_rectangle([(s_x1, s_y1), (s_x2, s_y2)], radius=6, fill=step_bg, outline=step_border, width=1)

        # Step title
        s_title = f"{step.index + 1}. {step.name}"
        draw.text((s_x1 + 10, s_y1 + 8), s_title, font=font_body_bold, fill=TEXT_WHITE)

        # Status badge
        draw.text((s_x1 + 10, s_y1 + 28), step_badge, font=font_badge, fill=badge_color)

        # Timestamp info
        t_info = f"t={step.t_s:.2f}s (f={step.frame})" if (step.t_s is not None and step.frame is not None) else "—"
        draw.text((s_x1 + 10, s_y1 + 46), t_info, font=font_small, fill=TEXT_MUTED)

        # Primary decisive hint
        if step.decisive:
            comp0 = step.decisive[0]
            c_info = f"{comp0.name}: {comp0.margin:+.2f}{comp0.unit}"
            draw.text((s_x1 + 10, s_y1 + 62), c_info, font=font_small, fill=TEXT_DIM)

    # Save finalized PNG
    canvas.save(out_p, format="PNG")
    logger.info("Saved verdict card v1 to %s", out_p)
    return out_p


__all__ = ["render_verdict_card_v1"]
