"""Prompt library and embodiment detection for Kodiac perception.

Provides canonical per-role prompt sets for robotic and human manipulation,
with automatic effector aliasing (gripper <-> hand) per Invariant I16,
ARCHITECTURE.md §3.1 and P03.S05.
"""

from __future__ import annotations

import os
from typing import Any, Literal

from Kodiac_robotics.contracts.core import Clip

# Canonical prompt dictionaries by embodiment
ROBOT_PROMPT_LIBRARY: dict[str, list[str]] = {
    "gripper": [
        "robot gripper",
        "parallel jaw gripper",
        "robot end effector",
        "robotic gripper",
    ],
    "fingers": [
        "gripper finger",
        "gripper tip",
        "robotic fingers",
    ],
    "cube_a": [
        "red cube",
        "red block",
        "cube a",
        "red rectangular block",
    ],
    "cube_b": [
        "green cube",
        "green block",
        "cube b",
        "green rectangular block",
    ],
    "target": [
        "target zone",
        "green cube target",
        "target surface",
        "goal receptacle",
    ],
    "container": [
        "plastic container",
        "bin",
        "tray",
        "box",
    ],
}

HUMAN_PROMPT_LIBRARY: dict[str, list[str]] = {
    "gripper": [  # Effector aliasing: 'gripper' maps to hand prompts for human embodiment
        "human hand",
        "right hand",
        "hand",
        "human palm and fingers",
    ],
    "fingers": [
        "human fingers",
        "fingertips",
        "thumb and index finger",
    ],
    "cube_a": [
        "red cube",
        "red block",
        "cube a",
        "red rectangular block",
    ],
    "cube_b": [
        "green cube",
        "green block",
        "cube b",
        "green rectangular block",
    ],
    "target": [
        "target zone",
        "green cube target",
        "target surface",
        "goal receptacle",
    ],
    "container": [
        "plastic container",
        "bin",
        "tray",
        "box",
    ],
}

TASK_ROLES: dict[str, list[str]] = {
    "stack_cube": ["gripper", "cube_a", "cube_b", "target"],
    "pick_place": ["gripper", "cube_a", "target", "container"],
    "lift": ["gripper", "cube_a"],
    "pour": ["gripper", "container", "target"],
}


def get_prompt_set(
    task: str,
    embodiment: Literal["robot", "human"] = "robot",
) -> dict[str, list[str]]:
    """Get canonical prompt dictionary for a task and embodiment.

    Parameters
    ----------
    task:
        Task name (e.g. 'stack_cube', 'pick_place', 'lift', or general task).
    embodiment:
        Embodiment type ('robot' or 'human'). When 'human', effector roles
        like 'gripper' are aliased to human hand prompts to satisfy Invariant I16.

    Returns
    -------
    dict[str, list[str]]:
        Mapping of role name -> list of textual prompt candidates.
    """
    library = HUMAN_PROMPT_LIBRARY if embodiment == "human" else ROBOT_PROMPT_LIBRARY

    normalized_task = task.lower().strip().replace("-", "_").replace(" ", "_")
    roles = TASK_ROLES.get(normalized_task)

    if roles is not None:
        return {role: list(library[role]) for role in roles if role in library}

    # If task is not a predefined subset, return full library
    return {role: list(prompts) for role, prompts in library.items()}


def detect_embodiment(
    clip: Clip,
    sample_frames: list[int],
    backend: Any = None,
) -> Literal["robot", "human"]:
    """Detect whether clip demonstrates robot manipulation or human demo.

    Performs confidence probing on sample frame 0 between robot gripper
    and human hand prompts when a backend is available. Falls back to clip
    metadata and URI inspection if offline or backend is absent.

    Parameters
    ----------
    clip:
        The video clip container.
    sample_frames:
        List of frame indices to evaluate (typically [0] or early keyframes).
    backend:
        Optional Segmenter backend instance.

    Returns
    -------
    Literal['robot', 'human']:
        The detected embodiment.
    """
    # Environment override for deterministic testing or manual forcing
    env_override = os.environ.get("KODIAC_EMBODIMENT", "").lower().strip()
    if env_override in ("robot", "human"):
        return env_override  # type: ignore[return-value]

    target_frame = sample_frames[0] if sample_frames else 0

    if backend is not None:
        try:
            probe_prompts = {
                "robot_gripper": ["robot gripper", "robotic arm end effector"],
                "human_hand": ["human hand", "person hand"],
            }
            tracks = backend.segment_frames(clip, [target_frame], probe_prompts)
            robot_score = 0.0
            human_score = 0.0

            if "robot_gripper" in tracks and target_frame in tracks["robot_gripper"].frames:
                robot_score = tracks["robot_gripper"].frames[target_frame].score

            if "human_hand" in tracks and target_frame in tracks["human_hand"].frames:
                human_score = tracks["human_hand"].frames[target_frame].score

            if human_score > robot_score and human_score > 0.4:
                return "human"
            if robot_score > 0.0:
                return "robot"
        except Exception:
            # Fall back to metadata heuristics on error
            pass

    # Metadata & URI heuristics
    uri_lower = clip.ref.uri.lower()
    dataset_lower = (clip.ref.dataset or "").lower()

    if any(h in uri_lower or h in dataset_lower for h in ("human", "ego4d", "epic", "hand")):
        return "human"

    if clip.ref.source_kind == "sim":
        return "robot"

    if any(r in uri_lower or r in dataset_lower for r in ("droid", "lerobot", "panda", "franka", "robot")):
        return "robot"

    # Default to robot embodiment for robotics evaluation
    return "robot"
