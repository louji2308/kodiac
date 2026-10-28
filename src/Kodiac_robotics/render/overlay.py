"""Perception debug overlay renderer for masks, bboxes, crosshairs, and bottom anchors.

Renders high-contrast, anti-aliased visual overlays at native clip resolution
for single frames and video streams. Decoupled from verdict logic per P03 RULING.md.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import cv2
import numpy as np

from Kodiac_robotics.contracts.core import Clip, ObjMask, Track
from Kodiac_robotics.segment.rle import rle_to_mask

logger = logging.getLogger(__name__)

# High-contrast BGR categorical colors for default palette
DEFAULT_ROLE_COLORS: dict[str, tuple[int, int, int]] = {
    # Effectors: High-contrast Red
    "gripper": (0, 0, 240),
    "effector": (0, 0, 240),
    "hand": (0, 0, 240),
    "fingers": (0, 0, 240),
    "left_finger": (0, 0, 240),
    "right_finger": (0, 0, 240),
    # Rigid Target Objects: High-contrast Green
    "target": (0, 220, 0),
    "green_block": (0, 220, 0),
    "target_block": (0, 220, 0),
    "cube_b": (0, 220, 0),
    # Container / Destination Objects: High-contrast Blue
    "container": (240, 80, 0),
    "box": (240, 80, 0),
    "bin": (240, 80, 0),
    "blue_block": (240, 80, 0),
    # Secondary Objects: High-contrast Yellow, Magenta, Cyan
    "red_block": (0, 0, 240),
    "cube_a": (0, 200, 255),
    "yellow_block": (0, 220, 240),
}

FALLBACK_PALETTE: list[tuple[int, int, int]] = [
    (0, 220, 240),  # Yellow
    (240, 0, 240),  # Magenta
    (240, 220, 0),  # Cyan
    (0, 140, 255),  # Orange
    (200, 50, 150),  # Purple
    (50, 205, 50),  # Lime
]


class OverlayRenderer:
    """Perception debug overlay renderer (masks, bboxes, anchors)."""

    def __init__(self, alpha: float = 0.35, line_width: int = 2) -> None:
        """Initialize renderer.

        Parameters
        ----------
        alpha:
            Transparency factor for mask fill alpha blending in [0.0, 1.0].
        line_width:
            Thickness in pixels for contour outlines, crosshairs, and bounding boxes.
        """
        self.alpha = float(alpha)
        self.line_width = int(line_width)

    def _resolve_color(
        self,
        obj_name: str,
        color_palette: dict[str, tuple[int, int, int]] | None = None,
    ) -> tuple[int, int, int]:
        """Resolve BGR color for an object from explicit palette, role mapping, or fallback."""
        if color_palette and obj_name in color_palette:
            return color_palette[obj_name]

        name_lower = obj_name.lower()
        for role_key, color in DEFAULT_ROLE_COLORS.items():
            if role_key in name_lower:
                return color

        # Stable fallback index from object name hash
        idx = hash(obj_name) % len(FALLBACK_PALETTE)
        return FALLBACK_PALETTE[idx]

    def render_frame(
        self,
        frame_bgr: np.ndarray,
        masks: dict[str, ObjMask],
        color_palette: dict[str, tuple[int, int, int]] | None = None,
        bottom_anchors: dict[str, tuple[float, float]] | None = None,
        watermark: str | None = None,
    ) -> np.ndarray:
        """Render debug overlay on a single frame.

        Decodes RLE masks, blends mask hues with transparency alpha, draws 2px anti-aliased
        contours, centroid crosshairs, bounding boxes, and bottom anchor (beta) markers.

        Parameters
        ----------
        frame_bgr:
            Input BGR frame numpy array (H, W, 3).
        masks:
            Dictionary mapping object names to ObjMask instances.
        color_palette:
            Optional custom BGR color dictionary per object name.
        bottom_anchors:
            Optional dictionary of explicit (x, y) bottom anchor pixel coordinates.
        watermark:
            Optional text string to render on a high-contrast top banner.

        Returns
        -------
        np.ndarray:
            Annotated BGR frame copy at native resolution.
        """
        out = frame_bgr.copy()
        h, w = out.shape[:2]

        for obj_name, obj_mask in masks.items():
            color = self._resolve_color(obj_name, color_palette)

            # 1. Decode mask from RLE
            mask_shape = obj_mask.rle_size if obj_mask.rle_size != (0, 0) else (h, w)
            try:
                binary_mask = rle_to_mask(obj_mask.rle, mask_shape)
            except Exception as e:
                logger.debug("Failed decoding RLE for %s: %s", obj_name, e)
                binary_mask = np.zeros((h, w), dtype=np.uint8)

            # Resize if mask shape differs from frame
            if binary_mask.shape != (h, w):
                binary_mask = cv2.resize(
                    binary_mask,
                    (w, h),
                    interpolation=cv2.INTER_NEAREST,
                )

            mask_bool = binary_mask > 0

            # 2. Alpha blending for mask interior
            if np.any(mask_bool):
                overlay = out.copy()
                overlay[mask_bool] = color
                cv2.addWeighted(overlay, self.alpha, out, 1.0 - self.alpha, 0.0, dst=out)

                # 3. 2px anti-aliased contour outlines
                contours, _ = cv2.findContours(
                    binary_mask.astype(np.uint8),
                    cv2.RETR_EXTERNAL,
                    cv2.CHAIN_APPROX_SIMPLE,
                )
                cv2.drawContours(
                    out,
                    contours,
                    -1,
                    color,
                    self.line_width,
                    lineType=cv2.LINE_AA,
                )

                # 4. Centroid calculation and crosshair marker
                moments = cv2.moments(binary_mask.astype(np.uint8))
                if moments["m00"] > 0:
                    cx = int(round(moments["m10"] / moments["m00"]))
                    cy = int(round(moments["m01"] / moments["m00"]))
                else:
                    cx = int(round((obj_mask.bbox_xyxy[0] + obj_mask.bbox_xyxy[2]) / 2))
                    cy = int(round((obj_mask.bbox_xyxy[1] + obj_mask.bbox_xyxy[3]) / 2))
            else:
                cx = int(round((obj_mask.bbox_xyxy[0] + obj_mask.bbox_xyxy[2]) / 2))
                cy = int(round((obj_mask.bbox_xyxy[1] + obj_mask.bbox_xyxy[3]) / 2))

            # Draw centroid crosshair
            arm = 8
            cv2.line(out, (cx - arm, cy), (cx + arm, cy), color, self.line_width, cv2.LINE_AA)
            cv2.line(out, (cx, cy - arm), (cx, cy + arm), color, self.line_width, cv2.LINE_AA)
            cv2.circle(out, (cx, cy), 1, (255, 255, 255), -1)

            # 5. Bounding box & label tag
            if len(obj_mask.bbox_xyxy) == 4 and any(obj_mask.bbox_xyxy):
                bx0 = int(round(obj_mask.bbox_xyxy[0]))
                by0 = int(round(obj_mask.bbox_xyxy[1]))
                bx1 = int(round(obj_mask.bbox_xyxy[2]))
                by1 = int(round(obj_mask.bbox_xyxy[3]))
                cv2.rectangle(
                    out,
                    (bx0, by0),
                    (bx1, by1),
                    color,
                    max(1, self.line_width // 2),
                    lineType=cv2.LINE_AA,
                )

                label_text = f"{obj_name} ({obj_mask.score:.2f})"
                font_scale = 0.45
                thickness = 1
                (tw, th), baseline = cv2.getTextSize(
                    label_text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
                )
                tag_y0 = max(0, by0 - th - 6)
                cv2.rectangle(
                    out,
                    (bx0, tag_y0),
                    (bx0 + tw + 6, tag_y0 + th + 6),
                    (20, 20, 20),
                    -1,
                )
                cv2.putText(
                    out,
                    label_text,
                    (bx0 + 3, tag_y0 + th + 2),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale,
                    (255, 255, 255),
                    thickness,
                    cv2.LINE_AA,
                )

            # 6. Bottom anchor (beta) circle
            if bottom_anchors and obj_name in bottom_anchors:
                ax, ay = bottom_anchors[obj_name]
            elif np.any(mask_bool):
                ys, xs = np.where(mask_bool)
                max_y = int(np.max(ys))
                xs_at_bottom = xs[ys == max_y]
                ax = float(np.median(xs_at_bottom))
                ay = float(max_y)
            elif len(obj_mask.bbox_xyxy) == 4 and any(obj_mask.bbox_xyxy):
                ax = (obj_mask.bbox_xyxy[0] + obj_mask.bbox_xyxy[2]) / 2.0
                ay = float(obj_mask.bbox_xyxy[3])
            else:
                ax, ay = float(cx), float(cy)

            iax, iay = int(round(ax)), int(round(ay))
            cv2.circle(out, (iax, iay), 5, (10, 10, 10), 2, cv2.LINE_AA)
            cv2.circle(out, (iax, iay), 4, color, -1, cv2.LINE_AA)
            cv2.circle(out, (iax, iay), 1, (255, 255, 255), -1)

        # 7. Watermark banner across top
        if watermark:
            banner_h = 28
            banner_area = out[:banner_h, :]
            dark_strip = np.zeros_like(banner_area)
            cv2.addWeighted(dark_strip, 0.7, banner_area, 0.3, 0.0, dst=banner_area)
            out[:banner_h, :] = banner_area

            cv2.putText(
                out,
                watermark,
                (10, 19),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

        return out

    def render_video(
        self,
        clip: Clip,
        tracks: dict[str, Track],
        output_path: Path | str,
        color_palette: dict[str, tuple[int, int, int]] | None = None,
        watermark: str | None = None,
    ) -> Path:
        """Render debug overlays across all frames and stream to CFR H.264 MP4.

        Parameters
        ----------
        clip:
            Source Clip contract instance.
        tracks:
            Dictionary mapping object names to Track instances with per-frame ObjMask annotations.
        output_path:
            Target destination path for the rendered MP4 video.
        color_palette:
            Optional custom BGR color dictionary.
        watermark:
            Optional text string banner displayed across top.

        Returns
        -------
        Path:
            Resolved path of the generated overlay video.
        """
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        cap = cv2.VideoCapture(clip.path_h264)
        if not cap.isOpened():
            raise RuntimeError(f"Failed opening video for overlay rendering: {clip.path_h264}")

        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-s",
            f"{clip.width}x{clip.height}",
            "-pix_fmt",
            "bgr24",
            "-r",
            f"{clip.fps:.4f}",
            "-i",
            "-",
            "-vf",
            "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-vsync",
            "cfr",
            "-an",
            str(out_p),
        ]

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        frame_idx = 0
        try:
            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                # Extract masks active at this frame index
                frame_masks = {
                    name: trk.frames[frame_idx]
                    for name, trk in tracks.items()
                    if frame_idx in trk.frames
                }

                annotated = self.render_frame(
                    frame_bgr=frame,
                    masks=frame_masks,
                    color_palette=color_palette,
                    watermark=watermark,
                )

                proc.stdin.write(annotated.tobytes())
                frame_idx += 1
        finally:
            cap.release()
            stdout, stderr = proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg overlay rendering failed ({proc.returncode}):\n{stderr.decode(errors='replace')}"
            )

        return out_p
