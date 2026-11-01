"""Keyframe Grounding, Embodiment Aliasing, and Typechecking for Kodiac.

Grounds AST object names to SAM 3.1 track IDs on demonstration keyframes.
Invokes detect_embodiment(clip) to map canonical 'gripper' to human hand or robot gripper
per Invariant I16 ("The same test grades human and robot").
Records container rim ellipses via cv2.fitEllipse and initial scale k0.
Raises E001/E002 on failure per ARCHITECTURE.md §6.1-§6.3 and RULING.md.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

import cv2
import numpy as np

from Kodiac_robotics.compiler.lint import lint_green
from Kodiac_robotics.contracts.core import (
    Clip,
    GreenTest,
    ObjMask,
    Track,
)
from Kodiac_robotics.segment.fixture import ROLE_ALIASES, FixtureBackend
from Kodiac_robotics.segment.prompts import (
    HUMAN_PROMPT_LIBRARY,
    ROBOT_PROMPT_LIBRARY,
    detect_embodiment,
)
from Kodiac_robotics.segment.reid import decode_mask

logger = logging.getLogger(__name__)


def _build_candidate_prompts(
    obj_name: str,
    obj_prompt: str | None,
    aliases: list[str],
    embodiment: Literal["robot", "human"],
) -> list[str]:
    """Build candidate query prompt list for an object role."""
    if obj_name.lower() == "gripper":
        library = HUMAN_PROMPT_LIBRARY if embodiment == "human" else ROBOT_PROMPT_LIBRARY
        return list(library.get("gripper", ["robot gripper"]))

    candidates: list[str] = []
    if obj_prompt:
        candidates.append(obj_prompt.strip())

    lib = ROBOT_PROMPT_LIBRARY
    norm_name = obj_name.lower().replace("-", "_")
    if norm_name in lib:
        candidates.extend(lib[norm_name])

    clean_name = obj_name.replace("_", " ").strip()
    if clean_name not in candidates:
        candidates.append(clean_name)

    for alias in aliases:
        if alias not in candidates:
            candidates.append(alias)

    return candidates


def _find_matching_track(
    obj_name: str,
    prompts: list[str],
    all_tracks: dict[str, Track],
) -> Track | None:
    """Find matching Track in all_tracks for object name or prompts."""
    # 1. Exact match
    if obj_name in all_tracks:
        return all_tracks[obj_name]

    norm = obj_name.lower().replace("_", "").replace("-", "")

    # 2. Normalized key match
    for k, tr in all_tracks.items():
        k_norm = k.lower().replace("_", "").replace("-", "")
        if k_norm == norm:
            return tr

    # 3. Predefined alias mapping
    if obj_name.lower() in ROLE_ALIASES:
        target_role = ROLE_ALIASES[obj_name.lower()]
        if target_role in all_tracks:
            return all_tracks[target_role]

    for k, tr in all_tracks.items():
        if k.lower() in ROLE_ALIASES and ROLE_ALIASES[k.lower()] == obj_name.lower():
            return tr

    # 4. Standard block heuristic fallbacks
    if "cubea" in norm or "red" in norm:
        for cand in ("cube_a", "cubeA", "red_block", "red_cube"):
            if cand in all_tracks:
                return all_tracks[cand]
    elif "cubeb" in norm or "green" in norm:
        for cand in ("cube_b", "cubeB", "green_block", "green_cube"):
            if cand in all_tracks:
                return all_tracks[cand]

    # 5. Candidate prompt matching
    for p in prompts:
        p_norm = p.lower().strip()
        if p_norm in all_tracks:
            return all_tracks[p_norm]
        if p_norm in ROLE_ALIASES and ROLE_ALIASES[p_norm] in all_tracks:
            return all_tracks[ROLE_ALIASES[p_norm]]

    return None


def typecheck_and_ground_objects(
    clip: Clip,
    test: GreenTest,
    backend: Any = None,
) -> tuple[GreenTest, dict[str, Any]]:
    """Grounds AST object names to SAM 3.1 track IDs.

    Invokes detect_embodiment(clip) to map canonical 'gripper' to human hand
    or robot gripper (Invariant I16).
    Records container rim ellipses and initial scale k0.
    Raises E001/E002 on failure.
    """
    # 1. Semantic Lint & Declaration Validation (E002, E003, E004)
    diagnostics = lint_green(test)
    for diag in diagnostics:
        if diag.severity == "error":
            if diag.code == "E002":
                raise ValueError(f"E002: {diag.message}")
            if diag.code == "E003":
                raise ValueError(f"E003: {diag.message}")
            if diag.code == "E004":
                raise ValueError(f"E004: {diag.message}")

    # 2. Embodiment Detection & Effector Aliasing (Invariant I16)
    embodiment = detect_embodiment(clip, [0], backend=backend)

    # 3. Resolve Segmenter Tracks
    resolved_tracks: dict[str, Track] = {}
    if backend is not None:
        try:
            prompt_map = {
                obj.name: _build_candidate_prompts(obj.name, obj.prompt, obj.aliases, embodiment)
                for obj in test.objects
            }
            resolved_tracks = backend.segment_frames(clip, [0], prompt_map)
        except Exception as e:
            logger.warning(f"Backend segmentation failed: {e}. Falling back to fixture.")
            resolved_tracks = {}

    if not resolved_tracks:
        fb = FixtureBackend()
        try:
            resolved_tracks = fb._load_tracks(clip)
        except FileNotFoundError:
            # If no stored track exists and no live backend, raise E001
            raise ValueError(
                f"E001: no segmentation track available for clip sha256={clip.sha256}"
            )

    # 4. Ground Objects and Extract Baselines
    object_baselines: dict[str, dict[str, Any]] = {}
    canvas_shape = (clip.height, clip.width)

    for obj in test.objects:
        prompts = _build_candidate_prompts(obj.name, obj.prompt, obj.aliases, embodiment)
        track = _find_matching_track(obj.name, prompts, resolved_tracks)

        if track is None or not track.frames:
            raise ValueError(
                f"E001: object '{obj.name}' not found in demonstration keyframes"
            )

        # Check mask score and existence on frame 0 or earliest keyframe
        frame_idx = 0 if 0 in track.frames else min(track.frames.keys())
        mask: ObjMask = track.frames[frame_idx]

        if mask.score < 0.40:
            raise ValueError(
                f"E001: object '{obj.name}' detection confidence ({mask.score:.2f}) "
                "below acceptable threshold (0.40)"
            )

        # Compute initial scale k0 (px/cm) and initial area A0 (px)
        bbox = mask.bbox_xyxy
        w_px = max(1.0, float(bbox[2] - bbox[0]))
        nominal_size_cm = obj.size_cm if obj.size_cm is not None else 4.0
        k0 = float(w_px / max(0.1, nominal_size_cm))
        a0 = int(mask.area_px) if mask.area_px > 0 else int(w_px * max(1.0, bbox[3] - bbox[1]))

        base_info: dict[str, Any] = {
            "name": obj.name,
            "role": obj.role,
            "A0": a0,
            "k0": k0,
            "score": float(mask.score),
            "bbox": [float(x) for x in bbox],
            "embodiment": embodiment,
        }

        # 5. Fit Container Rim Ellipse (if role == "container")
        if obj.role == "container":
            try:
                bin_mask = decode_mask(mask, canvas_shape)
                contours, _ = cv2.findContours(
                    bin_mask.astype(np.uint8),
                    cv2.RETR_EXTERNAL,
                    cv2.CHAIN_APPROX_SIMPLE,
                )
                if contours:
                    largest = max(contours, key=cv2.contourArea)
                    if len(largest) >= 5:
                        ellipse = cv2.fitEllipse(largest)
                        base_info["rim_ellipse"] = {
                            "center": (float(ellipse[0][0]), float(ellipse[0][1])),
                            "axes": (float(ellipse[1][0]), float(ellipse[1][1])),
                            "angle_deg": float(ellipse[2]),
                        }
            except Exception as exc:
                logger.debug(f"Could not fit container rim ellipse for {obj.name}: {exc}")

        object_baselines[obj.name] = base_info

    # Invariant I16: Preserve canonical 'gripper' identifier in AST
    return test, object_baselines
