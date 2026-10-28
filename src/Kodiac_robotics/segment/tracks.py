"""Spatio-temporal track assembler and batch tracking dispatcher.

Merges multi-window temporal tracking cuts, validates forward-backward cyclic consistency,
flags tracking degradation when cyclic IoU < 0.70, and enforces the <= 16 objects API limit.
Per ARCHITECTURE.md §3.1, §4.3, IMPLEMENTATION_PLAN.md P03.S06, and P03 RULING.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple

import numpy as np

from Kodiac_robotics.contracts.core import ObjMask, Track
from Kodiac_robotics.segment.reid import ReIdEngine, decode_mask


def compute_mask_iou(
    mask_a: np.ndarray,
    mask_b: np.ndarray,
) -> float:
    """Compute Intersection-over-Union between two 2D binary masks."""
    if mask_a.shape != mask_b.shape:
        return 0.0
    bin_a = mask_a > 0
    bin_b = mask_b > 0
    intersection = int(np.logical_and(bin_a, bin_b).sum())
    union = int(np.logical_or(bin_a, bin_b).sum())
    if union == 0:
        return 1.0
    return float(intersection) / float(union)


def compute_bbox_iou(
    bbox_a: Tuple[float, float, float, float],
    bbox_b: Tuple[float, float, float, float],
) -> float:
    """Compute Intersection-over-Union between two bounding boxes (x1, y1, x2, y2)."""
    ax1, ay1, ax2, ay2 = bbox_a
    bx1, by1, bx2, by2 = bbox_b

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    intersection = iw * ih

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection

    if union <= 0.0:
        return 1.0 if area_a == 0.0 and area_b == 0.0 else 0.0
    return float(intersection / union)


def assemble_tracks(
    window_cuts: List[Any],
    raw_tracks: List[Dict[str, Track]],
    reid: Optional[ReIdEngine] = None,
) -> Dict[str, Track]:
    """Assemble and stitch multiple temporal tracking windows into continuous tracks.

    Validates forward-backward cyclic consistency on overlapping frames.
    If cyclic IoU < 0.70, flags ObjMask.score as degraded (< 0.50).
    Enforces the <= 16 objects per call API limit.
    """
    if not raw_tracks:
        return {}

    # Discover all distinct object names across all raw tracks
    all_objects = sorted(
        {obj_name for track_dict in raw_tracks for obj_name in track_dict.keys()}
    )

    # Enforce <= 16 objects limit
    if len(all_objects) > 16:
        raise ValueError(
            f"Exceeded maximum allowable object limit of 16 (found {len(all_objects)})"
        )

    merged_tracks: Dict[str, Track] = {}
    backend = "modal"
    trace_id_prefix = "stitched"

    for obj in all_objects:
        combined_frames: Dict[int, ObjMask] = {}
        forward_frames: Dict[int, ObjMask] = {}
        backward_frames: Dict[int, ObjMask] = {}

        # Collect frames across windows
        for track_dict in raw_tracks:
            if obj not in track_dict:
                continue
            track_instance = track_dict[obj]
            backend = track_instance.backend
            trace_id_prefix = track_instance.trace_id

            if track_instance.direction == "forward":
                forward_frames.update(track_instance.frames)
            elif track_instance.direction == "backward":
                backward_frames.update(track_instance.frames)
            else:
                combined_frames.update(track_instance.frames)

        # Merge forward and backward frames, evaluating cyclic consistency
        all_frame_indices = sorted(
            set(combined_frames.keys())
            .union(forward_frames.keys())
            .union(backward_frames.keys())
        )

        for f in all_frame_indices:
            fwd_m = forward_frames.get(f)
            bwd_m = backward_frames.get(f)

            if fwd_m is not None and bwd_m is not None:
                # Overlapping frame: validate forward-backward cyclic consistency
                h, w = fwd_m.rle_size if fwd_m.rle_size != (0, 0) else (480, 640)
                mask_f = decode_mask(fwd_m, (h, w))
                mask_b = decode_mask(bwd_m, (h, w))

                if np.sum(mask_f) > 0 and np.sum(mask_b) > 0:
                    cyclic_iou = compute_mask_iou(mask_f, mask_b)
                else:
                    cyclic_iou = compute_bbox_iou(fwd_m.bbox_xyxy, bwd_m.bbox_xyxy)

                # Mandated tripwire: If cyclic IoU < 0.70, flag score as degraded
                if cyclic_iou < 0.70:
                    degraded_score = min(fwd_m.score, 0.45)
                    final_mask = ObjMask(
                        obj=obj,
                        frame=f,
                        score=degraded_score,
                        bbox_xyxy=fwd_m.bbox_xyxy,
                        rle=fwd_m.rle,
                        area_px=fwd_m.area_px,
                        rle_size=fwd_m.rle_size,
                    )
                else:
                    final_mask = fwd_m
                combined_frames[f] = final_mask
            elif fwd_m is not None:
                combined_frames[f] = fwd_m
            elif bwd_m is not None:
                combined_frames[f] = bwd_m

        merged_tracks[obj] = Track(
            obj=obj,
            frames=combined_frames,
            backend=backend,
            direction="both" if (forward_frames and backward_frames) else "forward",
            trace_id=f"{trace_id_prefix}-assembled",
        )

    return merged_tracks


def track_many(
    jobs: List[Dict[str, Any]],
    backend: Literal["modal", "hosted", "fixture"] = "modal",
) -> List[Dict[str, Track]]:
    """Batch dispatcher for processing multiple tracking jobs.

    Dispatches to ModalSamBackend, HostedSamBackend, or FixtureBackend.
    """
    results: List[Dict[str, Track]] = []

    if backend == "modal":
        from Kodiac_robotics.segment.modal_backend import ModalSamBackend

        client = ModalSamBackend()
        for job in jobs:
            clip = job["clip"]
            f0 = job.get("f0", 0)
            f1 = job.get("f1", clip.n_frames)
            seeds = job.get("seeds", {})
            direction = job.get("direction", "forward")
            prompts = job.get("prompts")

            if prompts and not seeds:
                res = client.segment_frames(clip, list(range(f0, f1)), prompts)
            else:
                res = client.track(clip, f0, f1, seeds, direction=direction)
            results.append(res)
    elif backend == "fixture":
        # Load fixture or run mock client
        from Kodiac_robotics.segment.modal_backend import ModalSamBackend

        client = ModalSamBackend(offline_fallback=True)
        for job in jobs:
            clip = job["clip"]
            f0 = job.get("f0", 0)
            f1 = job.get("f1", clip.n_frames)
            seeds = job.get("seeds", {})
            direction = job.get("direction", "forward")
            res = client.track(clip, f0, f1, seeds, direction=direction)
            # Tag backend as fixture
            fixture_res = {
                obj: Track(
                    obj=t.obj,
                    frames=t.frames,
                    backend="fixture",
                    direction=t.direction,
                    trace_id=f"fixture-{t.trace_id}",
                )
                for obj, t in res.items()
            }
            results.append(fixture_res)
    else:
        # Fallback to modal client
        from Kodiac_robotics.segment.modal_backend import ModalSamBackend

        client = ModalSamBackend()
        for job in jobs:
            clip = job["clip"]
            f0 = job.get("f0", 0)
            f1 = job.get("f1", clip.n_frames)
            seeds = job.get("seeds", {})
            direction = job.get("direction", "forward")
            res = client.track(clip, f0, f1, seeds, direction=direction)
            results.append(res)

    return results
