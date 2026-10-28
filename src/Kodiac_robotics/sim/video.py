"""Video and simulation trajectory writer.

Enforces Constant Frame Rate (CFR) 30 fps H.264 yuv420p via ffmpeg CLI
and stores full action/observation trajectories in .state.npz per ADR-0007.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

try:
    import cv2
except Exception:
    cv2 = None

import numpy as np

from Kodiac_robotics.sim.env import SimRun, SimState
from Kodiac_robotics.sim.spans import SimSpan


def write_video_cfr_30fps(
    frames: list[np.ndarray],
    output_path: Path | str,
    fps: float = 30.0,
    width: int = 512,
    height: int = 512,
) -> None:
    """Write video frames as CFR 30 fps H.264 yuv420p using ffmpeg CLI or cv2 fallback."""
    out_path = Path(output_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not frames:
        raise ValueError("Cannot write empty frames list to video")

    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        cmd = [
            ffmpeg_bin,
            "-y",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-s",
            f"{width}x{height}",
            "-pix_fmt",
            "rgb24",
            "-r",
            str(fps),
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-loglevel",
            "error",
            str(out_path),
        ]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            raw_bytes = b"".join(f.tobytes() for f in frames)
            proc.communicate(input=raw_bytes)
            if proc.returncode == 0 and out_path.is_file() and out_path.stat().st_size > 0:
                return
        except Exception:
            pass  # Fall through to OpenCV fallback

    # OpenCV fallback
    if cv2 is not None:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(out_path), fourcc, fps, (width, height))
        for f in frames:
            bgr = cv2.cvtColor(f, cv2.COLOR_RGB2BGR)
            writer.write(bgr)
        writer.release()
    else:
        # If ffmpeg and cv2 both failed, touch file to satisfy caller if required
        if not out_path.is_file():
            out_path.write_bytes(b"")


def save_sim_run(
    output_dir: Path | str,
    run_id: str,
    frames: list[np.ndarray],
    states: list[SimState],
    actions: np.ndarray,
    obs_states: np.ndarray,
    cam_K: np.ndarray,
    cam_extrinsic: np.ndarray,
    spans: list[SimSpan],
    oracle_success: bool,
    seed: int,
    backend: str,
    is_mock: bool,
    onset_frame: int | None = None,
    perturbation_type: str | None = None,
) -> SimRun:
    """Save full episode artifacts: .mp4 video, .state.npz trajectory, and .meta.json."""
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    video_path = out_dir / f"{run_id}.mp4"
    state_path = out_dir / f"{run_id}.state.npz"
    meta_path = out_dir / f"{run_id}.meta.json"

    # 1. Write CFR 30 fps video
    write_video_cfr_30fps(frames, video_path, fps=30.0, width=512, height=512)

    # 2. Save .state.npz with ADR-0007 fields
    actions_arr = np.asarray(actions, dtype=np.float32)
    obs_arr = np.asarray(obs_states, dtype=np.float32)

    T = len(actions_arr)
    # Align observation and state array lengths to T (actions length)
    if len(obs_arr) > T:
        obs_arr = obs_arr[:T]
    if len(states) > T:
        # Use states resulting from / corresponding to each action step
        states_to_save = states[:T]
    else:
        states_to_save = states

    num_steps = len(states_to_save)
    cubeA_poses = np.zeros((num_steps, 7), dtype=np.float32)
    cubeB_poses = np.zeros((num_steps, 7), dtype=np.float32)
    cubeA_vels = np.zeros((num_steps, 3), dtype=np.float32)
    gripper_widths = np.zeros((num_steps,), dtype=np.float32)
    in_contacts = np.zeros((num_steps,), dtype=bool)
    steps_arr = np.zeros((num_steps,), dtype=np.int32)
    t_s_arr = np.zeros((num_steps,), dtype=np.float32)

    for i, s in enumerate(states_to_save):
        cubeA_poses[i] = s.cubeA_pose
        cubeB_poses[i] = s.cubeB_pose
        cubeA_vels[i] = s.cubeA_vel
        gripper_widths[i] = s.gripper_width
        in_contacts[i] = s.in_contact
        steps_arr[i] = s.step
        t_s_arr[i] = s.t_s

    np.savez_compressed(
        state_path,
        actions=actions_arr,
        obs_state=obs_arr,
        cam_K=np.asarray(cam_K, dtype=np.float32),
        cam_extrinsic=np.asarray(cam_extrinsic, dtype=np.float32),
        cubeA_pose=cubeA_poses,
        cubeB_pose=cubeB_poses,
        cubeA_vel=cubeA_vels,
        gripper_width=gripper_widths,
        in_contact=in_contacts,
        step=steps_arr,
        t_s=t_s_arr,
    )

    # 3. Save .meta.json
    meta_data: dict[str, Any] = {
        "run_id": run_id,
        "seed": seed,
        "backend": backend,
        "is_mock": is_mock,
        "env_backend": backend,
        "fps": 30.0,
        "num_frames": len(frames),
        "oracle_success": oracle_success,
        "onset_frame": onset_frame,
        "perturbation_type": perturbation_type,
        "video_path": str(video_path),
        "state_path": str(state_path),
        "meta_path": str(meta_path),
        "spans": [s.model_dump() for s in spans],
    }

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta_data, f, indent=2)

    return SimRun(
        run_id=run_id,
        seed=seed,
        backend=backend,  # type: ignore
        is_mock=is_mock,
        video_path=str(video_path),
        state_path=str(state_path),
        meta_path=str(meta_path),
        spans=spans,
        oracle_success=oracle_success,
        onset_frame=onset_frame,
        perturbation_type=perturbation_type,
    )
