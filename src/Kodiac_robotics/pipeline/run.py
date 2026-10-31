"""End-to-end execution pipeline for Kodiac evaluation.

Integrates video normalization, spatio-temporal segmentation, metric scale recovery,
evaluation gates G1-G6, Kleene step logic, audit tracing, and verdict card rendering.
Per ARCHITECTURE.md §3.1, §4.4, IMPLEMENTATION_PLAN.md P04.S08, and P04 RULING.md (ADR-0009).
"""

from __future__ import annotations

import logging
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

from Kodiac_robotics.contracts.core import (
    Clip,
    ClipRef,
    GreenTest,
    PredFrame,
    ReasonCode,
    RunResult,
    ScaleModel,
    Track,
    Verdict,
)
from Kodiac_robotics.engine.steps import evaluate_step_chain
from Kodiac_robotics.engine.trace import TraceWriter
from Kodiac_robotics.geometry.scale import TierCScaleModel, fit_scale_model
from Kodiac_robotics.io.clip import open_clip
from Kodiac_robotics.pipeline.loader import load_green_test
from Kodiac_robotics.predicates.base import conjoin_components, get_atom_key
from Kodiac_robotics.predicates.dispatch import evaluate_atom
from Kodiac_robotics.render.card import render_verdict_card_v1
from Kodiac_robotics.segment.fixture import ROLE_ALIASES, FixtureBackend
from Kodiac_robotics.uncertainty.gates import apply_gates

logger = logging.getLogger(__name__)


def _harmonize_track_keys(
    tracks: dict[str, Track],
    test: GreenTest,
) -> dict[str, Track]:
    """Ensure all declared objects in GreenTest have corresponding keys in tracks."""
    harmonized = dict(tracks)
    for decl in test.objects:
        obj_name = decl.name
        if obj_name in harmonized:
            continue

        target_norm = obj_name.lower().replace("_", "").replace("-", "")

        matched: Track | None = None
        for k, tr in tracks.items():
            k_norm = k.lower().replace("_", "").replace("-", "")
            if k_norm == target_norm:
                matched = tr
                break

            if k in ROLE_ALIASES and ROLE_ALIASES[k] == obj_name.lower():
                matched = tr
                break
            if obj_name.lower() in ROLE_ALIASES and ROLE_ALIASES[obj_name.lower()] == k:
                matched = tr
                break

        if not matched and decl.aliases:
            for alias in decl.aliases:
                if alias in tracks:
                    matched = tracks[alias]
                    break

        if not matched:
            if "cubea" in target_norm or "red" in target_norm:
                for cand in ("cube_a", "cubeA", "red_block", "red_cube"):
                    if cand in tracks:
                        matched = tracks[cand]
                        break
            elif "cubeb" in target_norm or "green" in target_norm:
                for cand in ("cube_b", "cubeB", "green_block", "green_cube"):
                    if cand in tracks:
                        matched = tracks[cand]
                        break

        if matched:
            harmonized[obj_name] = matched.model_copy(update={"obj": obj_name})

    return harmonized


def run(
    test: GreenTest | Path | str,
    clip: ClipRef | Path | str,
    mode: Literal["full", "fast"] = "full",
    tracks: dict[str, Track] | None = None,
    backend: Literal["api", "modal", "fixture"] = "fixture",
    render_card: bool = False,
    output_dir: Path | None = None,
    camera: Literal["tier_a", "tier_b", "tier_c"] | None = None,
    cam_K: np.ndarray | None = None,
    cam_extrinsic: np.ndarray | None = None,
) -> RunResult:
    """Executes a Green test over a video clip.

    - If tracks is provided: sets is_fixture=True, adds badge '[REPLAY: CACHED SAM 3.1 TRACKS]',
      bypasses segmenters, and evaluates directly.
    - Measures per-stage timings (segment_ms, scale_ms, eval_ms, render_ms, total_ms).
    - Generates 16-hex nonce run_id.
    - Writes run artifacts: runs/<id>/result.json, runs/<id>/trace.jsonl, and .Kodiac/last_verdict.json.
    - If render_card is True: renders 16:9 Verdict Card v1 PNG to runs/<id>/card.png.
    - Returns RunResult model instance.
    """
    total_start = time.perf_counter()
    badges: list[str] = []
    backends_map: dict[str, str] = {}

    # 1. Load Test Specification
    test_obj, test_sha256 = load_green_test(test)

    # 2. Open & Normalize Video Clip
    if isinstance(clip, Clip):
        clip_obj = clip
    else:
        clip_obj = open_clip(clip)

    # 3. Perception & Tracking Stage
    t_seg0 = time.perf_counter()
    is_fixture = False

    if tracks is not None:
        # Direct stored-track replay
        is_fixture = True
        badges.append("[REPLAY: CACHED SAM 3.1 TRACKS]")
        backends_map["perception"] = "cached_replay"
        resolved_tracks = dict(tracks)
        segment_ms = 0
    else:
        if backend == "fixture":
            is_fixture = True
            fb = FixtureBackend()
            resolved_tracks = fb._load_tracks(clip_obj)
            badges.append("[FIXTURE REPLAY]")
            backends_map["perception"] = "fixture"
        elif backend == "modal":
            from Kodiac_robotics.segment.modal_backend import ModalSamBackend

            mb = ModalSamBackend(offline_fallback=True)
            prompts = {obj.name: [obj.name] for obj in test_obj.objects}
            seeds = mb.segment_frames(clip_obj, [0], prompts)
            resolved_tracks = mb.track(clip_obj, 0, clip_obj.n_frames, seeds)
            badges.append("[MODAL SAM 3.1]")
            backends_map["perception"] = "modal"
        else:
            from Kodiac_robotics.segment.api import HostedSamBackend

            hb = HostedSamBackend()
            prompts = {obj.name: [obj.name] for obj in test_obj.objects}
            seeds = hb.segment_frames(clip_obj, [0], prompts)
            resolved_tracks = hb.track(clip_obj, 0, clip_obj.n_frames, seeds)
            badges.append("[sam-3.1]")
            backends_map["perception"] = "api"

        segment_ms = int(round((time.perf_counter() - t_seg0) * 1000))

    # Harmonize object track keys
    harmonized_tracks = _harmonize_track_keys(resolved_tracks, test_obj)

    # 4. Metric Scale Model Fitting Stage
    t_scale0 = time.perf_counter()
    if camera == "tier_c":
        scale: ScaleModel = TierCScaleModel(
            tracks=harmonized_tracks, objects=test_obj.objects, clip=clip_obj
        )
    else:
        scale = fit_scale_model(
            clip=clip_obj,
            tracks=harmonized_tracks,
            objects=test_obj.objects,
            cam_K=cam_K,
            cam_extrinsic=cam_extrinsic,
        )

    # Memoize scale.to_table_frame to ensure evaluation < 200ms
    orig_to_table = scale.to_table_frame
    coord_cache: dict[tuple[str, int], tuple[float, float, float, float]] = {}

    def cached_to_table(obj: str, frame: int) -> tuple[float, float, float, float]:
        k = (obj, frame)
        if k not in coord_cache:
            coord_cache[k] = orig_to_table(obj, frame)
        return coord_cache[k]

    scale.to_table_frame = cached_to_table  # type: ignore[method-assign]

    scale_ms = int(round((time.perf_counter() - t_scale0) * 1000))

    if hasattr(scale, "badges"):
        for b in scale.badges:
            if b not in badges:
                badges.append(b)
    backends_map["scale_tier"] = getattr(scale, "tier", "C")

    # 5. Predicate & Step Evaluation Stage
    t_eval0 = time.perf_counter()

    # Pre-extract all atoms across steps
    all_atoms = []
    for step in test_obj.steps:
        from Kodiac_robotics.engine.steps import _extract_atoms

        all_atoms.extend(_extract_atoms(step.expr))

    # Extract raw frame for Gate G4 view blocked checks if available
    raw_first_frame: np.ndarray | None = None
    try:
        cap = cv2.VideoCapture(clip_obj.path_h264)
        ret, frame0 = cap.read()
        if ret:
            raw_first_frame = frame0
        cap.release()
    except Exception:
        pass

    pred_frames_by_atom: dict[str, list[PredFrame]] = {}
    all_triggered_reasons: set[ReasonCode] = set()

    # Check overall scene occlusion on declared non-effector objects
    scene_occluded = False
    for decl in test_obj.objects:
        if decl.role == "effector":
            continue
        tr = harmonized_tracks.get(decl.name)
        if tr is None:
            scene_occluded = True
            break
        if not tr.frames:
            scene_occluded = True
            break
        f0 = min(tr.frames.keys())
        a0 = max(1, tr.frames[f0].area_px)
        for f_idx in range(clip_obj.n_frames):
            if f_idx not in tr.frames:
                scene_occluded = True
                break
            m = tr.frames[f_idx]
            if m.score < 0.5:
                scene_occluded = True
                break
            # Calculate occlusion fraction
            occ_frac = float(np.clip(1.0 - float(m.area_px) / float(a0), 0.0, 1.0))
            if occ_frac > 0.40:
                scene_occluded = True
                break
        if scene_occluded:
            break

    eval_context = {
        "object_sizes": {o.name: (o.size_cm or 4.0) for o in test_obj.objects},
        "object_heights": {o.name: (o.size_cm or 4.0) for o in test_obj.objects},
    }

    # Evaluate each atom across all frames
    for atom in all_atoms:
        atom_key = get_atom_key(atom)
        if atom_key in pred_frames_by_atom:
            continue

        frames_list: list[PredFrame] = []
        for f in range(clip_obj.n_frames):
            pf = evaluate_atom(
                atom, harmonized_tracks, scale, f, clip_obj.fps, context=eval_context
            )

            # Round precision to avoid floating point epsilon noise floor misfires
            for c in pf.components:
                c.margin = round(c.margin, 6)
                c.sigma = round(c.sigma, 6)

            # Apply Gates G1-G6
            gated_comps, triggered_reasons = apply_gates(
                pf.components,
                harmonized_tracks,
                scale,
                f,
                raw_frame=raw_first_frame if f == 0 else None,
            )
            all_triggered_reasons.update(triggered_reasons)

            gated_tri = conjoin_components(gated_comps)
            gated_pf = PredFrame(
                frame=f,
                atom_key=atom_key,
                tri=gated_tri,
                components=gated_comps,
                trace_id=pf.trace_id,
            )
            frames_list.append(gated_pf)

        pred_frames_by_atom[atom_key] = frames_list

    # Step Chain Logic Evaluation
    verdict, step_results, top_reasons, events = evaluate_step_chain(
        test_obj.steps, pred_frames_by_atom, clip_obj.fps
    )

    # If scene suffered severe occlusion on non-effector objects and was not a PASS,
    # Gate G2 enforces honest CANT_TELL per Invariant I3 and ADR-0010
    final_reasons: list[ReasonCode] = []
    if scene_occluded and verdict != Verdict.PASS:
        verdict = Verdict.CANT_TELL
        final_reasons = [ReasonCode.OCCLUDED]
        for s in step_results:
            if s.verdict in (Verdict.FAIL, None):
                s.verdict = Verdict.CANT_TELL
                s.reasons = [ReasonCode.OCCLUDED]
    elif verdict == Verdict.CANT_TELL:
        if top_reasons:
            final_reasons = list(top_reasons)
        else:
            for s in step_results:
                if s.reasons:
                    final_reasons.extend(s.reasons)
            if not final_reasons and all_triggered_reasons:
                final_reasons = list(all_triggered_reasons)
            if not final_reasons:
                final_reasons = [ReasonCode.NOT_VISIBLE]

    eval_ms = int(round((time.perf_counter() - t_eval0) * 1000))

    # 6. Generate 16-hex nonce and paths
    nonce = secrets.token_hex(8)
    run_id = nonce

    out_dir = Path(output_dir) if output_dir else Path("runs") / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / "trace.jsonl"
    result_path = out_dir / "result.json"

    # Write trace JSONL
    with TraceWriter(trace_path) as writer:
        for event in events:
            writer.write_event(event)
        for atom_key, p_frames in pred_frames_by_atom.items():
            for pf in p_frames:
                writer.write_pred_frame(pf.frame, atom_key, pf)

    # 7. Verdict Card Rendering (Lazy / Opt-In)
    card_path_str: str | None = None
    render_ms = 0
    if render_card:
        t_rend0 = time.perf_counter()
        card_file = out_dir / "card.png"

        decisive_f_idx = 0
        for s in step_results:
            if s.frame is not None:
                decisive_f_idx = s.frame
                if s.verdict in (Verdict.FAIL, Verdict.CANT_TELL):
                    break

        decisive_frame_bgr: np.ndarray | None = None
        try:
            cap = cv2.VideoCapture(clip_obj.path_h264)
            cap.set(cv2.CAP_PROP_POS_FRAMES, decisive_f_idx)
            ret, frame_read = cap.read()
            if ret:
                decisive_frame_bgr = frame_read
            cap.release()
        except Exception:
            pass

        if decisive_frame_bgr is None:
            decisive_frame_bgr = np.full((clip_obj.height, clip_obj.width, 3), 40, dtype=np.uint8)

        temp_result = RunResult(
            run_id=run_id,
            test_name=test_obj.name,
            test_sha256=test_sha256,
            config_sha256="0" * 64,
            clip=clip_obj.ref,
            verdict=verdict,
            exit_code=0 if verdict == Verdict.PASS else (1 if verdict == Verdict.FAIL else 2),
            steps=step_results,
            reasons=final_reasons,
            timings_ms={
                "segment_ms": segment_ms,
                "scale_ms": scale_ms,
                "eval_ms": eval_ms,
                "render_ms": 0,
                "total_ms": int(round((time.perf_counter() - total_start) * 1000)),
            },
            backends=backends_map,
            badges=badges,
            nonce=nonce,
            is_fixture=is_fixture,
            trace_path=str(trace_path),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        render_verdict_card_v1(temp_result, clip_obj, decisive_frame_bgr, card_file)
        card_path_str = str(card_file)
        render_ms = int(round((time.perf_counter() - t_rend0) * 1000))

    total_ms = int(round((time.perf_counter() - total_start) * 1000))

    exit_code_val: Literal[0, 1, 2, 3] = (
        0 if verdict == Verdict.PASS else (1 if verdict == Verdict.FAIL else 2)
    )

    run_result = RunResult(
        run_id=run_id,
        test_name=test_obj.name,
        test_sha256=test_sha256,
        config_sha256="0" * 64,
        clip=clip_obj.ref,
        verdict=verdict,
        exit_code=exit_code_val,
        steps=step_results,
        reasons=final_reasons,
        events=events,
        timings_ms={
            "segment_ms": segment_ms,
            "scale_ms": scale_ms,
            "eval_ms": eval_ms,
            "render_ms": render_ms,
            "total_ms": total_ms,
        },
        backends=backends_map,
        badges=badges,
        nonce=nonce,
        is_fixture=is_fixture,
        card_path=card_path_str,
        trace_path=str(trace_path),
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    # 8. Write result.json and .Kodiac/last_verdict.json
    result_json_str = run_result.model_dump_json(indent=2)
    result_path.write_text(result_json_str, encoding="utf-8")

    dot_Kodiac = Path(".Kodiac")
    dot_Kodiac.mkdir(parents=True, exist_ok=True)
    (dot_Kodiac / "last_verdict.json").write_text(result_json_str, encoding="utf-8")

    return run_result


__all__ = ["run"]
