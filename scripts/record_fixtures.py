"""Dual-mode fixture recorder for Kodiac perception.

Records deterministic perception fixtures from live Meta SAM 3.1 API (--live)
or generates geometrically valid synthetic fixtures directly from golden clips
(--synthetic offline bootstrap mode) per RULING.md §5 and IP-P03-D1-4.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

from Kodiac_robotics.contracts.core import Clip, ClipRef, ObjMask, Track
from Kodiac_robotics.segment.api import HostedSamBackend
from Kodiac_robotics.segment.prompts import get_prompt_set
from Kodiac_robotics.segment.rle import mask_to_rle, rle_area


def _extract_synthetic_masks_from_frame(
    frame: np.ndarray,
    prev_gripper_box: tuple[int, int, int, int] | None = None,
) -> dict[str, tuple[np.ndarray, tuple[float, float, float, float], float]]:
    """Extract synthetic masks for cube_a, cube_b, target, and gripper using HSV segmentation."""
    h, w, _ = frame.shape
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    kernel = np.ones((3, 3), np.uint8)

    results: dict[str, tuple[np.ndarray, tuple[float, float, float, float], float]] = {}

    # 1. cube_a: Red Cube (H in [0, 10] or [170, 180], S > 70, V > 50)
    r_raw = cv2.inRange(hsv, (0, 70, 50), (10, 255, 255)) | cv2.inRange(hsv, (170, 70, 50), (180, 255, 255))
    r_clean = cv2.morphologyEx(r_raw, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(r_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    r_box = (0.0, 0.0, 0.0, 0.0)
    r_bin = np.zeros((h, w), dtype=np.uint8)
    if contours:
        c = max(contours, key=cv2.contourArea)
        if cv2.contourArea(c) > 50:
            bx, by, bw, bh = cv2.boundingRect(c)
            r_box = (float(bx), float(by), float(bx + bw), float(by + bh))
            cv2.drawContours(r_bin, [c], -1, 1, thickness=cv2.FILLED)
            results["cube_a"] = (r_bin, r_box, 0.98)

    # 2. cube_b: Green Cube (H in [35, 85], S > 70, V > 50)
    g_raw = cv2.inRange(hsv, (35, 70, 50), (85, 255, 255))
    g_clean = cv2.morphologyEx(g_raw, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(g_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    g_box = (0.0, 0.0, 0.0, 0.0)
    g_bin = np.zeros((h, w), dtype=np.uint8)
    if contours:
        c = max(contours, key=cv2.contourArea)
        if cv2.contourArea(c) > 50:
            bx, by, bw, bh = cv2.boundingRect(c)
            g_box = (float(bx), float(by), float(bx + bw), float(by + bh))
            cv2.drawContours(g_bin, [c], -1, 1, thickness=cv2.FILLED)
            results["cube_b"] = (g_bin, g_box, 0.98)

            # 3. target: Top surface area of Green Cube
            target_bin = np.zeros((h, w), dtype=np.uint8)
            target_h = max(5, bh // 3)
            target_bin[by : by + target_h, bx : bx + bw] = 1
            target_box = (float(bx), float(by), float(bx + bw), float(by + target_h))
            results["target"] = (target_bin, target_box, 0.95)

    # 4. gripper: Dark/metallic robotic effector in upper/middle region
    grip_raw = cv2.inRange(hsv, (0, 0, 10), (180, 80, 150))
    # Filter out table region and cube pixels
    table_cutoff = int(h * 0.75)
    grip_raw[table_cutoff:, :] = 0
    if np.any(r_bin):
        grip_raw[r_bin > 0] = 0
    if np.any(g_bin):
        grip_raw[g_bin > 0] = 0

    grip_clean = cv2.morphologyEx(grip_raw, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(grip_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        # Choose contour closest to previous gripper box or largest in upper half
        valid_contours = [c for c in contours if cv2.contourArea(c) > 100]
        if valid_contours:
            c = max(valid_contours, key=cv2.contourArea)
            bx, by, bw, bh = cv2.boundingRect(c)
            grip_box = (float(bx), float(by), float(bx + bw), float(by + bh))
            grip_bin = np.zeros((h, w), dtype=np.uint8)
            cv2.drawContours(grip_bin, [c], -1, 1, thickness=cv2.FILLED)
            results["gripper"] = (grip_bin, grip_box, 0.92)

    return results


def record_synthetic_fixtures(clips_dir: Path, out_dir: Path) -> list[Path]:
    """Generate deterministic track fixtures directly from golden clips offline."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = clips_dir / "manifest.json"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Clips manifest not found at {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    written_paths: list[Path] = []
    clips_data = manifest.get("clips", {})

    for filename, clip_info in clips_data.items():
        clip_path = clips_dir / filename
        sha256 = clip_info["sha256"]
        out_file = out_dir / f"{sha256}.json"

        print(f"Generating synthetic fixture for {filename} (sha256: {sha256[:12]}...)...")
        cap = cv2.VideoCapture(str(clip_path))
        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        tracks_dict: dict[str, Track] = {
            "cube_a": Track(obj="cube_a", frames={}, backend="fixture", direction="both", trace_id=f"fixture-{sha256[:8]}"),
            "cube_b": Track(obj="cube_b", frames={}, backend="fixture", direction="both", trace_id=f"fixture-{sha256[:8]}"),
            "target": Track(obj="target", frames={}, backend="fixture", direction="both", trace_id=f"fixture-{sha256[:8]}"),
            "gripper": Track(obj="gripper", frames={}, backend="fixture", direction="both", trace_id=f"fixture-{sha256[:8]}"),
        }

        prev_gripper_box: tuple[int, int, int, int] | None = None

        for frame_idx in range(n_frames):
            ret, frame = cap.read()
            if not ret:
                break

            masks = _extract_synthetic_masks_from_frame(frame, prev_gripper_box)

            for obj_name, (bin_mask, bbox, score) in masks.items():
                rle_str = mask_to_rle(bin_mask)
                area = rle_area(rle_str, (h, w))

                obj_mask = ObjMask(
                    obj=obj_name,
                    frame=frame_idx,
                    score=score,
                    bbox_xyxy=bbox,
                    rle=rle_str,
                    area_px=area,
                    rle_size=(h, w),
                )
                tracks_dict[obj_name].frames[frame_idx] = obj_mask

                if obj_name == "gripper":
                    prev_gripper_box = (int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))

        cap.release()

        # Save fixture payload
        payload = {
            "clip_sha256": sha256,
            "clip_name": filename,
            "backend": "fixture",
            "is_fixture": True,
            "badge": "[FIXTURE REPLAY]",
            "n_frames": n_frames,
            "width": w,
            "height": h,
            "tracks": {name: t.model_dump() for name, t in tracks_dict.items()},
        }

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        written_paths.append(out_file)
        print(f"  -> Saved {out_file} ({out_file.stat().st_size} bytes)")

    return written_paths


def record_live_fixtures(clips_dir: Path, out_dir: Path) -> list[Path]:
    """Record fixtures from live Meta SAM 3.1 streaming API."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = clips_dir / "manifest.json"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    backend = HostedSamBackend()
    written_paths: list[Path] = []
    prompts = get_prompt_set("stack_cube")

    for filename, clip_info in manifest.get("clips", {}).items():
        clip_path = clips_dir / filename
        sha256 = clip_info["sha256"]
        out_file = out_dir / f"{sha256}.json"

        clip = Clip(
            ref=ClipRef(uri=f"file://{clip_path.resolve()}", source_kind="sim"),
            path_h264=str(clip_path),
            fps=clip_info["fps"],
            n_frames=clip_info["n_frames"],
            width=clip_info["width"],
            height=clip_info["height"],
            sha256=sha256,
        )

        print(f"Calling live SAM 3.1 API for {filename}...")
        frames = list(range(clip.n_frames))
        tracks = backend.segment_frames(clip, frames, prompts=prompts)

        # Force fixture watermark on stored output
        payload = {
            "clip_sha256": sha256,
            "clip_name": filename,
            "backend": "fixture",
            "is_fixture": True,
            "badge": "[FIXTURE REPLAY]",
            "n_frames": clip.n_frames,
            "width": clip.width,
            "height": clip.height,
            "tracks": {name: t.model_dump() for name, t in tracks.items()},
        }

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        written_paths.append(out_file)
        print(f"  -> Saved {out_file}")

    return written_paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Record Kodiac perception fixtures (dual-mode).")
    parser.add_argument(
        "--mode",
        choices=["synthetic", "live"],
        default="synthetic",
        help="Recording mode: synthetic (offline bootstrap) or live (Meta SAM API)",
    )
    parser.add_argument("--synthetic", dest="mode", action="store_const", const="synthetic")
    parser.add_argument("--live", dest="mode", action="store_const", const="live")
    parser.add_argument(
        "--clips-dir",
        type=Path,
        default=Path("tests/fixtures/clips"),
        help="Directory containing golden MP4 clips and manifest.json",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("tests/fixtures/tracks"),
        help="Directory to write fixture JSON files",
    )

    args = parser.parse_args()

    if args.mode == "synthetic":
        print("=== Recording Fixtures in Offline Synthetic Mode ===")
        paths = record_synthetic_fixtures(args.clips_dir, args.out_dir)
        print(f"Successfully recorded {len(paths)} fixture files in {args.out_dir}.")
        return 0
    else:
        print("=== Recording Fixtures from Live Meta SAM 3.1 API ===")
        try:
            paths = record_live_fixtures(args.clips_dir, args.out_dir)
            print(f"Successfully recorded {len(paths)} live fixture files in {args.out_dir}.")
            return 0
        except Exception as e:
            print(f"Error recording live fixtures: {e}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    sys.exit(main())
